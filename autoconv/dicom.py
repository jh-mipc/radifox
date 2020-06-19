from datetime import datetime
from glob import glob
import logging
import os
import shutil
from subprocess import run

import pydicom as dicom
from pydicom.errors import InvalidDicomError
from pydicom.dicomdir import DicomDir

from .base import BaseInfo, BaseSet, ImageOrientation, MATCHING_ITEMS
from .utils import mkdir_p, convert_type, make_tuple


DCM_HEADER_ATTRS = [
    'InstitutionName',
    'Manufacturer',
    ('ManufacturerModelName', 'ScannerModelName'),
    'SeriesDescription',
    'MagneticFieldStrength',
    ('MRAcquisitionType', 'AcquisitionDimension'),
    ('SpacingBetweenSlices', 'SliceSpacing'),
    'SliceThickness',
    'FlipAngle',
    'RepetitionTime',
    'EchoTime',
    'InversionTime',
    'EchoTrainLength',
    'AcquisitionMatrix',
    ('ScanningSequence', 'SequenceType'),
    'ImageType',
    'SeriesNumber',
    'ComplexImageComponent',
    'BodyPartExamined',
    'StudyDescription',
    'SequenceVariant'
]


class DicomInfo(BaseInfo):

    def __init__(self, dcmdir):
        super().__init__(dcmdir)
        ds = dicom.read_file(sorted(glob(os.path.join(dcmdir, '*')))[0], stop_before_pixels=True)
        self.SeriesUID = os.path.basename(dcmdir)
        self.StudyUID = getattr(ds, 'StudyInstanceUID', None)
        self.NumFiles = len(glob(os.path.join(dcmdir, '*')))
        for item in DCM_HEADER_ATTRS:
            get_item, set_item = item if isinstance(item, tuple) else (item, item)
            setattr(self, set_item, convert_type(getattr(ds, get_item, None)))
        self.AcqDateTime = str(datetime.strptime(ds.SeriesDate + '-' + ds.SeriesTime.split('.')[0].ljust(6, '0'),
                                                 '%Y%m%d-%H%M%S'))
        self.Manufacturer = self.Manufacturer.lower().split(' ')[0]
        self.SequenceType = make_tuple(self.SequenceType)
        self.SequenceVariant = make_tuple(self.SequenceVariant)
        self.SequenceName = getattr(ds, 'SequenceName', getattr(ds, 'PulseSequenceName', None))
        self.ExContrastAgent = getattr(ds, 'ContrastBolusAgent', getattr(ds, 'ContrastBolusAgentSequence', None))
        self.ImageOrientationObj = ImageOrientation(getattr(ds, 'ImageOrientationPatient', None))
        self.ImageOrientation = self.ImageOrientationObj.dcm_plane()
        if self.ComplexImageComponent is None and any([comp in self.ImageType for comp in ['M', 'P']]):
            self.ComplexImageComponent = 'MAGNITUDE' if 'M' in self.ImageType else 'PHASE'


class DicomSet(BaseSet):
    def __init__(self, output_root, metadata_obj, lut_file):
        super().__init__(metadata_obj, lut_file)

        for dcmdir in sorted(glob(os.path.join(output_root, self.metadata.dir_to_str(), 'dcm', '*'))):
            logging.info('Processing %s' % dcmdir)
            di = DicomInfo(dcmdir)
            if di.should_convert():
                di.create_image_name(self.metadata.prefix_to_str(), self.lookup_table)
            self.series_list.append(di)

        logging.info('Generating unique names')
        self.generate_unique_names()


def convert_emf(dcmpath):
    run([shutil.which('emf2sf'), '--out-dir', os.path.dirname(dcmpath), dcmpath])
    os.remove(dcmpath)
    return sorted(glob(dcmpath + '-*'))


def decompress_jpeg(dcm_filename):
    run([shutil.which('dcmdjpeg'), dcm_filename, dcm_filename + '.decompress'])
    os.rename(dcm_filename + '.decompress', dcm_filename)


def sort_dicoms(dcm_dir):
    logging.info('Sorting DICOMs')
    valid_dcms = []
    mf_count = 0
    for path, subdirs, files in os.walk(dcm_dir):
        for name in files:
            curr_dcm_img = os.path.join(path, name)
            try:
                ds = dicom.dcmread(curr_dcm_img, stop_before_pixels=True)
            except InvalidDicomError:
                continue
            if isinstance(ds, DicomDir):
                continue
            if ds.SOPClassUID not in ['1.2.840.10008.5.1.4.1.1.4', '1.2.840.10008.5.1.4.1.1.4.1']:
                continue
            if ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.4.1':
                logging.debug('%s is an Enhanced DICOM file, converting to classic '
                              'DICOM for consistent processing' % curr_dcm_img)
                dcm_files = convert_emf(curr_dcm_img)
                mf_count += 1
                dcm_cand = [(dcm_file, dicom.dcmread(dcm_file, stop_before_pixels=True)) for dcm_file in dcm_files]
            else:
                dcm_cand = [(curr_dcm_img, ds)]
            decomp_count = 0
            for dcm_img, dcm_ds in dcm_cand:
                if dcm_ds.file_meta.TransferSyntaxUID == '1.2.840.10008.1.2.4.51' and dcm_ds.BitsAllocated == 16:
                    logging.debug('%s requires decompression of the imaging data. Decompressing now.' % dcm_img)
                    decompress_jpeg(dcm_img)
                    decomp_count += 1
                uid = getattr(dcm_ds, 'SeriesInstanceUID', None)
                if uid is not None:
                    valid_dcms.append((dcm_img, uid, dcm_ds.InstanceNumber,
                                       tuple([ImageOrientation(getattr(dcm_ds, item, None))
                                              if item == 'ImageOrientationPatient'
                                              else getattr(dcm_ds, item, None)
                                              for item in MATCHING_ITEMS])))
            if decomp_count > 0:
                logging.info('%d DICOM files were decompresssed' % decomp_count)
    if mf_count > 0:
        logging.info('%d Enhanced DICOM files were converted to classic DICOM' % mf_count)

    unique_scans = set([(item[1], item[3]) for item in valid_dcms])
    unique_change = {}
    unique_lists = {uid: [] for uid in set([item[0] for item in unique_scans])}
    for scan in unique_scans:
        unique_lists[scan[0]].append(scan)
        unique_change[scan] = scan[0] + ('.%02d' % len(unique_lists[scan[0]]))
    for new_dcm_dir in unique_change.values():
        mkdir_p(os.path.join(dcm_dir, new_dcm_dir))
    inst_nums = {}
    for dcm_tuple in valid_dcms:
        output_dir = os.path.join(dcm_dir, unique_change[(dcm_tuple[1], dcm_tuple[3])])
        os.rename(dcm_tuple[0], os.path.join(output_dir, os.path.basename(dcm_tuple[0])))
        if not unique_change[(dcm_tuple[1], dcm_tuple[3])] in inst_nums:
            inst_nums[unique_change[(dcm_tuple[1], dcm_tuple[3])]] = {}
        if not dcm_tuple[2] in inst_nums[unique_change[(dcm_tuple[1], dcm_tuple[3])]]:
            inst_nums[unique_change[(dcm_tuple[1], dcm_tuple[3])]][dcm_tuple[2]] = []
        inst_nums[unique_change[(dcm_tuple[1], dcm_tuple[3])]][dcm_tuple[2]].\
            append(os.path.join(output_dir, os.path.basename(dcm_tuple[0])))

    new_dirs = list(unique_change.values())
    for name in os.listdir(dcm_dir):
        if name not in new_dirs:
            if os.path.isdir(os.path.join(dcm_dir, name)):
                shutil.rmtree(os.path.join(dcm_dir, name))
            else:
                os.remove(os.path.join(dcm_dir, name))

    logging.info('Checking for duplicate DICOM files')
    for uid in inst_nums:
        if any([len(inst_nums[uid][num]) > 1 for num in inst_nums[uid]]):
            logging.info('Possible duplicates found for %s' % uid)
            remove_duplicates(os.path.join(dcm_dir, uid))

    logging.info('Sorting complete')


def remove_duplicates(dcmdir):
    inst_nums = {}
    for dcmfile in glob(os.path.join(dcmdir, '*')):
        ds = dicom.dcmread(dcmfile, stop_before_pixels=True)
        if ds.InstanceNumber not in inst_nums:
            inst_nums[ds.InstanceNumber] = []
        inst_nums[ds.InstanceNumber].append((dcmfile, ds))
    count = 0
    for num in inst_nums:
        inst_nums[num] = sorted(inst_nums[num], key=lambda x: getattr(x[1], 'InstanceCreationTime', None))
        for i in range(len(inst_nums[num])-1):
            for j in range(i+1, len(inst_nums[num])):
                diff_keys = []
                for key in inst_nums[num][i][1]._dict.keys():
                    if key not in inst_nums[num][j][1]._dict.keys() and \
                            key not in [(0x0008, 0x0013), (0x0008, 0x0018)]:
                        diff_keys.append(key)
                    elif inst_nums[num][i][1]._dict[key].value != inst_nums[num][j][1]._dict[key].value and \
                            key not in [(0x0008, 0x0013), (0x0008, 0x0018)]:
                        diff_keys.append(key)
                if len(diff_keys) == 0:
                    if (dicom.dcmread(inst_nums[num][i][0]).PixelData ==
                            dicom.dcmread(inst_nums[num][i][0]).PixelData):
                        logging.debug('Found duplicate of %s' % inst_nums[num][j][0])
                        logging.debug('Removing duplicate file %s' % inst_nums[num][i][0])
                        os.remove(inst_nums[num][i][0])
                        count += 1
                        break
    if count > 0:
        logging.info('Removed %d duplicate DICOM files' % count)
    else:
        logging.info('No duplicate DICOM files found')

import logging
from pathlib import Path
import shutil
from subprocess import run
from typing import List, Optional

import pydicom as dicom
from pydicom.errors import InvalidDicomError
from pydicom.dicomdir import DicomDir

from .base import BaseInfo, BaseSet, ImageOrientation, TruncatedImageValue, MATCHING_ITEMS
from .lut import LookupTable
from .metadata import Metadata
from .utils import mkdir_p, extract_de


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
    'ScanOptions',
    'ImageType',
    'SeriesNumber',
    'ComplexImageComponent',
    'BodyPartExamined',
    'StudyDescription',
    'SequenceVariant',
    ('PixelSpacing', 'ReconResolution'),
    'SoftwareVersions',
    'NumberOfAverages',
    'PercentSampling',
    'ReceiveCoilName',
    'PixelBandwidth',
    ('VariableFlipAngleFlag', 'VariableFlipAngle'),
]


DCM_HEADER_LISTS = [
    'ScanningSequence',
    'SequenceVariant',
    'ImageType',
    'ScanOptions',
    'SoftwareVersions',
]


class DicomInfo(BaseInfo):

    def __init__(self, dcmdir: Path) -> None:
        super().__init__(dcmdir)
        ds = dicom.dcmread(str(sorted(dcmdir.glob('*'))[0]), stop_before_pixels=True)
        self.SeriesUID = dcmdir.name
        self.StudyUID = getattr(ds, 'StudyInstanceUID', None)
        self.NumFiles = len(list(dcmdir.glob('*')))
        for item in DCM_HEADER_ATTRS:
            get_item, set_item = item if isinstance(item, tuple) else (item, item)
            setattr(self, set_item, extract_de(ds, get_item, self.SeriesUID, get_item in DCM_HEADER_LISTS))
        self.SeriesDescription = '' if self.SeriesDescription is None else self.SeriesDescription
        series_date = extract_de(ds, 'SeriesDate', self.SeriesUID, False)
        series_time = extract_de(ds, 'SeriesTime', self.SeriesUID, False)
        self.AcqDateTime = ' '.join([str(series_date) if series_date is not None else '0000-00-00',
                                     str(series_time) if series_date is not None else '00:00:00'])
        self.Manufacturer = '' if self.Manufacturer is None else self.Manufacturer.upper().split(' ')[0]
        if (0x2005, 0x1444) in ds:
            turbo = int(ds[(0x2005, 0x1444)].value)
            self.EchoTrainLength = turbo if turbo > 0 else self.EchoTrainLength
        if (0x2001, 0x1013) in ds:
            try:
                self.EPIFactor = int(ds[(0x2001, 0x1013)].value)
            except ValueError:
                pass
        if self.AcquisitionMatrix is not None:
            # noinspection PyUnresolvedReferences
            self.AcquisitionMatrix = [self.AcquisitionMatrix[0], self.AcquisitionMatrix[3]] \
                if self.AcquisitionMatrix[1] == 0 else [self.AcquisitionMatrix[2], self.AcquisitionMatrix[1]]
            self.ReconMatrix = [getattr(ds, 'Columns', 0), getattr(ds, 'Rows', 0)]
            self.FieldOfView = [res*num for res, num in zip(self.ReconResolution, self.ReconMatrix)]
            self.AcquiredResolution = [fov/num for fov, num in zip(self.FieldOfView, self.AcquisitionMatrix)]
            self.FieldOfView = [round(fov, 2) for fov in self.FieldOfView]
            self.AcquiredResolution = [round(res, 5) for res in self.AcquiredResolution]
            self.ReconResolution = [round(res, 5) for res in self.ReconResolution]
        self.SequenceName = getattr(ds, 'SequenceName', getattr(ds, 'PulseSequenceName', None))
        if self.SequenceName is None and (0x0019, 0x109c) in ds:
            self.SequenceName = str(ds[(0x0019, 0x109c)].value)
        self.ExContrastAgent = getattr(ds, 'ContrastBolusAgent', getattr(ds, 'ContrastBolusAgentSequence', None))
        self.ImageOrientationPatient = ImageOrientation(getattr(ds, 'ImageOrientationPatient', None))
        self.SliceOrientation = self.ImageOrientationPatient.get_plane()
        self.ImagePositionPatient = TruncatedImageValue(getattr(ds, 'ImagePositionPatient', None))
        if self.ComplexImageComponent is None and any([comp in self.ImageType
                                                       for comp in ['M', 'P', 'R', 'I',
                                                                    'MAGNITUDE', 'PHASE', 'REAL', 'IMAGINARY']]):
            if 'M' in self.ImageType or 'MAGNITUDE' in self.ImageType:
                self.ComplexImageComponent = 'MAGNITUDE'
            elif 'P' in self.ImageType or 'PHASE' in self.ImageType:
                self.ComplexImageComponent = 'PHASE'
            elif 'R' in self.ImageType or 'REAL' in self.ImageType:
                self.ComplexImageComponent = 'REAL'
            elif 'I' in self.ImageType or 'IMAGINARY' in self.ImageType:
                self.ComplexImageComponent = 'IMAGINARY'


class DicomSet(BaseSet):
    def __init__(self, source: Path, output_root: Path, metadata_obj: Metadata, lut_obj: LookupTable,
                 manual_names: Optional[dict] = None, input_hash: Optional[str] = None) -> None:
        super().__init__(source, output_root, metadata_obj, lut_obj, manual_names, input_hash)

        for dcmdir in sorted((output_root / self.Metadata.dir_to_str() / 'mr-dcm').glob('*')):
            logging.info('Processing %s' % dcmdir)
            di = DicomInfo(dcmdir)
            if di.should_convert():
                di.create_image_name(self.Metadata.prefix_to_str(), self.LookupTable, self.ManualNames)
            self.SeriesList.append(di)

        logging.info('Generating unique names')
        self.generate_unique_names()


def convert_emf(dcmpath: Path) -> List[Path]:
    run([shutil.which('emf2sf'), '--out-dir', str(dcmpath.parent), str(dcmpath)])
    dcmpath.unlink()
    return sorted(dcmpath.parent.glob(dcmpath.name + '-*'))


def decompress_jpeg(dcm_filename: Path) -> None:
    run([shutil.which('dcmdjpeg'), str(dcm_filename), str(dcm_filename) + '.decompress'])
    Path(str(dcm_filename) + '.decompress').rename(dcm_filename)


def sort_dicoms(dcm_dir: Path) -> None:
    logging.info('Sorting DICOMs')
    valid_dcms = []
    mf_count = 0
    for item in dcm_dir.rglob('*'):
        if item.is_file():
            curr_dcm_img = item
            try:
                ds = dicom.dcmread(str(curr_dcm_img), stop_before_pixels=True)
            except (InvalidDicomError, KeyError):
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
                dcm_cand = [(dcm_file, dicom.dcmread(str(dcm_file), stop_before_pixels=True))
                            for dcm_file in dcm_files]
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
                                       tuple([TruncatedImageValue(getattr(dcm_ds, item, None))
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
        mkdir_p(dcm_dir / new_dcm_dir)
    inst_nums = {}
    for dcm_tuple in valid_dcms:
        output_dir = dcm_dir / unique_change[(dcm_tuple[1], dcm_tuple[3])]
        dcm_tuple[0].rename(output_dir / dcm_tuple[0].name)
        if not unique_change[(dcm_tuple[1], dcm_tuple[3])] in inst_nums:
            inst_nums[unique_change[(dcm_tuple[1], dcm_tuple[3])]] = {}
        if not dcm_tuple[2] in inst_nums[unique_change[(dcm_tuple[1], dcm_tuple[3])]]:
            inst_nums[unique_change[(dcm_tuple[1], dcm_tuple[3])]][dcm_tuple[2]] = []
        inst_nums[unique_change[(dcm_tuple[1], dcm_tuple[3])]][dcm_tuple[2]].append(output_dir / dcm_tuple[0].name)

    new_dirs = list(unique_change.values())
    for item in dcm_dir.glob('*'):
        if item.name not in new_dirs:
            if item.is_dir():
                shutil.rmtree(item)
            elif item.is_file():
                item.unlink()

    logging.info('Checking for duplicate DICOM files')
    for uid in inst_nums:
        if any([len(inst_nums[uid][num]) > 1 for num in inst_nums[uid]]):
            logging.info('Possible duplicates found for %s' % uid)
            remove_duplicates(dcm_dir / uid)

    logging.info('Sorting complete')


def remove_duplicates(dcmdir: Path) -> None:
    inst_nums = {}  # type: dict
    for dcmfile in dcmdir.glob('*'):
        ds = dicom.dcmread(str(dcmfile), stop_before_pixels=True)
        if ds.InstanceNumber not in inst_nums:
            inst_nums[ds.InstanceNumber] = []
        inst_nums[ds.InstanceNumber].append((dcmfile, ds))
    count = 0
    for num in inst_nums:
        inst_nums[num] = sorted(inst_nums[num], key=lambda x: getattr(x[1], 'InstanceCreationTime', 0))
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
                    if (dicom.dcmread(str(inst_nums[num][i][0])).PixelData ==
                            dicom.dcmread(str(inst_nums[num][i][0])).PixelData):
                        logging.debug('Found duplicate of %s' % inst_nums[num][j][0])
                        logging.debug('Removing duplicate file %s' % inst_nums[num][i][0])
                        inst_nums[num][i][0].unlink()
                        count += 1
                        break
    if count > 0:
        logging.info('Removed %d duplicate DICOM files' % count)
    else:
        logging.info('No duplicate DICOM files found')

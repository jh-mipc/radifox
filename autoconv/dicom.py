from glob import glob
import logging
import os
import re
import shutil
from subprocess import run

import numpy as np
import pydicom as dicom
from pydicom.errors import InvalidDicomError
from pydicom.dicomdir import DicomDir

from .json import NoIndent
from .logging import WARNING_DEBUG
from .utils import mkdir_p, read_lut, check_lut, reorient, convert_type


DCM_HEADER_ATTRS = ['InstitutionName', 'Manufacturer', 'ManufacturerModelName',
                    'SeriesDescription', 'MagneticFieldStrength', 'MRAcquisitionType',
                    'SpacingBetweenSlices', 'SliceThickness', 'FlipAngle', 'RepetitionTime',
                    'EchoTime', 'InversionTime', 'EchoTrainLength', 'ContrastBolusAgent',
                    'AcquisitionMatrix', 'ScanningSequence', 'ImageType', 'SeriesNumber',
                    'ComplexImageComponent', 'BodyPartExamined', 'StudyDescription', 'SequenceVariant']
DESCRIPTION_IGNORE = ['loc', 'survey', 'scout', '3-pl', 'cal']
POSTGAD_DESC = ['post', '+c', 'gad', 'gd']
DCM_MATCHING_ITEMS = ['ImageOrientationPatient', 'RepetitionTime', 'FlipAngle', 'EchoTime',
                      'InversionTime', 'ComplexImageComponent']
DCM_ORIENT_PLANES = {0: 'sagittal', 1: 'coronal', 2: 'axial'}


class DicomInfo:
    """
    @DynamicAttrs
    """

    def __init__(self, dcmdir, metadata_obj, lut_obj):
        ds = dicom.read_file(sorted(glob(os.path.join(dcmdir, '*')))[0], stop_before_pixels=True)
        self.SourcePath = dcmdir
        self.SeriesUID = os.path.basename(dcmdir)
        self.StudyUID = getattr(ds, 'StudyInstanceUID', None)
        self.NumFiles = len(glob(os.path.join(dcmdir, '*')))
        for item in DCM_HEADER_ATTRS:
            setattr(self, item, convert_type(getattr(ds, item, None)))
        self.ImageType = self.ImageType
        self.ScanningSequence = self.ScanningSequence if isinstance(self.ScanningSequence, list) \
            else [self.ScanningSequence]
        self.SequenceVariant = self.SequenceVariant if isinstance(self.SequenceVariant, list) \
            else [self.SequenceVariant]
        self.SequenceName = getattr(ds, 'SequenceName', getattr(ds, 'PulseSequenceName', None))
        self.ContrastBolusAgent = getattr(ds, 'ContrastBolusAgent', getattr(ds, 'ContrastBolusAgentSequence', None))
        self.ImageOrientationPatient = ImageOrientation(getattr(ds, 'ImageOrientationPatient', None))
        self.ImageOrientation = self.ImageOrientationPatient.dcm_plane()
        if self.ComplexImageComponent is None and any([comp in self.ImageType for comp in ['M', 'P']]):
            self.ComplexImageComponent = 'MAGNITUDE' if 'M' in self.ImageType else 'PHASE'

        self.ConvertImage = self.should_convert()
        if not self.ConvertImage:
            logging.info('This series is localizer, derived or processed image. Skipping.')

        self.PredictedName = None
        self.NameAutoGen = None
        if self.ConvertImage:
            self.create_image_name(metadata_obj.prefix_to_str(), lut_obj)
        self.NiftiCreated = False

    def __repr_json__(self):
        return {k: NoIndent(v) for k, v in self.__dict__.items()}

    def should_convert(self):
        type_str = ' '.join(self.ImageType[:2]).lower()
        series_desc = self.SeriesDescription.lower()
        type_status = ('derived' not in type_str) or \
                      ('derived' in type_str and 'primary' in type_str)
        desc_ignore = any([item in series_desc for item in DESCRIPTION_IGNORE])
        mpr_ignore = (re.search(r'.*mpr(?!age).*', series_desc) is not None) or \
            any([img_type.lower() == 'mpr' for img_type in self.ImageType]) or \
            any(['projection' in img_type.lower() for img_type in self.ImageType]) or \
            'composed' in series_desc or any(['composed' in img_type.lower() for img_type in self.ImageType])
        mip_ignore = 'mip' in series_desc or any([img_type.lower() == 'mnip' for img_type in self.ImageType]) or \
            any([img_type.lower() == 'maximum' for img_type in self.ImageType])
        processed_ignore = any([img_type.lower() == 'adc' for img_type in self.ImageType]) or \
            any([img_type.lower() == 'sub' for img_type in self.ImageType])
        logging.debug('Derived:%s, Description:%s, MPR:%s, MIP:%s, Processed:%s' %
                      (not type_status, desc_ignore, mpr_ignore, mip_ignore, processed_ignore))
        return type_status and not desc_ignore and not mpr_ignore and not mip_ignore and not processed_ignore

    def create_image_name(self, scan_str, lut_obj):
        autogen = False
        pred_list = check_lut(self.InstitutionName, self.SeriesDescription, lut_obj)
        if pred_list is False:
            self.ConvertImage = False
            return
        if pred_list is None:
            logging.debug('Name lookup failed, using automatic name generation.')
            autogen = True
            series_desc = self.SeriesDescription.lower().replace(' ', '')
            manu = self.Manufacturer.lower()
            # Needs automatic naming
            # 1) Orientation
            orientation = self.ImageOrientation.upper()
            # 2) Resolution
            resolution = self.MRAcquisitionType
            # 3) Ex-contrast
            excontrast = 'PRE'
            if not (self.ContrastBolusAgent is None or self.ContrastBolusAgent == ''):
                excontrast = 'POST'
            elif any([item in series_desc for item in POSTGAD_DESC]):
                excontrast = 'POST'
            # 4) Modality
            desc_modalities = []
            if 't1' in series_desc:
                desc_modalities.append('T1')
            if 't2' in series_desc:
                desc_modalities.append('T2')
            if 'flair' in series_desc:
                desc_modalities.append('FLAIR')
            if re.search(r'medic(?!al)', series_desc) or 't2star' in series_desc or \
                    re.search(r'swi(?!p)', series_desc) or 't2*' in series_desc or 'swan' in series_desc:
                desc_modalities.append('T2STAR')
            if 'stir' in series_desc:
                desc_modalities.append('STIR')
            if 'dti' in series_desc or 'diff' in series_desc or 'dw' in series_desc or 'b1000' in series_desc:
                desc_modalities.append('DIFF')
            if 'trust' in series_desc:
                desc_modalities.append('PERF')

            modality = 'UNK'
            if len(desc_modalities) == 1:
                modality = desc_modalities[0]
            else:
                if 'T1' in desc_modalities and 'T2STAR' in desc_modalities:
                    modality = 'T1'
                if 'T1' in desc_modalities and 'FLAIR' in desc_modalities:
                    modality = 'T1'
                if 'T2' in desc_modalities and 'T2STAR' in desc_modalities:
                    modality = 'T2STAR'
            if series_desc in ['swi_images', 'pha_images', 'mag_images']:
                self.ComplexImageComponent = {'swi_images': 'SWI',
                                              'mag_images': 'MAGNITUDE',
                                              'pha_images': 'PHASE'}[series_desc]
                modality = 'T2STAR'
            elif any(['flow' in img_type.lower() for img_type in self.ImageType]) or \
                    any(['velocity' in img_type.lower() for img_type in self.ImageType]):
                modality = 'FLOW'
            elif any(['tof' in img_type.lower() for img_type in self.ImageType]) or \
                    any(['tof' in variant.lower() for variant in self.SequenceVariant]) or \
                    'tof' in series_desc:
                modality = 'TOF'
            elif any(['mtc' in variant.lower() for variant in self.SequenceVariant]):
                modality = 'MT'
            # 5) Sequence
            mp_status = 'mprage' in series_desc or 'bravo' in series_desc
            etl = 1 if self.EchoTrainLength is None else self.EchoTrainLength
            seq_name = '' if self.SequenceName is None else self.SequenceName.lower()
            scan_seq = [seq.lower() for seq in self.ScanningSequence]
            seq_var = [variant.lower() for variant in self.SequenceVariant]
            sequence = 'UNK'
            if mp_status:
                sequence = 'IRFSPGR'
            elif any([seq == 'se' for seq in scan_seq]):
                sequence = 'SE'
            elif any([seq == 'gr' for seq in scan_seq]):
                sequence = 'GRE'
            elif self.FlipAngle >= 90:
                sequence = 'SE'
            if any(['ep' == seq for seq in scan_seq]) or \
                    'epi' in seq_name or 'epi' in series_desc:
                sequence = 'EPI'
            if sequence == 'GRE' and any([variant == 'sp' for variant in seq_var]) or \
                    any([variant == 'ss' for variant in seq_var]):
                sequence = 'SPGR'
            if sequence != 'EPI' and etl > 1:
                sequence = 'F' + sequence
            if sequence != 'EPI' and 'IR' not in sequence:
                if self.InversionTime is not None and self.InversionTime > 50:
                    sequence = 'IR' + sequence
                elif any([seq == 'ir' for seq in scan_seq]):
                    sequence = 'IR' + sequence
                elif 'flair' in series_desc or 'stir' in series_desc:
                    sequence = 'IR' + sequence
            if sequence.startswith('IR') and resolution == '3D' and 'F' not in sequence:
                sequence = sequence.replace('IR', 'IRF')
            if 'philips' in manu and sequence == 'FSPGR' and 'MP' in self.SequenceVariant:
                sequence = 'IRFSPGR'
            if modality == 'UNK':
                if sequence == 'IRFSPGR':
                    modality = 'T1'
                elif sequence.endswith('SE'):
                    modality = 'T2'
                elif sequence.endswith('GRE') or sequence.endswith('SPGR'):
                    modality = 'T1' if self.EchoTime < 10 and self.RepetitionTime < 20 else 'T2STAR'
            if modality == 'T2' and sequence.startswith('IR'):
                modality = 'STIR' if self.InversionTime is not None and self.InversionTime < 400 else 'FLAIR'
            elif modality == 'T2' and (sequence.endswith('GRE') or sequence.endswith('SPGR')):
                modality = 'T2STAR'
            body_part = 'BRAIN'
            body_part_ex = '' if self.BodyPartExamined is None else self.BodyPartExamined.lower()
            study_desc = self.StudyDescription.lower().replace(' ', '')
            if 'brain' in series_desc:
                body_part = 'BRAIN'
            elif 'cerv' in series_desc or 'csp' in series_desc or \
                    'c-sp' in series_desc or 'msma' in series_desc:
                body_part = 'CSPINE'
            elif 'thor' in series_desc or 'tsp' in series_desc or 't-sp' in series_desc:
                body_part = 'TSPINE'
            elif 'lumb' in series_desc or 'lsp' in series_desc:
                body_part = 'LSPINE'
            elif 'me3d1r3' in seq_name or 'me2d1r2' in seq_name or \
                    re.search(r'\sct(?:\s+|$)', self.SeriesDescription.lower()) or 'vibe' in series_desc:
                body_part = 'SPINE'
            elif 'orbit' in series_desc or 'thin' in series_desc:
                body_part = 'ORBITS'
            elif 'brain' in study_desc:
                body_part = 'BRAIN'
            elif 'cerv' in study_desc or ('cspine' in study_desc and 'thor' not in study_desc):
                body_part = 'CSPINE'
            elif 'thor' in study_desc or 'tspine' in study_desc:
                body_part = 'TSPINE'
            elif 'lumb' in study_desc or 'lspine' in study_desc:
                body_part = 'LSPINE'
            elif 'orbit' in study_desc:
                body_part = 'ORBITS'
            elif 'brain' in body_part_ex:
                body_part = 'BRAIN'
            elif 'cspine' in body_part_ex or 'ctspine' in body_part_ex:
                body_part = 'CSPINE'
            elif 'tspine' in body_part_ex or 'tlspine' in body_part_ex:
                body_part = 'TSPINE'
            elif 'lspine' in body_part_ex or 'lsspine' in body_part_ex:
                body_part = 'LSPINE'
            elif 'spine' in series_desc or 'spine' in body_part_ex or \
                    'spine' in study_desc:
                body_part = 'SPINE'
            if modality == 'DIFF' and orientation == 'SAGITTAL':
                body_part = 'SPINE'
            if 'upper' in series_desc:
                body_part = 'CSPINE'
            elif 'lower' in series_desc:
                body_part = 'TSPINE'
            slice_sp = float(self.SliceThickness) if self.SpacingBetweenSlices is None \
                else float(self.SpacingBetweenSlices)
            if body_part == 'ORBITS' and self.NumFiles * slice_sp > 120:
                body_part = 'BRAIN'
            elif body_part == 'BRAIN' and self.NumFiles * slice_sp < 100 and orientation == 'SAGITTAL':
                body_part = 'SPINE'
            pred_list = [body_part, modality, sequence, resolution, orientation, excontrast]
        else:
            logging.debug('Name lookup successful.')
        if pred_list[1] == 'T2' and self.EchoTime < 25:
            pred_list[1] = 'PD'
        pred_name = '_'.join([scan_str, '-'.join(pred_list)])
        logging.debug('Predicted name: %s' % pred_name)
        self.PredictedName = pred_name
        self.NameAutoGen = autogen

    def create_nii(self):
        if not self.ConvertImage:
            return

        niidir = os.path.join(os.path.dirname(os.path.dirname(self.SourcePath)), 'nii')
        mkdir_p(niidir)
        if os.path.exists(os.path.join(niidir, self.PredictedName + '.nii.gz')):
            count = 2
            while os.path.exists(os.path.join(niidir, self.PredictedName + ('-ACQ%d' % count) + '.nii.gz')):
                count += 1
            logging.debug('Adjusting name for %s: %s --> %s' % (self.SeriesUID, self.PredictedName,
                                                                self.PredictedName + ('-ACQ%d' % count)))
            self.PredictedName = self.PredictedName + ('-ACQ%d' % count)
        if self.PredictedName.endswith('ACQ3'):
            logging.warning('%s has 3 or more acquisitions of the same name. This is uncommon and should be checked.'
                            % '-'.join(self.PredictedName.split('-')[:-1]))

        success = True
        dcm2niix_cmd = [shutil.which('dcm2niix'), '-b', 'n', '-z', 'y', '-f', self.PredictedName,
                        '-o', niidir, self.SourcePath]
        result = run(dcm2niix_cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logging.warning('dcm2niix failed for %s' % self.SourcePath)
            logging.warning('Attempted to create %s.nii.gz' % self.PredictedName)
            if logging.getLogger().level > logging.DEBUG:
                logging.warning('Run again with -v to print dcm2niix output')
            else:
                logging.log(WARNING_DEBUG, '\n' + result.stdout)
            for filename in parse_dcm2niix_filenames(result.stdout):
                remove_created_files(filename)
            logging.warning('Nifti creation failed.')
            return

        for filename in parse_dcm2niix_filenames(result.stdout):
            if not success:
                remove_created_files(filename)
            if len(glob(filename + '_Eq*.nii.gz')) > 0:
                remove_created_files(filename)
                logging.warning('Slices missing for DICOM UID %s, not converted.' % self.SeriesUID)
                logging.warning('Nifti creation failed.')
                success = False
                continue
            reo_result = reorient(filename + '.nii.gz', self.ImageOrientation)
            if not reo_result:
                remove_created_files(filename)
                success = False
                continue
            if 'DIFF' in filename and os.path.exists(filename + '_ADC.nii.gz'):
                logging.info('Additional ADC images produced by dcm2niix. Removing.')
                os.remove(filename + '_ADC.nii.gz')
            while re.search(r'_(e[0-9]+|ph)$', filename):
                os.rename(filename + '.nii.gz', re.sub(r'_(e[0-9]+|ph)$', '', filename) + '.nii.gz')
                filename = re.sub(r'_(e[0-9]+|ph)$', '', filename)
        if success:
            self.NiftiCreated = True
            logging.info('Nifti created successfully at %s' %
                         (os.path.join(niidir, self.PredictedName + '.nii.gz')))


class DicomSet:

    def __init__(self, output_root, metadata_obj, lut_file):
        self.metadata = metadata_obj
        self.lookup_table = read_lut(lut_file, self.metadata.project_id, self.metadata.site_id)

        self.series_list = []
        for dcmdir in sorted(glob(os.path.join(output_root, self.metadata.dir_to_str(), 'dcm', '*'))):
            logging.info('Processing %s' % dcmdir)
            self.series_list.append(DicomInfo(dcmdir, self.metadata, self.lookup_table))
        self.series_list = sorted(sorted(self.series_list, key=lambda x: (x.StudyUID, x.SeriesNumber, x.SeriesUID)),
                                  key=lambda x: x.ConvertImage, reverse=True)

        logging.info('Generating unique names')
        self.generate_unique_names()

    def __repr_json__(self):
        return self.__dict__

    def generate_unique_names(self):
        names_set = set([di.PredictedName for di in self.series_list])
        names_dict = {name: {} for name in names_set}
        for di in self.series_list:
            if di.PredictedName is None:
                continue
            root_uid = '.'.join(di.SeriesUID.split('.')[:-1])
            if root_uid not in names_dict[di.PredictedName]:
                names_dict[di.PredictedName][root_uid] = []
            names_dict[di.PredictedName][root_uid].append(di.SeriesUID.split('.')[-1])
        dyn_checks = {}
        for i, di in enumerate(self.series_list):
            if di.PredictedName is None:
                continue
            root_uid = '.'.join(di.SeriesUID.split('.')[:-1])
            orig_name = di.PredictedName
            if di.SeriesDescription.startswith('sWIP'):
                logging.debug('Adjusting name for %s: %s --> %s' %
                              (di.SeriesUID, di.PredictedName, di.PredictedName + '-SUM'))
                di.PredictedName = di.PredictedName + '-SUM'
            if di.PredictedName.split('_')[-1].split('-')[0] == 'SPINE':
                if di.SeriesDescription == self.series_list[i-1].SeriesDescription:
                    di.PredictedName = di.PredictedName.replace('SPINE', 'TSPINE')
                else:
                    di.PredictedName = di.PredictedName.replace('SPINE', 'CSPINE')
            if len(names_dict[orig_name][root_uid]) > 1:
                if root_uid not in dyn_checks:
                    dyn_checks[root_uid] = []
                dyn_checks[root_uid].append(di)
                dyn_num = names_dict[orig_name][root_uid].index(di.SeriesUID.split('.')[-1]) + 1
                logging.debug('Adjusting name for %s: %s --> %s' %
                              (di.SeriesUID, di.PredictedName, di.PredictedName + '-DYN%d' % dyn_num))
                di.PredictedName = di.PredictedName + ('-DYN%d' % dyn_num)

        for dcm_uid, di_list in dyn_checks.items():
            non_matching = []
            for item in DCM_MATCHING_ITEMS:
                if any([getattr(di_list[0], item) != getattr(di_list[i], item) for i in range(len(di_list))]):
                    non_matching.append(item)
            if non_matching == ['EchoTime']:
                for i, di in enumerate(sorted(di_list, key=lambda x: x.EchoTime)):
                    new_name = '-'.join(di.PredictedName.split('-')[:-1] + ['ECHO%d' % (i + 1)])
                    logging.debug('Adjusting name for %s: %s --> %s' % (di.SeriesUID, di.PredictedName, new_name))
                    di.PredictedName = new_name
            elif non_matching == ['ComplexImageComponent']:
                for di in di_list:
                    comp = 'MAG' if 'mag' in di.ComplexImageComponent.lower() else 'PHA'
                    new_name = '-'.join(di.PredictedName.split('-')[:-1] + [comp])
                    logging.debug('Adjusting name for %s: %s --> %s' % (di.SeriesUID, di.PredictedName, new_name))
                    di.PredictedName = new_name
            elif non_matching == ['EchoTime', 'ComplexImageComponent']:
                tes = list(set([di.EchoTime for di in sorted(di_list, key=lambda x: x.EchoTime)]))
                for di in di_list:
                    comp = 'MAG' if 'mag' in di.ComplexImageComponent.lower() else 'PHA'
                    echo_num = tes.index(di.EchoTime)
                    new_name = '-'.join(di.PredictedName.split('-')[:-1] + ['ECHO%d' % (echo_num + 1), comp])
                    logging.debug('Adjusting name for %s: %s --> %s' % (di.SeriesUID, di.PredictedName, new_name))
                    di.PredictedName = new_name
            elif non_matching == ['ImageOrientationPatient']:
                for di in di_list:
                    new_name = '-'.join(di.PredictedName.split('-')[:-1])
                    logging.debug('Undoing name adjustment for %s: %s --> %s' %
                                  (di.SeriesUID, di.PredictedName, new_name))
                    di.PredictedName = new_name
            else:
                continue

        for di in self.series_list:
            if di.PredictedName is None:
                continue
            if di.PredictedName.split('_')[2].split('-')[1] == 'T2STAR' and not \
                    any([di.PredictedName.split('_')[2].split('-')[-1] == item for item in ['MAG', 'PHA', 'SWI']]):
                comp = di.ComplexImageComponent[:3] if di.ComplexImageComponent is not None else 'MAG'
                logging.debug('Adjusting name for %s: %s --> %s' %
                              (di.SeriesUID, di.PredictedName, di.PredictedName + '-' + comp))
                di.PredictedName = di.PredictedName + '-' + comp

        for di in self.series_list:
            if di.PredictedName is not None and ' '.join(di.ImageType[:2]).lower() == 'derived primary':
                if len([di2.PredictedName for di2 in self.series_list
                        if di2.PredictedName == di.PredictedName and
                        ' '.join(di2.ImageType[:2]).lower() == 'original primary']) > 0:
                    di.PredictedName = None
                    di.ConvertImage = False

    def create_all_nii(self):
        for di in self.series_list:
            if di.ConvertImage:
                logging.info('Creating Nifti for %s' % di.SeriesUID)
                di.create_nii()


class ImageOrientation:

    def __init__(self, orientation, precision=1e-4):
        self.orientation = orientation
        self.precision = precision

    def __eq__(self, other):
        if isinstance(other, ImageOrientation) \
                and self.orientation is not None \
                and other.orientation is not None:
            return all([abs(self.orientation[i]-other.orientation[i]) <= 0.0001
                        for i in range(len(self.orientation))])
        else:
            return super().__eq__(other)

    def __hash__(self):
        return hash(tuple([self.truncate(num) for num in self.orientation]))

    def __repr_json__(self):
        return [self.truncate(num) for num in self.orientation]

    def truncate(self, num):
        return np.around(int(num/self.precision)*self.precision,
                         int(abs(np.log10(self.precision))+1))

    def dcm_plane(self):
        if self.orientation is None:
            return None
        orient_orth = [round(x) for x in self.orientation]
        plane = int(np.argmax([abs(x) for x in np.cross(orient_orth[0:3], orient_orth[3:6])]))
        return DCM_ORIENT_PLANES.get(plane, None)


def remove_created_files(filename):
    for imgname in [f for f in glob(filename + '*') if re.search(filename + r'_*[A-Za-z0-9_]*\..+$', f)]:
        os.remove(imgname)


def parse_dcm2niix_filenames(stdout):
    filenames = []
    for line in stdout.split("\n"):
        if line.startswith("Convert "):  # output
            fname = str(re.search(r"\S+/\S+", line).group(0))
            filenames.append(os.path.abspath(fname))
    return filenames


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
                                              for item in DCM_MATCHING_ITEMS])))
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

    logging.info('Sorting completed.')


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

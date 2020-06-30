from __future__ import annotations
from copy import deepcopy
import json
import logging
from pathlib import Path
import re
import shutil
from subprocess import run
from typing import List, Tuple, Union, Any, Optional

import numpy as np

from .info import __version__
from .json import NoIndent, JSONObjectEncoder
from .lut import LookupTable
from .metadata import Metadata
# from .logging import WARNING_DEBUG
from .utils import (mkdir_p, reorient, parse_dcm2niix_filenames, remove_created_files,
                    add_acq_num, find_closest, FILE_OCTAL, sha1_file_dir, p_add)


DESCRIPTION_IGNORE = ['loc', 'survey', 'scout', '3-pl', 'cal', 'scanogram']
POSTGAD_DESC = ['post', '+c', 'gad', 'gd', 'pstc']
MATCHING_ITEMS = ['ImageOrientationPatient',
                  'RepetitionTime', 'FlipAngle', 'EchoTime',
                  'InversionTime', 'ComplexImageComponent']
DCM_ORIENT_PLANES = {0: 'sagittal', 1: 'coronal', 2: 'axial'}
PARREC_ORIENTATIONS = {1: 'axial', 2: 'sagittal', 3: 'coronal'}


class BaseInfo:

    def __init__(self, path: Path) -> None:
        self.SourcePath = path
        self.SeriesUID = None
        self.StudyUID = None
        self.NumFiles = None
        self.InstitutionName = None
        self.Manufacturer = None
        self.ScannerModelName = None
        self.SeriesDescription = None
        self.AcqDateTime = None
        self.MagneticFieldStrength = None
        self.AcquisitionDimension = None
        self.SliceSpacing = None
        self.SliceThickness = None
        self.FlipAngle = None
        self.RepetitionTime = None
        self.EchoTime = None
        self.InversionTime = None
        self.EchoTrainLength = None
        self.AcquisitionMatrix = []
        self.AcquiredResolution = None
        self.ReconMatrix = None
        self.ReconResolution = None
        self.FieldOfView = None
        self.SequenceType = tuple()
        self.ImageType = None
        self.SeriesNumber = None
        self.ComplexImageComponent = None
        self.BodyPartExamined = None
        self.StudyDescription = None
        self.SequenceVariant = tuple()
        self.SequenceName = None
        self.ExContrastAgent = None
        self.ImageOrientationPatient = None
        self.ImagePositionPatient = None
        self.SliceOrientation = None
        self.SoftwareVersions = None
        self.NumberOfAverages = None
        self.PercentSampling = None
        self.ReceiveCoilName = None
        self.PixelBandwidth = None
        self.VariableFlipAngle = None

        self.ConvertImage = False
        self.NiftiCreated = False
        self.LookupName = None
        self.PredictedName = None
        self.NiftiName = None

    def __repr_json__(self) -> dict:
        return {k: NoIndent(v) for k, v in self.__dict__.items()}

    def should_convert(self) -> bool:
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
        processed_ignore = any(['adc' in img_type.lower() for img_type in self.ImageType]) or \
            any([img_type.lower() == 'sub' for img_type in self.ImageType])
        logging.debug('Derived:%s, Description:%s, MPR:%s, MIP:%s, Processed:%s' %
                      (not type_status, desc_ignore, mpr_ignore, mip_ignore, processed_ignore))
        self.ConvertImage = type_status and not desc_ignore and not mpr_ignore \
            and not mip_ignore and not processed_ignore
        if not self.ConvertImage:
            logging.info('This series is localizer, derived or processed image. Skipping.')
        return self.ConvertImage

    def create_image_name(self, scan_str: str, lut_obj: LookupTable) -> None:
        autogen = False
        pred_list = lut_obj.check(self.InstitutionName, self.SeriesDescription)
        if pred_list is False:
            self.ConvertImage = False
            return
        if pred_list is None:
            # Needs automatic naming
            logging.debug('Name lookup failed, using automatic name generation.')
            autogen = True
            series_desc = self.SeriesDescription.lower()
            if series_desc.startswith('wip'):
                series_desc = series_desc[3:].lstrip()
            # 1) Orientation
            orientation = self.SliceOrientation.upper()
            # 2) Resolution
            resolution = self.AcquisitionDimension
            # 3) Ex-contrast
            excontrast = 'PRE'
            if not (self.ExContrastAgent is None or self.ExContrastAgent == ''):
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
            if 'dti' in series_desc or 'diff' in series_desc or 'dw' in series_desc or 'b1000' in series_desc or \
                    any([img_type.lower() == 'diffusion' for img_type in self.ImageType]):
                desc_modalities.append('DIFF')

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
                    'tof' in series_desc or 'angio' in series_desc:
                modality = 'TOF'
            elif any(['mtc' in variant.lower() for variant in self.SequenceVariant]) or \
                    getattr(self, 'MTContrast', 0) == 1:
                modality = 'MT'
            elif getattr(self, 'DiffusionFlag', 0) == 1:
                modality = 'DIFF'
            # 5) Sequence
            etl = 1 if self.EchoTrainLength is None else self.EchoTrainLength
            seq_name = '' if self.SequenceName is None else self.SequenceName.lower()
            seq_type = [seq.lower() for seq in self.SequenceType]
            seq_var = [variant.lower() for variant in self.SequenceVariant]
            sequence = 'UNK'
            if any([seq == 'se' for seq in seq_type]):
                sequence = 'SE'
            elif any([seq == 'gr' for seq in seq_type]):
                sequence = 'GRE'
            elif 't1ffe' in seq_name:
                sequence = 'SPGR'
            elif self.FlipAngle >= 60:
                sequence = 'SE'
            if any(['ep' == seq for seq in seq_type]) or \
                    'epi' in seq_name or 'epi' in series_desc or \
                    getattr(self, 'EPIFactor', 0) > 1 or \
                    'feepi' in seq_name:
                sequence = 'EPI'
            if sequence == 'GRE' and (any([variant == 'sp' for variant in seq_var]) or
                                      any([variant == 'ss' for variant in seq_var])):
                sequence = 'SPGR'
            if sequence != 'EPI' and etl > 1:
                sequence = 'F' + sequence
            if sequence != 'EPI' and 'IR' not in sequence:
                if self.InversionTime is not None and self.InversionTime > 50:
                    sequence = 'IR' + sequence
                elif any([seq == 'ir' for seq in seq_type]):
                    sequence = 'IR' + sequence
                elif 'flair' in series_desc or 'stir' in series_desc:
                    sequence = 'IR' + sequence
            if sequence.startswith('IR') and resolution == '3D' and 'F' not in sequence:
                sequence = sequence.replace('IR', 'IRF')
            if 'mprage' in series_desc or 'bravo' in series_desc or \
                    self.Manufacturer == 'philips' and sequence == 'FSPGR' and 'MP' in self.SequenceVariant:
                sequence = 'IRFSPGR'
            if modality == 'UNK':
                if sequence == 'IRFSPGR':
                    modality = 'T1'
                elif sequence.endswith('SE'):
                    modality = 'T2'
                elif sequence.endswith('GRE') or sequence.endswith('SPGR'):
                    modality = 'T1' if self.EchoTime < 15 and self.RepetitionTime < 60 else 'T2STAR'
            if modality == 'T2' and sequence.startswith('IR'):
                modality = 'STIR' if self.InversionTime is not None and self.InversionTime < 400 else 'FLAIR'
            elif modality == 'T2' and (sequence.endswith('GRE') or sequence.endswith('SPGR')):
                modality = 'T2STAR'
            elif modality == 'T2' and self.EchoTime < 30:
                modality = 'PD' if self.RepetitionTime > 800 else 'T1'
            body_part = 'BRAIN'
            body_part_ex = '' if self.BodyPartExamined is None else self.BodyPartExamined.lower()
            study_desc = ('' if self.StudyDescription is None else self.StudyDescription.lower().replace(' ', ''))
            if 'brain' in series_desc or series_desc.startswith('br_'):
                body_part = 'BRAIN'
            elif 'cerv' in series_desc or 'csp' in series_desc or 'c sp' in series_desc or \
                    'c-sp' in series_desc or 'msma' in series_desc:
                body_part = 'CSPINE'
            elif 'thor' in series_desc or 'tsp' in series_desc or 't sp' in series_desc or \
                    't-sp' in series_desc:
                body_part = 'TSPINE'
            elif 'lumb' in series_desc or 'lsp' in series_desc or 'l sp' in series_desc or \
                    'l-sp' in series_desc:
                body_part = 'LSPINE'
            elif 'me3d1r3' in seq_name or 'me2d1r2' in seq_name or \
                    re.search(r'\sct(?:\s+|$)', self.SeriesDescription.lower()) or 'vibe' in series_desc or \
                    series_desc.startswith('sp_'):
                body_part = 'SPINE'
            elif 'orbit' in series_desc or 'thin' in series_desc or series_desc.startswith('on_'):
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
            slice_sp = float(self.SliceThickness) if self.SliceSpacing is None \
                else float(self.SliceSpacing)
            if self.NumFiles < 10 and body_part == 'BRAIN' and modality in ['T1', 'T2', 'T2STAR', 'FLAIR']:
                logging.info('This series is localizer, derived or processed image. Skipping.')
                self.ConvertImage = False
                return
            elif body_part == 'ORBITS' and self.NumFiles * slice_sp > 120:
                body_part = 'BRAIN'
            elif body_part == 'BRAIN' and self.NumFiles * slice_sp < 100 \
                    and orientation == 'SAGITTAL':
                body_part = 'SPINE'

            pred_list = [body_part, modality, sequence, resolution, orientation, excontrast]
        else:
            logging.debug('Name lookup successful.')
        if pred_list[1] == 'DE':
            pred_list[1] = 'PD' if self.EchoTime < 30 else 'T2'
        if autogen:
            self.PredictedName = pred_list
        else:
            self.LookupName = pred_list
        logging.debug('Predicted name: %s' % self.NiftiName)
        self.NiftiName = '_'.join([scan_str, '-'.join(pred_list)])

    def create_nii(self) -> None:
        if not self.ConvertImage:
            return

        niidir = Path(self.SourcePath.parent.parent, 'nii')
        mkdir_p(niidir)
        count = 1
        while Path(niidir, add_acq_num(self.NiftiName, count) + '.nii.gz').exists():
            count += 1
        logging.debug('Adjusting name for %s: %s --> %s' % (self.SeriesUID, self.NiftiName,
                                                            add_acq_num(self.NiftiName, count)))
        self.NiftiName = add_acq_num(self.NiftiName, count)

        success = True
        dcm2niix_cmd = [shutil.which('dcm2niix'), '-b', 'n', '-z', 'y', '-f',
                        self.NiftiName, '-o', niidir, self.SourcePath]
        result = run(dcm2niix_cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logging.warning('dcm2niix failed for %s' % self.SourcePath)
            logging.warning('Attempted to create %s.nii.gz' % self.NiftiName)
            logging.warning('dcm2niix return code: %d' % result.returncode)
            logging.warning('dcm2niix output:' % result.returncode)
            logging.warning('\n' + result.stdout)
            for filename in parse_dcm2niix_filenames(result.stdout):
                remove_created_files(filename)
            logging.warning('Nifti creation failed.')
            return

        for filename in parse_dcm2niix_filenames(result.stdout):
            if not success:
                remove_created_files(filename)
            if len(list(filename.parent.glob(filename.name + '_Eq*.nii.gz'))) > 0:
                remove_created_files(filename)
                logging.warning('Slices missing for DICOM UID %s, not converted.' % self.SeriesUID)
                logging.warning('Nifti creation failed.')
                success = False
                continue
            reo_result = reorient(p_add(filename, '.nii.gz'), self.SliceOrientation)
            if not reo_result:
                remove_created_files(filename)
                success = False
                continue
            if 'DIFF' in filename.name and p_add(filename, '_ADC.nii.gz').exists():
                logging.info('Additional ADC images produced by dcm2niix. Removing.')
                p_add(filename, '_ADC.nii.gz').unlink()
            while re.search(r'_(e[0-9]+|ph)$', filename.name):
                new_path = filename.parent / (re.sub(r'_(e[0-9]+|ph)$', '', filename.name))
                p_add(filename, '.nii.gz').rename(p_add(new_path, '.nii.gz'))
                filename = new_path
        if success:
            if (niidir / (self.NiftiName + '.nii.gz')).exists():
                self.NiftiCreated = True
                logging.info('Nifti created successfully at %s' % (niidir / (self.NiftiName + '.nii.gz')))
                if '-ACQ3' in self.NiftiName:
                    logging.warning('%s has 3 or more acquisitions of the same name. This is uncommon and '
                                    'should be checked.' % self.NiftiName.replace('-ACQ3', ''))
            else:
                self.NiftiCreated = False
                logging.warning('Nifti creation failed for %s' % self.SourcePath)
                logging.warning('Attempted to create %s.nii.gz' % self.NiftiName)
                logging.warning('dcm2niix return code: %d' % result.returncode)
                logging.warning('dcm2niix output:' % result.returncode)
                logging.warning('\n' + result.stdout)
                logging.warning('Nifti creation failed.')


class BaseSet:
    def __init__(self, source: Path, output_root: Path, metadata_obj: Metadata, lut_obj: LookupTable,
                 input_hash: Optional[str] = None) -> None:
        self.AutoConvVersion = __version__
        self.InputSource = source
        if input_hash is None:
            logging.info('Hashing source file(s) for record keeping.')
            self.InputHash = sha1_file_dir(self.InputSource)
            logging.info('Hashing complete.')
        else:
            logging.info('Using existing source hash for record keeping.')
            self.InputHash = input_hash
        self.Metadata = metadata_obj
        self.LookupTable = lut_obj
        self.OutputRoot = output_root
        self.SeriesList = []

    def __repr_json__(self) -> dict:
        return self.__dict__

    def generate_unique_names(self) -> None:
        self.SeriesList = sorted(sorted(self.SeriesList, key=lambda x: (x.StudyUID, x.SeriesNumber, x.SeriesUID)),
                                 key=lambda x: x.ConvertImage, reverse=True)
        names_set = set([di.NiftiName for di in self.SeriesList])
        names_dict = {name: {} for name in names_set}
        for di in self.SeriesList:
            if di.NiftiName is None:
                continue
            root_uid = '.'.join(di.SeriesUID.split('.')[:-1])
            if root_uid not in names_dict[di.NiftiName]:
                names_dict[di.NiftiName][root_uid] = []
            names_dict[di.NiftiName][root_uid].append(di.SeriesUID.split('.')[-1])
        dyn_checks = {}
        for i, di in enumerate(self.SeriesList):
            if di.NiftiName is None:
                continue
            root_uid = '.'.join(di.SeriesUID.split('.')[:-1])
            orig_name = di.NiftiName
            # sWIP is Philips indicator for a "sum" of a multi-echo image
            if di.SeriesDescription.startswith('sWIP'):
                logging.debug('Adjusting name for %s: %s --> %s' %
                              (di.SeriesUID, di.NiftiName, di.NiftiName + '-SUM'))
                di.NiftiName = di.NiftiName + '-SUM'
            # Change T1 image to MT/MTOFF if matches an MT sequence and add MTON for the corresponding MT scan
            if di.NiftiName.split('_')[-1].split('-')[1] in ['T1', 'T2STAR'] and \
                    any([di.NiftiName.split('_')[-1] ==
                         other_di.NiftiName.split('_')[-1].replace('-MT-', '-%s-' %
                                                                   di.NiftiName.split('_')[-1].split('-')[1])
                         for other_di in self.SeriesList
                         if other_di.NiftiName is not None and '-MT-' in other_di.NiftiName]):
                closest_mt = find_closest(i, [j for j, other_di in enumerate(self.SeriesList)
                                              if other_di.NiftiName is not None
                                              and '-MT-' in other_di.NiftiName
                                              and di.NiftiName ==
                                              other_di.NiftiName.replace('-MT-', '-%s-' %
                                                                         di.NiftiName.split('_')[-1].split('-')[1])
                                              and di.EchoTime == other_di.EchoTime
                                              and di.FlipAngle == other_di.FlipAngle
                                              and di.RepetitionTime == other_di.RepetitionTime])
                if closest_mt is not None:
                    logging.debug('Adjusting name for %s: %s --> %s' %
                                  (di.SeriesUID, di.NiftiName, di.NiftiName + '-MTOFF'))
                    di.NiftiName = di.NiftiName + '-MTOFF'
                    logging.debug('Adjusting name for %s: %s --> %s' %
                                  (self.SeriesList[closest_mt].SeriesUID,
                                   self.SeriesList[closest_mt].NiftiName,
                                   self.SeriesList[closest_mt].NiftiName + '-MTON'))
                    names_dict[self.SeriesList[closest_mt].NiftiName + '-MTON'] = \
                        names_dict[self.SeriesList[closest_mt].NiftiName]
                    del names_dict[self.SeriesList[closest_mt].NiftiName]
                    self.SeriesList[closest_mt].NiftiName = self.SeriesList[closest_mt].NiftiName + '-MTON'

            # Change generic spine into CSPINE/TSPINE/LSPINE based on previous image
            if di.NiftiName.split('_')[-1].split('-')[0] == 'SPINE':
                if self.SeriesList[i - 1].NiftiName is not None and \
                        di.SeriesDescription == self.SeriesList[i - 1].SeriesDescription and \
                        abs(di.ImagePositionPatient[2] - self.SeriesList[i - 1].ImagePositionPatient[2]) > 100:
                    if self.SeriesList[i - 1].NiftiName.split('_')[-1].split('-')[0] == 'CSPINE':
                        di.NiftiName = di.NiftiName.replace('SPINE', 'TSPINE')
                    else:
                        di.NiftiName = di.NiftiName.replace('SPINE', 'LSPINE')
                else:
                    di.NiftiName = di.NiftiName.replace('SPINE', 'CSPINE')
            if len(names_dict[orig_name][root_uid]) > 1:
                if root_uid not in dyn_checks:
                    dyn_checks[root_uid] = []
                dyn_checks[root_uid].append(di)
                dyn_num = names_dict[orig_name][root_uid].index(di.SeriesUID.split('.')[-1]) + 1
                logging.debug('Adjusting name for %s: %s --> %s' %
                              (di.SeriesUID, di.NiftiName, di.NiftiName + '-DYN%d' % dyn_num))
                di.NiftiName = di.NiftiName + ('-DYN%d' % dyn_num)

        for dcm_uid, di_list in dyn_checks.items():
            non_matching = []
            for item in MATCHING_ITEMS:
                if any([getattr(di_list[0], item) != getattr(di_list[i], item) for i in range(len(di_list))]):
                    non_matching.append(item)
            if non_matching == ['EchoTime']:
                switch_t2star = any(['T2STAR' in di.NiftiName for di in di_list])
                for i, di in enumerate(sorted(di_list, key=lambda x: x.EchoTime)):
                    new_name = '-'.join(di.NiftiName.split('-')[:-1] + ['ECHO%d' % (i + 1)])
                    logging.debug('Adjusting name for %s: %s --> %s' % (di.SeriesUID, di.NiftiName, new_name))
                    di.NiftiName = new_name
                    if switch_t2star:
                        new_name = di.NiftiName.replace('-T1-', '-T2STAR-')
                        logging.debug('Adjusting name for %s: %s --> %s' % (di.SeriesUID, di.NiftiName, new_name))
                        di.NiftiName = new_name
            elif non_matching == ['ComplexImageComponent']:
                for di in di_list:
                    comp = 'MAG' if 'mag' in di.ComplexImageComponent.lower() else 'PHA'
                    new_name = '-'.join(di.NiftiName.split('-')[:-1] + [comp])
                    logging.debug('Adjusting name for %s: %s --> %s' % (di.SeriesUID, di.NiftiName, new_name))
                    di.NiftiName = new_name
            elif non_matching == ['EchoTime', 'ComplexImageComponent']:
                tes = list(set([di.EchoTime for di in sorted(di_list, key=lambda x: x.EchoTime)]))
                for di in di_list:
                    comp = 'MAG' if 'mag' in di.ComplexImageComponent.lower() else 'PHA'
                    echo_num = tes.index(di.EchoTime)
                    new_name = '-'.join(di.NiftiName.split('-')[:-1] + ['ECHO%d' % (echo_num + 1), comp])
                    logging.debug('Adjusting name for %s: %s --> %s' % (di.SeriesUID, di.NiftiName, new_name))
                    di.NiftiName = new_name
            elif non_matching == ['ImageOrientationPatient']:
                for di in di_list:
                    new_name = '-'.join(di.NiftiName.split('-')[:-1])
                    logging.debug('Undoing name adjustment for %s: %s --> %s' %
                                  (di.SeriesUID, di.NiftiName, new_name))
                    di.NiftiName = new_name
            else:
                continue

        for di in self.SeriesList:
            if di.NiftiName is None:
                continue
            if di.NiftiName.split('_')[2].split('-')[1] == 'T2STAR' and not \
                    any([di.NiftiName.split('_')[2].split('-')[-1] == item for item in ['MAG', 'PHA', 'SWI']]):
                comp = di.ComplexImageComponent[:3] if di.ComplexImageComponent is not None else 'MAG'
                logging.debug('Adjusting name for %s: %s --> %s' %
                              (di.SeriesUID, di.NiftiName, di.NiftiName + '-' + comp))
                di.NiftiName = di.NiftiName + '-' + comp

        for di in self.SeriesList:
            if di.NiftiName is not None and ' '.join(di.ImageType[:2]).lower() == 'derived primary':
                if len([di2.NiftiName for di2 in self.SeriesList
                        if di2.NiftiName == di.NiftiName and
                        ' '.join(di2.ImageType[:2]).lower() == 'original primary']) > 0:
                    di.NiftiName = None
                    di.ConvertImage = False

    def create_all_nii(self) -> None:
        for di in self.SeriesList:
            if di.ConvertImage:
                logging.info('Creating Nifti for %s' % di.SeriesUID)
                di.create_nii()
                self.generate_sidecar(di)
        self.SeriesList = sorted(sorted(self.SeriesList, key=lambda x: (x.StudyUID, x.SeriesNumber, x.SeriesUID)),
                                 key=lambda x: x.ConvertImage, reverse=True)

    def generate_sidecar(self, di_obj: BaseInfo) -> None:
        sidecar_file = di_obj.SourcePath.parent.parent / 'nii' / (di_obj.NiftiName + '.json')
        logging.info('Writing image sidecar file to %s' % sidecar_file)
        out_dict = {k: v for k, v in self.__dict__.items() if k != 'SeriesList'}
        out_dict['SeriesInfo'] = di_obj
        sidecar_file.write_text(json.dumps(out_dict, indent=4, sort_keys=True, cls=JSONObjectEncoder))

    def generate_unconverted_info(self) -> None:
        info_file = self.OutputRoot / self.Metadata.dir_to_str() / (self.Metadata.prefix_to_str() +
                                                                    '_MR-UnconvertedInfo.json')
        logging.info('Writing unconverted info file to %s' % info_file)
        out_dict = deepcopy(self.__dict__)
        out_dict['SeriesList'] = [item for item in out_dict['SeriesList'] if not item.NiftiCreated]
        info_file.write_text(json.dumps(out_dict, indent=4, sort_keys=True, cls=JSONObjectEncoder))
        info_file.chmod(FILE_OCTAL)


class TruncatedImageValue:

    def __init__(self, value: Optional[Union[List[float], Tuple[float], np.ndarray]],
                 precision: float = 1e-4) -> None:
        self.value = value
        self.precision = precision

    def __eq__(self, other: Union[Any, TruncatedImageValue]) -> bool:
        if isinstance(other, TruncatedImageValue):
            if self.value is None or other.value is None:
                return False
            return all([abs(self.value[i]-other.value[i]) <= self.precision
                        for i in range(len(self.value))])
        else:
            return super().__eq__(other)

    def __hash__(self) -> int:
        return hash(tuple(self.truncate()))

    def __getitem__(self, item) -> Optional[float]:
        return self.value[item] if self.value is not None else None

    def __repr_json__(self) -> Optional[List[float]]:
        return self.truncate()

    def truncate(self) -> Optional[List[float]]:
        return [float(np.around(int(num/self.precision)*self.precision,
                                int(abs(np.log10(self.precision))+1)))
                for num in self.value] if self.value is not None else None


class ImageOrientation(TruncatedImageValue):
    def get_plane(self) -> Optional[str]:
        if self.value is None:
            return None
        if len(self.value) == 6:  # Direction Cosines
            orient_orth = [round(x) for x in self.value]
            plane = int(np.argmax([abs(x) for x in np.cross(orient_orth[0:3], orient_orth[3:6])]))
            return DCM_ORIENT_PLANES.get(plane, None)
        if len(self.value) == 4:  # Angulation + Plane
            return PARREC_ORIENTATIONS.get(self.value[3], None)

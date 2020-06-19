from datetime import datetime
from glob import glob
import logging
import os
import secrets
import shutil

import numpy as np

from .base import BaseInfo, BaseSet, ImageOrientation, TruncatedImageValue
from .nib_parrec_fork import PARRECHeader, PARRECImage, TruncatedPARRECError
from .parrec_writer import split_fix_parrec
from .utils import make_tuple, silentremove


GENERAL_INFO_FIELDS = {
    'StudyDescription': 'exam_name',
    'SeriesDescription': 'protocol_name',
    'SeriesNumber': 'acq_nr',
    'SequenceType': 'tech',
    'AcquisitionDimension': 'scan_mode',
}
COMPLEX_IMAGE_TYPES = {0: 'MAGNITUDE', 1: 'REAL', 2: 'IMAGINARY', 3: 'PHASE'}


class ParrecInfo(BaseInfo):

    def __init__(self, par_file, institution_name=None, magnetic_field_strength=3):
        super().__init__(par_file)
        file_map = PARRECImage.filespec_to_file_map(par_file)
        with file_map['header'].get_prepare_fileobj('rt') as hdr_fobj:
            try:
                hdr = PARRECHeader.from_fileobj(hdr_fobj, permit_truncated=False)
                self.Truncated = False
            except TruncatedPARRECError:
                hdr = PARRECHeader.from_fileobj(hdr_fobj, permit_truncated=True)
                self.Truncated = True

        self.SeriesUID = os.path.basename(par_file[:-4])
        self.StudyUID = '.'.join(self.SeriesUID.split('.')[:3])
        self.InstitutionName = institution_name
        self.MagneticFieldStrength = magnetic_field_strength
        self.Manufacturer = 'philips'
        for key, value in GENERAL_INFO_FIELDS.items():
            setattr(self, key, hdr.general_info[value])
        self.ReconstructionNumber = hdr.general_info['recon_nr']
        self.MTContrast = hdr.general_info['mtc']
        self.EPIFactor = hdr.general_info['epi_factor']
        self.DiffusionFlag = hdr.general_info['diffusion']
        self.AcquisitionDimension = '2D' if self.AcquisitionDimension == 'MS' else self.AcquisitionDimension
        self.SequenceType = make_tuple(self.SequenceType)
        self.AcqDateTime = str(datetime.strptime(hdr.general_info['exam_date'], '%Y.%m.%d / %H:%M:%S'))
        self.RepetitionTime = hdr.general_info['repetition_time'][0]
        self.ImageType = ['ORIGINAL', 'PRIMARY'] if hdr.general_info['recon_nr'] == 1 \
            else ['ORIGINAL', 'SECONDARY']
        self.NumFiles = hdr.general_info['max_slices']
        self.AcquisitionMatrix = [0, int(hdr.general_info['scan_resolution'][0]),
                                  int(hdr.general_info['scan_resolution'][1]), 0]

        image_defs = hdr.image_defs.view(np.recarray)
        self.ImageOrientationPatient = ImageOrientation(np.concatenate([hdr.general_info['angulation'],
                                                                       image_defs.slice_orientation[0]]))
        self.ImagePositionPatient = TruncatedImageValue(hdr.general_info['off_center'])
        self.SliceOrientation = self.ImageOrientationPatient.get_plane()
        self.EchoTime = float(image_defs.echo_time[0])
        self.FlipAngle = float(image_defs.image_flip_angle[0])
        self.EchoTrainLength = int(image_defs.turbo_factor[0])/int(hdr.general_info['max_echoes']) \
            if image_defs.turbo_factor[0] > 0 else 1
        self.InversionTime = float(image_defs.inversion_delay[0])
        self.ExContrastAgent = image_defs.contrast_bolus_agent[0].decode('UTF-8') \
            if 'contrast_bolus_agent' in hdr.image_defs.dtype.fields.keys() else ''
        self.ComplexImageComponent = COMPLEX_IMAGE_TYPES.get(image_defs.image_type_mr[0], 'MAGNITUDE')
        self.SliceThickness = float(image_defs.slice_thickness[0])
        self.SliceSpacing = float(image_defs.slice_thickness[0]) + float(image_defs.slice_gap[0])

        self.SequenceVariant = tuple()
        self.SequenceName = None
        self.BodyPartExamined = ''
        self.ScannerModelName = None

        if self.Truncated:
            logging.warning('PAR header shows truncated information for image (%s).' % self.SourcePath)


class ParrecSet(BaseSet):

    def __init__(self, output_root, metadata_obj, lut_file, institution_name=None, magnetic_field_strength=3):
        super().__init__(metadata_obj, lut_file)

        for parfile in sorted(glob(os.path.join(output_root, self.metadata.dir_to_str(), 'parrec', '*.par'))):
            logging.info('Processing %s' % parfile)
            self.series_list.append(ParrecInfo(parfile, institution_name, magnetic_field_strength))

        for di in self.series_list:
            if di.should_convert():
                if di.ReconstructionNumber > 1:
                    other_recons = [other_di for other_di in self.series_list
                                    if other_di.SeriesNumber == di.SeriesNumber]
                    if any([other_di.ReconstructionNumber == 1 for other_di in other_recons]):
                        di.ConvertImage = False
                    elif not di.SeriesDescription.startswith('sWIP'):
                        di.ConvertImage = False
                if di.ConvertImage:
                    di.create_image_name(self.metadata.prefix_to_str(), self.lookup_table)

        logging.info('Generating unique names')
        self.generate_unique_names()


def sort_parrecs(parrec_dir):
    logging.info('Sorting PARRECs')
    new_files = []
    study_uid = '2.25.' + str(int(str(secrets.randbits(96))))
    for parfile in sorted(glob(os.path.join(parrec_dir, '*.par'))):
        new_files.extend(split_fix_parrec(parfile, study_uid, parrec_dir))
        silentremove(parfile)
        silentremove(parfile[:-4] + '.rec')
    for name in os.listdir(parrec_dir):
        if name not in new_files:
            if os.path.isdir(os.path.join(parrec_dir, name)):
                shutil.rmtree(os.path.join(parrec_dir, name))
            else:
                os.remove(os.path.join(parrec_dir, name))
    logging.info('Sorting complete')

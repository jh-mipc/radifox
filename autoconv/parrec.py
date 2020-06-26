from datetime import datetime
import logging
from pathlib import Path
import secrets
import shutil

import numpy as np

from .base import BaseInfo, BaseSet, ImageOrientation, TruncatedImageValue
from .nib_parrec_fork import PARRECHeader, PARRECImage, TruncatedPARRECError
from .parrec_writer import split_fix_parrec
from .utils import silentremove


GENERAL_INFO_FIELDS = {
    'StudyDescription': 'exam_name',
    'SeriesDescription': 'protocol_name',
    'SeriesNumber': 'acq_nr',
    'SequenceName': 'tech',
    'AcquisitionDimension': 'scan_mode',
}
COMPLEX_IMAGE_TYPES = {0: 'MAGNITUDE', 1: 'REAL', 2: 'IMAGINARY', 3: 'PHASE'}


class ParrecInfo(BaseInfo):

    def __init__(self, par_file: Path, manual_args=None):
        super().__init__(par_file)
        file_map = PARRECImage.filespec_to_file_map(str(par_file))
        with file_map['header'].get_prepare_fileobj('rt') as hdr_fobj:
            try:
                hdr = PARRECHeader.from_fileobj(hdr_fobj, permit_truncated=False)
                self.Truncated = False
            except TruncatedPARRECError:
                hdr = PARRECHeader.from_fileobj(hdr_fobj, permit_truncated=True)
                self.Truncated = True

        self.SeriesUID = par_file.name[:-4]
        self.StudyUID = '.'.join(self.SeriesUID.split('.')[:3])
        self.Manufacturer = 'philips'
        for key, value in GENERAL_INFO_FIELDS.items():
            setattr(self, key, hdr.general_info[value])
        self.ReconstructionNumber = hdr.general_info['recon_nr']
        self.MTContrast = hdr.general_info['mtc']
        self.EPIFactor = hdr.general_info['epi_factor']
        self.DiffusionFlag = hdr.general_info['diffusion']
        self.AcquisitionDimension = '2D' if self.AcquisitionDimension == 'MS' else self.AcquisitionDimension
        self.AcqDateTime = str(datetime.strptime(hdr.general_info['exam_date'], '%Y.%m.%d / %H:%M:%S'))
        self.RepetitionTime = hdr.general_info['repetition_time'][0]
        self.ImageType = ['ORIGINAL', 'PRIMARY'] if hdr.general_info['recon_nr'] == 1 \
            else ['ORIGINAL', 'SECONDARY']
        self.NumFiles = hdr.general_info['max_slices']
        self.AcquisitionMatrix = [int(hdr.general_info['scan_resolution'][0]),
                                  int(hdr.general_info['scan_resolution'][1])]

        image_defs = hdr.image_defs.view(np.recarray)
        self.ImageOrientationPatient = ImageOrientation(np.concatenate([hdr.general_info['angulation'],
                                                                        [image_defs.slice_orientation[0]]]))
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
        self.ReconMatrix = [int(image_defs.recon_resolution[0][0]), int(image_defs.recon_resolution[0][1])]
        self.ReconResolution = [int(image_defs.pixel_spacing[0][0]), int(image_defs.pixel_spacing[0][1])]
        self.FieldOfView = [res * num for res, num in zip(self.ReconResolution, self.ReconMatrix)]
        self.AcquiredResolution = [fov / num for fov, num in zip(self.FieldOfView, self.AcquisitionMatrix)]
        self.NumberOfAverages = int(image_defs.number_of_averages[0])
        if manual_args is not None:
            for key, value in manual_args.items():
                setattr(self, key, value)

        if self.Truncated:
            logging.warning('PAR header shows truncated information for image (%s).' % self.SourcePath)


class ParrecSet(BaseSet):

    def __init__(self, source: Path, output_root: Path, metadata_obj, lut_obj, manual_args):
        super().__init__(source, output_root, metadata_obj, lut_obj)
        self.ManualArgs = manual_args

        for parfile in sorted(Path(output_root, self.Metadata.dir_to_str(), 'mr-parrec').rglob('*.par')):
            logging.info('Processing %s' % parfile)
            self.SeriesList.append(ParrecInfo(parfile, self.ManualArgs))

        for di in self.SeriesList:
            if di.should_convert():
                if di.ReconstructionNumber > 1:
                    other_recons = [other_di for other_di in self.SeriesList
                                    if other_di.SeriesNumber == di.SeriesNumber]
                    if any([other_di.ReconstructionNumber == 1 for other_di in other_recons]):
                        di.ConvertImage = False
                    elif not di.SeriesDescription.startswith('sWIP'):
                        di.ConvertImage = False
                if di.ConvertImage:
                    di.create_image_name(self.Metadata.prefix_to_str(), self.LookupTable)

        logging.info('Generating unique names')
        self.generate_unique_names()


def sort_parrecs(parrec_dir: Path):
    logging.info('Sorting PARRECs')
    new_files = []
    study_uid = '2.25.' + str(int(str(secrets.randbits(96))))
    for parfile in sorted(Path(parrec_dir).rglob('*.par')):
        new_files.extend(split_fix_parrec(parfile, study_uid, parrec_dir))
        silentremove(parfile)
        silentremove(parfile[:-4] + '.rec')
    for name in parrec_dir.rglob('*'):
        if name not in new_files:
            if Path(parrec_dir, name).is_dir():
                shutil.rmtree(Path(parrec_dir, name))
            else:
                Path(parrec_dir, name).unlink()
    logging.info('Sorting complete')

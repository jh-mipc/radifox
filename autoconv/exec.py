import logging
from pathlib import Path
import shutil

from .dicom import DicomSet, sort_dicoms
from .info import __version__
from .logging import create_loggers
from .metadata import Metadata
from .lut import LookupTable
from .parrec import ParrecSet, sort_parrecs
from .utils import mkdir_p, extract_archive, allowed_archives, recursive_chmod, DIR_OCTAL


def run_autoconv(source: Path, output_root: Path, metadata: Metadata, lut: LookupTable,
                 verbose: bool, parrec: bool, manual_args: dict, rerun: bool) -> None:
    session_path = output_root / metadata.dir_to_str()
    mkdir_p(session_path)
    session_path.chmod(DIR_OCTAL)
    session_path.parent.chmod(mode=DIR_OCTAL)

    create_loggers(output_root / metadata.dir_to_str(), verbose)
    metadata.check_metadata()

    try:
        logging.info('Beginning scan conversion using AutoConv v' + __version__)
        if parrec:
            logging.info('PARREC source indicated. Using InstitutionName=%s and MagneticFieldStrength=%d' %
                         (manual_args['institution'], manual_args['field_strength']))
        type_folder = session_path / ('mr-' + ('parrec' if parrec else 'dcm'))
        sort_func = sort_parrecs if parrec else sort_dicoms
        if not rerun:
            if source.is_dir():
                logging.info('Copying files from source to %s folder' % type_folder.name)
                # noinspection PyTypeChecker
                shutil.copytree(source, type_folder, copy_function=shutil.copyfile)
                logging.info('Copying complete')
            elif any([''.join(source.suffixes) == ext for ext in allowed_archives()[1]]):
                extract_archive(source, type_folder)
            else:
                raise ValueError('Source is not a directory, but does not match one of '
                                 'the available archive formats (%s)' % ', '.join(allowed_archives()[0]))
        recursive_chmod(type_folder)
        sort_func(type_folder)
        recursive_chmod(type_folder)

        if parrec:
            img_set = ParrecSet(source, output_root, metadata, lut, manual_args)
        else:
            img_set = DicomSet(source, output_root, metadata, lut)
        img_set.create_all_nii()
        recursive_chmod(session_path / 'nii')
        img_set.generate_unconverted_info()

        recursive_chmod(session_path / 'logs')
    except KeyboardInterrupt:
        raise
    except:
        logging.exception('Fatal error occurred.')

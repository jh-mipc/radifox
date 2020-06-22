import argparse
from glob import glob
import json
import logging
import os
import shutil
import sys

from .dicom import DicomSet, sort_dicoms
from .info import __version__
from .json import JSONObjectEncoder
from .logging import create_loggers
from .metadata import Metadata
from .parrec import ParrecSet, sort_parrecs
from .utils import silentremove, mkdir_p, unzip, recursive_chmod, FILE_OCTAL, DIR_OCTAL


def main(args=None):
    args = sys.argv[1:] if args is None else args
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=str)
    parser.add_argument('-o', '--output-root', type=str, required=True)
    parser.add_argument('-p', '--project-id', type=str)
    parser.add_argument('-a', '--patient-id', type=str)
    parser.add_argument('-s', '--site-id', type=str)
    parser.add_argument('-t', '--time-id', type=str)
    parser.add_argument('-l', '--lut-file', type=str, required=True)
    parser.add_argument('-m', '--tms-metafile', type=str)
    parser.add_argument('-r', '--project-shortname', type=str)
    parser.add_argument('-v', '--verbose', action='store_true', default=False)
    parser.add_argument('--force', action='store_true', default=False)
    parser.add_argument('--rerun', action='store_true', default=False)
    parser.add_argument('--no-zip', action='store_true', default=False)
    parser.add_argument('--parrec', action='store_true', default=False)
    parser.add_argument('--institution', type=str, default=None)
    parser.add_argument('--field_strength', type=int, default=3)
    parsed_args = parser.parse_args(args)

    parsed_args.output_root = os.path.realpath(os.path.expanduser(parsed_args.output_root))
    parsed_args.tms_metafile = os.path.realpath(os.path.expanduser(parsed_args.tms_metafile)) \
        if parsed_args.tms_metafile else None
    parsed_args.source = os.path.realpath(os.path.expanduser(parsed_args.source))

    if parsed_args.tms_metafile:
        metadata = Metadata.from_tms_metadata(parsed_args.tms_metafile)
        mapping = {'patient_id': 'PatientID', 'time_id': 'TimeID', 'site_id': 'SiteID'}
        for arg in ['patient_id', 'time_id', 'site_id']:
            if getattr(parsed_args, arg, None) is not None:
                setattr(metadata, mapping[arg], getattr(parsed_args, arg))
    else:
        if any([getattr(parsed_args, item) is None for item in ['project_id', 'patient_id', 'time_id']]):
            raise ValueError('Project ID, Patient ID and Time ID are all required arguments.')
        metadata = Metadata(parsed_args.project_id, parsed_args.patient_id, parsed_args.time_id,
                            parsed_args.site_id, parsed_args.project_shortname)

    if len(glob(os.path.join(parsed_args.output_root, metadata.dir_to_str(), '*'))) > 0 and not parsed_args.rerun:
        if parsed_args.force:
            shutil.rmtree(os.path.join(parsed_args.output_root, metadata.dir_to_str()))
        else:
            raise RuntimeError('Output directory exists, run with --force or --rerun to remove outputs and re-run.')
    elif parsed_args.rerun:
        silentremove(os.path.join(parsed_args.output_root, metadata.dir_to_str(), 'nii'))
        silentremove(os.path.join(parsed_args.output_root, metadata.dir_to_str(),
                                  metadata.prefix_to_str() + '_ScanInfo.json'))
        silentremove(os.path.join(parsed_args.output_root, metadata.dir_to_str(),
                                  'logs', 'conversion-info.log'))
        silentremove(os.path.join(parsed_args.output_root, metadata.dir_to_str(),
                                  'logs', 'conversion-warnings.log'))
        silentremove(os.path.join(parsed_args.output_root, metadata.dir_to_str(),
                                  'logs', 'conversion-errors.log'))

    mkdir_p(os.path.join(parsed_args.output_root, metadata.dir_to_str()))
    os.chmod(os.path.join(parsed_args.output_root, metadata.dir_to_str()), mode=DIR_OCTAL)
    os.chmod(os.path.dirname(os.path.join(parsed_args.output_root, metadata.dir_to_str())), mode=DIR_OCTAL)

    create_loggers(parsed_args.output_root, metadata.dir_to_str(), parsed_args.verbose)
    metadata.check_metadata()

    try:
        logging.info('Beginning scan conversion using AutoConv v' + __version__)
        if parsed_args.parrec:
            logging.info('PARREC source indicated. Using InstitutionName=%s and MagneticFieldStrength=%d' %
                         (parsed_args.institution, parsed_args.field_strength))
        type_folder = 'mr-' + ('parrec' if parsed_args.parrec else 'dcm')
        sort_func = sort_parrecs if parsed_args.parrec else sort_dicoms
        if not parsed_args.rerun:
            if parsed_args.no_zip:
                logging.info('Copying files from source to %s folder' % type_folder)
                shutil.copytree(parsed_args.source,
                                os.path.join(parsed_args.output_root, metadata.dir_to_str(), type_folder),
                                copy_function=shutil.copyfile)
                logging.info('Copying complete')
            else:
                unzip(parsed_args.source, os.path.join(parsed_args.output_root, metadata.dir_to_str(), type_folder))
            recursive_chmod(os.path.join(parsed_args.output_root, metadata.dir_to_str(), type_folder))
            sort_func(os.path.join(parsed_args.output_root, metadata.dir_to_str(), type_folder))
            recursive_chmod(os.path.join(parsed_args.output_root, metadata.dir_to_str(), type_folder))

        if parsed_args.parrec:
            img_set = ParrecSet(parsed_args.source, parsed_args.output_root, metadata, parsed_args.lut_file,
                                parsed_args.institution, parsed_args.field_strength)
        else:
            img_set = DicomSet(parsed_args.source, parsed_args.output_root, metadata, parsed_args.lut_file)
        img_set.create_all_nii()
        recursive_chmod(os.path.join(parsed_args.output_root, metadata.dir_to_str(), 'nii'))

        recursive_chmod(os.path.join(parsed_args.output_root, metadata.dir_to_str(), 'logs'))
    except KeyboardInterrupt:
        raise
    except:
        logging.exception('Fatal error occurred.')

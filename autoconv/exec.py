import argparse
from glob import glob
import json
import logging
import os
import shutil
import sys

from .base import BaseInfo
from .dicom import DicomSet, sort_dicoms
from .info import __version__
from .logging import create_loggers
from .lut import LookupTable
from .metadata import Metadata
from .parrec import ParrecSet, sort_parrecs, parse_manual_args
from .utils import mkdir_p, extract_archive, allowed_archives, recursive_chmod, DIR_OCTAL, sha1_file_dir, silentremove


def run_autoconv(source, output_root, metadata, lut, verbose, parrec, manual_args, rerun):
    mkdir_p(os.path.join(output_root, metadata.dir_to_str()))
    os.chmod(os.path.join(output_root, metadata.dir_to_str()), mode=DIR_OCTAL)
    os.chmod(os.path.dirname(os.path.join(output_root, metadata.dir_to_str())), mode=DIR_OCTAL)

    create_loggers(output_root, metadata.dir_to_str(), verbose)
    metadata.check_metadata()

    try:
        logging.info('Beginning scan conversion using AutoConv v' + __version__)
        if parrec:
            logging.info('PARREC source indicated. Using InstitutionName=%s and MagneticFieldStrength=%d' %
                         (manual_args['institution'], manual_args['field_strength']))
        type_folder = 'mr-' + ('parrec' if parrec else 'dcm')
        sort_func = sort_parrecs if parrec else sort_dicoms
        if not rerun:
            if os.path.isdir(source):
                logging.info('Copying files from source to %s folder' % type_folder)
                shutil.copytree(source, os.path.join(output_root, metadata.dir_to_str(), type_folder),
                                copy_function=shutil.copyfile)
                logging.info('Copying complete')
            elif any([source.endswith(ext) for ext in allowed_archives()[1]]):
                extract_archive(source, os.path.join(output_root, metadata.dir_to_str(), type_folder))
            else:
                raise ValueError('Source is not a directory, but does not match one of '
                                 'the available archive formats (%s)' % ', '.join(allowed_archives()[0]))
        recursive_chmod(os.path.join(output_root, metadata.dir_to_str(), type_folder))
        sort_func(os.path.join(output_root, metadata.dir_to_str(), type_folder))
        recursive_chmod(os.path.join(output_root, metadata.dir_to_str(), type_folder))

        if parrec:
            img_set = ParrecSet(source, output_root, metadata, lut, manual_args)
        else:
            img_set = DicomSet(source, output_root, metadata, lut)
        img_set.create_all_nii()
        recursive_chmod(os.path.join(output_root, metadata.dir_to_str(), 'nii'))
        img_set.generate_unconverted_info()

        recursive_chmod(os.path.join(output_root, metadata.dir_to_str(), 'logs'))
    except KeyboardInterrupt:
        raise
    except:
        logging.exception('Fatal error occurred.')


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
    parser.add_argument('--no-project-subdir', action='store_true', default=False)
    parser.add_argument('--parrec', action='store_true', default=False)
    parser.add_argument('--institution', type=str)
    parser.add_argument('--field_strength', type=int, default=3)
    parser.add_argument('--manual-arg', type=str, action='append')
    parsed_args = parser.parse_args(args)

    parsed_args.output_root = os.path.realpath(os.path.expanduser(parsed_args.output_root))
    parsed_args.tms_metafile = os.path.realpath(os.path.expanduser(parsed_args.tms_metafile)) \
        if parsed_args.tms_metafile else None
    parsed_args.source = os.path.realpath(os.path.expanduser(parsed_args.source))

    if not os.path.exists(parsed_args.source):
        raise ValueError('Source file/directory does not exist.')

    if parsed_args.tms_metafile:
        if not os.path.exists(parsed_args.tms_metafile):
            raise ValueError('')
        metadata = Metadata.from_tms_metadata(parsed_args.tms_metafile, parsed_args.no_project_subdir)
        mapping = {'patient_id': 'PatientID', 'time_id': 'TimeID', 'site_id': 'SiteID'}
        for arg in ['patient_id', 'time_id', 'site_id']:
            if getattr(parsed_args, arg, None) is not None:
                setattr(metadata, mapping[arg], getattr(parsed_args, arg))
    else:
        if any([getattr(parsed_args, item) is None for item in ['project_id', 'patient_id', 'time_id']]):
            raise ValueError('Project ID, Patient ID and Time ID are all required arguments.')
        metadata = Metadata(parsed_args.project_id, parsed_args.patient_id, parsed_args.time_id,
                            parsed_args.site_id, parsed_args.project_shortname, parsed_args.no_project_subdir)

    lut = LookupTable(parsed_args.lut_file, metadata.ProjectID, metadata.SiteID)

    if len(glob(os.path.join(parsed_args.output_root, metadata.dir_to_str(), '*'))) > 0 and not parsed_args.rerun:
        if parsed_args.force:
            shutil.rmtree(os.path.join(parsed_args.output_root, metadata.dir_to_str()))
        else:
            raise RuntimeError('Output directory exists, run with --force to remove outputs and re-run.')

    manual_args = parse_manual_args(parsed_args.manual_args, BaseInfo('')) \
        if parsed_args.manual_args is not None else {}
    manual_args['MagneticFieldStrength'] = parsed_args.field_strength
    manual_args['InstitutionName'] = parsed_args.institution_name

    run_autoconv(parsed_args.source, parsed_args.output_root, metadata, lut, parsed_args.verbose, parsed_args.parrec,
                 parsed_args.manual_args, False)


def update(args):
    args = sys.argv[1:] if args is None else args
    parser = argparse.ArgumentParser()
    parser.add_argument('dir', type=str)
    parser.add_argument('-l', '--lut-file', type=str, required=True)
    parser.add_argument('--force', action='store_true', default=False)
    parser.add_argument('--parrec', action='store_true', default=False)
    parser.add_argument('--reckless', action='store_true', default=False)
    parser.add_argument('-v', '--verbose', action='store_true', default=False)
    parsed_args = parser.parse_args(args)

    if not os.path.exists(parsed_args.dir):
        raise ValueError('Session directory (%s) does not exist.' % parsed_args.dir)

    session_id = os.path.basename(parsed_args.dir)
    subj_id = os.path.basename(os.path.dirname(parsed_args.dir))

    json_file = os.path.join(parsed_args.dir, '_'.join([subj_id, session_id, '_MR-UnconvertedInfo.json']))
    if not os.path.exists(json_file):
        raise ValueError('Unconverted info file (%s) does not exist.' % json_file)
    json_obj = json.load(open(os.path.join(parsed_args.dir,
                                           '_'.join([subj_id, session_id, '_MR-UnconvertedInfo.json']))))

    metadata = Metadata.from_dict(json_obj['Metadata'])
    if parsed_args.force or parsed_args.reckless:
        if not os.path.exists(json_obj['InputSource']):
            raise ValueError('Cannot use --force option, as input source (%s) does not exist.' %
                             json_obj['InputSource'])
        if json_obj['TMSMetaFile'] is not None and not os.path.exists(json_obj['TMSMetaFile']):
            raise ValueError('Cannot use --force option, as TMS metadata file (%s) does not exist.' %
                             json_obj['TMSMetaFile'])
        if not parsed_args.reckless:
            if json_obj['TMSMetaFile'] is not None:
                check_metadata = Metadata.from_tms_metadata(json_obj['TMSMetaFile'])
                if check_metadata.TMSMetaFileHash != metadata.TMSMetaFileHash:
                    raise ValueError('TMS meta data file has changed since last conversion, '
                                     'run with --reckless to ignore this error.')
            if sha1_file_dir(json_obj['InputSource']) != json_obj['InputHash']:
                raise ValueError('Source file(s) have changed since last conversion, '
                                 'run with --reckless to ignore this error.')
        shutil.rmtree(os.path.join(parsed_args.output_root, metadata.dir_to_str()))
    else:
        if parsed_args.parrec and \
                not os.path.exists(os.path.join(json_obj['OutputRoot'], metadata.dir_to_str(), 'mr-parrec')):
            raise ValueError('Update source was specified as PARREC, but mr-parrec source directory does not exist.')
        elif not parsed_args.parrec and \
                os.path.exists(os.path.join(json_obj['OutputRoot'], metadata.dir_to_str(), 'mr-dcm')):
            raise ValueError('Update source was specified as DICOM, but mr-parrec source directory does not exist.')

        silentremove(os.path.join(parsed_args.output_root, metadata.dir_to_str(), 'nii'))
        silentremove(os.path.join(parsed_args.output_root, metadata.dir_to_str(),
                                  metadata.prefix_to_str() + '_MR-UnconvertedInfo.json'))
        for filepath in glob(os.path.join(parsed_args.output_root, metadata.dir_to_str(),
                                          'logs', 'autoconv-*.log')):
            silentremove(filepath)

    lut = LookupTable(parsed_args.lut_file, metadata.ProjectID, metadata.SiteID)
    if json_obj['AutoConvVersion'] == __version__ and json_obj['LookupTable']['FileHash'] == lut.FileHash:
        print('No action required. Version and LUT file hash match for %s.' % parsed_args.dir)
        return

    run_autoconv(json_obj['InputSource'], json_obj['OutputRoot'], metadata, lut, parsed_args.verbose,
                 parsed_args.parrec, json_obj.get('ManualArgs', None), True)

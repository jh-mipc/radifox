import argparse
from glob import glob
import json
import logging
import os
import shutil
import sys

from .dicom import DicomSet, sort_dicoms
from .json import JSONObjectEncoder
from .logging import create_loggers
from .metadata import Metadata
from .utils import silentremove, mkdir_p, unzip


def main(args=None):
    args = sys.argv[1:] if args is None else args
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=str)
    parser.add_argument('-o', '--output-root', type=str, required=True)
    parser.add_argument('-p', '--project-id', type=str)
    parser.add_argument('-a', '--patient-id', type=str)
    parser.add_argument('-s', '--site-id', type=str, default=None)
    parser.add_argument('-t', '--time-id', type=str)
    parser.add_argument('-l', '--lut-file', type=str, required=True)
    parser.add_argument('-m', '--tms-metafile', type=str)
    parser.add_argument('-r', '--project-shortname', type=str, default=None)
    parser.add_argument('-v', '--verbose', action='store_true', default=False)
    parser.add_argument('--force', action='store_true', default=False)
    parser.add_argument('--rerun', action='store_true', default=False)
    parser.add_argument('--no-zip', action='store_true', default=False)
    parsed_args = parser.parse_args(args)

    if parsed_args.tms_metafile:
        metadata = Metadata.from_tms_metadata(parsed_args.tms_metafile)
        for arg in ['patient_id', 'time_id', 'site_id']:
            if getattr(parsed_args, arg, None) is not None:
                setattr(metadata, arg, getattr(parsed_args, arg))
    else:
        if any([getattr(parsed_args, item) is None for item in ['project_id', 'patient_id', 'time_id']]):
            raise ValueError('Project ID, Patient ID and Time ID are all required arguments.')
        metadata = Metadata(parsed_args.project_id, parsed_args.patient_id, parsed_args.time_id,
                            parsed_args.site_id, parsed_args.project_shortname)

    if len(glob(os.path.join(parsed_args.output_root, metadata.dir_to_str(), '*'))) > 0 and not parsed_args.rerun:
        if parsed_args.force:
            shutil.rmtree(os.path.join(parsed_args.output_root, metadata.dir_to_str()))
        else:
            raise RuntimeError('Output directory exists, run with --force to remove outputs and re-run.')
    elif parsed_args.rerun:
        silentremove(os.path.join(parsed_args.output_root, metadata.dir_to_str(), 'nii'))
        silentremove(os.path.join(parsed_args.output_root, metadata.dir_to_str(),
                                  metadata.prefix_to_str() + '_DcmInfo.json'))
        silentremove(os.path.join(parsed_args.output_root, metadata.dir_to_str(), 'conversion.log'))
        silentremove(os.path.join(parsed_args.output_root, metadata.dir_to_str(), 'warnings.log'))
        silentremove(os.path.join(parsed_args.output_root, metadata.dir_to_str(), 'errors.log'))

    mkdir_p(os.path.join(parsed_args.output_root, metadata.dir_to_str()))

    create_loggers(parsed_args.output_root, metadata.dir_to_str(), parsed_args.verbose)

    try:
        if not parsed_args.rerun:
            if parsed_args.no_zip:
                shutil.copytree(parsed_args.source,
                                os.path.join(parsed_args.output_root, metadata.dir_to_str(), 'dcm'))
            else:
                unzip(parsed_args.source, os.path.join(parsed_args.output_root, metadata.dir_to_str(), 'dcm'))
            sort_dicoms(os.path.join(parsed_args.output_root, metadata.dir_to_str(), 'dcm'))

        img_set = DicomSet(parsed_args.output_root, metadata, parsed_args.lut_file)
        img_set.create_all_nii()

        logging.info('Writing info file')
        with open(os.path.join(parsed_args.output_root, metadata.dir_to_str(),
                               metadata.prefix_to_str() + '_DcmInfo.json'), 'w') as json_fp:
            json_fp.write(json.dumps(img_set, indent=4, sort_keys=True, cls=JSONObjectEncoder))
    except KeyboardInterrupt:
        raise
    except:
        logging.exception('Fatal error occurred.')

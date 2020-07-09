import json
import logging
from pathlib import Path

import click

from .base import BaseInfo
from .exec import run_autoconv, ExecError
from .info import __version__
from .json import NoIndent, JSONObjectEncoder
from .lut import LookupTable
from .metadata import Metadata
from .utils import hash_file_dir, silentremove, mkdir_p


def abs_path(ctx, param, value) -> Path:
    if value is not None:
        return Path(value).expanduser().resolve()


def parse_manual_args(ctx, param, value) -> dict:
    arg_converter = {'int': int, 'float': float, 'str': str}
    template = BaseInfo(Path('/dev/null'))
    out_args = {}
    for argstr in value:
        arg_arr = argstr.split(':')
        if len(arg_arr) not in [2, 3]:
            raise ValueError('Manual argument is improperly formatted (%s).' % argstr)
        if arg_arr[0] not in template.__dict__:
            raise ValueError('Manual argument does not match an info argument (%s)' % argstr)
        if len(arg_arr) == 3:
            out_args[arg_arr[0]] = arg_converter.get(arg_arr[2], str)(arg_arr[1])
        elif len(arg_arr) == 2:
            out_args[arg_arr[0]] = str(arg_arr[1])
    return out_args


@click.group()
@click.version_option(__version__)
def cli():
    pass


@cli.command()
@click.argument('source', type=click.Path(exists=True), callback=abs_path)
@click.option('-o', '--output-root', type=click.Path(), callback=abs_path, required=True)
@click.option('-l', '--lut-file', type=click.Path(exists=True), callback=abs_path)
@click.option('-p', '--project-id', type=str)
@click.option('-a', '--patient-id', type=str)
@click.option('-s', '--site-id', type=str)
@click.option('-t', '--time-id', type=str)
@click.option('-r', '--project-shortname', type=str)
@click.option('-m', '--tms-metafile', type=click.Path(exists=True), callback=abs_path)
@click.option('-v', '--verbose', is_flag=True)
@click.option('--force', is_flag=True)
@click.option('--reckless', is_flag=True)
@click.option('--no-project-subdir', is_flag=True)
@click.option('--parrec', is_flag=True)
@click.option('--institution', type=str)
@click.option('--field-strength', type=int, default=3)
@click.option('--modality', type=str, default='mr')
@click.option('--manual-arg', type=str, multiple=True, callback=parse_manual_args)
def convert(source: Path, output_root: Path, lut_file: Path, project_id: str, patient_id: str, site_id: str,
            time_id: str, project_shortname: str, tms_metafile: Path, verbose: bool, force: bool, reckless: bool,
            no_project_subdir: bool, parrec: bool, institution: str, field_strength: int, modality: str,
            manual_arg: dict) -> None:

    mapping = {'patient_id': 'PatientID', 'time_id': 'TimeID', 'site_id': 'SiteID'}
    if tms_metafile:
        metadata = Metadata.from_tms_metadata(tms_metafile, no_project_subdir)
        for arg in ['patient_id', 'time_id', 'site_id']:
            if locals().get(arg) is not None:
                setattr(metadata, mapping[arg], getattr(locals(), arg))
    else:
        for item in ['project_id', 'patient_id', 'time_id']:
            if locals().get(item) is None:
                raise ValueError('%s is a required argument when no metadata file is provided.' % mapping[item])
        metadata = Metadata(project_id, patient_id, time_id, site_id, project_shortname, no_project_subdir)

    if lut_file is None:
        lut_file = (output_root / (project_id + '-lut.csv')) if no_project_subdir else \
            (output_root / project_id / (project_id + '-lut.csv'))
    lut = LookupTable(lut_file, metadata.ProjectID, metadata.SiteID)

    type_dir = output_root / metadata.dir_to_str() / (modality + '-' + 'parrec' if parrec else 'dcm')
    if len(list(type_dir.glob('*'))) > 0:
        # TODO: Add checks to see if data has moved (warn and update? error?)
        if force or reckless:
            if not reckless:
                json_file = output_root / metadata.dir_to_str() / (metadata.prefix_to_str() +
                                                                   '_%s-UnconvertedInfo.json' % modality.upper())
                if not json_file.exists():
                    raise ValueError('Unconverted info file (%s) does not exist for consistency checking. '
                                     'Cannot use --force, use --reckless instead.' % json_file)
                json_obj = json.loads(json_file.read_text())
                if json_obj['TMSMetaFile'] is not None:
                    if metadata.TMSMetaFile is None:
                        raise ValueError('Previous conversion did not use a TMS metadata file, '
                                         'run with --reckless to ignore this error.')
                    check_metadata = Metadata.from_tms_metadata(json_obj['TMSMetaFile'])
                    if check_metadata.TMSMetaFileHash != metadata.TMSMetaFileHash:
                        raise ValueError('TMS meta data file has changed since last conversion, '
                                         'run with --reckless to ignore this error.')
                elif json_obj['TMSMetaFile'] is None and metadata.TMSMetaFile is not None:
                    raise ValueError('Previous conversion used a TMS metadata file, '
                                     'run with --reckless to ignore this error.')
                if hash_file_dir(source) != json_obj['InputHash']:
                    raise ValueError('Source file(s) have changed since last conversion, '
                                     'run with --reckless to ignore this error.')
            silentremove(type_dir)
            # TODO: Need a way to distinguish nii files created for this modality
            silentremove(output_root / metadata.dir_to_str() / 'nii')
            for filepath in (output_root / metadata.dir_to_str() / 'logs').glob('autoconv-*.log'):
                silentremove(filepath)
            for filepath in (output_root / metadata.dir_to_str()).glob('%s-*.json' % modality.upper()):
                silentremove(filepath)
        else:
            raise RuntimeError('Output directory exists, run with --force to remove outputs and re-run.')

    manual_arg['MagneticFieldStrength'] = field_strength
    manual_arg['InstitutionName'] = institution

    run_autoconv(source, output_root, metadata, lut, verbose, modality, parrec, False, manual_arg, None)


@cli.command()
@click.argument('directory', type=click.Path(exists=True), callback=abs_path)
@click.option('-l', '--lut-file', type=click.Path(exists=True), callback=abs_path)
@click.option('--force', is_flag=True)
@click.option('--parrec', is_flag=True)
@click.option('--modality', type=str, default='mr')
@click.option('-v', '--verbose', is_flag=True)
def update(directory: Path, lut_file: Path, force: bool, parrec: bool, modality: str, verbose: bool) -> None:
    session_id = directory.name
    subj_id = directory.parent.name

    json_file = directory / '_'.join([subj_id, session_id, '%s-UnconvertedInfo.json' % modality.upper()])
    if not json_file.exists():
        raise ValueError('Unconverted info file (%s) does not exist.' % json_file)
    json_obj = json.loads(json_file.read_text())

    metadata = Metadata.from_dict(json_obj['Metadata'])

    if lut_file is None:
        lut_file = (directory.parent.parent / (metadata.ProjectID + '-lut.csv'))
    lut = LookupTable(lut_file, metadata.ProjectID, metadata.SiteID)

    if not force and (json_obj['AutoConvVersion'] == __version__ and
                      json_obj['LookupTable']['LookupDict'] == lut.LookupDict):
        print('No action required. Software version and LUT dictionary match for %s.' % directory)
        return

    if parrec and not (directory / ('%s-parrec' % modality)).exists():
        raise ValueError('Update source was specified as PARREC, but '
                         '%s-parrec source directory does not exist.' % modality)
    elif not parrec and not (directory / ('%s-dcm' % modality)).exists():
        raise ValueError('Update source was specified as DICOM, but '
                         '%s-dcm source directory does not exist.' % modality)

    mkdir_p(directory / 'prev')
    (directory / 'nii').rename(directory / 'prev' / 'nii')
    json_file.rename(directory / 'prev' / json_file.name)
    for filepath in (directory / 'logs').glob('autoconv-*.log'):
        silentremove(filepath)
    try:
        run_autoconv(Path(json_obj['InputSource']), Path(json_obj['OutputRoot']), metadata, lut, verbose, modality,
                     parrec, True, json_obj.get('ManualArgs', {}), json_obj['InputHash'])
    except ExecError:
        logging.info('Exception caught during update. Resetting to previous state.')
        silentremove(directory / 'nii')
        (directory / 'prev' / 'nii').rename(directory / 'nii')
        silentremove(json_file)
        (directory / 'prev' / json_file.name).rename(json_file)
    silentremove(directory / 'prev')


@cli.command('name')
@click.argument('directory', type=click.Path(exists=True), callback=abs_path)
@click.argument('source', type=str)
@click.argument('name', type=str)
@click.option('--modality', type=str, default='mr')
def set_manual_name(directory: Path, source: str, name: str, modality: str):
    session_id = directory.name
    subj_id = directory.parent.name

    if not (directory / Path(source)).exists():
        raise ValueError('Source directory/file does not exist.')

    json_file = directory / '_'.join([subj_id, session_id, '%s-ManualNaming.json' % modality.upper()])
    json_obj = json.loads(json_file.read_text()) if json_file.exists() else {}

    if source in json_obj:
        print('Updating manual name for %s (%s to %s)' % (source, '-'.join(json_obj[source]), name))
    else:
        print('Adding manual name for %s (%s)' % (source, name))

    json_obj[source] = name.split('-')

    for key in json_obj:
        json_obj[key] = NoIndent(json_obj[key])

    json_file.write_text(json.dumps(json_obj, indent=4, sort_keys=True, cls=JSONObjectEncoder))

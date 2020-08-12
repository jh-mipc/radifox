import json
import logging
from pathlib import Path
import shutil

import click

from .base import BaseInfo
from .exec import run_autoconv, ExecError
from .info import __version__
from .json import NoIndent, JSONObjectEncoder
from .lut import LookupTable
from .metadata import Metadata
from .utils import hash_file_dir, silentremove, mkdir_p, version_check


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
@click.option('--append', is_flag=True)
@click.option('--no-project-subdir', is_flag=True)
@click.option('--parrec', is_flag=True)
@click.option('--symlink', is_flag=True)
@click.option('--hardlink', is_flag=True)
@click.option('--institution', type=str)
@click.option('--field-strength', type=int, default=3)
@click.option('--modality', type=str, default='mr')
@click.option('--manual-arg', type=str, multiple=True, callback=parse_manual_args)
def convert(source: Path, output_root: Path, lut_file: Path, project_id: str, patient_id: str, site_id: str,
            time_id: str, project_shortname: str, tms_metafile: Path, verbose: bool, force: bool, reckless: bool,
            append: bool, no_project_subdir: bool, parrec: bool, symlink: bool, hardlink: bool, institution: str,
            field_strength: int, modality: str, manual_arg: dict) -> None:

    if hardlink and symlink:
        raise ValueError('Only one of --symlink and --hardlink can be used.')
    linking = 'hardlink' if hardlink else ('symlink' if symlink else None)

    mapping = {'patient_id': 'PatientID', 'time_id': 'TimeID', 'site_id': 'SiteID'}
    if tms_metafile:
        metadata = Metadata.from_tms_metadata(tms_metafile, no_project_subdir)
        for arg in ['patient_id', 'time_id', 'site_id']:
            if locals().get(arg) is not None:
                setattr(metadata, mapping[arg], locals().get(arg))
    else:
        for item in ['project_id', 'patient_id', 'time_id']:
            if locals().get(item) is None:
                raise ValueError('%s is a required argument when no metadata file is provided.' % mapping[item])
        metadata = Metadata(project_id, patient_id, time_id, site_id, project_shortname, no_project_subdir)

    if lut_file is None:
        lut_file = (output_root / (metadata.ProjectID + '-lut.csv')) if no_project_subdir else \
            (output_root / metadata.ProjectID / (metadata.ProjectID + '-lut.csv'))
    lut = LookupTable(lut_file, metadata.ProjectID, metadata.SiteID)

    manual_json_file = (output_root / metadata.dir_to_str() /
                        (metadata.prefix_to_str() + '_%s-ManualNaming.json' % modality.upper()))
    manual_names = json.loads(manual_json_file.read_text()) if manual_json_file.exists() else {}

    type_dirname = (modality + '-' + ('parrec' if parrec else 'dcm'))
    type_dir = output_root / metadata.dir_to_str() / type_dirname
    if type_dir.exists():
        # TODO: Add checks to see if data has moved (warn and update? error?)
        if append:
            metadata.AttemptNum = 2
            while (output_root / metadata.dir_to_str() / type_dirname).exists():
                metadata.AttemptNum += 1
            type_dir = output_root / metadata.dir_to_str() / type_dirname
        elif force or reckless:
            if not reckless:
                json_file = output_root / metadata.dir_to_str() / (metadata.prefix_to_str() +
                                                                   '_%s-UnconvertedInfo.json' % modality.upper())
                if not json_file.exists():
                    raise ValueError('Unconverted info file (%s) does not exist for consistency checking. '
                                     'Cannot use --force, use --reckless instead.' % json_file)
                json_obj = json.loads(json_file.read_text())
                if json_obj['Metadata']['TMSMetaFileHash'] is not None:
                    if metadata.TMSMetaFileHash is None:
                        raise ValueError('Previous conversion did not use a TMS metadata file, '
                                         'run with --reckless to ignore this error.')
                    if json_obj['Metadata']['TMSMetaFileHash'] != metadata.TMSMetaFileHash:
                        raise ValueError('TMS meta data file has changed since last conversion, '
                                         'run with --reckless to ignore this error.')
                elif json_obj['Metadata']['TMSMetaFileHash'] is None and metadata.TMSMetaFileHash is not None:
                    raise ValueError('Previous conversion used a TMS metadata file, '
                                     'run with --reckless to ignore this error.')
                if hash_file_dir(source, False) != json_obj['InputHash']:
                    raise ValueError('Source file(s) have changed since last conversion, '
                                     'run with --reckless to ignore this error.')
            shutil.rmtree(type_dir)
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

    run_autoconv(source, output_root, metadata, lut, verbose, modality, parrec, False, linking, manual_arg,
                 manual_names, None)


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
        att_json_file = directory / '_'.join([subj_id, '-'.join(session_id.split('-')[:-1]),
                                              '%s-UnconvertedInfo.json' % modality.upper()])
        if not att_json_file.exists():
            raise ValueError('Unconverted info file (%s) does not exist.' % json_file)
        json_file = att_json_file
    json_obj = json.loads(json_file.read_text())

    metadata = Metadata.from_dict(json_obj['Metadata'])
    if session_id != metadata.TimeID:
        metadata.AttemptNum = int(session_id.split('-')[-1])
    # noinspection PyProtectedMember
    output_root = Path(*directory.parts[:-2]) if metadata._NoProjectSubdir else Path(*directory.parts[:-3])

    if lut_file is None:
        lut_file = Path(*directory.parts[:-2]) / (metadata.ProjectID + '-lut.csv')
    lut = LookupTable(lut_file, metadata.ProjectID, metadata.SiteID)

    manual_json_file = (directory / (metadata.prefix_to_str() + '_%s-ManualNaming.json' % modality.upper()))
    manual_names = json.loads(manual_json_file.read_text()) if manual_json_file.exists() else {}

    if not force and (version_check(json_obj['AutoConvVersion'], __version__) and
                      json_obj['LookupTable']['LookupDict'] == lut.LookupDict and
                      json_obj['ManualNames'] == manual_names):
        print('No action required. Software version, LUT dictionary and naming dictionary match for %s.' % directory)
        return

    type_dir = directory / ('%s-%s' % (modality, 'parrec' if parrec else 'dcm'))
    if parrec and not (directory / ('%s-parrec' % modality)).exists():
        raise ValueError('Update source was specified as PARREC, but '
                         '%s-parrec source directory does not exist.' % modality)
    elif not parrec and not (directory / ('%s-dcm' % modality)).exists():
        raise ValueError('Update source was specified as DICOM, but '
                         '%s-dcm source directory does not exist.' % modality)

    mkdir_p(directory / 'prev')
    (directory / 'nii').rename(directory / 'prev' / 'nii')
    (directory / 'qa').rename(directory / 'prev' / 'qa')
    json_file.rename(directory / 'prev' / json_file.name)
    mkdir_p(directory / 'prev' / 'logs')
    for filepath in (directory / 'logs').glob('autoconv-*.log*'):
        if filepath.name.endswith('.log'):
            filepath.rename(directory / 'prev' / 'logs' / (filepath.name + '.01'))
        else:
            num = int(filepath.name.split('.')[-1]) + 1
            filepath.rename(directory / 'prev' / 'logs' / (filepath.name + '.%02d' % num))
    try:
        run_autoconv(type_dir, output_root, metadata, lut, verbose, modality,
                     parrec, True, None, json_obj.get('ManualArgs', {}), manual_names, json_obj['InputHash'])
    except ExecError:
        logging.info('Exception caught during update. Resetting to previous state.')
        silentremove(directory / 'nii')
        (directory / 'prev' / 'nii').rename(directory / 'nii')
        silentremove(directory / 'qa')
        (directory / 'prev' / 'qa').rename(directory / 'qa')
        silentremove(json_file)
        (directory / 'prev' / json_file.name).rename(json_file)
        for filepath in (directory / 'prev' / 'logs').glob('autoconv-*.log*'):
            filepath.rename(directory / 'logs' / filepath.name)
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

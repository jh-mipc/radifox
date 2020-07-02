import json
from pathlib import Path
import shutil

import click

from .base import BaseInfo
from .exec import run_autoconv
from .info import __version__
from .lut import LookupTable
from .metadata import Metadata
from .utils import sha1_file_dir, silentremove


def abs_path(ctx, param, value) -> Path:
    if value is not None:
        return Path(value).expanduser().resolve()


def parse_manual_args(ctx, param, value) -> dict:
    arg_converter = {'int': int, 'float': float, 'str': str}
    template = BaseInfo(Path('/'))
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
@click.option('-l', '--lut-file', type=click.Path(exists=True), callback=abs_path, required=True)
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
@click.option('--manual-arg', type=str, multiple=True, callback=parse_manual_args)
def convert(source: Path, output_root: Path, lut_file: Path, project_id: str, patient_id: str, site_id: str,
            time_id: str, project_shortname: str, tms_metafile: Path, verbose: bool, force: bool, reckless: bool,
            no_project_subdir: bool, parrec: bool, institution: str, field_strength: int, manual_arg: dict) -> None:

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

    lut = LookupTable(lut_file, metadata.ProjectID, metadata.SiteID)

    if len(list((output_root / metadata.dir_to_str()).glob('*'))) > 0:
        # TODO: Add checks to see if data has moved (warn and update? error?)
        if force or reckless:
            if not reckless:
                json_file = output_root / metadata.dir_to_str() / (metadata.prefix_to_str() +
                                                                   '_MR-UnconvertedInfo.json')
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
                if sha1_file_dir(source) != json_obj['InputHash']:
                    raise ValueError('Source file(s) have changed since last conversion, '
                                     'run with --reckless to ignore this error.')
            shutil.rmtree(output_root / metadata.dir_to_str())
        else:
            raise RuntimeError('Output directory exists, run with --force to remove outputs and re-run.')

    manual_arg['MagneticFieldStrength'] = field_strength
    manual_arg['InstitutionName'] = institution

    run_autoconv(source, output_root, metadata, lut, verbose, parrec, False, manual_arg, None)


@cli.command()
@click.argument('directory', type=click.Path(exists=True), callback=abs_path)
@click.option('-l', '--lut-file', type=click.Path(exists=True), required=True, callback=abs_path)
@click.option('--parrec', is_flag=True)
@click.option('-v', '--verbose', is_flag=True)
def update(directory: Path, lut_file: Path, parrec: bool, verbose: bool) -> None:
    session_id = directory.name
    subj_id = directory.parent.name

    json_file = directory / '_'.join([subj_id, session_id, 'MR-UnconvertedInfo.json'])
    if not json_file.exists():
        raise ValueError('Unconverted info file (%s) does not exist.' % json_file)
    json_obj = json.loads(json_file.read_text())

    metadata = Metadata.from_dict(json_obj['Metadata'])

    lut = LookupTable(lut_file, metadata.ProjectID, metadata.SiteID)
    # TODO: Simple update if LUT hash is different but dictionary is the same (updated for another project)
    if json_obj['AutoConvVersion'] == __version__ and json_obj['LookupTable']['FileHash'] == lut.FileHash:
        print('No action required. Software version and LUT file hash match for %s.' % directory)
        return

    if parrec and not (directory / 'mr-parrec').exists():
        raise ValueError('Update source was specified as PARREC, but mr-parrec source directory does not exist.')
    elif not parrec and not (directory / 'mr-dcm').exists():
        raise ValueError('Update source was specified as DICOM, but mr-dcm source directory does not exist.')

    silentremove(directory / 'nii')
    silentremove(directory / (metadata.prefix_to_str() + '_MR-UnconvertedInfo.json'))
    for filepath in (directory / 'logs').glob('autoconv-*.log'):
        silentremove(filepath)

    run_autoconv(Path(json_obj['InputSource']), Path(json_obj['OutputRoot']), metadata, lut, verbose,
                 parrec, True, json_obj.get('ManualArgs', {}), json_obj['InputHash'])

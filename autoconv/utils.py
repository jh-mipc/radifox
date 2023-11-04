from codecs import BOM_UTF8
from collections.abc import Sequence
import csv
from datetime import datetime, date, time, timedelta
import hashlib
import logging
from pathlib import Path
import re
import shutil
from subprocess import check_output
from typing import Union, Any, List, Optional

import nibabel as nib
from pydicom.dataset import Dataset, FileDataset, Tag


ORIENT_CODES = {'sagittal': 'PIL', 'coronal': 'LIP', 'axial': 'LPS'}


# http://stackoverflow.com/a/22718321
def mkdir_p(path: Path, mode: int = 0o777) -> None:
    path.mkdir(mode=mode, parents=True, exist_ok=True)


def copytree_link(source: Path, dest: Path, symlink: bool):
    dest.mkdir(parents=True, exist_ok=True)
    for path in source.glob('*'):
        if path.is_file():
            if symlink:
                (dest / path.name).symlink_to(path)
            else:
                (dest / path.name).hardlink_to(path)
        elif path.is_dir():
            (dest / path.name).mkdir()
            copytree_link(path, dest / path.name, symlink)


# http://stackoverflow.com/a/10840586
def silentremove(filename: Path) -> None:
    import shutil
    import errno
    try:
        if filename.is_file():
            filename.unlink()
        else:
            shutil.rmtree(filename)
    except OSError as e:  # this would be "except OSError, e:" before Python 2.6
        if e.errno != errno.ENOENT:  # errno.ENOENT = no such file or directory
            raise  # re-raise exception if a different error occurred


def read_csv(csv_filename: Path) -> (dict, str):
    data = csv_filename.read_bytes()
    codec = 'UTF-8-SIG' if data.startswith(BOM_UTF8) else 'UTF-8'
    data = data.decode(codec)
    line_sep = '\r\n' if '\r\n' in data else '\n'
    data = data.split(line_sep)
    out_dict = {key: [] for key in data[0].split(',')}
    for row in csv.DictReader(data):
        for key in out_dict.keys():
            out_dict[key].append(row[key])
    return out_dict


def convert_dicom_date(date_str: str) -> date:
    return datetime.strptime(date_str.replace('-', ''), '%Y%m%d').date()


def convert_dicom_time(time_str: str) -> time:
    return datetime.strptime(time_str.split('.')[0].ljust(6, '0'), '%H%M%S').time()


def convert_dicom_datetime(dt_str: str) -> date:
    return datetime.strptime(dt_str.replace('-', '').split('.')[0], '%Y%m%d%H%M%S')


vr_corr = {
    'CS': str,
    'DA': convert_dicom_date,
    'DS': float,
    'DT': convert_dicom_datetime,
    'FD': float,
    'FL': float,
    'IS': int,
    'LO': str,
    'LT': str,
    'OB': bytes,
    'PN': str,
    'SH': str,
    'SL': int,
    'SS': int,
    'ST': str,
    'TM': convert_dicom_time,
    'UI': str,
    'UL': int,
    'US': int
}


def extract_de(ds: Dataset | FileDataset, label: str, series_uid, keep_list: bool = False) -> \
        Union[None, tuple, float, int, str]:
    if label not in ds:
        return tuple() if keep_list else None
    de = ds[label]
    if de.VM == 0:
        return tuple() if keep_list else None
    value = [de.value] if de.VM == 1 else de.value
    try:
        out_list = []
        for item in value:
            out_list.append(vr_corr[de.VR](item))
        out_list = tuple(out_list)
    except ValueError:
        logging.warning('Data element (%s) will not conform to required type (%s) for %s.' %
                        (de.name, str(vr_corr[de.VR]), series_uid))
        return tuple() if keep_list else None
    return out_list[0] if (len(out_list) == 1 and not keep_list) else out_list


def is_intstr(test_str: str) -> bool:
    try:
        int(test_str)
    except ValueError:
        return False
    return True


def reorient(input_file: Path, orientation: str) -> bool:
    # noinspection PyTypeChecker
    input_obj = nib.Nifti1Image.load(input_file)
    input_orient = ''.join(nib.aff2axcodes(input_obj.affine))
    target_orient = ORIENT_CODES[orientation]
    logging.debug('Reorienting %s from %s to %s.' %
                  (input_file, input_orient, target_orient))
    if input_orient != tuple(target_orient):
        try:
            orig_ornt = nib.orientations.io_orientation(input_obj.affine)
            targ_ornt = nib.orientations.axcodes2ornt(target_orient)
            ornt_xfm = nib.orientations.ornt_transform(orig_ornt, targ_ornt)

            affine = input_obj.affine.dot(nib.orientations.inv_ornt_aff(ornt_xfm, input_obj.shape))
            data = nib.orientations.apply_orientation(input_obj.dataobj, ornt_xfm)
            nib.Nifti1Image(data, affine, input_obj.header).to_filename(str(input_file))
            return True
        except ValueError:
            logging.warning('Reorientation failed for %s' % input_file)
            return False


def allowed_archives() -> (List[str], List[str]):
    allowed_exts = []
    allowed_names = []
    for names, extensions, _ in shutil.get_unpack_formats():
        allowed_exts.extend(extensions)
        allowed_names.append(names)
    if '.zip' in allowed_exts:
        allowed_exts.append('.zip.zip')
    return allowed_names, allowed_exts


def extract_archive(input_zipfile: Path, output_dir: Path) -> None:
    logging.info('Extracting archive')
    mkdir_p(output_dir)
    # noinspection PyTypeChecker
    shutil.unpack_archive(input_zipfile, output_dir)
    logging.info('Extraction complete')


def make_tuple(item: Union[bytes, str, Sequence]) -> tuple:
    if isinstance(item, (bytes, str)):
        return tuple([item])
    return tuple(item) if isinstance(item, Sequence) else tuple([item])


def remove_created_files(filename: Path) -> None:
    for imgname in [f for f in filename.parent.glob(filename.name + '*')
                    if re.search(filename.name + r'_*[A-Za-z0-9_]*\..+$', f.name)]:
        imgname.unlink()


def parse_dcm2niix_filenames(stdout: str) -> List[Path]:
    filenames = []
    for line in stdout.split("\n"):
        if line.startswith("Convert "):  # output
            fname = Path(str(re.search(r"\S+/\S+", line).group(0)))
            filenames.append(fname.resolve())
    return filenames


def add_acq_num(name: str, count: int) -> str:
    prefix = '_'.join(name.split('_')[:-1])
    contrast_arr = name.split('_')[-1].split('-')
    addons = '' if len(contrast_arr) == 6 else ('-' + '-'.join(contrast_arr[6:]))
    base_contrast = '-'.join(contrast_arr[:6])
    return prefix + '_' + base_contrast + ('-ACQ%d' % count) + addons


FILE_OCTAL = 0o660
DIR_OCTAL = 0o2770


def has_permissions(path: Path, octal: int = DIR_OCTAL) -> bool:
    return int('0o' + oct(path.stat().st_mode)[-4:], 8) == octal


def recursive_chmod(directory: Path, dir_octal: int = DIR_OCTAL,
                    file_octal: int = FILE_OCTAL) -> None:
    if not directory.exists():
        return
    elif directory.is_file():
        directory.chmod(file_octal)
    else:
        directory.chmod(dir_octal)
        for item in directory.rglob('*'):
            if item.is_dir():
                item.chmod(dir_octal)
            elif item.is_file():
                item.chmod(file_octal)


def find_closest(target: int, to_check: List[int]) -> Optional[int]:
    if len(to_check) < 1:
        return None
    elif len(to_check) == 1:
        return to_check[0]
    signed_dists = []
    for check_val in to_check:
        signed_dists.append((check_val - target, check_val))
    min_dist = min([abs(val[0]) for val in signed_dists])
    candidates = [val[1] for val in signed_dists if abs(val[0]) == min_dist]
    return candidates[0] if len(candidates) == 1 else min(candidates)


def hash_update_from_file(filename: Path, hash_func: Any = hashlib.md5, include_names: bool = True) -> str:
    hash_obj = hash_func()
    if include_names:
        hash_obj.update(filename.name.encode())
    with filename.open('rb') as fp:
        for chunk in iter(lambda: fp.read(4096), b""):
            hash_obj.update(chunk)
    return str(hash_obj.hexdigest())


def hash_file(filename: Path, hash_type: Any = hashlib.md5, include_names: bool = True) -> str:
    return hash_update_from_file(filename, hash_type, include_names)


def hash_update_from_dir(directory: Path, hash_func: Any = hashlib.md5, include_names: bool = True,
                         existing_hashes: Optional[list] = None) -> list:
    if existing_hashes is None:
        existing_hashes = []
    if include_names:
        existing_hashes.append(directory.name)
    for path in sorted(directory.iterdir(), key=lambda p: str(p).lower()):
        if path.is_file():
            existing_hashes.append(hash_update_from_file(path, hash_func, include_names))
        elif path.is_dir():
            existing_hashes.extend(hash_update_from_dir(path, hash_func, include_names))
    return existing_hashes


def hash_dir(directory, outer_hash_func: Any = hashlib.sha256,
             inner_hash_func: Any = hashlib.md5, include_names: bool = True) -> str:
    hashobj = outer_hash_func()
    for item in sorted(hash_update_from_dir(directory, inner_hash_func, include_names)):
        hashobj.update(item.encode())
    return str(hashobj.hexdigest())


def hash_file_dir(file_dir: Path, include_names: bool = True) -> str:
    if file_dir.is_file():
        return hash_file(file_dir, hashlib.sha256, include_names=include_names)
    elif file_dir.is_dir():
        return hash_dir(file_dir, include_names=include_names)


def hash_file_list(file_list: List[Path], include_names: bool = True) -> str:
    hash_obj = hashlib.sha256()
    for path in file_list:
        hash_obj.update(hash_file_dir(path, include_names).encode())
    return str(hash_obj.hexdigest())


def hash_value(value: str, hash_func: Any = hashlib.sha256) -> Optional[str]:
    if value is None:
        return None
    m = hash_func()
    m.update(value.encode())
    return str(m.hexdigest())


def p_add(path: Path, extra: str) -> Path:
    return path.parent / (path.name + extra)


def get_software_versions():
    dcm2niix_version = check_output('dcm2niix --version; exit 0', shell=True).decode().strip().split('\n')[-1].strip()
    dcmdjpeg_version = check_output([shutil.which('dcmdjpeg'), '--version']).decode().strip().split('\n')[0].strip()
    emf2sf_version = check_output([shutil.which('emf2sf'), '--version']).decode().strip()
    return {'dcm2niix': dcm2niix_version, 'dcmdjpeg': dcmdjpeg_version, 'emf2sf': emf2sf_version}


def version_check(saved_version, current_version):
    if 'dev' in saved_version or 'dev' in current_version:
        return False
    saved_arr = saved_version.split('-')[0].split('.')
    current_arr = current_version.split('-')[0].split('.')
    for saved, current in zip(saved_arr, current_arr):
        if int(saved) < int(current):
            return False
    return True


def shift_date(datetime_str: Optional[str] = None, date_shift_days: int = 0):
    orig_date = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
    return (orig_date + timedelta(days=date_shift_days)).strftime('%Y-%m-%d %H:%M:%S')


def none_to_float(value):
    return float('inf') if value is None else value


def get_flattened_dataset(dataset):
    return Dataset({de.tag: de for de in dataset.iterall() if de.VR != 'SQ'})


EXCLUDE_TAGS = [
    Tag('SharedFunctionalGroupsSequence'),
    Tag('PerFrameFunctionalGroupsSequence'),
    Tag('DimensionIndexSequence'),
    Tag('NumberOfFrames'),
    Tag('SourceImageEvidenceSequence'),
    Tag('ReferencedImageEvidenceSequence'),
    Tag('PixelData')
]


def fix_sf_headers(dataset):
    if 'EffectiveEchoTime' in dataset:
        dataset.EchoTime = dataset.EffectiveEchoTime
    scan_seq: list = (dataset.ScanningSequence if dataset['ScanningSequence'].VM > 1 else [dataset.ScanningSequence]) \
        if 'ScanningSequence' in dataset else []
    if 'EchoPulseSequence' in dataset:
        if dataset.EchoPulseSequence != 'SPIN':
            scan_seq.append('GR')
        if dataset.EchoPulseSequence != 'GRADIENT':
            scan_seq.append('GR')
    if dataset.get('InversionRecovery', 'NO') == 'YES':
        scan_seq.append('IR')
    if dataset.get('EchoPlanarPulseSequence', 'NO') == 'YES':
        scan_seq.append('EP')
    dataset.ScanningSequence = list(set(scan_seq))

    seq_var: list = (dataset.SequenceVariant if dataset['SequenceVariant'].VM > 1 else [dataset.SequenceVariant]) \
        if 'SequenceVariant' in dataset else []
    if dataset.get('SegmentedKSpaceTraversal', 'SINGLE') != 'SINGLE':
        seq_var.append('SK')
    if dataset.get('MagnetizationTransfer', 'NONE') != 'NONE':
        seq_var.append('MTC')
    if dataset.get('SteadyStatePulseSequence', 'NONE') != 'NONE':
        seq_var.append('TRSS' if dataset.SteadyStatePulseSequence == 'TIME_REVERSED' else 'SS')
    if dataset.get('Spoiling', 'NONE') != 'NONE':
        seq_var.append('SP')
    if dataset.get('OversamplingPhase', 'NONE') != 'NONE':
        seq_var.append('OSP')
    if len(seq_var) == 0:
        seq_var.append('NONE')
    dataset.SequenceVariant = list(set(seq_var))

    scan_opts: list = (dataset.ScanOptions if dataset['ScanOptions'].VM > 1 else [dataset.ScanOptions]) \
        if 'ScanOptions' in dataset else []
    if dataset.get('RectilinearPhaseEncodeReordering', 'LINEAR') != 'LINEAR':
        scan_opts.append('PER')
    frame_type3 = dataset.FrameType[2]
    if frame_type3 == 'ANGIO':
        dataset.AngioFlag = 'Y'
    if frame_type3.startswith('CARD'):
        scan_opts.append('CG')
    if frame_type3.endswith('RESP_GATED'):
        scan_opts.append('RG')
    if 'PartialFourierDirection' in dataset:
        if dataset.PartialFourierDirection == 'PHASE':
            scan_opts.append('PFP')
        elif dataset.PartialFourierDirection == 'FREQUENCY':
            scan_opts.append('PFF')
    if dataset.get('SpatialPresaturation', 'NONE') != 'NONE':
        scan_opts.append('SP')
    if dataset.get('SpectrallySelectedSuppression', 'NONE').startswith('FAT'):
        scan_opts.append('FS')
    if dataset.get('FlowCompensation', 'NONE') != 'NONE':
        scan_opts.append('FC')
    dataset.ScanOptions = list(set(scan_opts))
    return dataset


def create_sf_headers(dataset):
    shared_ds = Dataset({de.tag: de for de in dataset if de.tag not in EXCLUDE_TAGS})
    shared_ds.file_meta = dataset.file_meta
    shared_ds.update(get_flattened_dataset(dataset.SharedFunctionalGroupsSequence[0]))
    flattened_frame_ds_list = [get_flattened_dataset(dataset.PerFrameFunctionalGroupsSequence[i])
                               for i in range(len(dataset.PerFrameFunctionalGroupsSequence))]

    sf_ds_list = []
    for flat_frame_ds in flattened_frame_ds_list:
        sf_ds = Dataset({de.tag: de for de in shared_ds})
        sf_ds.update(flat_frame_ds)
        sf_ds_list.append(fix_sf_headers(sf_ds))
    return sf_ds_list

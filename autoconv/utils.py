from codecs import BOM_UTF8
from collections.abc import Sequence
import csv
from glob import glob
import hashlib
import logging
import os
import re
import zipfile

import nibabel as nib
from pydicom.multival import MultiValue
from pydicom.valuerep import DSfloat
from pydicom.valuerep import IS


ORIENT_CODES = {'sagittal': 'PIL', 'coronal': 'LIP', 'axial': 'LPS'}


# http://stackoverflow.com/a/22718321
def mkdir_p(path, mode=0o777):
    import os
    import errno
    try:
        os.makedirs(path, mode=mode)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


# http://stackoverflow.com/a/10840586
def silentremove(filename):
    import os
    import shutil
    import errno
    try:
        if os.path.isfile(filename):
            os.remove(filename)
        else:
            shutil.rmtree(filename)
    except OSError as e:  # this would be "except OSError, e:" before Python 2.6
        if e.errno != errno.ENOENT:  # errno.ENOENT = no such file or directory
            raise  # re-raise exception if a different error occurred


def read_csv(csv_filename):
    with open(csv_filename, 'rb') as fp:
        data = fp.read()
    hasher = hashlib.sha1()
    hasher.update(data)
    codec = 'UTF-8-SIG' if data.startswith(BOM_UTF8) else 'UTF-8'
    data = data.decode(codec)
    line_sep = '\r\n' if '\r\n' in data else '\n'
    data = data.split(line_sep)
    out_dict = {key: [] for key in data[0].split(',')}
    for row in csv.DictReader(data):
        for key in out_dict.keys():
            out_dict[key].append(row[key])
    return out_dict, hasher.hexdigest()


def convert_type(val):
    if isinstance(val, MultiValue):
        return list(val)
    elif isinstance(val, DSfloat):
        return float(val)
    elif isinstance(val, IS):
        return int(val)
    else:
        return val


def is_intstr(test_str):
    try:
        int(test_str)
    except ValueError:
        return False
    return True


def reorient(input_file, orientation):
    input_obj = nib.load(input_file)
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
            nib.Nifti1Image(data, affine, input_obj.header).to_filename(input_file)
            return True
        except ValueError:
            logging.warning('Reorientation failed for %s' % input_file)
            return False


def unzip(input_zipfile, output_dir):
    logging.info('Unzipping zipfile')
    mkdir_p(output_dir)
    zip_ref = zipfile.ZipFile(input_zipfile, 'r')
    zip_ref.extractall(output_dir)
    zip_ref.close()
    logging.info('Unzipping complete')


def make_tuple(item):
    if isinstance(item, (bytes, str)):
        return tuple([item])
    return tuple(item) if isinstance(item, Sequence) else tuple([item])


def remove_created_files(filename):
    for imgname in [f for f in glob(filename + '*') if re.search(filename + r'_*[A-Za-z0-9_]*\..+$', f)]:
        os.remove(imgname)


def parse_dcm2niix_filenames(stdout):
    filenames = []
    for line in stdout.split("\n"):
        if line.startswith("Convert "):  # output
            fname = str(re.search(r"\S+/\S+", line).group(0))
            filenames.append(os.path.abspath(fname))
    return filenames


def add_acq_num(name, count):
    prefix = '_'.join(name.split('_')[:-1])
    contrast_arr = name.split('_')[-1].split('-')
    addons = '' if len(contrast_arr) == 6 else ('-' + '-'.join(contrast_arr[6:]))
    base_contrast = '-'.join(contrast_arr[:6])
    return prefix + '_' + base_contrast + ('-ACQ%d' % count) + addons


FILE_OCTAL=0o660
DIR_OCTAL=0o2770


def recursive_chmod(directory, dir_octal=DIR_OCTAL, file_octal=FILE_OCTAL):
    for dirpath, dirnames, filenames in os.walk(directory):
        os.chmod(dirpath, dir_octal)
        for filename in filenames:
            os.chmod(os.path.join(dirpath, filename), file_octal)

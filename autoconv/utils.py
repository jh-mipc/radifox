from codecs import BOM_UTF8
import csv
import logging
import zipfile

import nibabel as nib
from pydicom.multival import MultiValue
from pydicom.valuerep import DSfloat
from pydicom.valuerep import IS


ORIENT_CODES = {'sagittal': 'PIL', 'coronal': 'LIP', 'axial': 'LPS'}


# http://stackoverflow.com/a/22718321
def mkdir_p(path):
    import os
    import errno
    try:
        os.makedirs(path)
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
    codec = 'UTF-8-SIG' if data.startswith(BOM_UTF8) else 'UTF-8'
    data = data.decode(codec)
    line_sep = '\r\n' if '\r\n' in data else '\n'
    data = data.split(line_sep)
    out_dict = {key: [] for key in data[0].split(',')}
    for row in csv.DictReader(data):
        for key in out_dict.keys():
            out_dict[key].append(row[key])
    return out_dict


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


def read_lut(lut_file, project_id, site_id):
    lut = read_csv(lut_file)
    if site_id is None:
        site_id = ''
    out_lut = {}
    for row, (project, site) in enumerate(zip(lut['Project'], lut['Site'])):
        if is_intstr(site) and is_intstr(site_id):
            site = int(site)
            site_id = int(site_id)
        if site == site_id and project == project_id:
            if lut['InstitutionName'][row] not in out_lut:
                out_lut[lut['InstitutionName'][row]] = {}
            if lut['SeriesDescription'][row] in out_lut[lut['InstitutionName'][row]]:
                raise ValueError('Series description (%s) already exists for site (%04d) and institution name (%s)' %
                                 (lut['SeriesDescription'][row], int(site_id), lut['InstitutionName'][row]))
            out_lut[lut['InstitutionName'][row]][lut['SeriesDescription'][row]] = lut['OutputFilename'][row]
    return out_lut


def check_lut(inst_name, series_desc, lut_obj):
    if inst_name in lut_obj:
        if series_desc in lut_obj[inst_name]:
            if lut_obj[inst_name][series_desc] == 'None':
                return False
            return lut_obj[inst_name][series_desc].split('-')
    return None


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
    logging.info('Unzipping complete.')

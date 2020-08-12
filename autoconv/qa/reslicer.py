# -*- coding: utf-8 -*-
"""
Reslicing functions and classes
"""
import warnings

import nibabel as nib
import numpy as np
from scipy.ndimage import affine_transform


class Reslicer:
    """
    Reslice a NIfTI image

    This class reslices and image to a set resolution and provides as way to
    extract a slice in a specific orientation. It can currently bring the
    image to axial, coronal, and sagittal views.

    Params:
        data (np.ndarray): The Nifti image object from nibabel
        orient (tuple[str]): orientation tuple
    """
    inplane_dirs = {'axial': (('L', 'P'), ('R', 'A')), 'sagittal': (('P', 'I'), ('A', 'S')),
                    'coronal': (('L', 'I'), ('R', 'S'))}
    slice_dirs = {'axial': 'S', 'sagittal': 'L', 'coronal': 'P'}
    flip_dict = {'L': 'R', 'R': 'L', 'P': 'A', 'A': 'P', 'I': 'S', 'S': 'I'}

    def __init__(self, nii_obj, vox_res=1.0, order=0):
        """
        Args:
            nii_obj (nib.Nifti1Image): The Nifti image object from nibabel
            vox_res (float): Resliced object voxel resolution
            order (int, optional): The interpolation order (0 for nearest
                interpolation, 1 for linear interpolation, etc.)
        """
        # noinspection PyTypeChecker
        self.data: np.ndarray = reslice(nii_obj, (vox_res,)*3, order).get_fdata()
        self.orient = nib.aff2axcodes(nii_obj.affine)

    def get_num_slices(self, plane='axial'):
        if self.slice_dirs[plane] in self.orient:
            return self.data.shape[self.orient.index(self.slice_dirs[plane])]
        return self.data.shape[self.orient.index(self.flip_dict[self.slice_dirs[plane]])]

    def get_slice(self, slice_num, plane='axial'):
        slices, dirs = [], []
        for i, code in enumerate(self.orient):
            if code in self.inplane_dirs[plane][0]:
                slices.append(slice(None, None))
                dirs.append(code)
            elif code in self.inplane_dirs[plane][1]:
                slices.append(slice(None, None, -1))
                dirs.append(self.flip_dict[code])
            else:
                if code == self.slice_dirs[plane]:
                    slices.append(slice(slice_num, slice_num + 1))
                else:
                    slices.append(slice(self.data.shape[i] - slice_num - 1,
                                        self.data.shape[i] - slice_num))
        sel_slice = np.squeeze(self.data[tuple(slices)])
        return sel_slice if tuple(dirs) == self.inplane_dirs[plane][0] else sel_slice.T


def reslice(nii_obj, new_zooms, order=0, mode='constant', cval=0):
    # We are suppressing warnings emitted by scipy >= 0.18,
    # described in https://github.com/dipy/dipy/issues/1107.
    # These warnings are not relevant to us, as long as our offset
    # input to scipy's affine_transform is [0, 0, 0]
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message='.*scipy.*18.*',
                                category=UserWarning)
        new_zooms = np.array(new_zooms, dtype='f8')
        zooms = np.array(nii_obj.header.get_zooms(), dtype='f8')[:3]
        R = new_zooms / zooms
        new_shape = zooms / new_zooms * np.array(nii_obj.shape[:3])
        new_shape = tuple(np.round(new_shape).astype('i8'))
        kwargs = {'matrix': R, 'output_shape': new_shape, 'order': order,
                  'mode': mode, 'cval': cval}
        data = nii_obj.get_fdata() if len(nii_obj.shape) == 3 else nib.four_to_three(nii_obj)[0].get_fdata()
        data2 = affine_transform(input=data, **kwargs)
        Rx = np.eye(4)
        Rx[:3, :3] = np.diag(R)
        affine2 = np.dot(nii_obj.affine, Rx)
    return nib.Nifti1Image(data2, affine2, nii_obj.header)

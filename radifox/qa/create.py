import nibabel as nib
import numpy as np
from PIL import Image
from radifox.utils.resize.scipy import resize


def create_qa_image(
    input_filename,
    output_filename,
    axial_slices=(0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7),
    coronal_slices=(0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7),
    sagittal_slices=(0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7),
):
    input_obj = nib.Nifti1Image.load(input_filename)
    reslicer = Reslicer(input_obj)
    max_size = max(reslicer.data.shape)
    slices = [[], [], []]
    for i, (plane, dist_list) in enumerate(
        zip(["axial", "sagittal", "coronal"], [axial_slices, sagittal_slices, coronal_slices])
    ):
        slice_list = np.around(np.array(dist_list) * reslicer.get_num_slices(plane))
        for slice_num in slice_list:
            sel_slice = reslicer.get_slice(int(slice_num), plane)
            pad_width = [
                (
                    int(np.floor((max_size - sel_slice.shape[i]) / 2.0)),
                    int(np.ceil((max_size - sel_slice.shape[i]) / 2.0)),
                )
                for i in range(2)
            ]
            slices[i].append(np.pad(sel_slice, pad_width, "constant"))
    montage = np.concatenate([np.concatenate(slices[i], 0) for i in range(len(slices))], 1)
    montage -= np.min(montage)
    montage = np.array(montage / np.percentile(montage[np.nonzero(montage)], 99.9) * 255.0)
    montage[montage > 255.0] = 255.0
    Image.fromarray(montage.astype(np.ubyte).T).save(output_filename)


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

    inplane_dirs = {
        "axial": (("L", "P"), ("R", "A")),
        "sagittal": (("P", "I"), ("A", "S")),
        "coronal": (("L", "I"), ("R", "S")),
    }
    slice_dirs = {"axial": "S", "sagittal": "L", "coronal": "P"}
    flip_dict = {"L": "R", "R": "L", "P": "A", "A": "P", "I": "S", "S": "I"}

    def __init__(self, nii_obj, vox_res=1.0, order=0):
        """
        Args:
            nii_obj (nib.Nifti1Image): The Nifti image object from nibabel
            vox_res (float): Resliced object voxel resolution
            order (int, optional): The interpolation order (0 for nearest
                interpolation, 1 for linear interpolation, etc.)
        """
        # noinspection PyTypeChecker
        obj_3d = nii_obj if len(nii_obj.shape) == 3 else nib.four_to_three(nii_obj)[0]
        data = obj_3d.get_fdata()
        self.data: np.ndarray = resize(
            data, [vox_res / s for s in obj_3d.header.get_zooms()], order=order
        )
        self.orient = nib.aff2axcodes(nii_obj.affine)

    def get_num_slices(self, plane="axial") -> int:
        if self.slice_dirs[plane] in self.orient:
            return self.data.shape[self.orient.index(self.slice_dirs[plane])]
        return self.data.shape[self.orient.index(self.flip_dict[self.slice_dirs[plane]])]

    def get_slice(self, slice_num, plane="axial") -> np.ndarray:
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
                    slices.append(
                        slice(self.data.shape[i] - slice_num - 1, self.data.shape[i] - slice_num)
                    )
        sel_slice = np.squeeze(self.data[tuple(slices)])
        return sel_slice if tuple(dirs) == self.inplane_dirs[plane][0] else sel_slice.T

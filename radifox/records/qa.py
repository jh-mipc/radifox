import io

import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
import trimesh
from PIL import Image

from .resize import nn_resize_1mmiso
from .utils import get_tkr_matrix

BINARY_LUT = {1: [255, 0, 0]}

BRAIN_COLOR_LUT = {
    4: [0, 15, 247],
    11: [255, 245, 9],
    23: [178, 178, 22],
    30: [255, 255, 98],
    31: [131, 178, 46],
    32: [208, 255, 123],
    35: [255, 9, 245],
    36: [178, 178, 126],
    37: [255, 255, 203],
    38: [178, 96, 81],
    39: [255, 173, 158],
    40: [178, 142, 36],
    41: [255, 218, 112],
    44: [89, 89, 89],
    45: [165, 165, 165],
    47: [146, 178, 32],
    48: [222, 255, 108],
    49: [0, 61, 147],
    50: [76, 137, 224],
    51: [0, 139, 108],
    52: [76, 215, 185],
    53: [190, 0, 0],
    54: [255, 0, 0],
    55: [178, 54, 0],
    56: [255, 131, 76],
    57: [178, 124, 0],
    58: [255, 200, 76],
    59: [173, 0, 0],
    60: [250, 76, 76],
    61: [37, 0, 0],
    62: [113, 76, 76],
    71: [255, 34, 221],
    72: [255, 62, 192],
    73: [255, 91, 163],
    75: [188, 76, 76],
    76: [111, 0, 0],
    100: [102, 178, 75],
    101: [179, 255, 152],
    102: [106, 0, 0],
    103: [182, 76, 76],
    104: [0, 129, 178],
    105: [76, 206, 255],
    106: [34, 178, 143],
    107: [111, 255, 220],
    108: [174, 178, 4],
    109: [250, 255, 80],
    112: [178, 31, 0],
    113: [255, 107, 76],
    114: [178, 155, 0],
    115: [255, 231, 76],
    116: [151, 0, 0],
    117: [227, 76, 76],
    118: [0, 68, 178],
    119: [76, 144, 255],
    120: [0, 0, 170],
    121: [76, 76, 246],
    122: [135, 0, 0],
    123: [212, 76, 76],
    124: [0, 0, 112],
    125: [76, 76, 188],
    128: [178, 141, 0],
    129: [255, 218, 76],
    132: [166, 0, 0],
    133: [243, 76, 76],
    134: [178, 168, 0],
    135: [255, 245, 76],
    136: [0, 143, 178],
    137: [76, 220, 255],
    138: [89, 178, 89],
    139: [165, 255, 165],
    140: [0, 0, 97],
    141: [76, 76, 173],
    142: [0, 3, 178],
    143: [76, 79, 255],
    144: [178, 100, 0],
    145: [255, 176, 76],
    146: [0, 115, 178],
    147: [76, 192, 255],
    148: [0, 168, 178],
    149: [76, 245, 255],
    150: [0, 15, 178],
    151: [76, 92, 255],
    152: [0, 0, 127],
    153: [76, 76, 204],
    154: [178, 89, 0],
    155: [255, 165, 76],
    156: [160, 178, 17],
    157: [237, 255, 94],
    160: [178, 127, 0],
    161: [255, 204, 76],
    162: [0, 85, 178],
    163: [76, 162, 255],
    164: [0, 42, 178],
    165: [76, 119, 255],
    166: [76, 178, 101],
    167: [153, 255, 178],
    168: [0, 155, 178],
    169: [76, 232, 255],
    170: [119, 0, 0],
    171: [196, 76, 76],
    172: [94, 0, 0],
    173: [171, 76, 76],
    174: [63, 178, 115],
    175: [139, 255, 191],
    176: [48, 178, 129],
    177: [125, 255, 206],
    178: [0, 101, 178],
    179: [76, 178, 255],
    180: [178, 66, 0],
    181: [255, 142, 76],
    182: [0, 30, 178],
    183: [76, 107, 255],
    184: [178, 14, 0],
    185: [255, 90, 76],
    186: [117, 178, 61],
    187: [193, 255, 137],
    190: [0, 0, 157],
    191: [76, 76, 233],
    192: [0, 0, 143],
    193: [76, 76, 219],
    194: [20, 178, 158],
    195: [96, 255, 234],
    196: [178, 114, 0],
    197: [255, 190, 76],
    198: [5, 178, 173],
    199: [81, 255, 249],
    200: [178, 79, 0],
    201: [255, 156, 76],
    202: [178, 1, 0],
    203: [255, 77, 76],
    204: [0, 53, 178],
    205: [76, 130, 255],
    206: [178, 48, 0],
    207: [255, 125, 76],
}

COLORBLIND_LUT = {
    1: [229, 159, 1],
    2: [86, 180, 232],
    3: [0, 159, 115],
    4: [240, 228, 55],
    5: [0, 114, 177],
    6: [213, 94, 0],
    7: [204, 121, 167],
    8: [160, 111, 1],
    9: [60, 126, 162],
    10: [0, 111, 81],
    11: [168, 160, 46],
    12: [0, 80, 124],
    13: [149, 66, 0],
    14: [143, 85, 117],
}

luts = {"binary": BINARY_LUT, "brain_color": BRAIN_COLOR_LUT, "colorblind": COLORBLIND_LUT}


def create_montage(img_obj, axial_slices, coronal_slices, sagittal_slices):
    reslicer = Reslicer(img_obj)
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
            slices[i].append(
                np.pad(sel_slice, pad_width, "constant", constant_values=reslicer.bg_value)
            )
    return np.concatenate([np.concatenate(slices[i], 0) for i in range(len(slices))], 1)


def create_qa_image(
    input_filename,
    output_filename,
    overlay_filename=None,
    overlay_lut="binary",
    axial_slices=(0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7),
    coronal_slices=(0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7),
    sagittal_slices=(0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7),
    alpha=0.4,
):
    input_obj = nib.load(input_filename)
    base_img = create_montage(input_obj, axial_slices, coronal_slices, sagittal_slices)
    base_img -= np.min(base_img)
    base_img = np.array(base_img / np.percentile(base_img, 99.9) * 255.0)
    base_img[base_img > 255.0] = 255.0
    base_img = base_img.astype(np.ubyte).T

    if overlay_filename is not None:
        overlay_obj = nib.load(overlay_filename)
        overlay_img = (
            create_montage(overlay_obj, axial_slices, coronal_slices, sagittal_slices)
            .astype(np.ubyte)
            .T
        )
        lut = np.zeros((256, 3))
        for k, v in luts[overlay_lut].items():
            lut[k, :] = v
        colored_overlay = np.zeros(overlay_img.shape + (3,))
        for i in range(3):
            colored_overlay[overlay_img > 0, i] = np.take(lut[:, i], overlay_img[overlay_img > 0])
        base_img = np.repeat(base_img[:, :, np.newaxis], 3, axis=2)
        base_img = ((colored_overlay * alpha) + (base_img * (1 - alpha))).astype(np.ubyte)

    Image.fromarray(base_img).save(output_filename)


class Reslicer:
    """
    Reslice a NIfTI image

    This class reslices and image to a set resolution using nearest neighbor interpolation
    and provides as way to extract a slice in a specific orientation. It can currently bring the
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

    def __init__(self, nii_obj):
        """
        Args:
            nii_obj (nib.Nifti1Image): The Nifti image object from nibabel
        """
        # noinspection PyTypeChecker
        obj_3d = nii_obj if len(nii_obj.shape) == 3 else nib.four_to_three(nii_obj)[0]
        self.data = nn_resize_1mmiso(obj_3d)
        self.orient = nib.aff2axcodes(nii_obj.affine)
        self.bg_value = self.data.min()

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


def create_surface_qa_image(
    surf_file,
    img_file,
    output_file,
    color="red",
    axial_slices=(0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7),
    coronal_slices=(0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7),
    sagittal_slices=(0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7),
):
    linewidth = 0.5
    if color == "binary":
        linecolor = "red"
    if isinstance(color, (list, tuple)):
        linecolor = color[0]
        linewidth = color[1]
    else:
        linecolor = color
    img_obj = nib.Nifti1Image.load(img_file)
    img_data = img_obj.get_fdata()
    # noinspection PyUnresolvedReferences
    tk = get_tkr_matrix(img_obj.shape, img_obj.header.get_zooms())

    surf_obj = nib.GiftiImage.load(surf_file)
    mesh = trimesh.Trimesh(*surf_obj.agg_data(("pointset", "triangle")))
    # noinspection PyUnresolvedReferences
    mesh.vertices = nib.affines.apply_affine(np.linalg.inv(tk), mesh.vertices)

    directions = ["axial", "sagittal", "coronal"]
    axes = {"sagittal": 0, "coronal": 1, "axial": 2}
    slice_levels = {"axial": axial_slices, "sagittal": sagittal_slices, "coronal": coronal_slices}

    slice_arrs = []
    for direction in directions:
        size = img_data.shape[axes[direction]]
        slices = np.rint(np.array(slice_levels[direction]) * size).astype(int)
        for i, slice_idx in enumerate(slices):
            if direction == "sagittal":
                slice_arrs.append(img_data[slice_idx, :, ::-1].ravel())
            elif direction == "coronal":
                slice_arrs.append(img_data[:, slice_idx, ::-1].ravel())
            else:  # 'axial'
                slice_arrs.append(img_data[:, :, slice_idx].ravel())
    slice_arr = np.concatenate(slice_arrs, axis=0)
    img_data -= slice_arr.min()
    img_data = np.array(img_data / np.percentile(slice_arr, 99.9) * 255.0)
    img_data[img_data > 255.0] = 255.0
    img_data = img_data.astype(np.ubyte)

    imgs = []
    for d, direction in enumerate(directions):
        imgs.append([])
        size = img_data.shape[axes[direction]]
        slices = np.rint(np.array(slice_levels[direction]) * size).astype(int)
        if direction == "sagittal":
            plane_normal = [1, 0, 0]
            adding = [192, 0]
        elif direction == "coronal":
            plane_normal = [0, 1, 0]
            adding = [192, 176]
        else:
            plane_normal = [0, 0, 1]
            adding = [16, 0]
        sections = mesh.section_multiplane(
            plane_origin=[0, 0, 0],
            plane_normal=plane_normal,
            heights=slices,
        )

        for i, slice_idx in enumerate(slices):
            fig = plt.figure(frameon=False, figsize=(224 / 72, 224 / 72), dpi=72)
            ax = plt.Axes(fig, [0.0, 0.0, 1.0, 1.0])
            ax.set_axis_off()
            fig.add_axes(ax)

            if direction == "sagittal":
                slice_data = img_data[slice_idx, :, ::-1]
                extent = (0, img_data.shape[1], 16, img_data.shape[2] + 16)
            elif direction == "coronal":
                slice_data = img_data[:, slice_idx, ::-1]
                extent = (16, img_data.shape[0] + 16, 16, img_data.shape[2] + 16)
            else:  # 'axial'
                slice_data = img_data[:, :, slice_idx]
                extent = (16, img_data.shape[0] + 16, 0, img_data.shape[1])

            # Plot the slice with the correct extent
            ax.imshow(np.zeros((224, 224)), extent=(0, 224, 0, 224), cmap="gray")
            ax.imshow(slice_data.T, extent=extent, cmap="gray")

            # Find intersections
            if sections[i] is not None:
                # noinspection PyTypeChecker
                for points in sections[i].discrete:
                    points[:, 0] += adding[0]
                    points[:, 1] += adding[1]
                    if direction in ["sagittal", "coronal"]:
                        points = points[:, ::-1]
                        points[:, 1] = img_data.shape[2] - points[:, 1] + 16
                        if direction == "coronal":
                            points[:, 0] = img_data.shape[0] - points[:, 0]
                    else:
                        points[:, 1] = img_data.shape[1] - points[:, 1]
                    ax.plot(*points.T, color=linecolor, linewidth=linewidth)
            buf = io.BytesIO()
            fig.savefig(buf, format="png")
            buf.seek(0)
            imgs[d].append(np.array(Image.open(buf)))
            buf.close()
            plt.close(fig)
    montage = np.concatenate([np.concatenate(img_dir, 1) for img_dir in imgs], 0)
    montage_im = Image.fromarray(montage)
    montage_im.save(output_file)

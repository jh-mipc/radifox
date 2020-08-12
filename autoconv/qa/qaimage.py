import nibabel as nib
import numpy as np
from PIL import Image

from .reslicer import Reslicer


def create_qa_image(input_filename, output_filename,
                    axial_slices=(0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7),
                    coronal_slices=(0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7),
                    sagittal_slices=(0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7)):
    input_obj = nib.load(input_filename)
    reslicer = Reslicer(input_obj)
    max_size = max(reslicer.data.shape)
    slices = [[], [], []]
    for i, (plane, dist_list) in enumerate(zip(['axial', 'sagittal', 'coronal'],
                                               [axial_slices, sagittal_slices, coronal_slices])):
        slice_list = np.around(np.array(dist_list) * reslicer.get_num_slices(plane))
        for slice_num in slice_list:
            sel_slice = reslicer.get_slice(int(slice_num), plane)
            pad_width = [(int(np.floor((max_size - sel_slice.shape[i])/2.0)),
                          int(np.ceil((max_size - sel_slice.shape[i])/2.0))) for i in range(2)]
            slices[i].append(np.pad(sel_slice, pad_width, 'constant'))
    montage = np.concatenate([np.concatenate(slices[i], 0) for i in range(len(slices))], 1)
    montage += np.min(montage)
    montage = np.array(montage / np.percentile(montage[np.nonzero(montage)], 99.9) * 255.0)
    montage[montage > 255.0] = 255.0
    Image.fromarray(montage.astype(np.ubyte).T).save(output_filename)

"""This is code derived from radifox-utils/radifox/utils/resize/scipy.py v1.0.2 (03a716d)
The source code can be found at https://github.com/jh-mipc/radifox-utils
"""
import numpy as np
from scipy.ndimage import map_coordinates


def nn_resize_1mmiso(img_obj):
    # Extract image data
    data = img_obj.get_fdata()

    # Calculate the scaling factors for each dimension
    scaling_factors = [1.0 / zoom for zoom in img_obj.header.get_zooms()]

    # Compute the new shape based on the scaling factors
    new_shape = tuple(int(round(dim / scale)) for dim, scale in zip(img_obj.shape, scaling_factors))

    # Define the original bounds of the image
    original_bounds_start = (-0.5,) * len(data.shape)
    original_bounds_end = tuple(start + dim for start, dim in zip(original_bounds_start, img_obj.shape))

    # Calculate the original and new sizes
    original_size = [end - start for start, end in zip(original_bounds_start, original_bounds_end)]
    new_size = [dim * scale for dim, scale in zip(new_shape, scaling_factors)]

    # Calculate the size differences
    size_diff = [(orig - new) / 2 for orig, new in zip(original_size, new_size)]

    # Adjust the bounds to account for the size differences
    adjusted_bounds_start = tuple(start + diff for start, diff in zip(original_bounds_start, size_diff))
    adjusted_bounds_end = tuple(end - diff for end, diff in zip(original_bounds_end, size_diff))

    # Generate coordinates for the new grid
    coords = []
    for start, end, scale in zip(adjusted_bounds_start, adjusted_bounds_end, scaling_factors):
        coords.append(np.arange(start + scale / 2, end - scale / 4, scale))
    coords = np.meshgrid(*coords, indexing="ij")
    coords = np.array([coord.flatten() for coord in coords])

    # Perform the nearest-neighbor interpolation
    resized_data = map_coordinates(data, coords, mode="nearest", order=0)

    # Reshape the result to the new shape
    return resized_data.reshape(new_shape)

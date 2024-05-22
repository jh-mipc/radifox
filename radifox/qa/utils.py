import nibabel as nib
import numpy as np


def get_tkr_matrix(shape, zooms):
    tkrcosines = np.array([[-1, 0, 0], [0, 0, 1], [0, -1, 0]])
    mat = tkrcosines * zooms
    # noinspection PyUnresolvedReferences
    return nib.affines.from_matvec(mat, -mat @ shape / 2)

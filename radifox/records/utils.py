import datetime
import fcntl

import nibabel as nib
import numpy as np


def safe_append_to_file(filename, data):
    with open(filename, 'a') as file:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX)  # Exclusive lock
        file.write(data)
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)  # Release lock


def format_timedelta(delta: datetime.timedelta) -> str:
    # Extracting days and seconds
    days = delta.days
    seconds = delta.seconds

    # Converting seconds to hours, minutes, and seconds
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60

    # return formatted string
    return f"{days}-{hours:02}:{minutes:02}:{seconds:02}"


def get_tkr_matrix(shape, zooms):
    tkrcosines = np.array([[-1, 0, 0], [0, 0, 1], [0, -1, 0]])
    mat = tkrcosines * zooms
    # noinspection PyUnresolvedReferences
    return nib.affines.from_matvec(mat, -mat @ shape / 2)

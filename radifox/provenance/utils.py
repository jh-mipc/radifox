import fcntl
import msvcrt
import os


def append_to_file_unix(filename, data):
    with open(filename, 'a') as file:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX)  # Exclusive lock
        file.write(data)
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)  # Release lock


def append_to_file_windows(filename, data):
    with open(filename, 'a') as file:
        msvcrt.locking(file.fileno(), msvcrt.LK_LOCK, 1)  # Lock the file
        file.write(data)
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)  # Unlock the file


def safe_append_to_file(filename, data):
    if os.name == 'posix':  # Unix-based system
        append_to_file_unix(filename, data)
    else:  # Windows system
        append_to_file_windows(filename, data)

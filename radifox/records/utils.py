import fcntl


def safe_append_to_file(filename, data):
    with open(filename, 'a') as file:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX)  # Exclusive lock
        file.write(data)
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)  # Release lock

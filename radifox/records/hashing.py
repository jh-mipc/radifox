import hashlib
from pathlib import Path


def hash_file(
    filename: Path,
    include_names: bool = True,
    hashfunc: str = "sha256",
    *,
    _bufsize=2**18,
) -> str:
    hashobj = hashlib.new(hashfunc)
    if include_names:
        hashobj.update(filename.name.encode())
    with filename.open("rb") as fp:
        buf = bytearray(_bufsize)  # Reusable buffer to reduce allocations.
        view = memoryview(buf)
        while True:
            # noinspection PyUnresolvedReferences
            size = fp.readinto(buf)
            if size == 0:
                break  # EOF
            hashobj.update(view[:size])
    return str(hashobj.hexdigest())


def hash_dir(directory, include_names: bool = True, hashfunc: str = "sha256") -> str:
    hashobj = hashlib.new(hashfunc)
    for path in sorted(directory.iterdir(), key=lambda p: str(p).lower()):
        hashobj.update(hash_file_dir(path, include_names, hashfunc).encode())
    if include_names:
        hashobj.update(directory.name.encode())
    return str(hashobj.hexdigest())


def hash_file_dir(file_dir: Path, include_names: bool = True, hashfunc: str = "sha256") -> str:
    if file_dir.is_file():
        return hash_file(file_dir, include_names=include_names, hashfunc=hashfunc)
    elif file_dir.is_dir():
        return hash_dir(file_dir, include_names=include_names, hashfunc=hashfunc)


def hash_file_list(
    file_list: list[Path], include_names: bool = True, hashfunc: str = "sha256"
) -> str:
    hashobj = hashlib.new(hashfunc)
    for path in file_list:
        hashobj.update(hash_file(path, include_names, hashfunc).encode())
    return str(hashobj.hexdigest())


def hash_value(value: str | None, hashfunc: str = "sha256") -> str | None:
    if value is None:
        return None
    m = hashlib.new(hashfunc)
    m.update(value.encode())
    return str(m.hexdigest())

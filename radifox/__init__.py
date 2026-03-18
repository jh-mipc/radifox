try:
    from importlib.metadata import PackageNotFoundError, version
except ImportError:
    from importlib_metadata import PackageNotFoundError, version

try:
    __version__ = version("radifox")
except PackageNotFoundError:
    try:
        from ._version import __version__
    except (ImportError, AttributeError, ModuleNotFoundError):
        __version__ = "0+unknown"

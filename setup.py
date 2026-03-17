from setuptools import setup


def get_version_and_cmdclass():
    """Load version metadata from the package's _version.py file."""
    import os
    from importlib.util import module_from_spec, spec_from_file_location

    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    pyproject_path = "pyproject.toml"
    if not os.path.exists(pyproject_path):
        raise FileNotFoundError(
            "pyproject.toml not found. Please use pyproject.toml to define setup."
        )

    with open(pyproject_path, "rb") as f:
        pyproject_data = tomllib.load(f)

    pkg_path = pyproject_data.get("miniver", {}).get("package_path")
    if not pkg_path:
        pkg_path = pyproject_data.get("project", {}).get("name", "")

    version_file = os.path.join(pkg_path, "_version.py")
    if not os.path.exists(version_file):
        raise FileNotFoundError(
            "_version.py not found. Specify miniver.package_path in pyproject.toml."
        )

    spec = spec_from_file_location("version", version_file)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.__version__, module.get_cmdclass(pkg_path)


__version__, cmdclass = get_version_and_cmdclass()

setup(
    version=__version__,
    cmdclass=cmdclass,
)
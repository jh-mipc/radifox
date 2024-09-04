from setuptools import setup


def get_version_and_cmdclass():
    """Load version.py module without importing the whole package.

    Template code from miniver altered to use pyproject.toml
    """
    import os
    from importlib.util import module_from_spec, spec_from_file_location

    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    if not os.path.exists(os.path.join("pyproject.toml")):
        raise FileNotFoundError("pyproject.toml not found. "
                                "Please use pyproject.toml to define setup.")

    with open("pyproject.toml", "rb") as f:
        pyproject_data = tomllib.load(f)

    pkg_path = pyproject_data.get("miniver", {}).get("package_path")
    if pkg_path is None:
        pkg_path = pyproject_data.get("project", {}).get("name", "")

    if not os.path.exists(os.path.join(pkg_path, "_version.py")):
        raise FileNotFoundError("_version.py not found. "
                                "Specify miniver.package_path in pyproject.toml.")

    spec = spec_from_file_location("version", os.path.join(pkg_path, "_version.py"))
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.__version__, module.get_cmdclass(pkg_path)


__version__, cmdclass = get_version_and_cmdclass()


setup(
    version=__version__,
    cmdclass=cmdclass,
)

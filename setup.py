from pathlib import Path
from setuptools import setup, find_packages

__package_name__ = "radifox"


def get_version_and_cmdclass(pkg_path):
    """Load version.py module without importing the whole package.

    Template code from miniver
    """
    import os
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("version", os.path.join(pkg_path, "_version.py"))
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.__version__, module.get_cmdclass(pkg_path)


__version__, cmdclass = get_version_and_cmdclass(__package_name__)

setup(
    name=__package_name__,
    version=__version__,
    description=(
        "RADIFOX is the RADiological Image File Ontology eXtension, "
        "a Python package for the organization and management of medical images."
    ),
    long_description=(Path(__file__).parent.resolve() / "README.md").read_text(),
    long_description_content_type="text/markdown",
    author="Blake Dewey",
    author_email="blake.dewey@jhu.edu",
    url="https://github.com/jh-mipc/radifox",
    license="Apache License, 2.0",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3.7",
        "Topic :: Scientific/Engineering",
    ],
    packages=find_packages(),
    keywords="medical imaging reproducible organization",
    entry_points={
        "console_scripts": [
            "radifox-qa=radifox.qa.run:run",
            "radifox-stage=radifox.modules.staging:Staging",
        ]
    },
    python_requires=">=3.10",
    install_requires=[
        "nibabel",
        "numpy",
        "pillow",
        "pyyaml",
        "scipy",
        "matplotlib",
        "trimesh",
        "networkx",
    ],
    extras_require={
        "qa": [
            "flask",
            "gunicorn",
        ]
    },
    package_data={
        "radifox": [
            "conversion/parrec_templates/*.txt",
            "qa/templates/*.html",
        ]
    },
    cmdclass=cmdclass,
)

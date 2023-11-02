from setuptools import setup, find_packages

__package_name__ = "autoconv"


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
    description="Automatic conversion process for MRI data",
    long_description="Automatic conversion process for MRI data",
    author='Blake Dewey',
    author_email='blake.dewey@jhu.edu',
    url='https://gitlab.com/iacl/autoconv',
    license='Apache License, 2.0',
    classifiers=[
      'Development Status :: 3 - Alpha',
      'Environment :: Console',
      'Intended Audience :: Science/Research',
      'License :: OSI Approved :: Apache Software License',
      'Programming Language :: Python :: 3.7',
      'Topic :: Scientific/Engineering'
    ],
    packages=find_packages(),
    keywords="mri conversion",
    entry_points={
      'console_scripts': [
          'autoconv-convert=autoconv.cli:convert',
          'autoconv-update=autoconv.cli:update',
      ]
    },
    python_requires='>=3.8.2',
    install_requires=[
      'nibabel',
      'pydicom',
      'numpy',
      'pillow',
      'scipy',
    ],
    package_data={'autoconv': ['parrec_templates/*.txt']},
    cmdclass=cmdclass,
)

from pathlib import Path
from setuptools import setup, find_packages
from shutil import which

# Code from Nipype (modified by Blake Dewey) #####
# Commit hash writing, and dependency checking
from setuptools.command.build_py import build_py

pkg_path = Path(__file__).parent
# Python 3: use a locals dictionary
# http://stackoverflow.com/a/1463370/6820620
ldict = locals()
# Get version and release info, which is all stored in nipype/info.py
ver_file = Path(pkg_path, 'autoconv', 'info.py')
commit_file = Path(pkg_path, 'COMMIT_INFO.txt')
with ver_file.open() as info_fp:
    exec(info_fp.read(), globals(), ldict)
__version__ = ldict['__version__']


class BuildWithCommitInfoCommand(build_py):
    """ Return extended build command class for recording commit
    The extended command tries to run git to find the current commit, getting
    the empty string if it fails.  It then writes the commit hash into a file
    in the `pkg_dir` path, named ``COMMIT_INFO.txt``.
    In due course this information can be used by the package after it is
    installed, to tell you what commit it was installed from if known.
    To make use of this system, you need a package with a COMMIT_INFO.txt file -
    e.g. ``myproject/COMMIT_INFO.txt`` - that might well look like this::
        # This is an ini file that may contain information about the code state
        [commit hash]
        # The line below may contain a valid hash if it has been substituted during 'git archive'
        archive_subst_hash=$Format:%h$
        # This line may be modified by the install process
        install_hash=
    The COMMIT_INFO file above is also designed to be used with git substitution
    - so you probably also want a ``.gitattributes`` file in the root directory
    of your working tree that contains something like this::
       myproject/COMMIT_INFO.txt export-subst
    That will cause the ``COMMIT_INFO.txt`` file to get filled in by ``git
    archive`` - useful in case someone makes such an archive - for example with
    via the github 'download source' button.
    Although all the above will work as is, you might consider having something
    like a ``get_info()`` function in your package to display the commit
    information at the terminal.  See the ``pkg_info.py`` module in the nipy
    package for an example.
    """
    def run(self):
        from subprocess import check_output, CalledProcessError
        # noinspection PyCompatibility
        import configparser

        build_py.run(self)
        repo_commit = b''
        if which('git'):
            try:
                repo_commit = check_output(['git', 'rev-parse', '--short', 'HEAD'])
            except CalledProcessError:
                pass

        # We write the installation commit even if it's empty
        cfg_parser = configparser.RawConfigParser()
        cfg_parser.read(Path(pkg_path, 'COMMIT_INFO.txt'))
        cfg_parser.set('commit hash', 'install_hash', repo_commit.decode().strip())
        out_pth = Path(self.build_lib, 'autoconv', 'COMMIT_INFO.txt')
        with out_pth.open('wt') as out_fp:
            cfg_parser.write(out_fp)
# End code from Nipype #####


setup(
    name='autoconv',
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
          'autoconv=autoconv.exec:cli'
      ]
    },
    install_requires=[
      'nibabel',
      'pydicom',
      'numpy',
      'click',
    ],
    package_data={'autoconv': ['parrec_templates/*.txt']},
    cmdclass={'build_py': BuildWithCommitInfoCommand},
)

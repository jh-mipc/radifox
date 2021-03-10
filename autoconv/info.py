# Versioning code from Nipype (modified by Blake Dewey) #
from pathlib import Path
from subprocess import check_output, CalledProcessError
from shutil import which
import configparser


COMMIT_INFO_FNAME = 'COMMIT_INFO.txt'


def pkg_commit_hash(pkg_path: Path):
    """ Get short form of commit hash given directory `pkg_path`
    There should be a file called 'COMMIT_INFO.txt' in `pkg_path`.  This is a
    file in INI file format, with at least one section: ``commit hash`` and two
    variables ``archive_subst_hash`` and ``install_hash``.  The first has a
    substitution pattern in it which may have been filled by the execution of
    ``git archive`` if this is an archive generated that way.  The second is
    filled in by the installation, if the installation is from a git archive.
    We get the commit hash from (in order of preference):
    * A substituted value in ``archive_subst_hash``
    * A written commit hash value in ``install_hash`
    * git's output, if we are in a git repository
    If all these fail, we return a not-found placeholder tuple
    Parameters
    ----------
    pkg_path : str
       directory containing package
    Returns
    -------
    hash_from : str
       Where we got the hash from - description
    hash_str : str
       short form of hash
    """
    # Try and get commit from written commit text file
    pth = pkg_path / COMMIT_INFO_FNAME
    if not pth.is_file():
        raise IOError('Missing commit info file %s' % pth)
    cfg_parser = configparser.RawConfigParser()
    with pth.open(encoding='utf-8') as fp:
        cfg_parser.read_file(fp)
    archive_subst = cfg_parser.get('commit hash', 'archive_subst_hash')
    if not archive_subst.startswith('$Format'):  # it has been substituted
        return 'archive substitution', archive_subst
    install_subst = cfg_parser.get('commit hash', 'install_hash')
    if install_subst != '':
        return 'installation', install_subst
    # maybe we are in a repository
    if which('git'):
        try:
            # noinspection PyTypeChecker
            repo_commit = check_output(['git', 'rev-parse', '--short', 'HEAD'], cwd=pkg_path)
            if repo_commit:
                return 'repository', repo_commit.decode().strip()
        except CalledProcessError:
            pass
    return '(none found)', '<not found>'


_version_major = 0
_version_minor = 3
_version_micro = 3
_version_extra = ''  # Remove -dev for release

if '-dev' in _version_extra:
    src, hsh = pkg_commit_hash(Path(__file__).parent)
    if src == 'repository':
        _version_extra = '-dev+' + hsh
    elif src == 'installation':
        _version_extra = '-dev+' + hsh

# Format expected by setup.py and doc/source/conf.py: string of form 'X.Y.Z'
__version__ = '%s.%s.%s%s' % (_version_major,
                              _version_minor,
                              _version_micro,
                              _version_extra)
# End code from Nipype #

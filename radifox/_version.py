from pathlib import Path


def get_version() -> str:
    """
    Return the best available version string.

    Resolution order:
    1. Live Git checkout
    2. Git archival metadata
    3. Generated static version file
    4. Fallback constant
    """
    package_root = Path(__file__).resolve().parent

    version = _version_from_git(package_root)
    if version is not None:
        return version

    version = _version_from_git_archive(package_root)
    if version is not None:
        return version

    version = _version_from_static()
    if version is not None:
        return version

    return "0+unknown"


def _version_from_git(package_root: Path) -> str | None:
    # git describe --first-parent does not take into account tags from branches
    # that were merged-in. The '--long' flag gets us the 'dev' version and
    # git hash, '--always' returns the git hash even if there are no tags.
    import subprocess

    for opts in [["--first-parent"], []]:
        try:
            p = subprocess.Popen(
                ["git", "describe", "--long", "--always", "--tags", "--dirty"] + opts,
                cwd=package_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError:
            return None
        if p.wait() == 0:
            break
    else:
        return None

    description = (
        p.communicate()[0]
        .decode()
        .lstrip("v")  # Tags can have a leading 'v', but the version should not
        .rstrip("\n")
        .rsplit("-")  # Split the latest tag, commits since tag, and hash
    )

    try:
        release, dev, git = description[:3]
    except ValueError:  # No tags, only the git hash
        # prepend 'g' to match with format returned by 'git describe'
        git = "g{}".format(*description)
        release = "unknown"
        dev = None

    labels = []
    if dev == "0":
        dev = None
    else:
        labels.append(git)

    if description[-1] == "dirty":
        labels.append("dirty")

    return pep440_format(release, dev, labels)


def _version_from_git_archive(package_root: Path) -> str | None:
    import json
    import re

    archival_path = package_root / ".git_archival.json"
    if not archival_path.exists():
        return None

    try:
        data = json.loads(archival_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    tag = data.get("describe")
    commit = data.get("commit")

    if not tag or not commit:
        return None

    if tag.startswith("$Format:") or commit.startswith("$Format:"):
        return None

    tag_match = re.fullmatch(r"v?(\d+\.\d+\.\d+)", tag)
    if tag_match:
        return pep440_format(tag_match.group(1), None, None)

    tag_match = re.fullmatch(r"v?(\d+\.\d+\.\d+)-(\d+)-g([0-9a-f]+)", tag)
    if tag_match:
        release, dev, git = tag_match.groups()
        labels = [] if dev == "0" else [f"g{git}"]
        return pep440_format(release, None if dev == "0" else dev, labels)
    
    return pep440_format("unknown", dev=None, labels=["g{}".format(commit[:7])])


def _version_from_static() -> str | None:
    try:
        from ._static_version import version as static_version
    except ImportError:
        return None

    return static_version or None


def pep440_format(release: str, dev: str | None, labels: list[str] | None) -> str:
    if release.startswith("v"):
        release = release[1:]
    version_parts = [release]
    if dev:
        if release.endswith("-dev") or release.endswith(".dev"):
            version_parts.append(dev)
        else:  # prefer PEP440 over strict adhesion to semver
            version_parts.append(".dev{}".format(dev))

    if labels:
        version_parts.append("+")
        version_parts.append(".".join(labels))

    return "".join(version_parts)


def get_cmd_class():
    from setuptools.command.build_py import build_py as _build_py
    from setuptools.command.sdist import sdist as _sdist
    
    def write_static_version(version: str) -> None:
        (Path(__file__).resolve().parent / "_static_version.py").write_text(
            "# This file is auto-generated at build time.\n"
            f'version = "{version}"\n',
            encoding="utf-8",
        )
    
    class build_py(_build_py):
        def run(self):
            write_static_version(get_version())
            super().run()
    
    class sdist(_sdist):
        def run(self):
            write_static_version(get_version())
            super().run()
    
    return {"build_py": build_py, "sdist": sdist}

_cmdclass = get_cmd_class()
build_py_cls = _cmdclass["build_py"]
sdist_cls = _cmdclass["sdist"]
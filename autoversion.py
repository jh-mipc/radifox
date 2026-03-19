from importlib import import_module
from pathlib import Path

from setuptools.command.build_py import build_py as _build_py
from setuptools.command.sdist import sdist as _sdist


def _version_module(dist):
    packages = dist.packages or []
    candidates = sorted(
        pkg for pkg in packages
        if pkg.endswith("._version") is False
    )

    # Prefer the shortest declared package path
    if candidates:
        pkg = sorted(candidates, key=lambda p: (p.count("."), p))[0]
    else:
        pkg = dist.get_name().replace("-", "_")

    return import_module(f"{pkg}._version")


def _write_static_version(dist) -> None:
    mod = _version_module(dist)
    version = mod.get_version()
    path = Path(mod.__file__).resolve().parent / "_static_version.py"
    path.write_text(
        "# This file is auto-generated at build time.\n"
        f'version = "{version}"\n',
        encoding="utf-8",
    )
    

class build_py(_build_py):
    def run(self):
        _write_static_version(self.distribution)
        super().run()


class sdist(_sdist):
    def run(self):
        _write_static_version(self.distribution)
        super().run()
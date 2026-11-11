"""Empties a directory, keeping it: the old Node.js before another one unpacks into ``node``.

Run by the install plan as ``{host.python} empty_dir.py {component.node}``
with ``node`` as its working directory, which Windows does not let a
process remove; a directory that is not there is not an error.

A Node.js holding global packages beyond its own npm and corepack is
someone's, not one this extension unpacked: it is refused, and nothing is
emptied.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

NODE_OWN_PACKAGES = {"npm", "corepack"}


def main(argv: list[str]) -> int:
    """Empties each directory named in ``argv``; returns the exit code."""
    directories = [Path(name) for name in argv if Path(name).is_dir()]
    for directory in directories:
        if packages := global_packages(directory):
            print(
                f"empty_dir: {directory} holds global npm packages ({', '.join(packages)}); not emptying it",
                file=sys.stderr,
            )
            return 1
    for directory in directories:
        for entry in directory.iterdir():
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                entry.unlink()
    return 0


def global_packages(directory: Path) -> list[str]:
    """The packages in a Node.js at ``directory`` (Windows' layout or the others') that Node.js does not ship."""
    found: list[str] = []
    for packages in (directory / "node_modules", directory / "lib" / "node_modules"):
        try:
            names = sorted(entry.name for entry in packages.iterdir())
        except OSError:
            continue
        found += [name for name in names if not name.startswith(".") and name not in NODE_OWN_PACKAGES]
    return found


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

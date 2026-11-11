"""Empties a directory, keeping it: the old Node.js before another one unpacks into ``node``.

Run by the install plan as ``{host.python} empty_dir.py {component.node}``
with ``node`` as its working directory, which Windows does not let a
process remove; a directory that is not there is not an error.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    """Empties each directory named in ``argv``; returns the exit code."""
    for name in argv:
        directory = Path(name)
        if not directory.is_dir():
            continue
        for entry in directory.iterdir():
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                entry.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

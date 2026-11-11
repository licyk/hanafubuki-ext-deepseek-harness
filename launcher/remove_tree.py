"""Removes a directory and everything in it: an update's old Node.js before the new one unpacks.

Run by the install plan as ``{host.python} remove_tree.py {component.node}``;
a directory that is not there is not an error.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    """Removes each directory named in ``argv``."""
    for name in argv:
        target = Path(name)
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""dsh's homes: the instance's own folders, and copying the user's into them.

An instance's dsh keeps its profiles, credentials and sessions in
``<root>/dsh-home`` and its shared agent configuration in
``<root>/agents-home`` (``DSH_HOME``, ``DSH_AGENTS_HOME`` in
``types/dsh.toml``) unless its ``home`` is ``user``. A new instance so
starts without the login of a dsh the user ran before; copying the user's
``~/.dsh`` and ``~/.agents`` in brings it over. A copy never moves, and
never replaces a file the instance's home already has.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

DSH_HOME = "dsh-home"
AGENTS_HOME = "agents-home"


@dataclass(frozen=True)
class Copy:
    """One folder to copy: the user's, and the instance's it goes into."""

    source: Path
    target: Path


def user_homes(user: Path | None = None) -> list[Copy]:
    """What dsh shares by default (``~/.dsh``, ``~/.agents``), paired with an instance root's folder names."""
    base = user if user is not None else Path.home()
    return [Copy(base / ".dsh", Path(DSH_HOME)), Copy(base / ".agents", Path(AGENTS_HOME))]


def copies(root: Path, user: Path | None = None) -> list[Copy]:
    """The user's homes that exist, each with where it goes below ``root``."""
    return [Copy(entry.source, root / entry.target) for entry in user_homes(user) if entry.source.is_dir()]


def copy_missing(source: Path, target: Path) -> tuple[int, int]:
    """Copies every file of ``source`` that ``target`` lacks; returns how many were copied and skipped.

    Links are copied as links, never followed, so a link to a large folder
    outside the home stays a link. An entry that cannot be copied (a link
    where Windows grants no right to make one, a file in use) is skipped,
    so the rest still arrives.
    """
    copied = skipped = 0
    for directory, folders, files in os.walk(source):
        here = Path(directory)
        there = target / here.relative_to(source)
        there.mkdir(parents=True, exist_ok=True)
        for name in [*files, *(folder for folder in folders if (here / folder).is_symlink())]:
            destination = there / name
            if os.path.lexists(destination):
                continue
            try:
                if (here / name).is_symlink():
                    os.symlink(os.readlink(here / name), destination, target_is_directory=(here / name).is_dir())
                else:
                    shutil.copy2(here / name, destination)
            except OSError:
                skipped += 1
                continue
            copied += 1
    return copied, skipped

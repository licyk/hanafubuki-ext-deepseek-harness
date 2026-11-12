"""Which instances the user's ``~/.dsh`` was copied into, which the versions page offers once.

Kept as ``<data>/home-copied.json``, a list of instance ids, across the
backend's restarts.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path


class HomeCopies:
    """The instances whose home was filled from the user's."""

    def __init__(self, path: Path) -> None:
        """Reads what is there; a file that does not read is no copy."""
        self._path = path
        self._lock = threading.Lock()
        try:
            found = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            found = []
        self._ids = {entry for entry in found if isinstance(entry, str)} if isinstance(found, list) else set()

    def mark(self, instance_id: str) -> None:
        """Records that the user's home was copied into the instance."""
        with self._lock:
            if instance_id in self._ids:
                return
            self._ids.add(instance_id)
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                partial = self._path.with_name(self._path.name + ".part")
                partial.write_text(json.dumps(sorted(self._ids)), encoding="utf-8")
                partial.replace(self._path)
            except OSError:
                pass  # the page then offers the copy again

    def __contains__(self, instance_id: object) -> bool:
        """Whether the user's home was copied into the instance."""
        with self._lock:
            return instance_id in self._ids

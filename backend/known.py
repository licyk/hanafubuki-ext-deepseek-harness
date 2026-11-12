"""What the host last said of each instance (its components and install values), and whether its home was copied.

A provider call (``installPlan``, ``launchPlan``, ``manage``,
``validateSpec`` of an existing instance) carries the instance's
components, but a frame's call carries only its id and ``instances.ofType``
only its root. The versions page reads what was remembered here, kept in
the extension's data directory across restarts. It is a display aid: no
plan reads it. It also records that the user's ``~/.dsh`` was copied into
an instance, which the page offers once.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from layout import Components, components


class KnownInstances:
    """``<data>/instances.json``: by instance id, ``{components, values}`` as the host sent them, and ``homeCopied``."""

    def __init__(self, path: Path) -> None:
        """Reads what is there; a file that does not read is no knowledge."""
        self._path = path
        self._lock = threading.Lock()
        try:
            found = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            found = {}
        self._entries: dict[str, Any] = found if isinstance(found, dict) else {}

    def remember(self, instance_id: str, found: Components, values: dict[str, Any] | None) -> None:
        """Records the instance's components, and its values when the call had them."""
        update: dict[str, Any] = {"components": found.to_protocol()}
        if values is not None:
            update["values"] = values
        self._update(instance_id, update)

    def mark_home_copied(self, instance_id: str) -> None:
        """Records that the user's home was copied into the instance."""
        self._update(instance_id, {"homeCopied": True})

    def home_copied(self, instance_id: str) -> bool:
        """Whether the user's home was copied into the instance."""
        with self._lock:
            return (self._entries.get(instance_id) or {}).get("homeCopied") is True

    def components(self, instance_id: str) -> Components | None:
        """The instance's components when a provider call told them."""
        with self._lock:
            return components(self._entries.get(instance_id))

    def values(self, instance_id: str) -> dict[str, Any]:
        """The instance's install values when a provider call told them; ``{}`` otherwise."""
        with self._lock:
            found = (self._entries.get(instance_id) or {}).get("values")
        return found if isinstance(found, dict) else {}

    def _update(self, instance_id: str, update: dict[str, Any]) -> None:
        with self._lock:
            entry = {**(self._entries.get(instance_id) or {}), **update}
            if self._entries.get(instance_id) == entry:
                return
            self._entries[instance_id] = entry
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                partial = self._path.with_name(self._path.name + ".part")
                partial.write_text(json.dumps(self._entries, indent=1), encoding="utf-8")
                partial.replace(self._path)
            except OSError:
                pass  # the page then reads the root's default layout, and offers the copy again

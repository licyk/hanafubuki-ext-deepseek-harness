"""Documents the backend reads from the network, cached in its data directory.

A fetch goes through the host's ``download.fetch``, so the application's
proxy applies and the manifest's ``network`` list is what it may reach. A
mirror the user set on another host is refused there; that one is read
directly with urllib. A cached copy younger than its age bound is used as
it is, and an older one when the network fails, so a plan still answers
offline once it was made online.
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from hanafubuki_extension import PERMISSION_DENIED, REQUEST_FAILED, RpcError

FETCH_TIMEOUT = 15.0


class HostCalls(Protocol):
    """What ``Remote`` asks of the application: ``Host.call``."""

    def call(self, method: str, params: Any = None) -> Any:
        """Calls a host method and waits for its answer."""
        ...


class Remote:
    """Fetches and caches documents under ``<data>/cache``."""

    def __init__(self, host: HostCalls, data_dir: Path) -> None:
        """Builds the fetcher.

        Args:
            host: The application, for ``download.fetch``.
            data_dir: The extension's data directory.
        """
        self._host = host
        self._cache = data_dir / "cache"

    def text(self, url: str, name: str, max_age: float | None = None) -> str:
        """The document at ``url``, as cached under ``name``.

        Args:
            url: Where it is.
            name: Its file name in the cache.
            max_age: How old a cached copy may be, in seconds; ``None`` keeps it for good.

        Returns:
            Its text.

        Raises:
            RpcError: It could not be fetched and nothing is cached.
        """
        path = self._cache / name
        if path.is_file() and (max_age is None or time.time() - path.stat().st_mtime < max_age):
            return path.read_text(encoding="utf-8")
        try:
            self._fetch(url, path)
        except (RpcError, OSError) as error:
            if path.is_file():
                return path.read_text(encoding="utf-8")
            if isinstance(error, RpcError):
                raise
            raise RpcError(REQUEST_FAILED, f"fetch {url}: {error}") from error
        return path.read_text(encoding="utf-8")

    def json(self, url: str, name: str, max_age: float | None = None) -> Any:
        """The JSON document at ``url`` (see ``text``)."""
        return json.loads(self.text(url, name, max_age))

    def _fetch(self, url: str, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._host.call("download.fetch", {"url": url, "destination": str(path)})
        except RpcError as error:
            if error.code != PERMISSION_DENIED:
                raise
            partial = path.with_name(path.name + ".part")
            with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT) as response:
                partial.write_bytes(response.read())
            partial.replace(path)

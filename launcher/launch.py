"""Runs dsh's web UI for Hanafubuki and reports the address it opens.

The host starts this on its managed Python (``{host.python}``), with
``sd_webui_all_in_one`` importable and a runtime broker session in the
environment, since the ``web`` role's readiness is ``captured``. It runs
``node start-dsh.mjs --core <core> -- web …`` (which starts dsh's own
program in that process) with ``intercept.mjs`` loaded through
``NODE_OPTIONS``, so the browser dsh would open is a line in a channel file
instead; each http(s) address read there is reported as ``browser.open``,
which makes the role ready and is the page the WebView shows. dsh's
``dsh web: <url>`` line is reported when no opener reports within a few
seconds. The dsh tree runs under ``sd_webui_all_in_one``'s process tree, so
it ends with this launcher: SIGTERM, SIGHUP or CTRL_BREAK stops it.

Usage: launch.py --core <npm prefix> --node <node program> --port <port>
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
FALLBACK_SECONDS = 5.0
POLL_SECONDS = 0.2
# Variables of the launcher's own Python and of the broker session: none of
# them is dsh's business, and every tool dsh runs would inherit them.
DROPPED_PREFIXES = ("PYTHON", "SD_WEBUI_ALL_IN_ONE_")
# dsh does not open a browser when it believes it runs over SSH; the browser
# here is Hanafubuki's WebView on this machine.
DROPPED_NAMES = ("SSH_CONNECTION", "SSH_TTY", "SSH_CLIENT")


def main(argv: list[str] | None = None) -> int:
    """Runs dsh until it exits or the launcher is told to stop; returns dsh's exit code."""
    args = _parse(argv)
    from sd_webui_all_in_one.process_tree import run_process_tree

    reporter = _Reporter(_broker_client())
    work = Path(tempfile.mkdtemp(prefix="hfx-dsh-"))
    channel = work / "open-requests.jsonl"
    channel.touch()
    watcher = ChannelWatcher(channel, reporter.report)
    watcher.start()
    command = [
        str(args.node),
        str(HERE / "start-dsh.mjs"),
        "--core",
        str(args.core),
        "--",
        "web",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    try:
        return run_process_tree(
            command, custom_env=dsh_environment(os.environ, args.core, channel), cwd=args.core, check=False
        )
    except SystemExit as stop:  # ProcessTreeTerminated: the tree is already stopped
        print(f"launcher: stopped by signal {getattr(stop, 'signum', '?')}", file=sys.stderr, flush=True)
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        watcher.stop()
        reporter.close()
        shutil.rmtree(work, ignore_errors=True)


def dsh_environment(environ: Mapping[str, str], core: Path, channel: Path) -> dict[str, str]:
    """dsh's environment: the launcher's, without its own variables, with the hook and the channel."""
    env = {
        name: value
        for name, value in environ.items()
        if not name.upper().startswith(DROPPED_PREFIXES) and name.upper() not in DROPPED_NAMES
    }
    hook = (HERE / "intercept.mjs").as_uri()
    env["NODE_OPTIONS"] = f"{env.get('NODE_OPTIONS', '')} --import={hook}".strip()
    env["HFX_DSH_OPEN_CHANNEL"] = str(channel)
    env["HFX_DSH_PREFIX"] = str(core)
    env["HFX_DSH_LAUNCHER_PID"] = str(os.getpid())
    return env


class ChannelWatcher:
    """Follows the channel file and hands each address, and where it came from, to ``report``.

    An ``open`` line (the intercepted opener) is reported at once. A
    ``printed`` line (dsh's URL line) is reported only if no ``open`` came
    within ``fallback`` seconds of it.
    """

    def __init__(self, channel: Path, report: Callable[[str, str], None], fallback: float = FALLBACK_SECONDS) -> None:
        """Builds the watcher; ``start`` runs it on a thread of its own."""
        self._channel = channel
        self._report = report
        self._fallback = fallback
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._run, name="dsh-open-channel", daemon=True)
        self._offset = 0
        self._printed: tuple[str, float] | None = None
        self._opened = False

    def start(self) -> None:
        """Starts following the channel."""
        self._thread.start()

    def stop(self) -> None:
        """Stops following it, after one last read."""
        self._stopped.set()
        self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stopped.wait(POLL_SECONDS):
            self._poll()
        self._poll()

    def _poll(self) -> None:
        for entry in self._read():
            url = entry.get("url")
            if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
                continue
            if entry.get("kind") == "open":
                self._opened = True
                self._report(url, "opener")
            elif entry.get("kind") == "printed" and self._printed is None:
                self._printed = (url, time.monotonic())
        if self._printed is not None and not self._opened and time.monotonic() - self._printed[1] >= self._fallback:
            self._opened = True
            self._report(self._printed[0], "URL line")

    def _read(self) -> list[dict[str, Any]]:
        try:
            with self._channel.open("rb") as stream:
                stream.seek(self._offset)
                data = stream.read()
        except OSError:
            return []
        complete = data[: data.rfind(b"\n") + 1]
        self._offset += len(complete)
        entries = []
        for line in complete.decode("utf-8", errors="replace").splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict):
                entries.append(entry)
        return entries


class _Reporter:
    """Reports addresses to the broker session, or only prints them without one."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._lock = threading.Lock()
        self._reported: set[str] = set()

    def report(self, url: str, source: str) -> None:
        with self._lock:
            if url in self._reported:
                return
            self._reported.add(url)
        print(f"launcher: dsh web UI at {url.split('?', 1)[0]} (from its {source})", file=sys.stderr, flush=True)
        if self._client is not None and not self._client.emit_event("browser.open", {"url": url}):
            print("launcher: the broker refused the address", file=sys.stderr, flush=True)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()


def _broker_client() -> Any:
    # The client's own thread connects and keeps the session's heartbeat.
    from sd_webui_all_in_one_hotpatcher.runtime.desktop_broker import (
        DesktopBrokerClient,
        DesktopBrokerConfigurationError,
    )

    try:
        return DesktopBrokerClient.from_env().start()
    except DesktopBrokerConfigurationError as error:
        print(
            f"launcher: no Hanafubuki broker session ({error}); the address is only printed",
            file=sys.stderr,
            flush=True,
        )
        return None


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run dsh's web UI for Hanafubuki.")
    parser.add_argument(
        "--core", type=Path, required=True, help="dsh's npm prefix: the directory whose node_modules holds it"
    )
    parser.add_argument("--node", type=Path, required=True, help="the node program")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())

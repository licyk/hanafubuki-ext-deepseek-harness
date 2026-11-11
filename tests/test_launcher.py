"""``launch.py`` against a broker that speaks the desktop broker protocol v2.

The broker is the test's: it checks each request's session headers and
records the events, as Hanafubuki's runtime broker does for a ``captured``
role (``sd_webui_all_in_one/patcher/docs/desktop-broker-protocol.md``).
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from tests.fake_dsh import make_prefix
from tests.support import NODE, ROOT, launcher_pythonpath, needs_aio, needs_node

SESSION = {"id": "session-1", "token": "secret-token", "identity": "runtime-1"}


class FakeBroker:
    """The runtime broker's HTTP side, on a loopback port."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.paths: list[str] = []
        self.rejected = 0
        broker = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass

            def do_GET(self) -> None:
                self._serve(None)

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                self._serve(json.loads(self.rfile.read(length) or b"{}"))

            def _serve(self, body: Any) -> None:
                path = self.path.split("?", 1)[0]
                if not broker._authorized(self.headers):
                    broker.rejected += 1
                    self._send(401, {"error": "unauthorized"})
                    return
                broker.paths.append(path)
                if path == "/v1/runtime/connect":
                    self._send(
                        200,
                        {
                            "status": "connected",
                            "acknowledgedSequence": broker._acknowledged(),
                            "acknowledgedDiagnosticSequence": 0,
                        },
                    )
                elif path == "/v1/runtime/events":
                    broker.events.extend(body.get("events", []))
                    self._send(200, {"acknowledgedSequence": broker._acknowledged()})
                elif path == "/v1/runtime/heartbeat":
                    self._send(
                        200,
                        {
                            "status": "connected",
                            "acknowledgedSequence": broker._acknowledged(),
                            "acknowledgedDiagnosticSequence": 0,
                        },
                    )
                elif path == "/v1/runtime/commands":
                    time.sleep(0.05)
                    self._send(200, {"commands": []})
                elif path == "/v1/runtime/results":
                    self._send(200, {"acknowledgedCommandIds": []})
                else:
                    self._send(404, {})

            def _send(self, status: int, payload: dict[str, Any]) -> None:
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def _authorized(self, headers: Any) -> bool:
        return (
            headers.get("Authorization") == f"Bearer {SESSION['token']}"
            and headers.get("X-Runtime-Protocol-Version") == "2"
            and headers.get("X-Runtime-Session-Id") == SESSION["id"]
            and headers.get("X-Runtime-Identity") == SESSION["identity"]
        )

    def _acknowledged(self) -> int:
        return max((event["sequence"] for event in self.events), default=0)

    def environment(self) -> dict[str, str]:
        return {
            "SD_WEBUI_ALL_IN_ONE_RUNTIME_BROKER_URL": f"http://127.0.0.1:{self.server.server_address[1]}",
            "SD_WEBUI_ALL_IN_ONE_RUNTIME_SESSION_ID": SESSION["id"],
            "SD_WEBUI_ALL_IN_ONE_RUNTIME_TOKEN": SESSION["token"],
            "SD_WEBUI_ALL_IN_ONE_RUNTIME_IDENTITY": SESSION["identity"],
            "SD_WEBUI_ALL_IN_ONE_RUNTIME_PROTOCOL_VERSION": "2",
        }

    def browser_opens(self) -> list[str]:
        return [event["payload"]["url"] for event in self.events if event.get("eventType") == "browser.open"]

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@needs_node
@needs_aio
class LauncherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.core = self.directory / "core"
        make_prefix(self.core)
        self.browser = self.directory / "browser.log"
        self.pidfile = self.directory / "dsh.pid"
        self.broker = FakeBroker()
        self.launcher: subprocess.Popen[str] | None = None

    def tearDown(self) -> None:
        if self.launcher is not None and self.launcher.poll() is None:
            self.launcher.kill()
            self.launcher.wait()
        self.broker.close()
        shutil.rmtree(self.directory, ignore_errors=True)

    def start(self, mode: str, port: int) -> None:
        assert NODE is not None
        env = {
            **os.environ,
            **self.broker.environment(),
            "PYTHONPATH": launcher_pythonpath(),
            "PYTHONUNBUFFERED": "1",
            "FAKE_DSH_MODE": mode,
            "FAKE_DSH_PIDFILE": str(self.pidfile),
            "FAKE_BROWSER_LOG": str(self.browser),
        }
        self.launcher = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "launcher" / "launch.py"),
                "--core",
                str(self.core),
                "--node",
                NODE,
                "--port",
                str(port),
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def wait_for(self, condition: Any, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while not condition():
            if time.monotonic() > deadline:
                assert self.launcher is not None
                self.launcher.kill()
                output, errors = self.launcher.communicate()
                self.fail(f"timed out; events {self.broker.events}\nstdout:\n{output}\nstderr:\n{errors}")
            time.sleep(0.1)

    def stop(self) -> tuple[str, str]:
        assert self.launcher is not None
        self.launcher.send_signal(signal.SIGTERM)
        output, errors = self.launcher.communicate(timeout=30)
        return output, errors

    @unittest.skipIf(sys.platform == "win32", "SIGTERM is POSIX's; Windows stops the launcher with CTRL_BREAK")
    def test_reports_the_opened_url_and_stops_with_its_tree(self) -> None:
        self.start("open", 4601)
        self.wait_for(lambda: self.broker.browser_opens() and self.pidfile.exists(), 30)
        self.assertEqual(self.broker.browser_opens(), ["http://127.0.0.1:4601/?token=fake-token-4601"])
        self.assertEqual(self.broker.rejected, 0)
        self.assertEqual(self.broker.paths[0], "/v1/runtime/connect")
        self.wait_for(lambda: "/v1/runtime/heartbeat" in self.broker.paths, 15)
        dsh = int(self.pidfile.read_text())

        output, errors = self.stop()
        self.assertIn("dsh web: http://127.0.0.1:4601/", output)
        self.assertIn("(from its opener)", errors)
        self.assertFalse(self.browser.exists())
        with self.assertRaises(ProcessLookupError):
            os.kill(dsh, 0)

    @unittest.skipIf(sys.platform == "win32", "SIGTERM is POSIX's")
    def test_falls_back_to_the_url_line(self) -> None:
        self.start("print", 4602)
        started = time.monotonic()
        self.wait_for(lambda: self.broker.browser_opens(), 30)
        self.assertGreaterEqual(time.monotonic() - started, 4.0)
        self.assertEqual(self.broker.browser_opens(), ["http://127.0.0.1:4602/?token=fake-token-4602"])
        _, errors = self.stop()
        self.assertIn("(from its URL line)", errors)


if __name__ == "__main__":
    unittest.main()

"""The backend as the host runs it: ``backend/main.py`` over its stdin and stdout.

The test is the host: it sends the protocol's frames and answers the
backend's own calls (``host.info``, ``settings.get``, ``download.fetch``
from the recorded fixtures, ``instances.ofType``).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, BinaryIO, cast

import node_release
from tests.support import FIXTURES, ROOT, SDK, TYPE_ID, needs_sdk


class FakeHost:
    """Speaks the protocol to a backend process and answers what it asks."""

    def __init__(
        self, data_dir: Path, instance_root: Path, platform: str = "linux", settings: dict | None = None
    ) -> None:
        from hanafubuki_extension.protocol import read_frame, write_frame

        self._read, self._write = read_frame, write_frame
        self.platform = platform
        self.settings = settings or {}
        self.instance_root = instance_root
        self.fetched: list[str] = []
        env = {
            **os.environ,
            "PYTHONPATH": str(SDK),
            "HANAFUBUKI_EXTENSION_DATA": str(data_dir),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        self.process = subprocess.Popen(
            [sys.executable, str(ROOT / "backend" / "main.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            cwd=ROOT,
            env=env,
        )
        self._next = 1

    def request(self, method: str, params: Any = None) -> dict[str, Any]:
        call_id = self._next
        self._next += 1
        assert self.process.stdin is not None and self.process.stdout is not None
        self._write(
            cast(BinaryIO, self.process.stdin),
            {"jsonrpc": "2.0", "id": call_id, "method": method, "params": params or {}},
        )
        self.process.stdin.flush()
        while True:
            message = self._read(cast(BinaryIO, self.process.stdout))
            assert message is not None, "the backend closed its output"
            if "method" not in message:
                assert message["id"] == call_id
                return message
            if "id" in message:
                self._answer(message)

    def _answer(self, message: dict[str, Any]) -> None:
        method, params = message["method"], message.get("params") or {}
        reply: dict[str, Any] = {"jsonrpc": "2.0", "id": message["id"]}
        if method == "host.info":
            reply["result"] = {"version": "0.3.28", "protocolVersion": 1, "locale": "zh", "platform": self.platform}
        elif method == "settings.get":
            reply["result"] = {"values": self.settings}
        elif method == "instances.ofType":
            assert params == {"type": TYPE_ID}
            reply["result"] = {
                "instances": [
                    {"id": "dsh-1", "name": "dsh", "type": TYPE_ID, "path": str(self.instance_root), "running": False}
                ]
            }
        elif method == "download.fetch":
            self.fetched.append(params["url"])
            name = "node-index.json" if params["url"].endswith("/index.json") else "node-v24.11.0-SHASUMS256.txt"
            shutil.copyfile(FIXTURES / name, params["destination"])
            reply["result"] = {"path": params["destination"], "sha256": ""}
        else:
            reply["error"] = {"code": -32601, "message": f"no method {method}"}
        assert self.process.stdin is not None
        self._write(cast(BinaryIO, self.process.stdin), reply)
        self.process.stdin.flush()

    def close(self) -> int:
        answer = self.request("shutdown")
        assert answer["result"] == {}
        assert self.process.stdin is not None
        self.process.stdin.close()
        return self.process.wait(timeout=10)


@needs_sdk
class BackendProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.root = self.directory / "instance"
        (self.root / "core").mkdir(parents=True)
        self.host = FakeHost(self.directory / "data", self.root)

    def tearDown(self) -> None:
        if self.host.process.poll() is None:
            self.host.process.kill()
            self.host.process.wait()
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_initialize_ping_shutdown(self) -> None:
        answer = self.host.request(
            "initialize", {"protocolVersion": 1, "extension": {"id": "io.github.licyk.deepseek-harness"}}
        )
        self.assertEqual(answer["result"]["protocolVersion"], 1)
        self.assertEqual(self.host.request("ping")["result"], {})
        self.assertEqual(self.host.close(), 0)

    def test_validate_spec_answers_in_the_host_locale(self) -> None:
        good = self.host.request(
            "provider.validateSpec", {"type": TYPE_ID, "values": {"version": "latest", "nodeVersion": "24"}}
        )
        self.assertEqual(good["result"], {"issues": {}})
        bad = self.host.request(
            "provider.validateSpec", {"type": TYPE_ID, "values": {"version": "--x", "nodeVersion": "20"}}
        )
        self.assertEqual(set(bad["result"]["issues"]), {"version", "nodeVersion"})
        self.assertIn("24.9.0", bad["result"]["issues"]["nodeVersion"])
        self.assertIn("发布标签", bad["result"]["issues"]["version"])

    def test_install_plan_resolves_node_through_download_fetch(self) -> None:
        params = {
            "type": TYPE_ID,
            "kind": "install",
            "values": {"version": "latest", "nodeVersion": "24.11.0"},
            "instance": {"id": "dsh-1"},
        }
        steps = self.host.request("provider.installPlan", params)["result"]["steps"]
        self.assertEqual([step["kind"] for step in steps], ["download", "run", "write-file"])
        filename = f"node-v24.11.0-linux-{node_release.machine_arch()}.tar.xz"
        self.assertEqual(steps[0]["url"], f"https://nodejs.org/dist/v24.11.0/{filename}")
        shasums = (FIXTURES / "node-v24.11.0-SHASUMS256.txt").read_text(encoding="utf-8")
        self.assertIn(f"{steps[0]['sha256']}  {filename}", shasums)
        self.assertEqual(
            self.host.fetched,
            ["https://nodejs.org/dist/index.json", "https://nodejs.org/dist/v24.11.0/SHASUMS256.txt"],
        )
        # Both documents are cached: the next plan fetches nothing.
        self.host.request("provider.installPlan", params)
        self.assertEqual(len(self.host.fetched), 2)

    def test_update_with_the_same_node_runs_npm_only(self) -> None:
        (self.root / "node" / "bin").mkdir(parents=True)
        (self.root / "node" / "bin" / "node").write_text("")
        (self.root / "core" / "hanafubuki-install.txt").write_text("version=latest\nnodeVersion=24\nnode=24.11.0\n")
        values = {"version": "0.2.2", "nodeVersion": "24"}
        params = {"type": TYPE_ID, "kind": "update", "values": values, "instance": {"id": "dsh-1"}}
        steps = self.host.request("provider.installPlan", params)["result"]["steps"]
        self.assertEqual([step["kind"] for step in steps], ["run", "write-file"])
        self.assertEqual(steps[0]["command"][-1], "@deepseek-ai/dsh@0.2.2")
        self.assertEqual(self.host.fetched, [])

        values["nodeVersion"] = "24.11.0"
        steps = self.host.request("provider.installPlan", params)["result"]["steps"]
        self.assertEqual([step["kind"] for step in steps], ["run", "download", "run", "write-file"])

    def test_launch_plan(self) -> None:
        params = {"type": TYPE_ID, "role": "web", "port": 4000, "values": {}, "instance": {"id": "dsh-1"}}
        argv = self.host.request("provider.launchPlan", params)["result"]["argv"]
        self.assertEqual(argv[:2], ["{host.python}", "{extension.root}/launcher/launch.py"])
        self.assertIn("{component.node}/bin/node", argv)
        unknown = self.host.request("provider.launchPlan", {**params, "role": "api"})
        self.assertEqual(unknown["error"]["code"], -32602)

    def test_frame_status(self) -> None:
        package = self.root / "core" / "node_modules" / "@deepseek-ai" / "dsh"
        package.mkdir(parents=True)
        (package / "package.json").write_text(json.dumps({"name": "@deepseek-ai/dsh", "version": "0.2.2-rc.1"}))
        (self.root / "core" / "hanafubuki-install.txt").write_text("version=next\nnodeVersion=24\nnode=24.11.0\n")
        params = {"frame": "versions", "method": "status", "params": None, "context": {"instanceId": "dsh-1"}}
        status = self.host.request("ui.frame.call", params)["result"]
        self.assertEqual(status["installed"], "0.2.2-rc.1")
        self.assertEqual(status["node"], "24.11.0")
        self.assertEqual(status["requested"], {"version": "next", "nodeVersion": "24"})
        self.assertEqual(status["locale"], "zh")
        self.assertEqual(status["strings"]["zh"]["switch"], "切换")
        self.assertEqual(set(status["strings"]["en"]), set(status["strings"]["zh"]))
        missing = self.host.request("ui.frame.call", {**params, "context": {"instanceId": "other"}})
        self.assertEqual(missing["error"]["code"], -32003)


if __name__ == "__main__":
    unittest.main()

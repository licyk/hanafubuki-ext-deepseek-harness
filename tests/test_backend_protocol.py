"""The backend as the host runs it: ``backend/main.py`` over its stdin and stdout.

The test is the host: it sends the protocol's frames, with each provider
call's ``instance`` carrying the component map as Hanafubuki 0.3.30 does,
and answers the backend's own calls (``host.info``, ``settings.get``,
``download.fetch`` from the recorded fixtures, ``instances.ofType``,
``ui.progress``, ``ui.notify``).
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

ARCH = node_release.machine_arch()
NO_SHELL_NODE = unittest.skipIf(sys.platform == "win32", "the fake node is a shell script")


class FakeHost:
    """Speaks the protocol to a backend process and answers what it asks."""

    def __init__(
        self,
        data_dir: Path,
        instance_root: Path,
        user_home: Path,
        platform: str = "linux",
        settings: dict | None = None,
    ) -> None:
        from hanafubuki_extension.protocol import read_frame, write_frame

        self._read, self._write = read_frame, write_frame
        self.platform = platform
        self.settings = settings or {}
        self.instance_root = instance_root
        self.running = False
        self.fail_fetches = False
        self.refused: set[str] = set()
        self.fetched: list[str] = []
        self.calls: list[tuple[str, Any]] = []
        self.emitted: list[dict[str, Any]] = []
        env = {
            **os.environ,
            "PYTHONPATH": str(SDK),
            "HANAFUBUKI_EXTENSION_DATA": str(data_dir),
            "PYTHONDONTWRITEBYTECODE": "1",
            "HOME": str(user_home),
            "USERPROFILE": str(user_home),
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
        self._send({"jsonrpc": "2.0", "id": call_id, "method": method, "params": params or {}})
        while True:
            message = self._receive()
            if "method" not in message:
                assert message["id"] == call_id
                return message

    def wait_for_emit(self, event: str) -> dict[str, Any]:
        """Answers the backend's calls until it emits ``event`` to a frame; its payload."""
        while True:
            for emitted in self.emitted:
                if emitted["event"] == event:
                    return emitted["payload"]
            self._receive()

    def _receive(self) -> dict[str, Any]:
        assert self.process.stdout is not None
        message = self._read(cast(BinaryIO, self.process.stdout))
        assert message is not None, "the backend closed its output"
        if "method" in message and "id" in message:
            self._answer(message)
        elif message.get("method") == "ui.frame.emit":
            self.emitted.append(message["params"])
        return message

    def _answer(self, message: dict[str, Any]) -> None:
        method, params = message["method"], message.get("params") or {}
        self.calls.append((method, params))
        reply: dict[str, Any] = {"jsonrpc": "2.0", "id": message["id"]}
        if method == "host.info":
            reply["result"] = {"version": "0.3.30", "protocolVersion": 1, "locale": "zh", "platform": self.platform}
        elif method == "settings.get":
            reply["result"] = {"values": self.settings}
        elif method == "instances.ofType":
            assert params == {"type": TYPE_ID}
            reply["result"] = {
                "instances": [
                    {
                        "id": "dsh-1",
                        "name": "dsh",
                        "type": TYPE_ID,
                        "path": str(self.instance_root),
                        "running": self.running,
                    }
                ]
            }
        elif method == "download.fetch" and self.fail_fetches:
            reply["error"] = {"code": -32003, "message": "network unreachable"}
        elif method == "download.fetch":
            self.fetched.append(params["url"])
            _serve(params["url"], Path(params["destination"]))
            reply["result"] = {"path": params["destination"], "sha256": ""}
        elif method in self.refused:
            reply["error"] = {"code": -32002, "message": f"{method} refused"}
        elif method in ("ui.progress", "ui.notify", "log.write"):
            reply["result"] = {}
        else:
            reply["error"] = {"code": -32601, "message": f"no method {method}"}
        self._send(reply)

    def _send(self, message: dict[str, Any]) -> None:
        assert self.process.stdin is not None
        self._write(cast(BinaryIO, self.process.stdin), message)
        self.process.stdin.flush()

    def close(self) -> int:
        answer = self.request("shutdown")
        assert answer["result"] == {}
        assert self.process.stdin is not None
        self.process.stdin.close()
        return self.process.wait(timeout=10)


def _serve(url: str, destination: Path) -> None:
    # The recorded index and 24.11.0's SHASUMS; another release's SHASUMS
    # lists its Linux archives with a made-up digest.
    if url.endswith("/index.json"):
        shutil.copyfile(FIXTURES / "node-index.json", destination)
        return
    version = url.rsplit("/", 2)[-2]
    if version == "v24.11.0":
        shutil.copyfile(FIXTURES / "node-v24.11.0-SHASUMS256.txt", destination)
        return
    names = [f"node-{version}-linux-{ARCH}.tar.xz", f"node-{version}-linux-{ARCH}-musl.tar.xz"]
    destination.write_text("".join(f"{'ab' * 32}  {name}\n" for name in names), encoding="utf-8")


def instance(core: Path, node: Path, core_external: bool = False, node_external: bool = False) -> dict[str, Any]:
    return {
        "id": "dsh-1",
        "components": {
            "core": {"path": str(core), "external": core_external},
            "node": {"path": str(node), "external": node_external},
        },
    }


def fake_node(path: Path, version: str) -> Path:
    """A ``node`` program that answers ``--version`` as Node.js ``version`` would."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\necho v{version}\n")
    path.chmod(0o755)
    return path


@needs_sdk
class BackendProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.root = self.directory / "instance"
        self.user = self.directory / "user"
        self.user.mkdir()
        (self.root / "core").mkdir(parents=True)
        self.instance = instance(self.root / "core", self.root / "node")
        self.host = FakeHost(self.directory / "data", self.root, self.user)

    def tearDown(self) -> None:
        if self.host.process.poll() is None:
            self.host.process.kill()
            self.host.process.wait()
        shutil.rmtree(self.directory, ignore_errors=True)

    def plan(self, kind: str, values: dict[str, Any], sent: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        params = {"type": TYPE_ID, "kind": kind, "values": values, "instance": sent or self.instance}
        answer = self.host.request("provider.installPlan", params)
        self.assertIn("result", answer, answer)
        return answer["result"]["steps"]

    def status(self) -> dict[str, Any]:
        params = {"frame": "versions", "method": "status", "params": None, "context": {"instanceId": "dsh-1"}}
        return self.host.request("ui.frame.call", params)["result"]

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
        steps = self.plan("install", {"version": "latest", "nodeVersion": "24.11.0"})
        self.assertEqual([step["kind"] for step in steps], ["download", "write-file", "run", "write-file"])
        filename = f"node-v24.11.0-linux-{ARCH}.tar.xz"
        self.assertEqual(steps[0]["url"], f"https://nodejs.org/dist/v24.11.0/{filename}")
        self.assertTrue(steps[0]["replace"])
        shasums = (FIXTURES / "node-v24.11.0-SHASUMS256.txt").read_text(encoding="utf-8")
        self.assertIn(f"{steps[0]['sha256']}  {filename}", shasums)
        self.assertEqual(
            self.host.fetched,
            ["https://nodejs.org/dist/index.json", "https://nodejs.org/dist/v24.11.0/SHASUMS256.txt"],
        )
        # Both documents are cached: the next plan fetches nothing.
        self.plan("install", {"version": "latest", "nodeVersion": "24.11.0"})
        self.assertEqual(len(self.host.fetched), 2)

    def test_the_registry_setting_goes_to_the_instance_npmrc(self) -> None:
        self.host.settings = {"npmRegistry": "https://registry.npmmirror.com"}
        steps = self.plan("install", {"nodeVersion": "24.11.0"})
        self.assertEqual(steps[1]["path"], "{component.core}/.npmrc")
        self.assertIn("registry=https://registry.npmmirror.com\n", steps[1]["content"])
        self.assertEqual(steps[2]["env"], {})

    def test_an_update_keeps_node_for_the_same_release_and_follows_a_major(self) -> None:
        fake_node(self.root / "node" / "bin" / "node", "24.22.3")
        marker = self.root / "core" / "hanafubuki-install.txt"
        marker.write_text("version=latest\nnodeVersion=24\nnode=24.22.3\n")
        steps = self.plan("update", {"version": "0.2.2", "nodeVersion": "24"})
        self.assertEqual([step["kind"] for step in steps], ["write-file", "run", "write-file"])
        self.assertEqual(steps[1]["command"][-1], "@deepseek-ai/dsh@0.2.2")

        # Installed when 24.11.0 was the newest 24: `24` now resolves to 24.22.3.
        marker.write_text("version=latest\nnodeVersion=24\nnode=24.11.0\n")
        steps = self.plan("update", {"version": "0.2.2", "nodeVersion": "24"})
        self.assertEqual([step["kind"] for step in steps], ["download", "write-file", "run", "write-file"])
        self.assertIn("/v24.22.3/", steps[0]["url"])
        self.assertIn("node=24.22.3\n", steps[3]["content"])

        # An exact version is kept as it is, and asked for, is downloaded.
        steps = self.plan("update", {"version": "0.2.2", "nodeVersion": "24.11.0"})
        self.assertEqual(steps[0]["kind"], "write-file")
        marker.write_text("version=latest\nnodeVersion=24\nnode=24.22.3\n")
        steps = self.plan("update", {"version": "0.2.2", "nodeVersion": "24.11.0"})
        self.assertEqual(steps[0]["kind"], "download")
        self.assertIn("/v24.11.0/", steps[0]["url"])

    def test_offline_an_update_keeps_node_for_an_unchanged_request(self) -> None:
        fake_node(self.root / "node" / "bin" / "node", "24.11.0")
        (self.root / "core" / "hanafubuki-install.txt").write_text("version=latest\nnodeVersion=24\nnode=24.11.0\n")
        self.host.settings = {"nodeMirror": "https://offline.example/node"}
        self.host.fail_fetches = True
        steps = self.plan("update", {"nodeVersion": "24"})
        self.assertEqual([step["kind"] for step in steps], ["write-file", "run", "write-file"])
        self.assertIn("node=24.11.0\n", steps[2]["content"])
        # Another request needs the index.
        params = {"type": TYPE_ID, "kind": "update", "values": {"nodeVersion": "26"}, "instance": self.instance}
        self.assertEqual(self.host.request("provider.installPlan", params)["error"]["code"], -32003)

    def test_a_retried_install_replaces_the_earlier_node_whole(self) -> None:
        (self.root / "node" / "lib").mkdir(parents=True)
        steps = self.plan("install", {"nodeVersion": "24.11.0"})
        self.assertEqual([step["kind"] for step in steps], ["download", "write-file", "run", "write-file"])
        self.assertTrue(steps[0]["replace"])
        self.assertNotIn("empty_dir", json.dumps(steps))

    @NO_SHELL_NODE
    def test_an_external_node_is_never_downloaded_into(self) -> None:
        mine = self.directory / "my-node"
        fake_node(mine / "bin" / "node", "24.10.0")
        (mine / "lib" / "node_modules" / "npm" / "bin").mkdir(parents=True)
        (mine / "lib" / "node_modules" / "npm" / "bin" / "npm-cli.js").write_text("")
        sent = instance(self.root / "core", mine, node_external=True)
        for kind in ("install", "update", "reinstall"):
            steps = self.plan(kind, {"version": "0.2.2", "nodeVersion": "26"}, sent)
            self.assertEqual([step["kind"] for step in steps], ["write-file", "run", "write-file"])
            self.assertEqual(
                steps[1]["command"][:2],
                ["{component.node}/bin/node", "{component.node}/lib/node_modules/npm/bin/npm-cli.js"],
            )
            self.assertIn("node=24.10.0\n", steps[2]["content"])
        self.assertEqual(self.host.fetched, [])

    @NO_SHELL_NODE
    def test_an_external_node_must_be_recent_and_have_npm(self) -> None:
        mine = self.directory / "my-node"
        sent = instance(self.root / "core", mine, node_external=True)
        params = {"type": TYPE_ID, "values": {"version": "latest", "nodeVersion": "24"}, "instance": sent}

        missing = self.host.request("provider.validateSpec", params)["result"]["issues"]
        self.assertIn("--version", missing["nodeVersion"])

        fake_node(mine / "bin" / "node", "22.12.0")
        old = self.host.request("provider.validateSpec", params)["result"]["issues"]
        self.assertIn("22.12.0", old["nodeVersion"])
        self.assertIn("24.9.0", old["nodeVersion"])
        refused = self.host.request(
            "provider.installPlan", {"type": TYPE_ID, "kind": "update", "values": {}, "instance": sent}
        )
        self.assertIn("22.12.0", refused["error"]["message"])

        fake_node(mine / "bin" / "node", "24.9.0")
        no_npm = self.host.request("provider.validateSpec", params)["result"]["issues"]
        self.assertIn("npm-cli.js", no_npm["nodeVersion"])

        (mine / "lib" / "node_modules" / "npm" / "bin").mkdir(parents=True)
        (mine / "lib" / "node_modules" / "npm" / "bin" / "npm-cli.js").write_text("")
        self.assertEqual(self.host.request("provider.validateSpec", params)["result"], {"issues": {}})
        # The managed Node.js is not asked: it is downloaded to the version asked for.
        managed = {**params, "instance": self.instance}
        self.assertEqual(self.host.request("provider.validateSpec", managed)["result"], {"issues": {}})

    def test_launch_plan(self) -> None:
        params = {"type": TYPE_ID, "role": "web", "port": 4000, "values": {}, "instance": self.instance}
        answer = self.host.request("provider.launchPlan", params)["result"]
        self.assertEqual(answer["argv"][:2], ["{host.python}", "{extension.root}/launcher/launch.py"])
        self.assertIn("{component.node}/bin/node", answer["argv"])
        self.assertEqual(answer["env"], {})
        user = self.host.request("provider.launchPlan", {**params, "values": {"home": "user"}})["result"]
        self.assertEqual(user["env"], {"DSH_HOME": "", "DSH_AGENTS_HOME": ""})
        unknown = self.host.request("provider.launchPlan", {**params, "role": "api"})
        self.assertEqual(unknown["error"]["code"], -32602)

    def test_frame_status(self) -> None:
        package = self.root / "core" / "node_modules" / "@deepseek-ai" / "dsh"
        package.mkdir(parents=True)
        (package / "package.json").write_text(json.dumps({"name": "@deepseek-ai/dsh", "version": "0.2.2-rc.1"}))
        (self.root / "core" / "hanafubuki-install.txt").write_text("version=next\nnodeVersion=24\nnode=24.11.0\n")
        status = self.status()
        self.assertEqual(status["installed"], "0.2.2-rc.1")
        self.assertEqual(status["node"], "24.11.0")
        self.assertEqual(status["requested"], {"version": "next", "nodeVersion": "24"})
        self.assertEqual(status["nodeSource"], "managed")
        self.assertEqual(status["home"], "instance")
        self.assertEqual(status["homePath"], str(self.root / "dsh-home"))
        self.assertFalse(status["canCopyHome"])  # there is no ~/.dsh
        self.assertEqual(status["locale"], "zh")
        self.assertEqual(status["strings"]["zh"]["switch"], "切换")
        self.assertEqual(set(status["strings"]["en"]), set(status["strings"]["zh"]))
        params = {"frame": "versions", "method": "status", "params": None, "context": {"instanceId": "other"}}
        self.assertEqual(self.host.request("ui.frame.call", params)["error"]["code"], -32003)

    @NO_SHELL_NODE
    def test_frame_status_of_an_external_node_from_the_last_provider_call(self) -> None:
        mine = self.directory / "my-node"
        fake_node(mine / "bin" / "node", "25.9.0")
        sent = instance(self.root / "core", mine, node_external=True)
        self.host.request(
            "provider.launchPlan",
            {"type": TYPE_ID, "role": "web", "port": 4000, "values": {"home": "user"}, "instance": sent},
        )
        self.assertEqual(self.host.close(), 0)
        # A restarted backend still knows: the frame's call carries only the id.
        self.host = FakeHost(self.directory / "data", self.root, self.user)
        status = self.status()
        self.assertEqual(status["nodeSource"], "own")
        self.assertEqual(status["node"], "25.9.0")
        self.assertEqual(status["nodePath"], str(mine / "bin" / "node"))
        self.assertEqual(status["home"], "user")
        self.assertEqual(status["homePath"], "~/.dsh")

    def test_copy_home_once_from_the_frame(self) -> None:
        dsh = self.user / ".dsh"
        (dsh / "profiles" / "default").mkdir(parents=True)
        (dsh / "profiles" / "default" / "credentials.json").write_text("login")
        (dsh / "settings.json").write_text("user's")
        (self.user / ".agents" / "skills").mkdir(parents=True)
        (self.user / ".agents" / "skills" / "a.md").write_text("skill")
        (self.root / "dsh-home").mkdir()
        (self.root / "dsh-home" / "settings.json").write_text("instance's")
        self.assertTrue(self.status()["canCopyHome"])

        self.host.running = True
        call = {"frame": "versions", "method": "copyHome", "params": None, "context": {"instanceId": "dsh-1"}}
        refused = self.host.request("ui.frame.call", call)
        self.assertEqual(refused["error"]["code"], -32003)
        self.assertIn("停止", refused["error"]["message"])

        self.host.running = False
        self.assertIn("notice", self.host.request("ui.frame.call", call)["result"])
        done = self.host.wait_for_emit("home-copied")
        self.assertEqual(done, {"instanceId": "dsh-1", "copied": 2, "skipped": 0, "error": None})
        self.assertEqual((self.root / "dsh-home" / "profiles" / "default" / "credentials.json").read_text(), "login")
        self.assertEqual((self.root / "dsh-home" / "settings.json").read_text(), "instance's")
        self.assertEqual((self.root / "agents-home" / "skills" / "a.md").read_text(), "skill")
        self.assertTrue((dsh / "profiles" / "default" / "credentials.json").is_file())
        self.assertFalse(self.status()["canCopyHome"])
        progress = [params for method, params in self.host.calls if method == "ui.progress"]
        self.assertEqual([entry["done"] for entry in progress], [False, True])

    def test_a_refused_progress_report_does_not_stop_the_copy(self) -> None:
        (self.user / ".dsh").mkdir()
        (self.user / ".dsh" / "a").write_text("a")
        self.host.refused = {"ui.progress", "ui.notify"}
        call = {"frame": "versions", "method": "copyHome", "params": None, "context": {"instanceId": "dsh-1"}}
        self.assertIn("notice", self.host.request("ui.frame.call", call)["result"])
        self.assertEqual(self.host.wait_for_emit("home-copied")["copied"], 1)
        self.assertEqual((self.root / "dsh-home" / "a").read_text(), "a")

    def test_copy_home_as_an_operation(self) -> None:
        (self.user / ".dsh").mkdir()
        (self.user / ".dsh" / "a").write_text("a")
        params = {"type": TYPE_ID, "operation": "copy-user-home", "instance": self.instance}
        answer = self.host.request("provider.manage.copy-user-home", params)
        self.assertIn("notice", answer["result"], answer)
        self.assertEqual(self.host.wait_for_emit("home-copied")["copied"], 1)
        unknown = self.host.request("provider.manage.other", {**params, "operation": "other"})
        self.assertEqual(unknown["error"]["code"], -32602)


@needs_sdk
@NO_SHELL_NODE
class GlobalPrefixTest(unittest.TestCase):
    """An instance discovery attached from a Unix Node.js prefix where dsh was installed with ``npm -g``."""

    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.prefix = self.directory / "nodejs"
        fake_node(self.prefix / "bin" / "node", "24.11.0")
        package = self.prefix / "lib" / "node_modules" / "@deepseek-ai" / "dsh"
        package.mkdir(parents=True)
        (package / "package.json").write_text(json.dumps({"name": "@deepseek-ai/dsh", "version": "0.2.1"}))
        # What the Unix signature attaches: `core` the prefix, `node` its bin, both external.
        self.instance = instance(self.prefix, self.prefix / "bin", True, True)
        self.host = FakeHost(self.directory / "data", self.prefix, self.directory)

    def tearDown(self) -> None:
        if self.host.process.poll() is None:
            self.host.process.kill()
            self.host.process.wait()
        shutil.rmtree(self.directory, ignore_errors=True)

    def plan(self, kind: str, values: dict[str, Any]) -> list[dict[str, Any]]:
        params = {"type": TYPE_ID, "kind": kind, "values": values, "instance": self.instance}
        return self.host.request("provider.installPlan", params)["result"]["steps"]

    def test_update_runs_the_prefix_npm_globally_and_leaves_node(self) -> None:
        for kind in ("update", "install"):
            for node_version in ("24", "26"):
                [step] = self.plan(kind, {"version": "0.2.2", "nodeVersion": node_version})
                self.assertEqual(
                    step["command"][:4],
                    [
                        "{component.core}/bin/node",
                        "{component.core}/lib/node_modules/npm/bin/npm-cli.js",
                        "install",
                        "--global",
                    ],
                )
                self.assertEqual(step["command"][-1], "@deepseek-ai/dsh@0.2.2")
        self.assertEqual(self.host.fetched, [])

    def test_without_dsh_the_prefix_node_is_still_left_alone(self) -> None:
        shutil.rmtree(self.prefix / "lib" / "node_modules" / "@deepseek-ai")
        for kind in ("update", "install"):
            [step] = self.plan(kind, {})
            self.assertEqual(step["command"][2:4], ["install", "--global"])
        self.assertEqual(self.host.fetched, [])

    def test_launch_plan_runs_the_prefix_node(self) -> None:
        params = {"type": TYPE_ID, "role": "web", "port": 4000, "values": {"home": "user"}, "instance": self.instance}
        answer = self.host.request("provider.launchPlan", params)["result"]
        self.assertEqual(answer["argv"][2:6], ["--core", "{component.core}/lib", "--node", "{component.core}/bin/node"])
        self.assertEqual(answer["env"], {"DSH_HOME": "", "DSH_AGENTS_HOME": ""})

    def test_frame_status(self) -> None:
        # Never seen by a provider call: read from the root, as its signature maps it.
        params = {"frame": "versions", "method": "status", "params": None, "context": {"instanceId": "dsh-1"}}
        status = self.host.request("ui.frame.call", params)["result"]
        self.assertEqual(status["installed"], "0.2.1")
        self.assertEqual(status["node"], "24.11.0")
        self.assertEqual(status["nodeSource"], "prefix")
        self.assertEqual(status["prefix"], str(self.prefix))
        self.assertEqual(status["home"], "user")
        self.assertFalse(status["canCopyHome"])
        self.assertEqual(status["requested"], {"version": None, "nodeVersion": None})


if __name__ == "__main__":
    unittest.main()

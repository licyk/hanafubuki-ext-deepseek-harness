"""``intercept.mjs`` and ``open-stub.mjs`` on the real Node: dsh's opener reports its URL and opens nothing."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import launch
from tests.fake_dsh import make_prefix, write_open_package
from tests.support import NODE, ROOT, needs_node


@needs_node
class InterceptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.prefix = self.directory / "core"
        make_prefix(self.prefix)
        self.channel = self.directory / "channel.jsonl"
        self.channel.touch()
        self.browser = self.directory / "browser.log"
        self.env = launch.dsh_environment(os.environ, self.prefix, self.channel)
        self.env["FAKE_BROWSER_LOG"] = str(self.browser)

    def tearDown(self) -> None:
        shutil.rmtree(self.directory, ignore_errors=True)

    def run_node(
        self, *args: str, cwd: Path | None = None, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        assert NODE is not None
        return subprocess.run(
            [NODE, *args],
            cwd=cwd or self.prefix,
            env=env or self.env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def entries(self) -> list[dict[str, object]]:
        return [json.loads(line) for line in self.channel.read_text(encoding="utf-8").splitlines()]

    def browser_log(self) -> list[str]:
        return self.browser.read_text(encoding="utf-8").splitlines() if self.browser.exists() else []

    def start_dsh(self, prefix: Path, port: int, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        start = str(ROOT / "launcher" / "start-dsh.mjs")
        arguments = ("--core", str(prefix), "--", "web", "--host", "127.0.0.1", "--port", str(port))
        return self.run_node(start, *arguments, cwd=prefix, env={**env, "FAKE_DSH_ONESHOT": "1"})

    def test_dsh_opener_is_captured_and_no_browser_opens(self) -> None:
        result = self.start_dsh(self.prefix, 4567, self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("opener exited 0", result.stdout)
        url = "http://127.0.0.1:4567/?token=fake-token-4567"
        kinds = {entry["kind"]: entry["url"] for entry in self.entries()}
        self.assertEqual(kinds, {"printed": url, "open": url})
        self.assertEqual(self.browser_log(), [])

    def test_a_global_install_nests_open_in_dsh(self) -> None:
        # `npm install --global` keeps each package's dependencies in its own node_modules.
        prefix = self.directory / "global" / "lib"
        make_prefix(prefix, open_under=prefix / "node_modules" / "@deepseek-ai" / "dsh")
        env = {**launch.dsh_environment(os.environ, prefix, self.channel), "FAKE_BROWSER_LOG": str(self.browser)}
        result = self.start_dsh(prefix, 4569, env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([entry["kind"] for entry in self.entries()], ["printed", "open"])
        self.assertEqual(self.browser_log(), [])

    def test_hook_reaches_the_child_through_the_scrub(self) -> None:
        # The child dsh spawns keeps NODE_OPTIONS and the channel's variable.
        scrubbed = {
            name for name in self.env if any(word in name.upper() for word in ("KEY", "PASSWORD", "SECRET", "TOKEN"))
        }
        self.assertFalse(scrubbed & {"NODE_OPTIONS", "HFX_DSH_OPEN_CHANNEL", "HFX_DSH_PREFIX"})
        self.assertIn(f"--import={(ROOT / 'launcher' / 'intercept.mjs').as_uri()}", self.env["NODE_OPTIONS"])

    def test_other_targets_reach_the_real_package(self) -> None:
        script = self.prefix / "other.mjs"
        script.write_text(
            'import open, { apps, openApp } from "open";\n'
            'await open("/tmp/a file.txt");\n'
            "await openApp(apps.browser);\n"
        )
        result = self.run_node(str(script))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.browser_log(), ["/tmp/a file.txt", "app:browser"])
        self.assertEqual(self.entries(), [])

    def test_open_outside_dsh_prefix_is_left_alone(self) -> None:
        project = self.directory / "project"
        write_open_package(project / "node_modules" / "open")
        (project / "main.mjs").write_text('import open from "open";\nawait open("http://127.0.0.1:9/");\n')
        result = self.run_node(str(project / "main.mjs"), cwd=project)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.browser_log(), ["http://127.0.0.1:9/"])
        self.assertEqual(self.entries(), [])

    def test_without_the_channel_nothing_is_replaced(self) -> None:
        env = {**self.env}
        del env["HFX_DSH_OPEN_CHANNEL"]
        result = self.start_dsh(self.prefix, 4568, env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.browser_log(), ["http://127.0.0.1:4568/?token=fake-token-4568"])


if __name__ == "__main__":
    unittest.main()

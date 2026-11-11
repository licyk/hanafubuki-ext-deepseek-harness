"""``start-dsh.mjs`` on the real Node: dsh's program from its package, its command line and its exit code."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.fake_dsh import make_prefix
from tests.support import NODE, ROOT, needs_node

START = ROOT / "launcher" / "start-dsh.mjs"


@needs_node
class StartDshTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.prefix = self.directory / "core"
        self.argv = self.directory / "argv.json"

    def tearDown(self) -> None:
        shutil.rmtree(self.directory, ignore_errors=True)

    def start(self, *dsh: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        assert NODE is not None
        return subprocess.run(
            [NODE, str(START), "--core", str(self.prefix), "--", *dsh],
            env={**os.environ, "FAKE_DSH_ARGV": str(self.argv), **(env or {})},
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def test_runs_the_program_bin_names_with_dsh_arguments(self) -> None:
        program = make_prefix(self.prefix, program="dist/cli.js")
        result = self.start("web", "--host", "127.0.0.1", "--port", "4570", env={"FAKE_DSH_EXIT": "0"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(self.argv.read_text()), [str(program), "web", "--host", "127.0.0.1", "--port", "4570"]
        )

    def test_dsh_exit_code_is_the_process(self) -> None:
        make_prefix(self.prefix)
        self.assertEqual(self.start("web", env={"FAKE_DSH_EXIT": "7"}).returncode, 7)

    def test_a_failing_dsh_exits_1(self) -> None:
        program = make_prefix(self.prefix)
        program.write_text('export async function runCli() { throw new Error("broken install"); }\n')
        result = self.start("web")
        self.assertEqual(result.returncode, 1)
        self.assertIn("broken install", result.stderr)

    def test_an_entry_that_runs_on_import_runs_once(self) -> None:
        program = make_prefix(self.prefix)
        program.write_text(
            'import { appendFileSync } from "node:fs";\n'
            "appendFileSync(process.env.FAKE_DSH_ARGV, JSON.stringify(process.argv.slice(2)) + '\\n');\n"
        )
        self.assertEqual(self.start("web", "--port", "1").returncode, 0)
        self.assertEqual(self.argv.read_text().splitlines(), ['["web","--port","1"]'])

    def test_not_installed(self) -> None:
        self.prefix.mkdir()
        result = self.start("web")
        self.assertEqual(result.returncode, 3)
        self.assertIn("DeepSeek Harness is not installed in", result.stderr)
        self.assertFalse(self.argv.exists())


if __name__ == "__main__":
    unittest.main()

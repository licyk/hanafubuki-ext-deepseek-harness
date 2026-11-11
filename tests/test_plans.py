"""The install parameters, the Node.js release choice and the plans the backend answers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import node_release
import plans
import spec
from tests.support import FIXTURES

INDEX = json.loads((FIXTURES / "node-index.json").read_text(encoding="utf-8"))
SHASUMS = (FIXTURES / "node-v24.11.0-SHASUMS256.txt").read_text(encoding="utf-8")


class ValuesTest(unittest.TestCase):
    def test_accepted_values(self) -> None:
        for version in ("latest", "next", "alpha", "0.2.2", "0.2.2-rc.1", None, ""):
            for node in ("24", "v24", "26", "lts", "LTS", "24.9.0", "24.11.0", None, " 24 "):
                with self.subTest(version=version, node=node):
                    self.assertEqual(spec.issues({"version": version, "nodeVersion": node}), {})

    def test_refused_values(self) -> None:
        cases = {
            ("-g", "24"): {"version": "version"},
            ("{param.x}", "24"): {"version": "version"},
            ("latest", "22"): {"nodeVersion": "nodeTooOld"},
            ("latest", "24.8.9"): {"nodeVersion": "nodeTooOld"},
            ("latest", "24.x"): {"nodeVersion": "nodeVersion"},
            ("latest", "current"): {"nodeVersion": "nodeVersion"},
        }
        for (version, node), expected in cases.items():
            with self.subTest(version=version, node=node):
                self.assertEqual(spec.issues({"version": version, "nodeVersion": node}), expected)

    def test_versions_sort_by_precedence(self) -> None:
        versions = ["0.2.2-rc.1", "0.2.10", "0.2.2", "0.2.2-alpha.3", "0.2.2-rc.10", "0.2.2-rc.2"]
        self.assertEqual(
            sorted(versions, key=spec.version_key),
            ["0.2.2-alpha.3", "0.2.2-rc.1", "0.2.2-rc.2", "0.2.2-rc.10", "0.2.2", "0.2.10"],
        )


class NodeReleaseTest(unittest.TestCase):
    def test_archive_per_platform_and_arch(self) -> None:
        expected = {
            ("linux", "x64"): "node-v24.22.3-linux-x64.tar.xz",
            ("linux", "arm64"): "node-v24.22.3-linux-arm64.tar.xz",
            ("macos", "arm64"): "node-v24.22.3-darwin-arm64.tar.xz",
            ("macos", "x64"): "node-v24.22.3-darwin-x64.tar.xz",
            ("windows", "x64"): "node-v24.22.3-win-x64.zip",
            ("windows", "arm64"): "node-v24.22.3-win-arm64.zip",
        }
        for (platform, arch), filename in expected.items():
            with self.subTest(platform=platform, arch=arch):
                release = node_release.select(INDEX, "24", platform, arch)
                self.assertEqual(release.filename, filename)
                self.assertEqual(release.url, f"https://nodejs.org/dist/v24.22.3/{filename}")

    def test_spec_kinds(self) -> None:
        self.assertEqual(node_release.select(INDEX, "lts", "linux", "x64").version, "26.13.1")
        self.assertEqual(node_release.select(INDEX, "24.11.0", "linux", "x64").version, "24.11.0")
        self.assertEqual(node_release.select(INDEX, "26", "linux", "x64").version, "26.13.1")
        # A pre-release major is never chosen.
        with self.assertRaises(node_release.ReleaseError):
            node_release.select(INDEX, "27", "linux", "x64")
        with self.assertRaises(node_release.ReleaseError):
            node_release.select(INDEX, "24.8.0", "linux", "x64")
        with self.assertRaises(node_release.ReleaseError):
            node_release.select(INDEX, "24", "freebsd", "x64")

    def test_mirror(self) -> None:
        release = node_release.select(INDEX, "24.11.0", "windows", "x64", "https://cdn.npmmirror.com/binaries/node/")
        self.assertEqual(release.url, "https://cdn.npmmirror.com/binaries/node/v24.11.0/node-v24.11.0-win-x64.zip")
        self.assertEqual(
            node_release.shasums_url(release, "https://cdn.npmmirror.com/binaries/node"),
            "https://cdn.npmmirror.com/binaries/node/v24.11.0/SHASUMS256.txt",
        )

    def test_digest_from_shasums(self) -> None:
        expected = {
            "linux": "46da9a098973ab7ba4fca76945581ecb2eaf468de347173897044382f10e0a0a",
            "macos": "30bbe12b71f5b89ba44e15dc0cfaf3c733538d46ee375691534b7bbe622225cc",
            "windows": "1054540bce22b54ec7e50ebc078ec5d090700a77657607a58f6a64df21f49fdd",
        }
        for platform, digest in expected.items():
            arch = "arm64" if platform == "macos" else "x64"
            release = node_release.with_digest(node_release.select(INDEX, "24.11.0", platform, arch), SHASUMS)
            self.assertEqual(release.sha256, digest)
        with self.assertRaises(node_release.ReleaseError):
            node_release.with_digest(node_release.select(INDEX, "24.11.0", "linux", "x64"), "")

    def test_machine_names(self) -> None:
        self.assertEqual(node_release.machine_arch("x86_64"), "x64")
        self.assertEqual(node_release.machine_arch("AMD64"), "x64")
        self.assertEqual(node_release.machine_arch("aarch64"), "arm64")
        self.assertEqual(node_release.machine_arch("ARM64"), "arm64")
        with self.assertRaises(node_release.ReleaseError):
            node_release.machine_arch("riscv64")


class PlanTest(unittest.TestCase):
    release = node_release.with_digest(node_release.select(INDEX, "24.11.0", "linux", "x64"), SHASUMS)

    def test_install_downloads_node_then_runs_npm(self) -> None:
        steps = plans.install_steps("linux", {"version": "next", "nodeVersion": "24.11.0"}, self.release, "24.11.0")
        self.assertEqual(
            steps[0],
            {
                "kind": "download",
                "url": self.release.url,
                "sha256": "46da9a098973ab7ba4fca76945581ecb2eaf468de347173897044382f10e0a0a",
                "unpackTo": "{component.node}",
                "strip": 1,
            },
        )
        self.assertEqual(
            steps[1]["command"],
            [
                "{component.node}/bin/node",
                "{component.node}/lib/node_modules/npm/bin/npm-cli.js",
                "install",
                "--prefix",
                "{component.core}",
                "--no-fund",
                "--no-audit",
                "@deepseek-ai/dsh@next",
            ],
        )
        self.assertEqual(steps[1]["cwd"], "{component.node}")
        self.assertEqual(steps[2]["path"], "{component.core}/hanafubuki-install.txt")
        self.assertEqual(steps[2]["content"], "version=next\nnodeVersion=24.11.0\nnode=24.11.0\n")

    def test_windows_runs_npm_from_node_root(self) -> None:
        steps = plans.install_steps("windows", {}, self.release, "24.11.0")
        self.assertEqual(
            steps[1]["command"][:2], ["{component.node}/node.exe", "{component.node}/node_modules/npm/bin/npm-cli.js"]
        )
        self.assertEqual(steps[1]["command"][-1], "@deepseek-ai/dsh@latest")

    def test_update_keeps_or_replaces_node(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            node = Path(directory) / "node"
            (node / "bin").mkdir(parents=True)
            (node / "bin" / "node").write_text("")
            marker = plans.Marker("latest", "24", "24.11.0")
            self.assertTrue(plans.keeps_node("update", {"nodeVersion": "24"}, marker, node, "linux"))
            self.assertTrue(plans.keeps_node("update", {}, marker, node, "linux"))
            self.assertFalse(plans.keeps_node("update", {"nodeVersion": "26"}, marker, node, "linux"))
            self.assertFalse(plans.keeps_node("install", {"nodeVersion": "24"}, marker, node, "linux"))
            self.assertFalse(plans.keeps_node("update", {"nodeVersion": "24"}, marker, node, "windows"))
            self.assertFalse(plans.keeps_node("update", {"nodeVersion": "24"}, None, node, "linux"))

        kept = plans.install_steps("linux", {"version": "0.2.2"}, None, "24.11.0")
        self.assertEqual([step["kind"] for step in kept], ["run", "write-file"])
        self.assertIn("node=24.11.0\n", kept[1]["content"])
        replaced = plans.install_steps("linux", {"nodeVersion": "26"}, self.release, "24.11.0", clean_node=True)
        self.assertEqual([step["kind"] for step in replaced], ["run", "download", "run", "write-file"])
        self.assertEqual(
            replaced[0]["command"], ["{host.python}", "{extension.root}/launcher/empty_dir.py", "{component.node}"]
        )
        # Windows does not remove a process's working directory: the step empties it.
        self.assertEqual(replaced[0]["cwd"], "{component.node}")

    def test_text_the_backend_did_not_write_stays_literal(self) -> None:
        steps = plans.install_steps("linux", {}, self.release, "24.11.0", registry="https://mirror.example/{x}")
        self.assertEqual(steps[1]["env"], {"npm_config_registry": "https://mirror.example/{{x}}"})
        self.assertEqual(plans.install_steps("linux", {}, self.release, "24.11.0")[1]["env"], {})

    def test_marker_reads_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            core = Path(directory)
            self.assertIsNone(plans.read_marker(core))
            (core / plans.MARKER).write_text(plans.Marker("next", "lts", "26.13.1").text())
            self.assertEqual(plans.read_marker(core), plans.Marker("next", "lts", "26.13.1"))

    def test_launch_command(self) -> None:
        for platform, node in (("linux", "{component.node}/bin/node"), ("windows", "{component.node}/node.exe")):
            command = plans.launch_command(platform)
            self.assertEqual(
                command["argv"],
                [
                    "{host.python}",
                    "{extension.root}/launcher/launch.py",
                    "--core",
                    "{component.core}",
                    "--node",
                    node,
                    "--port",
                    "{port}",
                ],
            )


class EmptyDirTest(unittest.TestCase):
    def test_empties_and_tolerates_missing(self) -> None:
        import empty_dir

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "node"
            (target / "lib").mkdir(parents=True)
            (target / "lib" / "x").write_text("x")
            (target / "CHANGELOG.md").write_text("x")
            self.assertEqual(empty_dir.main([str(target), str(Path(directory) / "missing")]), 0)
            self.assertTrue(target.is_dir())
            self.assertEqual(list(target.iterdir()), [])


if __name__ == "__main__":
    unittest.main()

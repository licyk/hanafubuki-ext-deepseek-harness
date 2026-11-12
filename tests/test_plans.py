"""The install parameters, the Node.js release choice and the plans the backend answers."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import layout
import node_release
import plans
import spec
from tests.support import FIXTURES

INDEX = json.loads((FIXTURES / "node-index.json").read_text(encoding="utf-8"))
SHASUMS = (FIXTURES / "node-v24.11.0-SHASUMS256.txt").read_text(encoding="utf-8")


class ValuesTest(unittest.TestCase):
    def test_accepted_values(self) -> None:
        for version in ("latest", "next", "alpha", "0.2.2", "0.2.2-rc.1", None, ""):
            for node in ("24", "v24", "26", "lts", "LTS", "latest", "24.9.0", "24.11.0", None, " 24 "):
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
        # The newest release, not a pre-release.
        self.assertEqual(node_release.select(INDEX, "latest", "linux", "x64").version, "26.13.1")
        # A major names its newest release, so it moves on as the index does.
        self.assertEqual(node_release.select(INDEX, "24", "linux", "x64").version, "24.22.3")
        older = [entry for entry in INDEX if entry["version"] != "v24.22.3"]
        self.assertEqual(node_release.select(older, "24", "linux", "x64").version, "24.11.0")
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

    def test_musl_takes_the_musl_build_or_says_where_one_is(self) -> None:
        release = node_release.select(INDEX, "24", "linux", "x64", libc="musl")
        self.assertEqual(release.filename, "node-v24.22.3-linux-x64-musl.tar.xz")
        self.assertEqual(release.url, "https://nodejs.org/dist/v24.22.3/node-v24.22.3-linux-x64-musl.tar.xz")
        # musl changes nothing elsewhere.
        self.assertEqual(node_release.select(INDEX, "24", "macos", "arm64", libc="musl").filename.count("musl"), 0)
        for node_spec, arch in (("24.11.0", "x64"), ("24", "arm64")):
            with self.subTest(spec=node_spec, arch=arch), self.assertRaises(node_release.ReleaseError) as refused:
                node_release.select(INDEX, node_spec, "linux", arch, "https://mirror.example/node", libc="musl")
            self.assertIn("musl", str(refused.exception))
            self.assertIn("https://mirror.example/node", str(refused.exception))
            self.assertIn(node_release.MUSL_MIRROR, str(refused.exception))

    def test_machine_names(self) -> None:
        self.assertEqual(node_release.machine_arch("x86_64"), "x64")
        self.assertEqual(node_release.machine_arch("AMD64"), "x64")
        self.assertEqual(node_release.machine_arch("aarch64"), "arm64")
        self.assertEqual(node_release.machine_arch("ARM64"), "arm64")
        with self.assertRaises(node_release.ReleaseError):
            node_release.machine_arch("riscv64")


LINUX = layout.own("linux")


def components(core: Path, node: Path, core_external: bool = False, node_external: bool = False) -> layout.Components:
    return layout.Components(layout.Component(core, core_external), layout.Component(node, node_external))


class PlanTest(unittest.TestCase):
    release = node_release.with_digest(node_release.select(INDEX, "24.11.0", "linux", "x64"), SHASUMS)

    def test_install_downloads_node_replacing_it_then_runs_npm(self) -> None:
        steps = plans.install_steps(LINUX, {"version": "next", "nodeVersion": "24.11.0"}, self.release, "24.11.0")
        self.assertEqual([step["kind"] for step in steps], ["download", "write-file", "run", "write-file"])
        self.assertEqual(
            steps[0],
            {
                "kind": "download",
                "url": self.release.url,
                "sha256": "46da9a098973ab7ba4fca76945581ecb2eaf468de347173897044382f10e0a0a",
                "unpackTo": "{component.node}",
                "strip": 1,
                "replace": True,
            },
        )
        self.assertEqual(steps[1]["path"], "{component.core}/.npmrc")
        self.assertEqual(
            steps[2]["command"],
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
        self.assertEqual(steps[2]["cwd"], "{component.node}")
        # The registry is the instance's .npmrc, which the type's environment names.
        self.assertEqual(steps[2]["env"], {})
        self.assertEqual(steps[3]["path"], "{component.core}/hanafubuki-install.txt")
        self.assertEqual(steps[3]["content"], "version=next\nnodeVersion=24.11.0\nnode=24.11.0\n")

    def test_windows_runs_npm_from_node_root(self) -> None:
        steps = plans.install_steps(layout.own("windows"), {}, self.release, "24.11.0")
        self.assertEqual(
            steps[2]["command"][:2], ["{component.node}/node.exe", "{component.node}/node_modules/npm/bin/npm-cli.js"]
        )
        self.assertEqual(steps[2]["command"][-1], "@deepseek-ai/dsh@latest")

    def test_update_keeps_node_only_for_the_release_it_resolves_to(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            node = Path(directory) / "node"
            (node / "bin").mkdir(parents=True)
            (node / "bin" / "node").write_text("")
            marker = plans.Marker("latest", "24", "24.11.0")
            program = LINUX.path(LINUX.node, components(Path(directory) / "core", node))
            self.assertTrue(plans.keeps_node("update", marker, "24.11.0", program))
            # `24` now resolves to a newer 24.x: the update downloads it.
            self.assertFalse(plans.keeps_node("update", marker, "24.22.3", program))
            self.assertFalse(plans.keeps_node("install", marker, "24.11.0", program))
            self.assertFalse(plans.keeps_node("update", None, "24.11.0", program))
            self.assertFalse(plans.keeps_node("update", marker, "24.11.0", node / "node.exe"))

        kept = plans.install_steps(LINUX, {"version": "0.2.2"}, None, "24.11.0")
        self.assertEqual([step["kind"] for step in kept], ["write-file", "run", "write-file"])
        self.assertIn("node=24.11.0\n", kept[2]["content"])

    def test_npmrc_holds_the_registry_and_text_the_backend_did_not_write_stays_literal(self) -> None:
        steps = plans.install_steps(LINUX, {}, self.release, "24.11.0", registry="https://mirror.example/{x}")
        self.assertTrue(steps[1]["content"].endswith("\nregistry=https://mirror.example/{{x}}\n"))
        plain = plans.install_steps(LINUX, {}, self.release, "24.11.0")[1]["content"]
        self.assertNotIn("registry=", plain)
        self.assertTrue(plain.startswith("# "))

    def test_marker_reads_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            core = Path(directory)
            self.assertIsNone(plans.read_marker(core))
            (core / plans.MARKER).write_text(plans.Marker("next", "lts", "26.13.1").text())
            self.assertEqual(plans.read_marker(core), plans.Marker("next", "lts", "26.13.1"))

    def test_launch_command(self) -> None:
        cases = (
            (layout.own("linux"), "{component.core}", "{component.node}/bin/node"),
            (layout.own("windows"), "{component.core}", "{component.node}/node.exe"),
            (layout.global_prefix("linux"), "{component.core}/lib", "{component.core}/bin/node"),
            (layout.global_prefix("windows"), "{component.core}", "{component.core}/node.exe"),
        )
        for kind, core, node in cases:
            command = plans.launch_command(kind, "instance")
            self.assertEqual(
                command["argv"],
                [
                    "{host.python}",
                    "{extension.root}/launcher/launch.py",
                    "--core",
                    core,
                    "--node",
                    node,
                    "--port",
                    "{port}",
                ],
            )

    def test_dsh_home_per_choice(self) -> None:
        # `instance`: the type's environment (DSH_HOME under the root) stands.
        self.assertEqual(plans.launch_command(LINUX, "instance")["env"], {})
        # `user`: emptied, which dsh reads as unset, so its ~/.dsh and ~/.agents.
        self.assertEqual(plans.launch_command(LINUX, "user")["env"], {"DSH_HOME": "", "DSH_AGENTS_HOME": ""})
        self.assertEqual(spec.home({}), "instance")
        self.assertEqual(spec.home({"home": "user"}), "user")

    def test_a_global_prefix_runs_its_own_npm_globally_and_nothing_else(self) -> None:
        for platform, node, npm in (
            ("linux", "{component.core}/bin/node", "{component.core}/lib/node_modules/npm/bin/npm-cli.js"),
            ("windows", "{component.core}/node.exe", "{component.core}/node_modules/npm/bin/npm-cli.js"),
        ):
            [step] = plans.global_install_steps(layout.global_prefix(platform), {"version": "0.2.2"}, "https://r/")
            self.assertEqual(
                step["command"],
                [
                    node,
                    npm,
                    "install",
                    "--global",
                    "--prefix",
                    "{component.core}",
                    "--no-fund",
                    "--no-audit",
                    "@deepseek-ai/dsh@0.2.2",
                ],
            )
            self.assertEqual(step["cwd"], "{component.core}")
            # Nothing is written in the user's prefix: the registry is the step's.
            self.assertEqual(step["env"], {"npm_config_registry": "https://r/"})


class LayoutTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def touch(self, *paths: str) -> None:
        for path in paths:
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            (self.root / path).write_text("")

    def test_a_unix_global_prefix(self) -> None:
        self.touch("bin/node", "lib/node_modules/@deepseek-ai/dsh/package.json")
        parts = components(self.root, self.root / "bin", True, True)
        found = layout.read(parts, "linux")
        self.assertEqual(found, layout.global_prefix("linux"))
        self.assertEqual(found.path(found.node, parts), self.root / "bin" / "node")
        self.assertEqual(found.path(found.dsh_prefix, parts), self.root / "lib")
        self.assertEqual(layout.read(parts, "windows"), layout.own("windows"))
        self.assertEqual(layout.below_root(self.root, "linux"), parts)

    def test_a_windows_global_prefix(self) -> None:
        self.touch("node.exe", "node_modules/@deepseek-ai/dsh/package.json")
        parts = components(self.root, self.root / "node_modules" / "npm", True, True)
        found = layout.read(parts, "windows")
        self.assertEqual(found, layout.global_prefix("windows"))
        self.assertEqual(found.path(found.npm, parts), self.root / "node_modules/npm/bin/npm-cli.js")
        self.assertEqual(layout.below_root(self.root, "windows"), parts)

    def test_a_global_prefix_without_dsh_is_still_one(self) -> None:
        # dsh uninstalled, or a global install that stopped: the Node.js is still the user's.
        self.touch("bin/node", "node.exe")
        parts = components(self.root, self.root / "bin")
        self.assertEqual(layout.read(parts, "linux"), layout.global_prefix("linux"))
        self.assertEqual(layout.read(parts, "windows"), layout.global_prefix("windows"))

    def test_everything_else_is_the_extension_own(self) -> None:
        own = layout.below_root(self.root, "linux")
        self.assertEqual(own, components(self.root / "core", self.root / "node"))
        self.assertEqual(layout.read(own, "linux"), layout.own("linux"))
        self.touch("node/bin/node", "node/node.exe", "core/node_modules/@deepseek-ai/dsh/package.json")
        self.assertEqual(layout.read(own, "linux"), layout.own("linux"))
        self.assertEqual(layout.read(own, "windows"), layout.own("windows"))
        found = layout.own("linux")
        self.assertEqual(found.path(found.node, own), self.root / "node" / "bin" / "node")

    def test_the_components_the_host_sends(self) -> None:
        elsewhere = self.root / "elsewhere"
        sent = {
            "id": "dsh-1",
            "components": {
                "core": {"path": str(self.root / "core"), "external": False},
                "node": {"path": str(elsewhere), "external": True},
                "unknown": {"path": "x"},
            },
        }
        parts = layout.components(sent)
        self.assertEqual(parts, components(self.root / "core", elsewhere, False, True))
        assert parts is not None
        self.assertEqual(layout.components({"components": parts.to_protocol()}), parts)
        # The user's Node.js in `node` is still the own layout: its program is `<node>/bin/node`.
        found = layout.read(parts, "linux")
        self.assertEqual(found.path(found.node, parts), elsewhere / "bin" / "node")
        self.assertIsNone(layout.components({"id": "dsh-1"}))
        self.assertIsNone(layout.components({"components": {"core": {"path": "a"}}}))


if __name__ == "__main__":
    unittest.main()

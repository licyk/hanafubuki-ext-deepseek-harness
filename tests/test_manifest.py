"""The package as the host reads it: the manifest, what it contributes, its strings, its frame and its archive."""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path
from typing import Any

import layout
import plans
from tests.support import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import package

EXTENSION_ID = "io.github.licyk.deepseek-harness"
KEY = re.compile(r"ext\.io\.github\.licyk\.deepseek-harness\.([A-Za-z0-9_.-]+)")


def manifest() -> dict[str, Any]:
    return tomllib.loads((ROOT / "hanafubuki-extension.toml").read_text(encoding="utf-8"))


def descriptor() -> dict[str, Any]:
    return tomllib.loads((ROOT / "types" / "dsh.toml").read_text(encoding="utf-8"))


def flatten(strings: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for name, value in strings.items():
        if isinstance(value, dict):
            flat.update(flatten(value, f"{prefix}{name}."))
        else:
            flat[f"{prefix}{name}"] = value
    return flat


def locale(name: str) -> dict[str, str]:
    return flatten(json.loads((ROOT / "locales" / f"{name}.json").read_text(encoding="utf-8")))


class ManifestTest(unittest.TestCase):
    def test_manifest(self) -> None:
        document = manifest()
        self.assertEqual(document["id"], EXTENSION_ID)
        self.assertEqual(document["engines"], {"hanafubuki": ">=0.3.30, <0.4", "api": 1})
        self.assertEqual(document["backend"], {"python": "backend/main.py", "sdWebuiAllInOne": True})
        self.assertTrue((ROOT / document["backend"]["python"]).is_file())
        self.assertEqual(document["permissions"]["instances"], "own-types")
        self.assertNotIn("processes", document["permissions"])

    def test_every_contributed_path_exists(self) -> None:
        contributes = manifest()["contributes"]
        self.assertEqual(sorted(path.name for path in ROOT.glob(contributes["instanceTypes"])), ["dsh.toml"])
        self.assertTrue((ROOT / contributes["settings"]).is_file())
        for name in ("en", "zh"):
            self.assertTrue((ROOT / contributes["locales"].replace("{locale}", name)).is_file())
        for entry in contributes["ui"]:
            self.assertTrue((ROOT / entry["entry"]).is_file(), entry)
        self.assertTrue((ROOT / descriptor()["preview"]).is_file())
        for script in ("launch.py", "start-dsh.mjs", "intercept.mjs", "open-stub.mjs"):
            self.assertTrue((ROOT / "launcher" / script).is_file(), script)

    def test_type(self) -> None:
        document = descriptor()
        self.assertEqual(document["provider"], "backend")
        core, node = document["components"]
        self.assertEqual((core["name"], core["external"]), ("core", "allowed"))
        self.assertNotIn("executable", core)
        self.assertEqual((node["name"], node["external"]), ("node", "allowed"))
        # The program the Paths panel picks: Node's own layout, as the backend's plans address it.
        self.assertEqual(node["executable"], {"unix": "bin/node", "windows": "node.exe"})
        for platform in ("linux", "windows"):
            own = layout.own(platform)
            program = node["executable"]["windows" if platform == "windows" else "unix"]
            self.assertEqual(own.node, f"{{component.node}}/{program}")
        self.assertEqual(document["runtime"], {"kind": "none"})
        self.assertEqual(document["management"]["operations"], ["update", "terminal", "copy-user-home"])
        self.assertNotIn("steps", document.get("install", {}))
        [server] = document["servers"]
        self.assertEqual(server["role"], "web")
        self.assertNotIn("command", server)
        self.assertEqual(server["readiness"], {"captured": True, "timeoutSeconds": 180})
        self.assertEqual(server["port"], {"allocate": True})
        self.assertTrue(server["webview"])
        self.assertEqual(server["restart"], "on-failure")
        defaults = {parameter["name"]: parameter["default"] for parameter in document["install"]["parameters"]}
        self.assertEqual(defaults, {"version": "latest", "nodeVersion": "24", "home": "instance"})
        [home] = [parameter for parameter in document["install"]["parameters"] if parameter["name"] == "home"]
        self.assertEqual([option["value"] for option in home["options"]], ["instance", "user"])
        own, unix, windows = document["discovery"]
        self.assertEqual(own["markers"], ["core/node_modules/@deepseek-ai/dsh/package.json", "node"])
        self.assertEqual(unix["markers"], ["bin/node", "lib/node_modules/@deepseek-ai/dsh/package.json"])
        self.assertEqual(unix["components"], {"core": ".", "node": "bin"})
        self.assertEqual(
            windows["markers"],
            ["node.exe", "node_modules/@deepseek-ai/dsh/package.json", "node_modules/npm/package.json"],
        )
        self.assertEqual(windows["components"], {"core": ".", "node": "node_modules/npm"})
        self.assertNotIn("external", own)
        for signature in (unix, windows):
            # The prefix is the user's Node.js: never deleted with the instance, and its dsh's home is ~/.dsh.
            self.assertEqual(signature["external"], ["core", "node"])
            self.assertEqual(signature["values"], {**defaults, "home": "user"})

    def test_environment_isolates_npm_node_and_dsh(self) -> None:
        environment = descriptor()["environment"]
        self.assertEqual(environment["unset"], ["npm_config_*", "NPM_CONFIG_*", "NODE_OPTIONS", "NODE_PATH"])
        self.assertEqual(
            environment["vars"],
            {
                "npm_config_userconfig": "{component.core}/.npmrc",
                "npm_config_globalconfig": "{component.node}/etc/npmrc",
                "npm_config_prefix": "{component.core}",
                "npm_config_cache": "{instance.root}/.npm-cache",
                "npm_config_update_notifier": "false",
                "DSH_HOME": "{instance.root}/dsh-home",
                "DSH_AGENTS_HOME": "{instance.root}/agents-home",
            },
        )
        path = environment["path"]
        # dsh by name is the instance's: its packages' programs come before
        # everything; the prefix's global programs before Node's own.
        self.assertEqual(
            path,
            [
                "{component.core}/node_modules/.bin",
                "{component.core}/bin",
                "{component.core}",
                "{component.node}",
                "{component.node}/bin",
            ],
        )
        self.assertLess(path.index("{component.core}/node_modules/.bin"), path.index("{component.core}"))
        # The homes the launch plan's `user` empties are the ones the environment sets.
        user = plans.launch_command(layout.own("linux"), "user")["env"]
        self.assertEqual(set(user), {name for name in environment["vars"] if name.startswith("DSH_")})

    def test_each_signature_is_the_layout_the_backend_reads(self) -> None:
        # A tree holding just a signature's markers: the host attaches its root with
        # those components, and the backend's plans for those components name what is there.
        expected = {0: ("linux", False), 1: ("linux", True), 2: ("windows", True)}
        for index, signature in enumerate(descriptor()["discovery"]):
            platform, global_prefix = expected[index]
            with self.subTest(signature=index), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for marker in signature["markers"]:
                    (root / marker).parent.mkdir(parents=True, exist_ok=True)
                    if marker == "node":  # the own layout's Node.js directory
                        (root / marker).mkdir()
                    else:
                        (root / marker).write_text("{}")
                mapped = {"core": "core", "node": "node", **signature.get("components", {})}
                paths = {name: (root / path).resolve() for name, path in mapped.items()}
                for name, path in paths.items():
                    self.assertTrue(path.is_dir(), name)
                # The host's rule (InstancePathPolicy::validate_component_layout): no
                # component equals another, only `core` may be the root, and another
                # lies inside it only then. So a prefix's `node` cannot be the prefix.
                node, core = paths["node"], paths["core"]
                self.assertNotEqual(node, core)
                self.assertNotEqual(node, root.resolve())
                self.assertFalse(core.is_relative_to(node))
                if node.is_relative_to(core):
                    self.assertEqual(core, root.resolve())

                external = set(signature.get("external", []))
                sent = layout.Components(
                    layout.Component(paths["core"], "core" in external),
                    layout.Component(paths["node"], "node" in external),
                )
                kind = layout.read(sent, platform)
                self.assertEqual(kind.global_prefix, global_prefix)
                # What the backend falls back to for a root no provider call described.
                self.assertEqual(layout.below_root(root.resolve(), platform), sent)
                if global_prefix:
                    self.assertTrue(kind.path(kind.node, sent).is_file())
                    self.assertTrue((kind.path(kind.dsh_prefix, sent) / layout.PACKAGE_JSON).is_file())

    def test_preview_is_a_16_9_png(self) -> None:
        data = (ROOT / descriptor()["preview"]).read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
        self.assertEqual((width, height), (1280, 720))
        self.assertLess(len(data), 200_000)


class StringsTest(unittest.TestCase):
    def test_locales_hold_the_same_keys(self) -> None:
        self.assertEqual(set(locale("en")), set(locale("zh")))

    def test_every_key_used_is_defined(self) -> None:
        used = set()
        for path in (ROOT / "types" / "dsh.toml", ROOT / "schemas" / "settings.json"):
            used |= set(KEY.findall(path.read_text(encoding="utf-8")))
        self.assertTrue(used)
        for name in ("en", "zh"):
            self.assertEqual(used - set(locale(name)), set(), name)

    def test_frame_keys_cover_the_page(self) -> None:
        source = (ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8")
        used = set(re.findall(r"""\bt\(\s*["']([A-Za-z]+)["']""", source))
        self.assertEqual(used - {key.removeprefix("frame.") for key in locale("en") if key.startswith("frame.")}, set())


class LayoutTest(unittest.TestCase):
    def test_no_link_anywhere_in_the_folder(self) -> None:
        # A development link refuses the whole folder for one (web/node_modules included).
        links = [
            os.path.relpath(os.path.join(directory, name), ROOT)
            for directory, directories, files in os.walk(ROOT)
            for name in directories + files
            if os.path.islink(os.path.join(directory, name))
        ]
        self.assertEqual(links, [])

    def test_built_frame_fits_the_frame_policy(self) -> None:
        page = (ROOT / "ui" / "versions" / "index.html").read_text(encoding="utf-8")
        scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", page, re.S)
        self.assertTrue(scripts)
        for attributes, body in scripts:
            self.assertEqual(body.strip(), "", "an inline script is refused")
            self.assertIn('src="./', attributes)
        self.assertNotRegex(page, r"""(src|href)="/""")
        script = (ROOT / "ui" / "versions" / "index.js").read_text(encoding="utf-8")
        # From ui/versions/index.js, ../../ is the package root, where the host serves the client.
        self.assertIn('from"../../__hanafubuki/frame.js"', script.replace(" ", ""))
        self.assertNotRegex(script, r"\bfetch\(|new Function|\beval\(")
        self.assertFalse((ROOT / "__hanafubuki").exists())


class PackageTest(unittest.TestCase):
    def test_archive_holds_the_package_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = package.build(Path(directory))
            self.assertEqual(archive.name, f"{EXTENSION_ID}-{manifest()['version']}.zip")
            with zipfile.ZipFile(archive) as bundle:
                names = set(bundle.namelist())
        for required in (
            "hanafubuki-extension.toml",
            "types/dsh.toml",
            "locales/en.json",
            "locales/zh.json",
            "schemas/settings.json",
            "images/preview.png",
            "backend/main.py",
            "launcher/launch.py",
            "launcher/start-dsh.mjs",
            "launcher/intercept.mjs",
            "launcher/open-stub.mjs",
            "ui/versions/index.html",
            "ui/versions/index.js",
        ):
            self.assertIn(required, names)
        for name in names:
            self.assertFalse(name.startswith(("web/", "tests/", "scripts/", ".git")), name)
            self.assertNotIn("__pycache__", name)


if __name__ == "__main__":
    unittest.main()

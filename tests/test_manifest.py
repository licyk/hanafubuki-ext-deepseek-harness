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
        self.assertEqual(document["engines"], {"hanafubuki": ">=0.3.28, <0.4", "api": 1})
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
        for script in ("launch.py", "intercept.mjs", "open-stub.mjs", "remove_tree.py"):
            self.assertTrue((ROOT / "launcher" / script).is_file(), script)

    def test_type(self) -> None:
        document = descriptor()
        self.assertEqual(document["provider"], "backend")
        self.assertEqual([component["name"] for component in document["components"]], ["core", "node"])
        self.assertEqual(document["runtime"], {"kind": "none"})
        self.assertEqual(document["environment"]["path"], ["{component.node}", "{component.node}/bin"])
        self.assertEqual(document["management"]["operations"], ["update", "terminal"])
        self.assertNotIn("steps", document.get("install", {}))
        [server] = document["servers"]
        self.assertEqual(server["role"], "web")
        self.assertNotIn("command", server)
        self.assertEqual(server["readiness"], {"captured": True, "timeoutSeconds": 180})
        self.assertEqual(server["port"], {"allocate": True})
        self.assertTrue(server["webview"])
        self.assertEqual(server["restart"], "on-failure")
        defaults = {parameter["name"]: parameter["default"] for parameter in document["install"]["parameters"]}
        self.assertEqual(defaults, {"version": "latest", "nodeVersion": "24"})
        [signature] = document["discovery"]
        self.assertEqual(signature["markers"], ["core/node_modules/@deepseek-ai/dsh/package.json", "node"])

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

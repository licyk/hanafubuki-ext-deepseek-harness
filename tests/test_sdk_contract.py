"""What the package relies on from Hanafubuki: its frame client and the typings the page builds against.

The typings under ``web/hanafubuki/`` are verbatim copies of the host's
``sdk/frame/frame.d.ts`` and ``sdk/ui/ui.d.ts``, so the page is type-checked
against the real contract rather than against a hand-kept restatement. A
sibling checkout (``../Hanafubuki-dev``, or ``HANAFUBUKI_CHECKOUT``) is
compared byte for byte; without one, the functions this page calls are still
checked to be declared, which needs no checkout at all.
"""

from __future__ import annotations

import json
import os
import re
import unittest
from pathlib import Path

from tests.support import ROOT

VENDORED = ROOT / "web" / "hanafubuki"
WEB_SRC = ROOT / "web" / "src"
# What the page asks the backend's strings for, as `page.t("key")`.
PAGE_KEY = re.compile(r'\bpage\.t\(\s*"([A-Za-z0-9_]+)"')
# The host's own copies, by the name the page builds against.
UPSTREAM = {
    "frame.d.ts": Path("sdk") / "frame" / "frame.d.ts",
    "ui.d.ts": Path("sdk") / "ui" / "ui.d.ts",
}
CHECKOUT = next(
    (
        Path(candidate)
        for candidate in (
            os.environ.get("HANAFUBUKI_CHECKOUT"),
            ROOT.parent / "Hanafubuki-dev",
        )
        if candidate and (Path(candidate) / "sdk").is_dir()
    ),
    None,
)


class TypingsTest(unittest.TestCase):
    def test_the_copies_are_the_hosts_own_when_a_checkout_is_there(self) -> None:
        if CHECKOUT is None:
            self.skipTest("no Hanafubuki checkout to compare with (HANAFUBUKI_CHECKOUT)")
        for name, relative in UPSTREAM.items():
            with self.subTest(typing=name):
                self.assertEqual(
                    (VENDORED / name).read_bytes(),
                    (CHECKOUT / relative).read_bytes(),
                    f"web/hanafubuki/{name} is not the host's {relative.as_posix()}",
                )


class FrameClientTest(unittest.TestCase):
    """The frame client's functions the page calls, as its typings declare them."""

    def source(self, name: str) -> str:
        return (VENDORED / name).read_text(encoding="utf-8")

    def test_the_page_calls_only_functions_the_client_declares(self) -> None:
        page = (ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8")
        called = set(re.findall(r"\bclient\.([A-Za-z]+)\(", page))
        self.assertTrue(called, "the page calls nothing on the frame client")
        declared = set(re.findall(r"^export function ([A-Za-z]+)", self.source("frame.d.ts"), re.M))
        self.assertEqual(called - declared, set())

    def test_the_components_and_helpers_the_page_uses_are_exported(self) -> None:
        page = (ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8")
        block = re.search(r"import \{([^}]+)\} from \"hanafubuki-ui\";", page)
        assert block is not None, "the page imports hanafubuki-ui"
        used = {name.strip() for name in block.group(1).split(",") if name.strip()}
        exported = set(re.findall(r"^export declare (?:const|function) ([A-Za-z_]+)", self.source("ui.d.ts"), re.M))
        self.assertEqual(used - exported, set())


class PageStringsTest(unittest.TestCase):
    """The page's own strings: the keys its views ask for, in both locales."""

    def asked(self) -> set[str]:
        found: set[str] = set()
        for path in WEB_SRC.rglob("*"):
            if path.suffix in (".vue", ".ts"):
                found |= set(PAGE_KEY.findall(path.read_text(encoding="utf-8")))
        return found

    def test_every_key_the_page_asks_for_is_in_both_locales(self) -> None:
        asked = self.asked()
        self.assertTrue(asked, "the page asks for no string")
        for name in ("en", "zh"):
            frame = json.loads((ROOT / "locales" / f"{name}.json").read_text(encoding="utf-8"))["frame"]
            with self.subTest(locale=name):
                self.assertEqual(asked - set(frame), set())

    def test_the_locales_carry_the_same_keys(self) -> None:
        tables = {
            name: json.loads((ROOT / "locales" / f"{name}.json").read_text(encoding="utf-8")) for name in ("en", "zh")
        }
        self.assertEqual(set(tables["en"]["frame"]), set(tables["zh"]["frame"]))


if __name__ == "__main__":
    unittest.main()

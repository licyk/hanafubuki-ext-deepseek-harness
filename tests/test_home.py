"""dsh's homes: copying the user's into an instance, and what the backend remembers of an instance."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

import home
import layout
from known import KnownInstances


class CopyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.base = Path(self._directory.name)
        self.user = self.base / "user"
        self.root = self.base / "instance"

    def tearDown(self) -> None:
        self._directory.cleanup()

    def write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_only_existing_homes_are_copied_each_into_its_folder(self) -> None:
        self.assertEqual(home.copies(self.root, self.user), [])
        (self.user / ".dsh").mkdir(parents=True)
        self.assertEqual(home.copies(self.root, self.user), [home.Copy(self.user / ".dsh", self.root / "dsh-home")])
        (self.user / ".agents").mkdir()
        self.assertEqual(
            [entry.target for entry in home.copies(self.root, self.user)],
            [self.root / "dsh-home", self.root / "agents-home"],
        )

    def test_copies_what_is_missing_keeps_what_is_there_and_moves_nothing(self) -> None:
        source = self.user / ".dsh"
        self.write(source / "profiles" / "default" / "credentials.json", "user login")
        self.write(source / "profiles" / "default" / "sessions" / "a.jsonl", "a")
        self.write(source / "settings.json", "user settings")
        target = self.root / "dsh-home"
        self.write(target / "settings.json", "instance settings")

        self.assertEqual(home.copy_missing(source, target), 2)
        self.assertEqual((target / "profiles" / "default" / "credentials.json").read_text(), "user login")
        self.assertEqual((target / "profiles" / "default" / "sessions" / "a.jsonl").read_text(), "a")
        self.assertEqual((target / "settings.json").read_text(), "instance settings")
        # A copy: the user's home is as it was.
        self.assertEqual((source / "settings.json").read_text(), "user settings")
        self.assertTrue((source / "profiles" / "default" / "credentials.json").is_file())
        # Again: nothing left to copy.
        self.assertEqual(home.copy_missing(source, target), 0)

    @unittest.skipIf(sys.platform == "win32", "symbolic links need a privilege on Windows")
    def test_a_link_is_copied_as_a_link(self) -> None:
        source = self.user / ".dsh"
        self.write(self.base / "big" / "file", "x")
        source.mkdir(parents=True)
        os.symlink(self.base / "big", source / "plugins")
        target = self.root / "dsh-home"
        self.assertEqual(home.copy_missing(source, target), 1)
        self.assertTrue((target / "plugins").is_symlink())
        self.assertEqual(os.readlink(target / "plugins"), str(self.base / "big"))


class KnownInstancesTest(unittest.TestCase):
    def test_remembers_across_restarts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data" / "instances.json"
            parts = layout.Components(
                layout.Component(Path(directory) / "core"), layout.Component(Path(directory) / "mine", True)
            )
            known = KnownInstances(path)
            self.assertIsNone(known.components("dsh-1"))
            self.assertEqual(known.values("dsh-1"), {})
            self.assertFalse(known.home_copied("dsh-1"))
            known.remember("dsh-1", parts, {"home": "user"})
            known.remember("dsh-1", parts, None)  # a call without values keeps the last ones
            known.mark_home_copied("dsh-1")

            again = KnownInstances(path)
            self.assertEqual(again.components("dsh-1"), parts)
            self.assertEqual(again.values("dsh-1"), {"home": "user"})
            self.assertTrue(again.home_copied("dsh-1"))

    def test_a_file_that_does_not_read_is_no_knowledge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instances.json"
            path.write_text("[not json", encoding="utf-8")
            self.assertIsNone(KnownInstances(path).components("dsh-1"))


if __name__ == "__main__":
    unittest.main()

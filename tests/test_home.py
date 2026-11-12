"""dsh's homes: copying the user's into an instance, and remembering that it was."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import home
from copied import HomeCopies


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

        self.assertEqual(home.copy_missing(source, target), (2, 0))
        self.assertEqual((target / "profiles" / "default" / "credentials.json").read_text(), "user login")
        self.assertEqual((target / "profiles" / "default" / "sessions" / "a.jsonl").read_text(), "a")
        self.assertEqual((target / "settings.json").read_text(), "instance settings")
        # A copy: the user's home is as it was.
        self.assertEqual((source / "settings.json").read_text(), "user settings")
        self.assertTrue((source / "profiles" / "default" / "credentials.json").is_file())
        # Again: nothing left to copy.
        self.assertEqual(home.copy_missing(source, target), (0, 0))

    @unittest.skipIf(sys.platform == "win32", "symbolic links need a privilege on Windows")
    def test_a_link_is_copied_as_a_link(self) -> None:
        source = self.user / ".dsh"
        self.write(self.base / "big" / "file", "x")
        source.mkdir(parents=True)
        os.symlink(self.base / "big", source / "plugins")
        target = self.root / "dsh-home"
        self.assertEqual(home.copy_missing(source, target), (1, 0))
        self.assertTrue((target / "plugins").is_symlink())
        self.assertEqual(os.readlink(target / "plugins"), str(self.base / "big"))

    @unittest.skipIf(sys.platform == "win32" or os.geteuid() == 0, "needs a file the user cannot read")
    def test_an_entry_that_cannot_be_copied_is_skipped(self) -> None:
        source = self.user / ".dsh"
        self.write(source / "locked", "x")
        self.write(source / "ok", "y")
        (source / "locked").chmod(0)
        try:
            self.assertEqual(home.copy_missing(source, self.root / "dsh-home"), (1, 1))
        finally:
            (source / "locked").chmod(0o600)
        self.assertEqual((self.root / "dsh-home" / "ok").read_text(), "y")

    @unittest.skipIf(sys.platform == "win32", "symbolic links need a privilege on Windows")
    def test_a_link_that_cannot_be_made_is_skipped(self) -> None:
        # As on Windows without the privilege: the link is left out, the rest arrives.
        source = self.user / ".dsh"
        self.write(source / "ok", "y")
        os.symlink(self.base, source / "link")
        refused = OSError("A required privilege is not held by the client")
        with mock.patch.object(home.os, "symlink", side_effect=refused):
            self.assertEqual(home.copy_missing(source, self.root / "dsh-home"), (1, 1))
        self.assertEqual((self.root / "dsh-home" / "ok").read_text(), "y")


class HomeCopiesTest(unittest.TestCase):
    def test_remembers_across_restarts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data" / "home-copied.json"
            copies = HomeCopies(path)
            self.assertNotIn("dsh-1", copies)
            copies.mark("dsh-1")
            copies.mark("dsh-1")
            self.assertIn("dsh-1", HomeCopies(path))
            self.assertNotIn("dsh-2", HomeCopies(path))

    def test_a_file_that_does_not_read_is_no_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "home-copied.json"
            path.write_text("[not json", encoding="utf-8")
            self.assertNotIn("dsh-1", HomeCopies(path))


if __name__ == "__main__":
    unittest.main()

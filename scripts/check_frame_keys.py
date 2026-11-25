"""Checks that every string the versions page asks for is defined, in both locales.

The page calls ``t("key")`` for its own strings and, for the components an
update check reports, ``t(`component_${name}`)``. This reads the page's source
for both shapes and compares them with ``locales/en.json`` and
``locales/zh.json``, then reports a page key that no locale defines and a key
one locale has and the other does not.

Usage: python scripts/check_frame_keys.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# A key either literal, or a prefix the page completes from data it was sent.
LITERAL = re.compile(r"""\bt\(\s*["']([A-Za-z_]+)["']""")
PREFIXED = re.compile(r"""\bt\(`([A-Za-z_]+)\$\{""")
# The names the page completes `component_` with: the update check's components.
COMPONENTS = ("core", "node")


def used_keys(source: str) -> set[str]:
    """The keys the page asks for; a prefixed key stands for each name it is completed with."""
    keys = set(LITERAL.findall(source))
    for prefix in PREFIXED.findall(source):
        keys.update(f"{prefix}{name}" for name in COMPONENTS)
    return keys


def main() -> int:
    """Compares the page's keys with each locale's, and prints what is wrong."""
    used = used_keys((ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8"))
    frames = {
        name: json.loads((ROOT / "locales" / f"{name}.json").read_text(encoding="utf-8"))["frame"]
        for name in ("en", "zh")
    }
    problems = [f"{name} lacks {key}" for name, frame in frames.items() for key in sorted(used - set(frame))]
    problems += [
        f"{key} is only in {sorted(name for name, frame in frames.items() if key in frame)}"
        for key in sorted(set(frames["en"]) ^ set(frames["zh"]))
    ]
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

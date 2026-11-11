"""What the tests share: the package's places and the libraries they need from outside it.

The SDK and ``sd_webui_all_in_one`` come with Hanafubuki, not with this
package. ``HANAFUBUKI_SDK_PYTHON`` names the SDK's directory (the one holding
``hanafubuki_extension``) and ``SD_WEBUI_ALL_IN_ONE_PATH`` a checkout or the
application's launcher code (the directory holding ``sd_webui_all_in_one``);
each defaults to a sibling checkout, and a test that needs one it cannot
find is skipped.
"""

from __future__ import annotations

import os
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
TYPE_ID = "io.github.licyk.deepseek-harness:dsh"


def _first_dir(*candidates: str | Path | None) -> Path | None:
    for candidate in candidates:
        if candidate and Path(candidate).is_dir():
            return Path(candidate)
    return None


SDK = _first_dir(os.environ.get("HANAFUBUKI_SDK_PYTHON"), ROOT.parent / "Hanafubuki-dev" / "sdk" / "python")
SD_WEBUI_ALL_IN_ONE = _first_dir(os.environ.get("SD_WEBUI_ALL_IN_ONE_PATH"), ROOT.parent / "sd-webui-all-in-one")
NODE = shutil.which("node")

if SDK is not None and str(SDK) not in sys.path:
    sys.path.insert(0, str(SDK))
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))
if str(ROOT / "launcher") not in sys.path:
    sys.path.insert(0, str(ROOT / "launcher"))


def launcher_pythonpath() -> str:
    """``PYTHONPATH`` as Hanafubuki gives a ``{host.python}`` program: the launcher code and its patcher."""
    assert SD_WEBUI_ALL_IN_ONE is not None
    return os.pathsep.join([str(SD_WEBUI_ALL_IN_ONE), str(SD_WEBUI_ALL_IN_ONE / "sd_webui_all_in_one" / "patcher")])


needs_sdk = unittest.skipIf(SDK is None, "the extension SDK is not found (HANAFUBUKI_SDK_PYTHON)")
needs_aio = unittest.skipIf(SD_WEBUI_ALL_IN_ONE is None, "sd_webui_all_in_one is not found (SD_WEBUI_ALL_IN_ONE_PATH)")
needs_node = unittest.skipIf(NODE is None, "node is not on PATH")

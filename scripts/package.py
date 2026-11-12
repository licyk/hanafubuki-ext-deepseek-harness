"""Builds the extension's archive: the package's files, without what only development needs.

Usage: python scripts/package.py [--out DIR]

Writes ``<out>/io.github.licyk.deepseek-harness-<version>.zip`` (``dist/``
by default), the files at the archive's root, as Hanafubuki installs it from
Settings > Extensions, and ``<out>/latest.json`` beside it: the update source
the manifest's ``[update] url`` names, one entry for every system, whose
``download_url`` is the archive as the release ``v<version>`` publishes it.
Build the frame first (``npm run build`` in ``web/``): the archive holds
``ui/versions`` as it is.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# What the package is; everything else (web/, tests/, scripts/, caches) stays out.
INCLUDED = [
    "hanafubuki-extension.toml",
    "README.md",
    "LICENSE",
    "types",
    "locales",
    "schemas",
    "images",
    "backend",
    "launcher",
    "ui",
]
SKIPPED_PARTS = {"__pycache__", ".ruff_cache", ".pytest_cache", "node_modules"}
# The newest release's asset, as the manifest's `[update] url` names it.
LATEST_ASSET = "/releases/latest/download/latest.json"


def package_files(root: Path = ROOT) -> list[Path]:
    """The package's files, relative to ``root``, in a stable order."""
    files: list[Path] = []
    for name in INCLUDED:
        path = root / name
        candidates = [path] if path.is_file() else sorted(path.rglob("*"))
        for candidate in candidates:
            relative = candidate.relative_to(root)
            if candidate.is_file() and not candidate.is_symlink() and not SKIPPED_PARTS & set(relative.parts):
                files.append(relative)
    return files


def build(out: Path, root: Path = ROOT) -> Path:
    """Writes the archive and its ``latest.json`` into ``out`` and returns the archive's path."""
    manifest = tomllib.loads((root / "hanafubuki-extension.toml").read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    archive = out / f"{manifest['id']}-{manifest['version']}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for relative in package_files(root):
            bundle.write(root / relative, relative.as_posix())
    entries = latest(archive, manifest["version"], manifest["update"]["url"])
    (out / "latest.json").write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    return archive


def latest(archive: Path, version: str, update_url: str) -> list[dict[str, str]]:
    """``latest.json`` for ``archive``: one entry for any system, as release ``v<version>`` publishes it."""
    if not update_url.endswith(LATEST_ASSET):
        raise ValueError(f"[update] url is not a GitHub release's latest.json: {update_url}")
    releases = update_url.removesuffix(LATEST_ASSET)
    return [
        {
            "version": version,
            "download_url": f"{releases}/releases/download/v{version}/{archive.name}",
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "platform": "any",
            "architecture": "any",
        }
    ]


def main(argv: list[str] | None = None) -> int:
    """Builds the archive and prints where it is."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    args = parser.parse_args(argv)
    if not (ROOT / "ui" / "versions" / "index.html").is_file():
        print("ui/versions is not built: run `npm ci && npm run build` in web/", file=sys.stderr)
        return 1
    print(build(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

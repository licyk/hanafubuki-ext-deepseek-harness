"""Choosing the Node.js release an instance gets, from nodejs.org's release index."""

from __future__ import annotations

import platform as host_platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spec import MINIMUM_NODE, NodeSpec, parse_node_spec

DEFAULT_MIRROR = "https://nodejs.org/dist"
# nodejs.org builds no musl Node.js; this one does, for x64 and arm64.
MUSL_MIRROR = "https://unofficial-builds.nodejs.org/download/release"

# Per Hanafubuki's platform name: the index's `files` key, the archive's
# platform part and its extension.
_ARCHIVES = {
    "linux": ("linux-{arch}", "linux-{arch}", "tar.xz"),
    "macos": ("osx-{arch}-tar", "darwin-{arch}", "tar.xz"),
    "windows": ("win-{arch}-zip", "win-{arch}", "zip"),
}
_ARCHES = {"x86_64": "x64", "amd64": "x64", "x64": "x64", "aarch64": "arm64", "arm64": "arm64"}


class ReleaseError(Exception):
    """No release answers the spec on this platform."""


@dataclass(frozen=True)
class NodeRelease:
    """One Node.js archive: what the plan downloads and unpacks into ``node``."""

    version: str  # without its `v`
    filename: str
    url: str
    sha256: str = ""


def machine_arch(machine: str | None = None) -> str:
    """Node's name for this machine's architecture (``x64``, ``arm64``)."""
    name = (machine if machine is not None else host_platform.machine()).lower()
    arch = _ARCHES.get(name)
    if arch is None:
        raise ReleaseError(f"Node.js has no build for this machine ({name or 'unknown'})")
    return arch


def machine_libc() -> str:
    """This Linux's C library: ``musl`` (Alpine and the like) or ``glibc``.

    ``platform.libc_ver`` names glibc from the interpreter's own binary; a
    musl system is told by its dynamic loader.
    """
    if host_platform.libc_ver()[0] == "glibc":
        return "glibc"
    return "musl" if any(Path("/lib").glob("ld-musl-*")) else "glibc"


def select(
    index: list[dict[str, Any]],
    node_spec: str,
    platform: str,
    arch: str,
    mirror: str = DEFAULT_MIRROR,
    libc: str = "glibc",
) -> NodeRelease:
    """The newest release of the index that matches ``node_spec`` and has an archive for the platform.

    Args:
        index: The mirror's ``index.json``.
        node_spec: ``lts``, ``latest``, a major or an exact version.
        platform: Hanafubuki's platform name.
        arch: Node's architecture name.
        mirror: Where the archives are.
        libc: On Linux, ``musl`` asks for the mirror's musl builds.

    Raises:
        ReleaseError: The spec does not read, the platform is unknown, or no release matches.
    """
    spec = parse_node_spec(node_spec)
    if spec is None:
        raise ReleaseError(f"`{node_spec}` is not a Node.js version")
    if platform not in _ARCHIVES:
        raise ReleaseError(f"Node.js has no build for {platform}")
    musl = platform == "linux" and libc == "musl"
    files_key, name_part, extension = (
        part.format(arch=f"{arch}-musl" if musl else arch) for part in _ARCHIVES[platform]
    )
    candidates = [
        version
        for entry in index
        if isinstance(entry, dict)
        and (version := _release_version(entry)) is not None
        and files_key in entry.get("files", ())
        and _matches(spec, version, entry)
    ]
    if not candidates and musl:
        raise ReleaseError(
            f"this Linux uses musl libc, and {mirror.rstrip('/')} has no musl build of Node.js `{spec.text}` "
            f"for {arch}; set the Node.js download mirror to {MUSL_MIRROR}, or choose a Node.js of your own "
            "in the instance's Paths"
        )
    if not candidates:
        raise ReleaseError(f"no Node.js release matches `{spec.text}` for {platform}-{arch}")
    version = max(candidates)
    if version < MINIMUM_NODE:
        raise ReleaseError(f"Node.js {_text(version)} is older than dsh needs ({_text(MINIMUM_NODE)})")
    text = _text(version)
    filename = f"node-v{text}-{name_part}.{extension}"
    return NodeRelease(text, filename, f"{mirror.rstrip('/')}/v{text}/{filename}")


def shasums_url(release: NodeRelease, mirror: str = DEFAULT_MIRROR) -> str:
    """The release's ``SHASUMS256.txt``."""
    return f"{mirror.rstrip('/')}/v{release.version}/SHASUMS256.txt"


def with_digest(release: NodeRelease, shasums: str) -> NodeRelease:
    """The release with its archive's SHA-256 from ``SHASUMS256.txt``.

    Raises:
        ReleaseError: The file does not list the archive.
    """
    for line in shasums.splitlines():
        digest, _, name = line.strip().partition("  ")
        if name.strip() == release.filename and len(digest) == 64:
            return NodeRelease(release.version, release.filename, release.url, digest.lower())
    raise ReleaseError(f"SHASUMS256.txt of Node.js {release.version} does not list {release.filename}")


def _release_version(entry: dict[str, Any]) -> tuple[int, int, int] | None:
    # A pre-release (`v27.0.0-alpha.0`) is never chosen.
    text = str(entry.get("version", "")).lstrip("v")
    parts = text.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def _matches(spec: NodeSpec, version: tuple[int, int, int], entry: dict[str, Any]) -> bool:
    if spec.kind == "lts":
        return bool(entry.get("lts"))
    if spec.kind == "latest":
        return True
    if spec.exact is not None:
        return version == spec.exact
    return version[0] == spec.major


def _text(version: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in version)

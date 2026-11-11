"""Where an instance's dsh and Node.js are, as plan templates and as paths below its root.

The host gives a backend an instance's root only, so the layout is read
from what the root holds; each kind's templates name components as its
discovery signature (``types/dsh.toml``) maps them:

- **own**: what this extension installs: ``core`` (an npm project holding
  dsh) and ``node`` (the Node.js it downloaded), both below the root.
- **global prefix**: a Node.js prefix where dsh was installed with
  ``npm install --global``, attached by discovery with ``core`` as the
  prefix itself: ``bin/node`` and ``lib/node_modules`` on Unix,
  ``node.exe`` and ``node_modules`` on Windows. Its ``node`` component is
  a directory inside the prefix (the host refuses one equal to the root),
  so these templates address Node.js through ``core``. That Node.js is the
  user's: no plan downloads, replaces or empties it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PACKAGE_JSON = Path("node_modules") / "@deepseek-ai" / "dsh" / "package.json"


@dataclass(frozen=True)
class Layout:
    """One kind of instance: its templates for dsh's npm prefix, the node program and npm's CLI."""

    global_prefix: bool
    dsh_prefix: str  # the directory whose node_modules holds dsh
    node: str
    npm: str

    def path(self, template: str, root: Path) -> Path:
        """``template`` as a path, with the components where this kind keeps them below ``root``."""
        core = root if self.global_prefix else root / "core"
        return Path(template.replace("{component.core}", str(core)).replace("{component.node}", str(root / "node")))


def own(platform: str) -> Layout:
    """What this extension installs: Node's own layout in ``node`` (Windows' or the others')."""
    if platform == "windows":
        return Layout(
            False, "{component.core}", "{component.node}/node.exe", "{component.node}/node_modules/npm/bin/npm-cli.js"
        )
    return Layout(
        False, "{component.core}", "{component.node}/bin/node", "{component.node}/lib/node_modules/npm/bin/npm-cli.js"
    )


def global_prefix(platform: str) -> Layout:
    """A Node.js prefix with dsh installed globally, ``core`` being the prefix."""
    if platform == "windows":
        return Layout(
            True, "{component.core}", "{component.core}/node.exe", "{component.core}/node_modules/npm/bin/npm-cli.js"
        )
    return Layout(
        True,
        "{component.core}/lib",
        "{component.core}/bin/node",
        "{component.core}/lib/node_modules/npm/bin/npm-cli.js",
    )


def read(root: Path | None, platform: str) -> Layout:
    """The layout of the instance at ``root``: a global prefix when its node and dsh are there, else its own."""
    if root is not None:
        candidate = global_prefix(platform)
        if (
            candidate.path(candidate.node, root).is_file()
            and (candidate.path(candidate.dsh_prefix, root) / PACKAGE_JSON).is_file()
        ):
            return candidate
    return own(platform)

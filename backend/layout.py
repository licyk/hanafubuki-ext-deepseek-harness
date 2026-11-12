"""Where an instance's dsh and Node.js are: its components, and the plan templates that name them.

The host gives each provider call the instance's components
(``ProviderInstance.components``: each one's path and whether it is
external, a folder of the user's). The layout is read from what ``core``
holds; each kind's templates name components as its discovery signature
(``types/dsh.toml``) maps them:

- **own**: what this extension installs: ``core`` (an npm project holding
  dsh) and ``node`` (the Node.js it downloaded, or the user's own when
  ``node`` is external).
- **global prefix**: a Node.js prefix where dsh was installed with
  ``npm install --global``, attached by discovery with ``core`` as the
  prefix itself: ``bin/node`` and ``lib/node_modules`` on Unix,
  ``node.exe`` and ``node_modules`` on Windows. The host refuses a
  ``node`` equal to ``core``, so ``node`` is a folder inside the prefix
  and these templates address Node.js through ``core``. That Node.js is
  the user's: no plan downloads, replaces or empties it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

PACKAGE_JSON = Path("node_modules") / "@deepseek-ai" / "dsh" / "package.json"


@dataclass(frozen=True)
class Component:
    """One component: its folder, and whether it is the user's (external) rather than the instance's."""

    path: Path
    external: bool = False


@dataclass(frozen=True)
class Components:
    """The type's two components, as the host gave them."""

    core: Component
    node: Component

    def to_protocol(self) -> dict[str, dict[str, Any]]:
        """The ``components`` object the host sends."""
        return {
            name: {"path": str(component.path), "external": component.external}
            for name, component in (("core", self.core), ("node", self.node))
        }


def components(instance: Any) -> Components | None:
    """``instance.components`` as the host sends it; ``None`` when it names no ``core`` or ``node``."""
    found = instance.get("components") if isinstance(instance, dict) else None
    if not isinstance(found, dict):
        return None
    parts = {}
    for name in ("core", "node"):
        entry = found.get(name)
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not entry["path"]:
            return None
        parts[name] = Component(Path(entry["path"]), entry.get("external") is True)
    return Components(parts["core"], parts["node"])


def below_root(root: Path, platform: str) -> Components:
    """The components of an instance at ``root`` when nothing else says: what its discovery signature maps."""
    prefix = global_prefix(platform)
    if (root / prefix.node.removeprefix("{component.core}/")).is_file():
        node = root / ("node_modules/npm" if platform == "windows" else "bin")
        return Components(Component(root, True), Component(node, True))
    return Components(Component(root / "core"), Component(root / "node"))


@dataclass(frozen=True)
class Layout:
    """One kind of instance: its templates for dsh's npm prefix, the node program and npm's CLI."""

    global_prefix: bool
    dsh_prefix: str  # the directory whose node_modules holds dsh
    node: str
    npm: str

    def path(self, template: str, found: Components) -> Path:
        """``template`` as a path, with the instance's components."""
        return Path(
            template.replace("{component.core}", str(found.core.path)).replace("{component.node}", str(found.node.path))
        )


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


def read(found: Components, platform: str) -> Layout:
    """The layout of an instance: a global prefix when ``core`` holds the node program, else its own.

    The node program alone decides, with or without dsh: a prefix whose dsh
    was uninstalled, or whose global install stopped half-way, is still the
    user's Node.js. The extension's own layout keeps it in ``node``, never
    in ``core``.
    """
    candidate = global_prefix(platform)
    if candidate.path(candidate.node, found).is_file():
        return candidate
    return own(platform)

"""Where an instance's dsh and Node.js are: its components, and the plan templates that name them.

The host gives each provider call, and each instance it lists, the
instance's components (``components``: each one's path and whether it is
external, a folder of the user's). Each type has its layout, and its
templates name components as its discovery signatures map them:

- ``dsh`` (**own**): what this extension installs: ``core`` (an npm project
  holding dsh) and ``node`` (the Node.js it downloaded, or the user's own
  when ``node`` is external).
- ``dsh-global`` (**global prefix**): a Node.js prefix where dsh was
  installed with ``npm install --global``, attached by discovery with
  ``core`` as the prefix itself: ``bin/node`` and ``lib/node_modules`` on
  Unix, ``node.exe`` and ``node_modules`` on Windows. The host refuses a
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


GLOBAL_TYPE = "dsh-global"


def for_type(type_name: str, platform: str) -> Layout:
    """The layout of the type ``type_name`` (``dsh`` or ``dsh-global``)."""
    return global_prefix(platform) if type_name == GLOBAL_TYPE else own(platform)


def holds_node_program(found: Components, platform: str) -> bool:
    """Whether ``core`` holds a node program, as a global prefix does and this extension's ``core`` never does.

    A ``dsh`` instance like that is a global prefix an earlier version of
    the extension attached as ``dsh``, with ``node`` owned: a plan for it
    would unpack Node.js over the prefix's ``bin``.
    """
    candidate = global_prefix(platform)
    return candidate.path(candidate.node, found).is_file()

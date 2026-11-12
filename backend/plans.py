"""The steps and commands the backend plans for the host, as templates.

The host resolves the placeholders (``{component.node}``, ``{host.python}``,
``{extension.root}``, ``{port}``), gives each step and the server the
type's ``[environment]`` (for ``dsh``, npm's configuration and dsh's homes,
``types/dsh.toml``) and runs what is planned; text the backend did not
write itself has its braces doubled so it stays literal.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from layout import Layout
from node_release import NodeRelease
from spec import dsh_version, node_version

PACKAGE = "@deepseek-ai/dsh"
# Written last by every install and update of the extension's own layout, so
# it names what is installed.
MARKER = "hanafubuki-install.txt"
NPMRC = ".npmrc"


@dataclass(frozen=True)
class Marker:
    """What an install recorded in ``core``: the values it used and the Node.js it got."""

    version: str
    node_version: str
    node: str

    def text(self) -> str:
        """The marker file's content."""
        return f"version={self.version}\nnodeVersion={self.node_version}\nnode={self.node}\n"


def read_marker(core: Path) -> Marker | None:
    """The marker an install wrote in ``core``; ``None`` when there is none."""
    try:
        lines = (core / MARKER).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    fields = dict(line.split("=", 1) for line in lines if "=" in line)
    return Marker(fields.get("version", ""), fields.get("nodeVersion", ""), fields.get("node", ""))


def keeps_node(kind: str, marker: Marker | None, release: str, node_program: Path) -> bool:
    """Whether an update keeps the instance's Node.js: it is the release ``nodeVersion`` resolves to now.

    The marker records the exact release an install got, so an update of
    ``24`` downloads a newer 24.x once the index lists one.
    """
    return kind == "update" and marker is not None and marker.node == release and node_program.is_file()


def install_steps(
    layout: Layout,
    values: dict[str, object],
    node: NodeRelease | None,
    node_text: str,
    registry: str = "",
) -> list[dict[str, Any]]:
    """The own layout's plan: Node.js when ``node`` is given, the instance's npm configuration, npm, the marker.

    Args:
        layout: The instance's layout, the extension's own.
        values: The install parameters' values.
        node: The release to download, or ``None`` to keep the Node.js there
            (the instance's, or the user's own in an external ``node``).
        node_text: The Node.js version the instance has once the plan ran.
        registry: The npm registry, empty for npm's default.

    Returns:
        Step documents.
    """
    steps: list[dict[str, Any]] = []
    if node is not None:
        # `replace`: the new Node.js is unpacked beside the old one and swapped
        # in whole, so a failed download keeps the working one.
        steps.append(
            {
                "kind": "download",
                "url": literal(node.url),
                "sha256": node.sha256,
                "unpackTo": "{component.node}",
                "strip": 1,
                "replace": True,
            }
        )
    # The type's environment points npm's user configuration here, never at
    # the user's ~/.npmrc. Writing it creates `core` on a first install.
    steps.append({"kind": "write-file", "path": f"{{component.core}}/{NPMRC}", "content": literal(npmrc(registry))})
    steps.append(_npm_install(layout, [], values, {}, cwd="{component.node}"))
    marker = Marker(dsh_version(values), node_version(values), node_text)
    steps.append({"kind": "write-file", "path": f"{{component.core}}/{MARKER}", "content": literal(marker.text())})
    return steps


def npmrc(registry: str) -> str:
    """The instance's npm user configuration: the registry setting, when there is one."""
    text = "# Written by Hanafubuki's DeepSeek Harness extension at each install and update.\n"
    return text + (f"registry={registry}\n" if registry else "")


def global_install_steps(layout: Layout, values: dict[str, object]) -> list[dict[str, Any]]:
    """A global prefix's plan: dsh with the prefix's own npm, globally; Node.js and the prefix are left as they are.

    Nothing is written in the user's prefix, and npm reads the user's own
    configuration (the type sets none).
    """
    return [_npm_install(layout, ["--global"], values, {}, cwd="{component.core}")]


def launch_command(layout: Layout) -> dict[str, Any]:
    """The ``web`` role's command: the launcher on the managed Python, which runs dsh."""
    return {
        "argv": [
            "{host.python}",
            "{extension.root}/launcher/launch.py",
            "--core",
            layout.dsh_prefix,
            "--node",
            layout.node,
            "--port",
            "{port}",
        ],
        "env": {},
    }


def literal(text: str) -> str:
    """``text`` as template text that resolves to itself."""
    return text.replace("{", "{{").replace("}", "}}")


def _npm_install(
    layout: Layout, options: list[str], values: dict[str, object], env: dict[str, str], cwd: str
) -> dict[str, Any]:
    command = [layout.node, layout.npm, "install", *options, "--prefix", "{component.core}", "--no-fund", "--no-audit"]
    return {"kind": "run", "command": [*command, f"{PACKAGE}@{dsh_version(values)}"], "cwd": cwd, "env": env}

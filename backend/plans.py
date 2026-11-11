"""The steps and commands the backend plans for the host, as templates.

The host resolves the placeholders (``{component.node}``, ``{host.python}``,
``{extension.root}``, ``{port}``) and runs what is planned; text the backend
did not write itself has its braces doubled so it stays literal.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from node_release import NodeRelease
from spec import dsh_version, node_version

PACKAGE = "@deepseek-ai/dsh"
# Written last by every install and update, so it names what is installed.
MARKER = "hanafubuki-install.txt"

NODE_EXE = {"windows": "{component.node}/node.exe"}
NODE_EXE_DEFAULT = "{component.node}/bin/node"
NPM_CLI = {"windows": "{component.node}/node_modules/npm/bin/npm-cli.js"}
NPM_CLI_DEFAULT = "{component.node}/lib/node_modules/npm/bin/npm-cli.js"


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


def node_executable(node_dir: Path, platform: str) -> Path:
    """The ``node`` program of a Node.js unpacked at ``node_dir``."""
    return node_dir / "node.exe" if platform == "windows" else node_dir / "bin" / "node"


def keeps_node(
    kind: str, values: dict[str, object], marker: Marker | None, node_dir: Path | None, platform: str
) -> bool:
    """Whether an update keeps the instance's Node.js: same ``nodeVersion``, and it is there."""
    return (
        kind == "update"
        and marker is not None
        and node_dir is not None
        and marker.node_version == node_version(values)
        and node_executable(node_dir, platform).is_file()
    )


def install_steps(
    platform: str,
    values: dict[str, object],
    node: NodeRelease | None,
    node_text: str,
    clean_node: bool = False,
    registry: str = "",
) -> list[dict[str, Any]]:
    """The plan: Node.js when ``node`` is given (after emptying ``node`` with ``clean_node``), then npm.

    Args:
        platform: Hanafubuki's platform name.
        values: The install parameters' values.
        node: The release to download, or ``None`` to keep the instance's.
        node_text: The Node.js version the instance has once the plan ran.
        clean_node: Empty ``node`` first: an archive unpacks over what is there.
        registry: The npm registry, empty for npm's default.

    Returns:
        Step documents.
    """
    steps: list[dict[str, Any]] = []
    if node is not None:
        if clean_node:
            steps.append(
                {
                    "kind": "run",
                    "command": ["{host.python}", "{extension.root}/launcher/empty_dir.py", "{component.node}"],
                    "cwd": "{component.node}",
                }
            )
        steps.append(
            {
                "kind": "download",
                "url": literal(node.url),
                "sha256": node.sha256,
                "unpackTo": "{component.node}",
                "strip": 1,
            }
        )
    version = dsh_version(values)
    env = {"npm_config_registry": literal(registry)} if registry else {}
    steps.append(
        {
            "kind": "run",
            "command": [
                NODE_EXE.get(platform, NODE_EXE_DEFAULT),
                NPM_CLI.get(platform, NPM_CLI_DEFAULT),
                "install",
                "--prefix",
                "{component.core}",
                "--no-fund",
                "--no-audit",
                f"{PACKAGE}@{version}",
            ],
            # `core` does not exist before the first install; npm creates it.
            "cwd": "{component.node}",
            "env": env,
        }
    )
    marker = Marker(version, node_version(values), node_text)
    steps.append({"kind": "write-file", "path": f"{{component.core}}/{MARKER}", "content": literal(marker.text())})
    return steps


def launch_command(platform: str) -> dict[str, Any]:
    """The ``web`` role's command: the launcher on the managed Python, which runs dsh."""
    return {
        "argv": [
            "{host.python}",
            "{extension.root}/launcher/launch.py",
            "--core",
            "{component.core}",
            "--node",
            NODE_EXE.get(platform, NODE_EXE_DEFAULT),
            "--port",
            "{port}",
        ],
        "env": {},
    }


def literal(text: str) -> str:
    """``text`` as template text that resolves to itself."""
    return text.replace("{", "{{").replace("}", "}}")

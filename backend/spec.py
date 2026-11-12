"""The instance's install parameters: what they accept, read without the network.

``provider.validateSpec`` is also asked when an existing installation is
attached, so nothing here may fetch: a Node.js spec is checked by its shape,
and resolved against the release index only when a plan is made.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
# An npm dist-tag: never a leading `-` (it is one argument of npm's) nor a
# brace (the plan is a template).
DIST_TAG = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
MAJOR = re.compile(r"^v?(\d+)$")
EXACT = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")

MINIMUM_NODE = (24, 9, 0)
DEFAULT_VERSION = "latest"
DEFAULT_NODE_VERSION = "24"
# Where dsh keeps its profiles, credentials and sessions: the instance's own
# folders, or the user's `~/.dsh` and `~/.agents`.
HOMES = ("instance", "user")
DEFAULT_HOME = "instance"


@dataclass(frozen=True)
class NodeSpec:
    """What ``nodeVersion`` asks for: the latest LTS, the latest release, the latest of a major, or one release."""

    kind: str  # "lts", "latest", "major" or "exact"
    major: int = 0
    exact: tuple[int, int, int] | None = None

    @property
    def text(self) -> str:
        """The spec as the user writes it."""
        if self.kind in ("lts", "latest"):
            return self.kind
        if self.exact is not None:
            return ".".join(str(part) for part in self.exact)
        return str(self.major)

    def below_minimum(self) -> bool:
        """Whether every release it can name is older than dsh needs; ``lts`` and ``latest`` are checked resolved."""
        if self.exact is not None:
            return self.exact < MINIMUM_NODE
        return self.kind == "major" and self.major < MINIMUM_NODE[0]


def parse_node_spec(value: str) -> NodeSpec | None:
    """Reads ``nodeVersion``; ``None`` when it is none of the accepted shapes."""
    text = value.strip().lower()
    if text in ("lts", "latest"):
        return NodeSpec(text)
    if match := MAJOR.match(text):
        return NodeSpec("major", major=int(match.group(1)))
    if match := EXACT.match(text):
        exact = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        return NodeSpec("exact", major=exact[0], exact=exact)
    return None


def exact_version(text: str) -> tuple[int, int, int] | None:
    """A release's version (``v24.11.0``, ``24.11.0``) as numbers; ``None`` for anything else."""
    match = EXACT.match(text.strip().lower())
    return (int(match.group(1)), int(match.group(2)), int(match.group(3))) if match else None


def dsh_version(values: dict[str, object]) -> str:
    """The ``version`` value, its default when unset."""
    value = values.get("version")
    return value.strip() if isinstance(value, str) and value.strip() else DEFAULT_VERSION


def node_version(values: dict[str, object]) -> str:
    """The ``nodeVersion`` value, its default when unset."""
    value = values.get("nodeVersion")
    return value.strip() if isinstance(value, str) and value.strip() else DEFAULT_NODE_VERSION


def home(values: dict[str, object]) -> str:
    """The ``home`` value, its default when unset or unknown."""
    value = values.get("home")
    return value if isinstance(value, str) and value in HOMES else DEFAULT_HOME


def issues(values: dict[str, object]) -> dict[str, str]:
    """What is wrong with the values, by parameter, as message names of ``issues.*``."""
    found: dict[str, str] = {}
    version = dsh_version(values)
    if not (SEMVER.match(version) or DIST_TAG.match(version)):
        found["version"] = "version"
    spec = parse_node_spec(node_version(values))
    if spec is None:
        found["nodeVersion"] = "nodeVersion"
    elif spec.below_minimum():
        found["nodeVersion"] = "nodeTooOld"
    return found


def version_key(version: str) -> tuple:
    """Sorts semver text by precedence: its numbers, then a release after its pre-releases."""
    match = SEMVER.match(version)
    if match is None:
        return (-1, -1, -1, 0, ())
    numbers = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    prerelease = version.split("+", 1)[0].partition("-")[2]
    if not prerelease:
        return (*numbers, 1, ())
    parts = tuple((0, int(part), "") if part.isdigit() else (1, 0, part) for part in prerelease.split("."))
    return (*numbers, 0, parts)

"""The DeepSeek Harness extension's backend.

It provides the type ``io.github.licyk.deepseek-harness:dsh``: it checks an
instance's values, plans its install and update (Node.js, then dsh with
npm) and its ``web`` server's command, and answers the version page's calls.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from hanafubuki_extension import INVALID_PARAMS, REQUEST_FAILED, Handler, Host, RpcError, run

import node_release
import plans
import spec
from remote import Remote

TYPE_ID = "io.github.licyk.deepseek-harness:dsh"
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = "https://registry.npmjs.org"
INDEX_MAX_AGE = 3600.0
REGISTRY_MAX_AGE = 600.0


class Backend(Handler):
    """Answers the host for the ``dsh`` type and the ``versions`` frame."""

    def __init__(self) -> None:
        """Builds the backend; what it learns from the host is read when first needed."""
        self._platform: str | None = None

    def validate_spec(self, host: Host, type_id: str, values: dict[str, Any]) -> dict[str, str]:
        """``provider.validateSpec``: the values' shapes, without the network."""
        found = spec.issues(values)
        if not found:
            return {}
        texts = locale_strings(self._locale(host)).get("issues", {})
        return {name: texts.get(issue, issue) for name, issue in found.items()}

    def install_plan(
        self, host: Host, type_id: str, kind: str, values: dict[str, Any], instance: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """``provider.installPlan``: Node.js (unless an update keeps it), npm install, the marker."""
        platform = self._platform_of(host)
        settings = self._settings(host)
        root = self._instance_root(host, str(instance.get("id", ""))) if kind == "update" else None
        marker = plans.read_marker(root / "core") if root is not None else None
        node_dir = root / "node" if root is not None else None
        if marker is not None and plans.keeps_node(kind, values, marker, node_dir, platform):
            return plans.install_steps(platform, values, None, marker.node, registry=settings["npmRegistry"])
        release = self._node_release(host, spec.node_version(values), platform, settings["nodeMirror"])
        clean = kind == "update" and node_dir is not None and node_dir.is_dir()
        return plans.install_steps(platform, values, release, release.version, clean, settings["npmRegistry"])

    def launch_plan(
        self, host: Host, type_id: str, role: str, port: int, values: dict[str, Any], instance: dict[str, Any]
    ) -> dict[str, Any]:
        """``provider.launchPlan``: the launcher on the managed Python for the ``web`` role."""
        if role != "web":
            raise RpcError(INVALID_PARAMS, f"no server role `{role}`")
        return plans.launch_command(self._platform_of(host))

    def frame_call(self, host: Host, frame: str, method: str, params: Any, context: dict[str, Any]) -> Any:
        """``ui.frame.call`` from the ``versions`` frame: ``status`` and ``versions``."""
        if frame != "versions":
            raise RpcError(INVALID_PARAMS, f"no frame `{frame}`")
        options = params if isinstance(params, dict) else {}
        if method == "status":
            return self._status(host, str(context.get("instanceId") or ""))
        if method == "versions":
            return self._versions(host, bool(options.get("refresh")))
        raise RpcError(INVALID_PARAMS, f"no method `{method}`")

    def _status(self, host: Host, instance_id: str) -> dict[str, Any]:
        found = self._instance(host, instance_id)
        root = Path(found["path"])
        marker = plans.read_marker(root / "core")
        installed = _package_version(root / "core" / "node_modules" / "@deepseek-ai" / "dsh" / "package.json")
        return {
            "instanceId": instance_id,
            "running": bool(found.get("running")),
            "installed": installed,
            "node": (marker.node if marker and marker.node else None)
            or _node_version(root / "node", self._platform_of(host)),
            "requested": {
                "version": marker.version if marker else None,
                "nodeVersion": marker.node_version if marker else None,
            },
            "locale": self._locale(host),
            "strings": {name: locale_strings(name).get("frame", {}) for name in ("en", "zh")},
        }

    def _versions(self, host: Host, refresh: bool) -> dict[str, Any]:
        registry = self._settings(host)["npmRegistry"] or DEFAULT_REGISTRY
        url = f"{registry.rstrip('/')}/@deepseek-ai%2Fdsh"
        document = self._remote(host).json(url, f"dsh-{_digest(url)}.json", 0.0 if refresh else REGISTRY_MAX_AGE)
        published = document.get("time") if isinstance(document.get("time"), dict) else {}
        versions = [version for version in document.get("versions", {}) if spec.SEMVER.match(version)]
        versions.sort(key=spec.version_key, reverse=True)
        return {
            "registry": registry,
            "distTags": document.get("dist-tags", {}),
            "versions": [{"version": version, "published": published.get(version)} for version in versions],
        }

    def _node_release(self, host: Host, node_spec: str, platform: str, mirror: str) -> node_release.NodeRelease:
        mirror = (mirror or node_release.DEFAULT_MIRROR).rstrip("/")
        remote = self._remote(host)
        try:
            index = remote.json(f"{mirror}/index.json", f"node-index-{_digest(mirror)}.json", INDEX_MAX_AGE)
            release = node_release.select(index, node_spec, platform, node_release.machine_arch(), mirror)
            shasums = remote.text(
                node_release.shasums_url(release, mirror), f"node-v{release.version}-{_digest(mirror)}.sha256sums"
            )
            return node_release.with_digest(release, shasums)
        except node_release.ReleaseError as error:
            raise RpcError(REQUEST_FAILED, str(error)) from error

    def _instance(self, host: Host, instance_id: str) -> dict[str, Any]:
        for found in host.call("instances.ofType", {"type": TYPE_ID}).get("instances", []):
            if found.get("id") == instance_id:
                return found
        raise RpcError(REQUEST_FAILED, f"no DeepSeek Harness instance {instance_id}")

    def _instance_root(self, host: Host, instance_id: str) -> Path | None:
        try:
            return Path(self._instance(host, instance_id)["path"])
        except RpcError:
            return None

    def _platform_of(self, host: Host) -> str:
        if self._platform is None:
            self._platform = str(host.call("host.info").get("platform", ""))
        return self._platform

    def _locale(self, host: Host) -> str:
        return str(host.call("host.info").get("locale", "en"))

    def _settings(self, host: Host) -> dict[str, str]:
        values = host.call("settings.get").get("values", {})
        return {name: str(values.get(name) or "").strip() for name in ("npmRegistry", "nodeMirror")}

    def _remote(self, host: Host) -> Remote:
        data = os.environ.get("HANAFUBUKI_EXTENSION_DATA") or host.call("storage.path")["path"]
        return Remote(host, Path(data))


def locale_strings(locale: str) -> dict[str, Any]:
    """The package's strings for ``locale`` (``auto`` follows ``LANG``), English when it has none."""
    if locale not in ("en", "zh"):
        locale = "zh" if os.environ.get("LANG", "").lower().startswith("zh") else "en"
    try:
        return json.loads((PACKAGE_ROOT / "locales" / f"{locale}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _package_version(path: Path) -> str | None:
    try:
        version = json.loads(path.read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError, AttributeError):
        return None
    return version if isinstance(version, str) else None


def _node_version(node_dir: Path, platform: str) -> str | None:
    # An instance without the marker (attached by discovery): ask its Node.
    program = plans.node_executable(node_dir, platform)
    if not program.is_file():
        return None
    try:
        output = subprocess.run(
            [str(program), "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return output.stdout.strip().lstrip("v") or None


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


if __name__ == "__main__":
    run(Backend())

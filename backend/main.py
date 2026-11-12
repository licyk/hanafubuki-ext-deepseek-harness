"""The DeepSeek Harness extension's backend.

It provides the type ``io.github.licyk.deepseek-harness:dsh``: it checks an
instance's values (and a Node.js of the user's), plans its install and
update (Node.js, then dsh with npm) and its ``web`` server's command, runs
its ``copy-user-home`` operation, and answers the version page's calls.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any

from hanafubuki_extension import INVALID_PARAMS, REQUEST_FAILED, Handler, Host, RpcError, run

import home
import layout
import node_release
import plans
import spec
from known import KnownInstances
from layout import Components
from remote import Remote

TYPE_ID = "io.github.licyk.deepseek-harness:dsh"
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = "https://registry.npmjs.org"
INDEX_MAX_AGE = 3600.0
REGISTRY_MAX_AGE = 600.0
COPY_HOME = "copy-user-home"


class Backend(Handler):
    """Answers the host for the ``dsh`` type and the ``versions`` frame."""

    def __init__(self) -> None:
        """Builds the backend; what it learns from the host is read when first needed."""
        self._platform: str | None = None
        self._known: KnownInstances | None = None
        self._copying: set[str] = set()
        self._lock = threading.Lock()

    def validate_spec(
        self, host: Host, type_id: str, values: dict[str, Any], instance: dict[str, Any] | None = None
    ) -> dict[str, str]:
        """``provider.validateSpec``: the values' shapes, without the network, and a Node.js of the user's.

        ``instance`` comes only for an existing instance; with an external
        ``node`` its program must run and be recent enough for dsh.
        """
        texts = locale_strings(self._locale(host))
        issues = texts.get("issues", {})
        found = {name: issues.get(issue, issue) for name, issue in spec.issues(values).items()}
        parts = layout.components(instance)
        if instance is not None and parts is not None and "nodeVersion" not in found:
            self._known_instances(host).remember(str(instance.get("id", "")), parts, None)
            problem = own_node_problem(parts, self._platform_of(host), texts)
            if problem:
                found["nodeVersion"] = problem
        return found

    def install_plan(
        self, host: Host, type_id: str, kind: str, values: dict[str, Any], instance: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """``provider.installPlan``: Node.js (unless an update keeps it, or it is the user's), npm, the marker.

        A global prefix's plan is its npm alone, and an external ``node``
        is never downloaded into: either Node.js is the user's, whatever
        ``nodeVersion`` says.
        """
        platform = self._platform_of(host)
        registry = self._settings(host)["npmRegistry"]
        parts = self._instance_components(host, instance, values)
        shape = layout.read(parts, platform)
        if shape.global_prefix:
            return plans.global_install_steps(shape, values, registry)
        if parts.node.external:
            if problem := own_node_problem(parts, platform, locale_strings(self._locale(host))):
                raise RpcError(REQUEST_FAILED, problem)
            version = _node_version(shape.path(shape.node, parts)) or ""
            return plans.install_steps(shape, values, None, version, registry)
        marker = plans.read_marker(parts.core.path)
        program = shape.path(shape.node, parts)
        try:
            release = self._node_release(host, spec.node_version(values), platform)
        except RpcError as error:
            # Offline, an update keeps the Node.js the same request got before.
            unchanged = marker is not None and marker.node_version == spec.node_version(values)
            if kind != "update" or not unchanged or not program.is_file():
                raise
            host.log("warn", f"keeping Node.js {marker.node}: {error.message}")
            return plans.install_steps(shape, values, None, marker.node, registry)
        if plans.keeps_node(kind, marker, release.version, program):
            return plans.install_steps(shape, values, None, release.version, registry)
        return plans.install_steps(shape, values, release, release.version, registry)

    def launch_plan(
        self, host: Host, type_id: str, role: str, port: int, values: dict[str, Any], instance: dict[str, Any]
    ) -> dict[str, Any]:
        """``provider.launchPlan``: the launcher on the managed Python for the ``web`` role."""
        if role != "web":
            raise RpcError(INVALID_PARAMS, f"no server role `{role}`")
        parts = self._instance_components(host, instance, values)
        return plans.launch_command(layout.read(parts, self._platform_of(host)), spec.home(values))

    def manage(self, host: Host, type_id: str, operation: str, instance: dict[str, Any]) -> str:
        """``provider.manage.copy-user-home``: copies the user's ``~/.dsh`` into the instance's home."""
        if operation != COPY_HOME:
            raise RpcError(INVALID_PARAMS, f"no operation `{operation}`")
        instance_id = str(instance.get("id", ""))
        if (parts := layout.components(instance)) is not None:
            self._known_instances(host).remember(instance_id, parts, None)
        return self._start_copy(host, instance_id)

    def frame_call(self, host: Host, frame: str, method: str, params: Any, context: dict[str, Any]) -> Any:
        """``ui.frame.call`` from the ``versions`` frame: ``status``, ``versions`` and ``copyHome``."""
        if frame != "versions":
            raise RpcError(INVALID_PARAMS, f"no frame `{frame}`")
        options = params if isinstance(params, dict) else {}
        instance_id = str(context.get("instanceId") or "")
        if method == "status":
            return self._status(host, instance_id)
        if method == "versions":
            return self._versions(host, bool(options.get("refresh")))
        if method == "copyHome":
            return {"notice": self._start_copy(host, instance_id)}
        raise RpcError(INVALID_PARAMS, f"no method `{method}`")

    def _status(self, host: Host, instance_id: str) -> dict[str, Any]:
        found = self._instance(host, instance_id)
        root = Path(found["path"])
        platform = self._platform_of(host)
        known = self._known_instances(host)
        parts = known.components(instance_id) or layout.below_root(root, platform)
        shape = layout.read(parts, platform)
        values = known.values(instance_id)
        source = "prefix" if shape.global_prefix else "own" if parts.node.external else "managed"
        marker = None if shape.global_prefix else plans.read_marker(parts.core.path)
        program = shape.path(shape.node, parts)
        node = marker.node if source == "managed" and marker and marker.node else None
        chosen_home = spec.home(values) if "home" in values else "user" if shape.global_prefix else "instance"
        return {
            "instanceId": instance_id,
            "running": bool(found.get("running")),
            "installed": _package_version(shape.path(shape.dsh_prefix, parts) / layout.PACKAGE_JSON),
            "node": node or _node_version(program),
            "nodeSource": source,
            "nodePath": str(program),
            "prefix": str(parts.core.path) if shape.global_prefix else None,
            "home": chosen_home,
            "homePath": str(root / home.DSH_HOME) if chosen_home == "instance" else "~/.dsh",
            "canCopyHome": chosen_home == "instance" and not known.home_copied(instance_id) and bool(home.copies(root)),
            "copying": instance_id in self._copying,
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

    def _start_copy(self, host: Host, instance_id: str) -> str:
        # A home can hold many sessions: the copy runs on a thread of its own,
        # past the host's bound for this call, and reports with ui.progress.
        notices = locale_strings(self._locale(host)).get("notices", {})
        found = self._instance(host, instance_id)
        if found.get("running"):
            raise RpcError(REQUEST_FAILED, notices.get("copyRunning", "stop the instance first"))
        jobs = home.copies(Path(found["path"]))
        if not jobs:
            raise RpcError(REQUEST_FAILED, notices.get("copyNothing", "there is no ~/.dsh to copy"))
        with self._lock:
            if instance_id in self._copying:
                raise RpcError(REQUEST_FAILED, notices.get("copyBusy", "the copy is already running"))
            self._copying.add(instance_id)
        threading.Thread(target=self._copy, args=(host, instance_id, jobs, notices), daemon=True).start()
        return notices.get("copyStarted", "copying")

    def _copy(self, host: Host, instance_id: str, jobs: list[home.Copy], notices: dict[str, str]) -> None:
        progress = f"copy-home-{instance_id}"
        title = notices.get("copyTitle", "Copying ~/.dsh")
        copied, error = 0, None
        try:
            host.call("ui.progress", {"id": progress, "title": title, "done": False})
            for job in jobs:
                copied += home.copy_missing(job.source, job.target)
            self._known_instances(host).mark_home_copied(instance_id)
        except (OSError, RpcError) as failure:
            error = str(failure)
        finally:
            with self._lock:
                self._copying.discard(instance_id)
        message = notices.get("copyFailed", "{error}") if error else notices.get("copyDone", "{count}")
        try:
            host.call("ui.progress", {"id": progress, "title": title, "done": True, "error": error})
            host.call(
                "ui.notify",
                {"message": message.format(error=error, count=copied), "level": "error" if error else "info"},
            )
        except RpcError:
            pass
        host.emit_frame("versions", "home-copied", {"instanceId": instance_id, "copied": copied, "error": error})

    def _node_release(self, host: Host, node_spec: str, platform: str) -> node_release.NodeRelease:
        mirror = (self._settings(host)["nodeMirror"] or node_release.DEFAULT_MIRROR).rstrip("/")
        remote = self._remote(host)
        index = remote.json(f"{mirror}/index.json", f"node-index-{_digest(mirror)}.json", INDEX_MAX_AGE)
        try:
            libc = node_release.machine_libc() if platform == "linux" else "glibc"
            release = node_release.select(index, node_spec, platform, node_release.machine_arch(), mirror, libc)
            shasums = remote.text(
                node_release.shasums_url(release, mirror), f"node-v{release.version}-{_digest(mirror)}.sha256sums"
            )
            return node_release.with_digest(release, shasums)
        except node_release.ReleaseError as error:
            raise RpcError(REQUEST_FAILED, str(error)) from error

    def _instance_components(self, host: Host, instance: dict[str, Any], values: dict[str, Any]) -> Components:
        parts = layout.components(instance)
        if parts is None:
            raise RpcError(INVALID_PARAMS, "the instance's components are missing (Hanafubuki 0.3.30 sends them)")
        self._known_instances(host).remember(str(instance.get("id", "")), parts, values)
        return parts

    def _instance(self, host: Host, instance_id: str) -> dict[str, Any]:
        for found in host.call("instances.ofType", {"type": TYPE_ID}).get("instances", []):
            if found.get("id") == instance_id:
                return found
        raise RpcError(REQUEST_FAILED, f"no DeepSeek Harness instance {instance_id}")

    def _known_instances(self, host: Host) -> KnownInstances:
        with self._lock:
            if self._known is None:
                self._known = KnownInstances(self._data_dir(host) / "instances.json")
            return self._known

    def _platform_of(self, host: Host) -> str:
        if self._platform is None:
            self._platform = str(host.call("host.info").get("platform", ""))
        return self._platform

    def _locale(self, host: Host) -> str:
        return str(host.call("host.info").get("locale", "en"))

    def _settings(self, host: Host) -> dict[str, str]:
        values = host.call("settings.get").get("values", {})
        return {name: str(values.get(name) or "").strip() for name in ("npmRegistry", "nodeMirror")}

    def _data_dir(self, host: Host) -> Path:
        return Path(os.environ.get("HANAFUBUKI_EXTENSION_DATA") or host.call("storage.path")["path"])

    def _remote(self, host: Host) -> Remote:
        return Remote(host, self._data_dir(host))


def own_node_problem(parts: Components, platform: str, texts: dict[str, Any]) -> str | None:
    """Why an external ``node`` cannot run dsh: no program, one too old, or no npm beside it; ``None`` when it can.

    A global prefix's Node.js is not asked: the prefix is what it is.
    """
    shape = layout.read(parts, platform)
    if shape.global_prefix or not parts.node.external:
        return None
    notices = texts.get("notices", {})
    program = shape.path(shape.node, parts)
    version = _node_version(program)
    exact = spec.exact_version(version or "")
    if exact is None:
        return notices.get("nodeUnreadable", "{program}").format(program=program)
    if exact < spec.MINIMUM_NODE:
        return notices.get("nodeOwnTooOld", "{version}").format(program=program, version=version)
    npm = shape.path(shape.npm, parts)
    if not npm.is_file():
        return notices.get("npmMissing", "{npm}").format(program=program, npm=npm)
    return None


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


def _node_version(program: Path) -> str | None:
    # What the program says it is: a Node.js of the user's, or one without the marker.
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

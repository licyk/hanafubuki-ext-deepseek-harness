"""The DeepSeek Harness extension's backend.

It provides two types: ``io.github.licyk.deepseek-harness:dsh``, which it
installs isolated (it checks an instance's values and a Node.js of the
user's, plans its install and update, Node.js then dsh with npm, and runs
its ``copy-user-home`` operation), and ``...:dsh-global``, a global npm
install of the user's, attached by discovery and updated with its own npm.
It plans both types' ``web`` server and answers the version page's calls.
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
from copied import HomeCopies
from layout import Components, Layout
from remote import Remote

TYPE_ID = "io.github.licyk.deepseek-harness:dsh"
GLOBAL_TYPE_ID = f"io.github.licyk.deepseek-harness:{layout.GLOBAL_TYPE}"
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
        self._copies: HomeCopies | None = None
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
        if type_id == TYPE_ID and parts is not None and "nodeVersion" not in found:
            problem = own_node_problem(parts, self._platform_of(host), texts)
            if problem:
                found["nodeVersion"] = problem
        return found

    def install_plan(
        self, host: Host, type_id: str, kind: str, values: dict[str, Any], instance: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """``provider.installPlan``: Node.js (unless an update keeps it, or it is the user's), npm, the marker.

        A ``dsh-global`` instance is attached, never installed: its plan is
        an update with the prefix's own npm alone, whatever else it says. An
        external ``node`` is never downloaded into.
        """
        platform = self._platform_of(host)
        parts = _components(instance)
        if type_id == GLOBAL_TYPE_ID:
            if kind == "install":
                raise RpcError(REQUEST_FAILED, self._notice(host, "globalNotInstallable"))
            return plans.global_install_steps(layout.global_prefix(platform), values)
        shape = self._own_layout(host, parts, platform)
        registry = self._settings(host)["npmRegistry"]
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
        platform = self._platform_of(host)
        if type_id == GLOBAL_TYPE_ID:
            return plans.launch_command(layout.global_prefix(platform))
        return plans.launch_command(self._own_layout(host, _components(instance), platform))

    def manage(self, host: Host, type_id: str, operation: str, instance: dict[str, Any]) -> str:
        """``provider.manage.copy-user-home``: copies the user's ``~/.dsh`` into the instance's home."""
        if operation != COPY_HOME or type_id != TYPE_ID:
            raise RpcError(INVALID_PARAMS, f"no operation `{operation}`")
        return self._start_copy(host, str(instance.get("id", "")))

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
        parts = _components(found)
        isolated = found.get("type") == TYPE_ID
        shape = layout.for_type(str(found.get("type", "")).rpartition(":")[2], self._platform_of(host))
        source = "prefix" if not isolated else "own" if parts.node.external else "managed"
        marker = plans.read_marker(parts.core.path) if isolated else None
        program = shape.path(shape.node, parts)
        node = marker.node if source == "managed" and marker and marker.node else None
        return {
            "instanceId": instance_id,
            "running": bool(found.get("running")),
            "installed": _package_version(shape.path(shape.dsh_prefix, parts) / layout.PACKAGE_JSON),
            "node": node or _node_version(program),
            "nodeSource": source,
            "nodePath": str(program),
            "prefix": None if isolated else str(parts.core.path),
            "homePath": str(root / home.DSH_HOME) if isolated else None,
            "canCopyHome": isolated and instance_id not in self._home_copies(host) and bool(home.copies(root)),
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
        if found.get("type") != TYPE_ID:
            raise RpcError(INVALID_PARAMS, notices.get("copyGlobal", "copyGlobal"))
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
        _report(host, "ui.progress", {"id": progress, "title": title, "done": False})
        copied = skipped = 0
        error = None
        try:
            for job in jobs:
                files, missed = home.copy_missing(job.source, job.target)
                copied, skipped = copied + files, skipped + missed
            self._home_copies(host).mark(instance_id)
        except OSError as failure:
            error = str(failure)
        finally:
            with self._lock:
                self._copying.discard(instance_id)
        _report(host, "ui.progress", {"id": progress, "title": title, "done": True, "error": error})
        if error:
            message = notices.get("copyFailed", "{error}").format(error=error)
        else:
            message = notices.get("copyDone", "{count}").format(count=copied)
            if skipped:
                message += " " + notices.get("copySkipped", "{count}").format(count=skipped)
        _report(host, "ui.notify", {"message": message, "level": "error" if error else "info"})
        payload = {"instanceId": instance_id, "copied": copied, "skipped": skipped, "error": error}
        host.emit_frame("versions", "home-copied", payload)

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

    def _own_layout(self, host: Host, parts: Components, platform: str) -> Layout:
        # A `dsh` instance whose `core` holds Node.js is a global prefix an
        # earlier version attached as `dsh`, its `node` (the prefix's `bin`)
        # owned: a plan would unpack Node.js over it.
        if layout.holds_node_program(parts, platform):
            raise RpcError(REQUEST_FAILED, self._notice(host, "legacyGlobal").format(prefix=parts.core.path))
        return layout.own(platform)

    def _instance(self, host: Host, instance_id: str) -> dict[str, Any]:
        for found in host.call("instances.ofType", {}).get("instances", []):
            if found.get("id") == instance_id:
                return found
        raise RpcError(REQUEST_FAILED, f"no DeepSeek Harness instance {instance_id}")

    def _home_copies(self, host: Host) -> HomeCopies:
        with self._lock:
            if self._copies is None:
                self._copies = HomeCopies(self._data_dir(host) / "home-copied.json")
            return self._copies

    def _notice(self, host: Host, name: str) -> str:
        return str(locale_strings(self._locale(host)).get("notices", {}).get(name, name))

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


def _components(instance: Any) -> Components:
    # Sent with every provider call and listed instance since Hanafubuki 0.3.31.
    parts = layout.components(instance)
    if parts is None:
        raise RpcError(INVALID_PARAMS, "the instance's components are missing (Hanafubuki 0.3.31 sends them)")
    return parts


def own_node_problem(parts: Components, platform: str, texts: dict[str, Any]) -> str | None:
    """Why an external ``node`` cannot run dsh: no program, one too old, or no npm beside it; ``None`` when it can.

    Only a ``dsh`` instance is asked: a global prefix is what it is.
    """
    if not parts.node.external:
        return None
    shape = layout.own(platform)
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


def _report(host: Host, method: str, params: dict[str, Any]) -> None:
    # What the user is told about a copy never stops it.
    try:
        host.call(method, params)
    except RpcError as error:
        host.log("warn", f"{method}: {error.message}")


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

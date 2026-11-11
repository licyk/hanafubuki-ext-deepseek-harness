"""A dsh-shaped npm prefix for the tests: what the launcher and the hook meet in a real install.

``bin.js`` opens its URL as dsh does (``packages/bundle/web-app/src/index.ts``
upstream): it resolves ``open`` in its own process, then imports that URL in
a ``node --input-type=module --eval`` child whose environment is scrubbed of
``/KEY|PASSWORD|SECRET|TOKEN/i`` and ``DSH_*``. The ``open`` package here is
a stand-in browser: it appends each target to ``FAKE_BROWSER_LOG``.

``FAKE_DSH_MODE``: ``open`` (the default) prints the URL line and opens it;
``print`` only prints it, as dsh does under SSH or with ``openBrowser``
off. With ``FAKE_DSH_ONESHOT`` it exits once the opener ended; otherwise it
runs until it is stopped, its pid in ``FAKE_DSH_PIDFILE``.
"""

from __future__ import annotations

import json
from pathlib import Path

BIN = r"""
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";

const OPENER = import.meta.resolve("open");
const PROGRAM = `
const { default: open } = await import(${JSON.stringify(OPENER)});
const launcher = await open(process.argv[1]);
process.exitCode = launcher.exitCode === 0 ? 0 : 1;
`;

const port = process.argv[process.argv.indexOf("--port") + 1];
const url = `http://127.0.0.1:${port}/?token=fake-token-${port}`;
if (process.env.FAKE_DSH_PIDFILE) writeFileSync(process.env.FAKE_DSH_PIDFILE, String(process.pid));
console.log(`dsh web: ${url}`);
const oneshot = Boolean(process.env.FAKE_DSH_ONESHOT);
if ((process.env.FAKE_DSH_MODE ?? "open") === "open") {
  const env = Object.fromEntries(
    Object.entries(process.env).filter(
      ([name]) => !/KEY|PASSWORD|SECRET|TOKEN/i.test(name) && !name.toUpperCase().startsWith("DSH_"),
    ),
  );
  const child = spawn(process.execPath, ["--input-type=module", "--eval", PROGRAM, "--", url], {
    env,
    stdio: ["ignore", "inherit", "inherit"],
  });
  child.on("close", (code) => {
    console.log(`opener exited ${code}`);
    if (oneshot) process.exit(code ?? 1);
  });
} else if (oneshot) {
  process.exit(0);
}
if (!oneshot) setInterval(() => {}, 1000);
"""

OPEN = r"""
import { appendFileSync } from "node:fs";

export const apps = { browser: "browser" };

export async function openApp(name) {
  appendFileSync(process.env.FAKE_BROWSER_LOG, `app:${name}\n`);
  return { exitCode: 0 };
}

export default async function open(target) {
  appendFileSync(process.env.FAKE_BROWSER_LOG, `${target}\n`);
  return { exitCode: 0 };
}
"""


def make_prefix(prefix: Path) -> Path:
    """Writes the fake install under ``prefix`` and returns dsh's ``bin.js``."""
    dsh = prefix / "node_modules" / "@deepseek-ai" / "dsh"
    (dsh / "lib").mkdir(parents=True)
    (dsh / "package.json").write_text(
        json.dumps({"name": "@deepseek-ai/dsh", "version": "0.0.0-test", "type": "module"})
    )
    (dsh / "lib" / "bin.js").write_text(BIN)
    write_open_package(prefix / "node_modules" / "open")
    return dsh / "lib" / "bin.js"


def write_open_package(directory: Path) -> None:
    """Writes the stand-in ``open`` package into ``directory``."""
    directory.mkdir(parents=True)
    (directory / "package.json").write_text(
        json.dumps({"name": "open", "version": "11.0.0", "type": "module", "exports": "./index.js"})
    )
    (directory / "index.js").write_text(OPEN)

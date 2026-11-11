// What dsh gets for the npm `open` package (intercept.mjs redirects it here,
// with the real package's URL as `?original=`). An http(s) URL is written
// to the launcher's channel, which reports it to Hanafubuki; no browser
// starts. Anything else goes to the real package.
import { appendFileSync } from "node:fs";
import { EventEmitter } from "node:events";

const original = new URL(import.meta.url).searchParams.get("original");
const real = original ? await import(original) : {};

export const apps = real.apps ?? {};

export async function openApp(...args) {
  return real.openApp(...args);
}

export default async function open(target, options) {
  const channel = process.env.HFX_DSH_OPEN_CHANNEL;
  if (!channel || typeof target !== "string" || !/^https?:\/\//i.test(target)) {
    return real.default(target, options);
  }
  appendFileSync(channel, `${JSON.stringify({ kind: "open", url: target, pid: process.pid })}\n`);
  return finishedLauncher();
}

// `open` resolves with the launcher process it spawned; dsh's opener waits
// for it on Windows unless it already has an exit code.
function finishedLauncher() {
  const launcher = new EventEmitter();
  launcher.pid = undefined;
  launcher.exitCode = 0;
  launcher.signalCode = null;
  launcher.killed = false;
  launcher.ref = () => launcher;
  launcher.unref = () => launcher;
  launcher.kill = () => false;
  return launcher;
}

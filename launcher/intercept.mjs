// Loaded into every Node process of the dsh tree by `NODE_OPTIONS=--import`
// (launch.py sets it): dsh itself (start-dsh.mjs, which runs dsh's program
// in its own process) and the opener child dsh spawns.
//
// dsh opens its web UI by resolving the npm `open` package in its own
// process (`import.meta.resolve('open')`) and importing that URL in a child
// (`node --input-type=module --eval ...`) whose environment it scrubs of
// names matching /KEY|PASSWORD|SECRET|TOKEN/i and `DSH_*`. This hook
// replaces the `open` installed under dsh's prefix with `open-stub.mjs`,
// which writes the URL to the launcher's channel file instead of starting a
// browser. Our variables survive the scrub: `HFX_DSH_*` matches neither.
//
// In dsh's own process (the launcher's child) it also watches stdout for
// dsh's `dsh web: <url>` line: the launcher's fallback when no opener runs
// (dsh skips it under SSH, or its config turns it off).
//
// Every other Node program dsh runs (tools, MCP servers) loads this too, so
// it does nothing outside dsh's prefix and without the channel.
import { appendFileSync } from "node:fs";
// A namespace import: a Node without `registerHooks` (before 22.15), which a
// tool dsh runs may pin, still loads this file and is left alone.
import * as nodeModule from "node:module";
import { sep } from "node:path";
import { pathToFileURL } from "node:url";

const channel = process.env.HFX_DSH_OPEN_CHANNEL;
const prefix = process.env.HFX_DSH_PREFIX; // dsh's npm prefix: `core`

if (channel && prefix && typeof nodeModule.registerHooks === "function") {
  const fold = (url) => (process.platform === "win32" ? url.toLowerCase() : url);
  const scope = fold(pathToFileURL(prefix.endsWith(sep) ? prefix : prefix + sep).href);
  const stub = new URL("./open-stub.mjs", import.meta.url).href;
  // The `open` package's entry: a file directly in a `node_modules/open/` under dsh's prefix.
  const isOpenEntry = (url) => {
    const folded = fold(url);
    return folded.startsWith(scope) && /\/node_modules\/open\/[^/]+\.js$/.test(folded);
  };

  nodeModule.registerHooks({
    resolve(specifier, context, nextResolve) {
      const resolved = nextResolve(specifier, context);
      // The stub imports the real package for what it does not intercept.
      if (context.parentURL?.startsWith(stub) || !isOpenEntry(resolved.url)) return resolved;
      return {
        url: `${stub}?original=${encodeURIComponent(resolved.url)}`,
        format: "module",
        shortCircuit: true,
      };
    },
  });

  if (String(process.ppid) === process.env.HFX_DSH_LAUNCHER_PID) watchUrlLine();
}

function watchUrlLine() {
  const write = process.stdout.write;
  let pending = "";
  process.stdout.write = function (chunk, ...rest) {
    pending += typeof chunk === "string" ? chunk : Buffer.from(chunk).toString("utf8");
    const lines = pending.split("\n");
    pending = lines.pop().slice(-4096);
    for (const line of lines) {
      const match = /^dsh web: (https?:\/\/\S+)/.exec(line.trim());
      if (match) {
        report("printed", match[1]);
        process.stdout.write = write;
        break;
      }
    }
    return write.call(this, chunk, ...rest);
  };
}

function report(kind, url) {
  try {
    appendFileSync(channel, `${JSON.stringify({ kind, url, pid: process.pid })}\n`);
  } catch {
    // The launcher is gone; nothing reads the channel any more.
  }
}

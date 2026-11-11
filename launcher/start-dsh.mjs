// Starts dsh in this Node process for launch.py:
//
//   node start-dsh.mjs --core <npm prefix> -- <dsh arguments>
//
// `<npm prefix>` is the directory whose `node_modules` holds
// `@deepseek-ai/dsh`. Its program is the package's own `bin.dsh` entry, read
// from its package.json. dsh's entry runs itself only as the process's main
// module (`import.meta.main`); imported, it exports `runCli`, its entry for
// embedding runtimes, which reads `process.argv` as its own command line.
//
// dsh stays in this process: intercept.mjs (loaded through NODE_OPTIONS,
// as in every Node process of the tree) watches the stdout of the
// launcher's direct child for dsh's URL line.
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const PACKAGE = join("node_modules", "@deepseek-ai", "dsh");
// What a missing or unusable install exits with.
const NOT_INSTALLED = 3;

const { core, args } = parseArguments(process.argv.slice(2));
const program = dshProgram(core);
process.argv = [process.argv[0], program, ...args];
try {
  const cli = await import(pathToFileURL(program).href);
  // An entry without `runCli` ran itself when it was imported.
  if (typeof cli.runCli === "function") await cli.runCli();
} catch (error) {
  console.error("start-dsh: dsh failed:", error);
  process.exitCode = 1;
}

function parseArguments(argv) {
  const separator = argv.indexOf("--");
  const own = separator < 0 ? argv : argv.slice(0, separator);
  const index = own.indexOf("--core");
  if (index < 0 || !own[index + 1]) fail("usage: start-dsh.mjs --core <npm prefix> -- <dsh arguments>", 2);
  return { core: resolve(own[index + 1]), args: separator < 0 ? [] : argv.slice(separator + 1) };
}

// The file `bin.dsh` names in dsh's package.json (`bin` may also be one path).
function dshProgram(prefix) {
  const directory = join(prefix, PACKAGE);
  let manifest;
  try {
    manifest = JSON.parse(readFileSync(join(directory, "package.json"), "utf8"));
  } catch (error) {
    fail(
      `start-dsh: DeepSeek Harness is not installed in ${prefix} (${join(PACKAGE, "package.json")}: ${error.code ?? error.message}); install or update the instance`,
      NOT_INSTALLED,
    );
  }
  const bin = typeof manifest?.bin === "string" ? manifest.bin : manifest?.bin?.dsh;
  if (typeof bin !== "string" || !bin) {
    fail(`start-dsh: ${join(directory, "package.json")} names no \`dsh\` program in \`bin\``, NOT_INSTALLED);
  }
  return resolve(directory, bin);
}

function fail(message, code) {
  console.error(message);
  process.exit(code);
}

#!/usr/bin/env bun
/**
 * Builds the three management sections, one frame page each.
 *
 * A Vite build has one entry and one output directory, so this runs it once
 * per page: it writes the entry HTML with that page's name stamped into
 * `data-page` (which `src/pages.ts` reads to choose the view), builds
 * `index.html` with `--mode <page>` (so `vite.config.ts` targets
 * `ui/<page>/`), and removes the stamped file again. `npm run build` runs the
 * type check first and then this.
 */

import { PAGES } from "../src/pages";

const web = `${import.meta.dir}/..`;
const ENTRY = `${web}/index.html`;
const VITE = `${web}/node_modules/vite/bin/vite.js`;

// Vite names each built page after its entry, and a frame is served at
// `ui/<page>/index.html`; the entry is therefore the real `index.html`, whose
// `data-page` this stamps per page and puts back afterwards.
const source = await Bun.file(ENTRY).text();

for (const page of PAGES) {
  await Bun.write(ENTRY, source.replace("%PAGE%", page));
  const build = Bun.spawnSync([process.execPath, VITE, "build", "--mode", page], {
    cwd: web,
    stdout: "inherit",
    stderr: "inherit",
  });
  if (build.exitCode !== 0) {
    await Bun.write(ENTRY, source);
    process.exit(build.exitCode ?? 1);
  }
}

await Bun.write(ENTRY, source);
console.log(`built ${PAGES.length} pages: ${PAGES.join(", ")}`);

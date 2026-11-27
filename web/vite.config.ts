import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

// The extension has three management sections, each its own frame page under
// `ui/<page>/` (manifest `contributes.ui`, one entry per page). Every page is
// built from the same sources, and each is served under a policy of
// `script-src` its own files only and `connect-src 'none'`: relative URLs,
// one flat directory per page (so `../../__hanafubuki/` from its script is
// the package root's, which the host serves), no module preload polyfill (it
// fetches), and the host's modules left as imports. Vue is one of them: the
// page and the component bundle (`ui.js`, which imports `./vue.js`) must
// share the host's one runtime, so every page imports the same
// `__hanafubuki/vue.js`.
const HOST_MODULES: Record<string, string> = {
  "hanafubuki-frame": "../../__hanafubuki/frame.js",
  "hanafubuki-ui": "../../__hanafubuki/ui.js",
  vue: "../../__hanafubuki/vue.js",
};

/** The management sections, one frame page each: its entry, and where it goes. */
export const PAGES = ["versions", "node", "configuration"] as const;
export type PageId = (typeof PAGES)[number];

/**
 * One page per build, `--mode <page>`: the entry HTML's `data-page` names it,
 * so the sources pick which view mounts (`src/pages.ts`) and the output lands
 * in `ui/<page>/`. `scripts/build-pages.ts` runs this once per page.
 */
export default defineConfig(({ mode }) => {
  const page: PageId = PAGES.find((name) => name === mode) ?? PAGES[0];
  return {
    base: "./",
    plugins: [vue()],
    build: {
      outDir: `../ui/${page}`,
      emptyOutDir: true,
      modulePreload: false,
      assetsDir: "",
      rollupOptions: {
        // `scripts/build-pages.ts` stamps `data-page` into this entry before
        // each build and puts the source back after, so every page is built
        // from the same file and lands in its own folder.
        input: "index.html",
        external: Object.keys(HOST_MODULES),
        output: {
          paths: HOST_MODULES,
          entryFileNames: "[name].js",
          chunkFileNames: "[name].js",
          assetFileNames: "[name][extname]",
          // A frame may load its own directory only.
          inlineDynamicImports: true,
        },
      },
    },
  };
});

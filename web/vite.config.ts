import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

// The frame is served from the package at `ui/versions/` under a policy of
// `script-src` its own files only and `connect-src 'none'`: relative URLs,
// one flat directory (so `../../__hanafubuki/` from its script is the package
// root's, which the host serves), no module preload polyfill (it fetches),
// and the host's modules left as imports. Vue is one of them: the page and
// the component bundle (`ui.js`, which imports `./vue.js`) must share the
// host's one runtime, so the page imports the same `__hanafubuki/vue.js`.
const HOST_MODULES: Record<string, string> = {
  "hanafubuki-frame": "../../__hanafubuki/frame.js",
  "hanafubuki-ui": "../../__hanafubuki/ui.js",
  vue: "../../__hanafubuki/vue.js",
};

export default defineConfig({
  base: "./",
  plugins: [vue()],
  build: {
    outDir: "../ui/versions",
    emptyOutDir: true,
    modulePreload: false,
    assetsDir: "",
    rollupOptions: {
      external: Object.keys(HOST_MODULES),
      output: {
        paths: HOST_MODULES,
        entryFileNames: "[name].js",
        chunkFileNames: "[name].js",
        assetFileNames: "[name][extname]",
      },
    },
  },
});

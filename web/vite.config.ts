import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

// The frame is served from the package at `ui/versions/` under a policy of
// `script-src` its own files only and `connect-src 'none'`: relative URLs,
// one flat directory (so `../../__hanafubuki/frame.js` from its script is
// the package root's frame client, which the host serves), no module
// preload polyfill (it fetches), and the frame client left as an import.
const FRAME_CLIENT = "hanafubuki-frame";

export default defineConfig({
  base: "./",
  plugins: [vue()],
  build: {
    outDir: "../ui/versions",
    emptyOutDir: true,
    modulePreload: false,
    assetsDir: "",
    rollupOptions: {
      external: [FRAME_CLIENT],
      output: {
        paths: { [FRAME_CLIENT]: "../../__hanafubuki/frame.js" },
        entryFileNames: "[name].js",
        chunkFileNames: "[name].js",
        assetFileNames: "[name][extname]",
      },
    },
  },
});

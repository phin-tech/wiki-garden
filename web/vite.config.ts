import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { fileURLToPath } from "node:url";

// The compiled app is served by `garden tend` (wiki_garden/_web.py) from a path we
// don't control, so assets must be referenced relatively (base: "./"). Output lands
// *inside the package* at skills/wiki-garden/wiki_garden/web-dist and is committed,
// so end users get the UI without a JS toolchain.
const kitUi = fileURLToPath(new URL("./vendor/kit-ui/lib", import.meta.url));

export default defineConfig({
  base: "./",
  plugins: [svelte()],
  resolve: {
    alias: {
      "@kit-ui": kitUi,
    },
  },
  build: {
    outDir: "../skills/wiki-garden/wiki_garden/web-dist",
    emptyOutDir: true,
    chunkSizeWarningLimit: 1200,
  },
  server: {
    // `bun run dev` proxies the API to a `garden tend` server you run alongside.
    proxy: {
      "/api": "http://127.0.0.1:8787",
    },
  },
});

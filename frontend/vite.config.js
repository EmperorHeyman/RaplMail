import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// Tauri expects a fixed dev port; 1420 is the Tauri convention.
export default defineConfig({
  plugins: [svelte()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: false,
    proxy: {
      // During browser dev, proxy API calls to the Python backend so we avoid
      // CORS and can use same-origin relative URLs.
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
      "/ws": {
        target: "ws://127.0.0.1:8765",
        ws: true,
      },
    },
  },
});

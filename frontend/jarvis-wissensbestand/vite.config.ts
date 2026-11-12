import { defineConfig } from "vite";
import preact from "@preact/preset-vite";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [preact(), tailwindcss()],
  base: "/admin/",
  server: {
    port: 3001,
    strictPort: true,
    proxy: {
      "/admin/wissen": "http://127.0.0.1:8001",
      "/health": "http://127.0.0.1:8001",
      "/ready": "http://127.0.0.1:8001",
    },
  },
  build: {
    outDir: "dist",
    target: "es2020",
    minify: "esbuild",
  },
});

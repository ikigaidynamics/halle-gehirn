import { defineConfig } from "vite";
import preact from "@preact/preset-vite";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [preact(), tailwindcss()],
  server: {
    port: 3000,
    proxy: {
      "/chat": "http://localhost:8001",
      "/health": "http://localhost:8001",
      "/ready": "http://localhost:8001",
    },
  },
  build: {
    target: "es2020",
    minify: "esbuild",
  },
});

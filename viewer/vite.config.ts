import { defineConfig } from "vite";

export default defineConfig({
  build: {
    outDir: "dist",
    emptyOutDir: true,
    target: "es2020",
  },
  server: {
    port: 5173,
    proxy: {
      "/ws":      { target: "ws://localhost:8765", ws: true },
      "/live2d":  { target: "http://localhost:8765", changeOrigin: true },
    },
  },
});

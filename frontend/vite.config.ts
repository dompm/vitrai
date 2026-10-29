import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  ...(mode === "performance"
    ? {
        build: {
          target: "esnext",
          outDir: "dist-performance",
          rollupOptions: { input: "performance/index.html" },
        },
      }
    : {}),
  plugins: [react()],
  server: {
    headers: {
      "Cross-Origin-Opener-Policy": "same-origin",
      "Cross-Origin-Embedder-Policy": "require-corp",
    },
  },
}));

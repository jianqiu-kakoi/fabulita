import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";
import path from "node:path";

export default defineConfig({
  build: {
    target: "es2022",
    sourcemap: false,
    rollupOptions: {
      input: {
        main: path.resolve(
          path.dirname(fileURLToPath(import.meta.url)),
          "index.html",
        ),
        privacy: path.resolve(
          path.dirname(fileURLToPath(import.meta.url)),
          "privacy.html",
        ),
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 4174,
    strictPort: true,
  },
});

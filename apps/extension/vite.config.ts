import { resolve } from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        sidepanel: resolve(__dirname, "sidepanel.html"),
        "focus-fixture": resolve(__dirname, "focus-fixture.html"),
        "service-worker": resolve(__dirname, "src/service-worker.ts"),
        "content-script": resolve(__dirname, "src/content-script.ts")
      },
      output: {
        entryFileNames: (chunk) =>
          ["service-worker", "content-script"].includes(chunk.name)
            ? `${chunk.name}.js`
            : "assets/[name]-[hash].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]"
      }
    }
  }
});

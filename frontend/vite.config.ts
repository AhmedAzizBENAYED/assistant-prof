/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Tauri expects a fixed dev port and does not want Vite to clear its output.
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    target: "es2022",
  },
  test: {
    // Worker threads instead of the default forked processes (ADR-042): on Windows a forked
    // worker twice failed to answer vitest's fixed 60 s start handshake ("Timeout waiting for
    // worker to respond"). Threads start inside the vitest process: no child node.exe, no IPC.
    // Fine here: jsdom and React load no native modules.
    pool: "threads",
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});

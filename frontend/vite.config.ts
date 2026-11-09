/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend answers its API at the root (/prerolls, /schedules, /auth/...),
// so in development every path that isn't one of Vite's own goes to it.
const backend = process.env.PMAX_BACKEND ?? "http://127.0.0.1:9393";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    // /static/ is open before sign-in (see auth_gate.py), so the sign-in page can load.
    assetsDir: "static/app",
    sourcemap: false,
    rollupOptions: {
      output: {
        // Libraries change less often than the app, so browsers keep them cached.
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (/react-markdown|remark|micromark|mdast|unified|hast|unist|vfile|property-information|decode-named/.test(id)) return "markdown";
          if (/@radix-ui/.test(id)) return "radix";
          if (/zod|react-hook-form|@hookform/.test(id)) return "forms";
          if (/react-dom|react-router|scheduler|@tanstack/.test(id)) return "react";
          return "vendor";
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "^/(?!src/|@|node_modules/|icons/|manifest\\.json|favicon\\.ico|$).*": {
        target: backend,
        changeOrigin: false,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    css: false,
  },
});

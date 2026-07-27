import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./", import.meta.url)),
      // lib/api/* guards itself with `server-only`, which throws outside an RSC render
      "server-only": fileURLToPath(new URL("./tests/support/server-only.ts", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/support/setup.ts"],
    // tests/e2e is Playwright's, and it must not be handed to Vitest
    include: ["tests/unit/**/*.test.ts", "tests/unit/**/*.test.tsx"],
    exclude: ["node_modules/**", ".next/**", "tests/e2e/**"],
  },
});

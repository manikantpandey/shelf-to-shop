import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Absolute address for link previews in index.html (%VITE_SITE_URL%/og.png); builds for other hosts set it.
process.env.VITE_SITE_URL ??= "https://shop.shankhyaai.com";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, host: true },
  build: { target: "es2020", sourcemap: false, assetsInlineLimit: 0 },
  test: { environment: "jsdom", include: ["src/**/*.test.{ts,tsx}"] },
});

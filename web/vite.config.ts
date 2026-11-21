import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    fs: { allow: [".."] }, // reference patterns live in ../tests/reference
    proxy: { "/api": process.env.STITCHCRAFT_API ?? "http://localhost:8000" },
  },
  test: { environment: "node" },
});

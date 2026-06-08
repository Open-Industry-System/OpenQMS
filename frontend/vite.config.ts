import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: backendUrl,
        changeOrigin: true,
      },
    },
  },
  optimizeDeps: {
    include: ["@ant-design/charts"],
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});

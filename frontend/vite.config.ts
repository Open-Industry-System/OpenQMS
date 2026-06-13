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
  build: {
    // The Ant ecosystem (antd + @ant-design/charts + @antv/g6 + echarts + d3)
    // has deep cross-dependencies that make fine-grained chunking impossible
    // without circular chunk errors. We accept a larger UI chunk and focus on
    // splitting it from the app code and React core for cache efficiency.
    chunkSizeWarningLimit: 2500,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return;

          // Ant ecosystem: UI framework + charts + graph vis + echarts
          // Cross-deps: @ant-design/charts→@ant-design/graphs→@antv/g6,
          // @ant-design/plots→@antv/g2, echarts↔echarts-for-react
          if (/antd|@ant-design|rc-|echarts|@antv|d3-/.test(id)) return "vendor-ui";

          // React core — rarely changes, cached separately
          if (/react-dom|\/react\//.test(id)) return "vendor-react";

          // Utility libraries
          if (/zustand|axios|dayjs/.test(id)) return "vendor-utils";
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    exclude: ["e2e/**", "node_modules", "dist"],
  },
});
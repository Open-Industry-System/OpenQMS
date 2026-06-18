import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  define: {
    // react-draggable references process.env.DRAGGABLE_DEBUG in its log function;
    // without this, the browser throws ReferenceError: process is not defined,
    // which crashes DraggableCore.handleDragStart and prevents grid drag/resize.
    "process.env.DRAGGABLE_DEBUG": "false",
  },
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
    // Split route code from stable vendor groups. Ant Design is used broadly,
    // while chart / graph engines are loaded by a smaller set of lazy routes;
    // keeping them in separate vendor chunks reduces the largest shared chunk.
    chunkSizeWarningLimit: 2500,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return;

          // Heavy chart / graph engines are loaded only by a few lazy routes.
          // Keep them out of the shared Ant Design UI chunk so the largest
          // vendor chunk is smaller and easier to cache independently.
          if (/echarts/.test(id)) return "vendor-echarts";
          if (/@antv|@ant-design\/(charts|graphs|plots)|d3-/.test(id)) return "vendor-charts";

          // Ant Design ecosystem used broadly across pages.
          if (/antd|@ant-design|rc-/.test(id)) return "vendor-ui";

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
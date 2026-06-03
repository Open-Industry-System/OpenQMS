import { ThemeConfig } from "antd";
import { theme } from "antd";

const prefersReduced =
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export const darkTheme: ThemeConfig = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: "#3b82f6",
    colorSuccess: "#10b981",
    colorWarning: "#f59e0b",
    colorError: "#ef4444",
    colorInfo: "#06b6d4",
    colorBgLayout: "#0a0e1a",
    colorBgContainer: "#111827",
    colorBgElevated: "#1f2937",
    colorText: "#f0f9ff",
    colorTextSecondary: "#94a3b8",
    colorTextTertiary: "#8696a8",
    colorBorder: "rgba(148, 163, 184, 0.2)",
    colorBorderSecondary: "rgba(148, 163, 184, 0.1)",
    borderRadius: 8,
    fontSize: 14,
    fontFamily:
      "system-ui, -apple-system, 'Segoe UI', sans-serif",
    motionDurationMid: prefersReduced ? "0s" : "0.2s",
    motionDurationSlow: prefersReduced ? "0s" : "0.3s",
  },
  components: {
    Layout: {
      headerBg: "#111827",
      bodyBg: "#0a0e1a",
      siderBg: "#111827",
    },
    Card: {
      colorBgContainer: "#111827",
    },
    Menu: {
      colorBgContainer: "#111827",
      itemHoverBg: "#1f2937",
      itemSelectedBg: "#1f2937",
    },
    Table: {
      colorBgContainer: "#111827",
      headerBg: "#1f2937",
    },
  },
};

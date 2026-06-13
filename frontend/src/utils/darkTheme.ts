import type { ThemeConfig } from "antd";
import { theme } from "antd";

const prefersReduced =
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * OpenQMS — Precision Forge 工业暗色主题
 * 与 frontend/src/styles/design-system.css 中的 CSS 变量保持一致。
 */
export const darkTheme: ThemeConfig = {
  algorithm: theme.darkAlgorithm,
  token: {
    // 核心强调色：青蓝为主，琥珀为警告
    colorPrimary: "#00e5ff",
    colorSuccess: "#00d68f",
    colorWarning: "#ffb800",
    colorError: "#ff4757",
    colorInfo: "#3b82f6",
    colorLink: "#00e5ff",

    // 背景层级
    colorBgLayout: "#0b0d12",
    colorBgContainer: "#14161d",
    colorBgElevated: "#1c1f29",
    colorBgSpotlight: "#1c1f29",

    // 文本
    colorText: "#f0f2f5",
    colorTextSecondary: "#8b93a7",
    colorTextTertiary: "#5c6477",

    // 边框
    colorBorder: "rgba(255, 255, 255, 0.08)",
    colorBorderSecondary: "rgba(255, 255, 255, 0.14)",

    // 字体
    fontFamily:
      "'Chakra Petch', 'PingFang SC', 'Microsoft YaHei', sans-serif",
    fontFamilyCode:
      "'JetBrains Mono', 'SF Mono', 'Consolas', monospace",

    // 形状
    borderRadius: 8,
    borderRadiusLG: 12,
    borderRadiusSM: 4,
    fontSize: 14,

    // 动效（尊重减少动画偏好）
    motionDurationFast: prefersReduced ? "0s" : "0.12s",
    motionDurationMid: prefersReduced ? "0s" : "0.2s",
    motionDurationSlow: prefersReduced ? "0s" : "0.3s",
  },
  components: {
    Layout: {
      headerBg: "#14161d",
      bodyBg: "#0b0d12",
      siderBg: "#14161d",
      triggerBg: "#1c1f29",
      triggerColor: "#8b93a7",
    },
    Menu: {
      colorBgContainer: "#14161d",
      itemColor: "#8b93a7",
      itemHoverColor: "#f0f2f5",
      itemHoverBg: "#1c1f29",
      itemSelectedColor: "#00e5ff",
      itemSelectedBg: "rgba(0, 229, 255, 0.1)",
      activeBarBorderWidth: 0,
      activeBarHeight: 0,
    },
    Card: {
      colorBgContainer: "#14161d",
      colorBorderSecondary: "rgba(255, 255, 255, 0.08)",
    },
    Table: {
      colorBgContainer: "#14161d",
      headerBg: "#1c1f29",
      headerColor: "#8b93a7",
      rowHoverBg: "#222633",
      rowSelectedBg: "rgba(0, 229, 255, 0.1)",
      borderColor: "rgba(255, 255, 255, 0.06)",
    },
    Button: {
      colorPrimary: "#00e5ff",
      colorPrimaryHover: "#33ebff",
      colorPrimaryActive: "#00b8d4",
      colorPrimaryText: "#0b0d12",
      colorPrimaryTextHover: "#0b0d12",
      colorPrimaryTextActive: "#0b0d12",
      defaultBg: "#1c1f29",
      defaultBorderColor: "rgba(255, 255, 255, 0.14)",
      defaultColor: "#f0f2f5",
      textHoverBg: "#1c1f29",
    },
    Input: {
      colorBgContainer: "#11141a",
      colorBorder: "rgba(255, 255, 255, 0.08)",
      hoverBorderColor: "#00e5ff",
      activeBorderColor: "#00e5ff",
      activeShadow: "0 0 0 2px rgba(0, 229, 255, 0.2)",
    },
    Select: {
      colorBgContainer: "#11141a",
      colorBorder: "rgba(255, 255, 255, 0.08)",
      hoverBorderColor: "#00e5ff",
      activeBorderColor: "#00e5ff",
      optionSelectedBg: "rgba(0, 229, 255, 0.1)",
      optionSelectedColor: "#00e5ff",
    },
    Modal: {
      contentBg: "#14161d",
      headerBg: "#14161d",
      footerBg: "#14161d",
      titleColor: "#f0f2f5",
    },
    Drawer: {
      colorBgElevated: "#14161d",
      colorText: "#f0f2f5",
    },
    Tag: {
      defaultBg: "#1c1f29",
      defaultColor: "#8b93a7",
    },
    Tabs: {
      colorBgContainer: "transparent",
      itemColor: "#8b93a7",
      itemSelectedColor: "#00e5ff",
      itemHoverColor: "#f0f2f5",
      inkBarColor: "#00e5ff",
    },
    Pagination: {
      colorBgContainer: "transparent",
      colorBgTextHover: "#1c1f29",
      itemActiveBg: "rgba(0, 229, 255, 0.1)",
      itemActiveColor: "#00e5ff",
    },
    Popover: {
      colorBgElevated: "#1c1f29",
    },
    Dropdown: {
      colorBgElevated: "#1c1f29",
    },
    DatePicker: {
      colorBgContainer: "#11141a",
      colorBorder: "rgba(255, 255, 255, 0.08)",
      activeBorderColor: "#00e5ff",
    },
    Message: {
      contentBg: "#1c1f29",
    },
    Notification: {
      colorBgElevated: "#1c1f29",
    },
  },
};

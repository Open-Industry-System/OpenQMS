import type { TFunction } from "i18next";

// Backend stores Chinese severity values; these maps convert between English keys and Chinese values.
// Use getSeverityMap(t) for display labels, getSeverityColor for badge colors.
export const getSeverityMap = (t: TFunction) => ({
  fatal: t("severity.fatal", "致命"),
  serious: t("severity.serious", "严重"),
  general: t("severity.general", "一般"),
  minor: t("severity.minor", "轻微"),
});

export const SEVERITY_COLOR: Record<string, string> = {
  fatal: "red",
  serious: "orange",
  general: "blue",
  minor: "default",
};
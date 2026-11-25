import type { TFunction } from "i18next";

// Backend stores Chinese severity values; these maps convert between English keys and Chinese values.
// Use getSeverityMap(t) for display labels, getSeverityColor for badge colors.
export const getSeverityMap = (t: TFunction) => ({
  fatal: t("severity.fatal"),
  serious: t("severity.serious"),
  general: t("severity.general"),
  minor: t("severity.minor"),
});

export const SEVERITY_COLOR: Record<string, string> = {
  fatal: "red",
  serious: "orange",
  general: "blue",
  minor: "default",
};
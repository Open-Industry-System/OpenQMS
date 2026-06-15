import i18n from "../i18n";

/**
 * Format an ISO timestamp using the application's current language locale,
 * so dates follow the zh-CN / en-US switch (toLocaleString() with no locale
 * arg would otherwise fall back to the host browser locale).
 */
export function formatDateTime(v: string): string {
  return new Date(v).toLocaleString(i18n.language || "zh-CN");
}

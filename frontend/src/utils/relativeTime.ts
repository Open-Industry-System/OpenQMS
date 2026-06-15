import { useTranslation } from "react-i18next";

export function relativeTime(dateStr: string, t: (key: string, options?: Record<string, unknown>) => string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHour = Math.floor(diffMs / 3600000);

  if (diffMin < 5) {
    return t("relativeTime.justNow");
  }
  if (diffHour < 1) {
    return t("relativeTime.minutesAgo", { count: diffMin });
  }
  if (diffHour < 24) {
    return t("relativeTime.hoursAgo", { count: diffHour });
  }
  if (diffHour < 48) {
    return t("relativeTime.yesterday");
  }

  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hour = String(date.getHours()).padStart(2, "0");
  const minute = String(date.getMinutes()).padStart(2, "0");

  return `${month}-${day} ${hour}:${minute}`;
}

export function useRelativeTime(): (dateStr: string) => string {
  const { t } = useTranslation("dashboard");
  return (dateStr: string) => relativeTime(dateStr, t);
}

import { useTranslation } from "react-i18next";

export function useLevelMap(): Record<number, { label: string; color: string; icon: string }> {
  const { t } = useTranslation("qualityGoal");
  return {
    1: { label: t("level.1"), color: "blue", icon: "🏢" },
    2: { label: t("level.2"), color: "green", icon: "🏭" },
    3: { label: t("level.3"), color: "orange", icon: "🔧" },
  };
}

export function useStatusColor(): Record<string, string> {
  return {
    draft: "draft",
    pending: "warning",
    active: "success",
    archived: "closed",
  };
}

export function useStatusMap(): Record<string, string> {
  const { t } = useTranslation("qualityGoal");
  return {
    draft: t("status.draft"),
    pending: t("status.pending"),
    active: t("status.active"),
    archived: t("status.archived"),
  };
}

export function useAchievementMap(): Record<string, { label: string; color: string; prefix: string }> {
  const { t } = useTranslation("qualityGoal");
  return {
    achieved: { label: t("achievement.achieved"), color: "success", prefix: "✅" },
    not_achieved: { label: t("achievement.not_achieved"), color: "error", prefix: "🔴" },
    pending: { label: t("achievement.pending"), color: "draft", prefix: "⏳" },
  };
}

export function usePeriodOptions(): { value: string; label: string }[] {
  const { t } = useTranslation("qualityGoal");
  return [
    { value: t("period.monthly.value"), label: t("period.monthly.label") },
    { value: t("period.quarterly.value"), label: t("period.quarterly.label") },
    { value: t("period.yearly.value"), label: t("period.yearly.label") },
  ];
}

export function usePeriodLabelMap(): Record<string, string> {
  const { t } = useTranslation("qualityGoal");
  return {
    [t("period.monthly.value")]: t("period.monthly.label"),
    [t("period.quarterly.value")]: t("period.quarterly.label"),
    [t("period.yearly.value")]: t("period.yearly.label"),
  };
}
import { useTranslation } from "react-i18next";

export const STATUS_COLORS: Record<string, string> = {
  open: "default",
  in_progress: "processing",
  responded: "warning",
  verified: "success",
  closed: "default",
};

export function useSCARStatusMap(): Record<string, string> {
  const { t } = useTranslation("scar");
  return {
    open: t("status.open"),
    in_progress: t("status.in_progress"),
    responded: t("status.responded"),
    verified: t("status.verified"),
    closed: t("status.closed"),
  };
}

export function useSCARSourceMap(): Record<string, string> {
  const { t } = useTranslation("scar");
  return {
    iqc: t("source.iqc"),
    complaint: t("source.complaint"),
    rma: t("source.rma"),
    manual: t("source.manual"),
  };
}

export function useSCARTabs(): { key: string; label: string }[] {
  const { t } = useTranslation("scar");
  return [
    { key: "all", label: t("tabs.all") },
    { key: "pending", label: t("tabs.pending") },
    { key: "responded", label: t("tabs.responded") },
    { key: "verified", label: t("tabs.verified") },
    { key: "closed", label: t("tabs.closed") },
  ];
}

export function useSCARSourceOptions(): { value: string; label: string }[] {
  const { t } = useTranslation("scar");
  return [
    { value: "iqc", label: t("source.iqc") },
    { value: "complaint", label: t("source.complaint") },
    { value: "rma", label: t("source.rma") },
    { value: "manual", label: t("source.manual") },
  ];
}

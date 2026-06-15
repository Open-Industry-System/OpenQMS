import { useTranslation } from "react-i18next";

export function useAuditTypeMap(): Record<string, string> {
  const { t } = useTranslation("internalAudit");
  return {
    system: t("auditType.system"),
    process: t("auditType.process"),
    product: t("auditType.product"),
  };
}

export function useAuditStatusColor(): Record<string, string> {
  return {
    planned: "info",
    in_progress: "warning",
    completed: "success",
    cancelled: "info",
  };
}

export function useAuditStatusMap(): Record<string, string> {
  const { t } = useTranslation("internalAudit");
  return {
    planned: t("status.audit.planned"),
    in_progress: t("status.audit.in_progress"),
    completed: t("status.audit.completed"),
    cancelled: t("status.audit.cancelled"),
  };
}

export function useFindingTypeMap(): Record<string, { label: string; color: string }> {
  const { t } = useTranslation("internalAudit");
  return {
    major_nc: { label: t("findingType.major_nc"), color: "error" },
    minor_nc: { label: t("findingType.minor_nc"), color: "warning" },
    ofi: { label: t("findingType.ofi"), color: "info" },
    observation: { label: t("findingType.observation"), color: "info" },
  };
}

export function useFindingStatusMap(): Record<string, { label: string; color: string }> {
  const { t } = useTranslation("internalAudit");
  return {
    open: { label: t("status.finding.open"), color: "error" },
    in_progress: { label: t("status.finding.in_progress"), color: "warning" },
    verified: { label: t("status.finding.verified"), color: "info" },
    closed: { label: t("status.finding.closed"), color: "success" },
  };
}

export function useResultOptions(): { value: string; label: string }[] {
  const { t } = useTranslation("internalAudit");
  return [
    { value: t("resultOptions.conform.value"), label: t("resultOptions.conform.label") },
    { value: t("resultOptions.nonConform.value"), label: t("resultOptions.nonConform.label") },
    { value: t("resultOptions.notApplicable.value"), label: t("resultOptions.notApplicable.label") },
  ];
}
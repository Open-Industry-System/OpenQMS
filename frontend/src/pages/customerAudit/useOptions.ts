import { useTranslation } from "react-i18next";

export function useAuditStatusMap(): Record<string, string> {
  const { t } = useTranslation("customerQuality");
  return {
    planned: t("status.audit.planned"),
    in_progress: t("status.audit.in_progress"),
    completed: t("status.audit.completed"),
    cancelled: t("status.audit.cancelled"),
  };
}

export function useAuditStatusColor(): Record<string, string> {
  return {
    planned: "blue",
    in_progress: "processing",
    completed: "success",
    cancelled: "default",
  };
}

export function useFindingStatusMap(): Record<string, string> {
  const { t } = useTranslation("customerQuality");
  return {
    open: t("status.finding.open"),
    in_progress: t("status.finding.in_progress"),
    closed: t("status.finding.closed"),
  };
}

export function useFindingStatusColor(): Record<string, string> {
  return {
    open: "error",
    in_progress: "processing",
    closed: "success",
  };
}

export function useFindingTypeMap(): Record<string, string> {
  const { t } = useTranslation("customerQuality");
  return {
    major_nc: t("findingType.major_nc"),
    minor_nc: t("findingType.minor_nc"),
    ofi: t("findingType.ofi"),
    observation: t("findingType.observation"),
  };
}

export function useAuditModeMap(): Record<string, string> {
  const { t } = useTranslation("customerQuality");
  return {
    on_site: t("auditMode.on_site"),
    remote: t("auditMode.remote"),
  };
}

export function useCustomerTypeOptions() {
  const { t } = useTranslation("customerQuality");
  return [
    { value: "OEM", label: t("customerType.OEM") },
    { value: "Tier 1", label: t("customerType.Tier 1") },
    { value: "Tier 2", label: t("customerType.Tier 2") },
    { value: "other", label: t("customerType.other") },
  ];
}

export function useCustomerTypeLabel() {
  const { t } = useTranslation("customerQuality");
  return (value?: string | null) => {
    if (!value) return "-";
    return t([`customerType.${value}`, value]);
  };
}

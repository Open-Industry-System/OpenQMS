import { useTranslation } from "react-i18next";
import { SEVERITY_COLOR, SEVERITY_MAP } from "./constants";

export function useSeverityReverseMap(): Record<string, string> {
  return Object.fromEntries(Object.entries(SEVERITY_MAP).map(([k, v]) => [v, k]));
}

export function useSeverityOptions() {
  const { t } = useTranslation("customerQuality");
  return Object.keys(SEVERITY_MAP).map((key) => ({
    value: key,
    label: t(`severity.${key}`),
  }));
}

export function useSeverityColor(): Record<string, string> {
  return SEVERITY_COLOR;
}

export function useCategoryOptions() {
  const { t } = useTranslation("customerQuality");
  return [
    { value: "safety", label: t("category.safety") },
    { value: "function", label: t("category.function") },
    { value: "appearance", label: t("category.appearance") },
    { value: "delivery", label: t("category.delivery") },
  ];
}

export function useComplaintStatusMap(): Record<string, string> {
  const { t } = useTranslation("customerQuality");
  return {
    open: t("status.complaint.open"),
    investigating: t("status.complaint.investigating"),
    responded: t("status.complaint.responded"),
    closed: t("status.complaint.closed"),
    cancelled: t("status.complaint.cancelled"),
  };
}

export function useRmaStatusMap(): Record<string, string> {
  const { t } = useTranslation("customerQuality");
  return {
    open: t("status.rma.open"),
    analysis: t("status.rma.analysis"),
    action_pending: t("status.rma.action_pending"),
    closed: t("status.rma.closed"),
    cancelled: t("status.rma.cancelled"),
  };
}

export function useResponsibilityOptions() {
  const { t } = useTranslation("customerQuality");
  return [
    { value: "supplier", label: t("responsibility.supplier") },
    { value: "internal", label: t("responsibility.internal") },
    { value: "transport", label: t("responsibility.transport") },
    { value: "customer_misuse", label: t("responsibility.customer_misuse") },
    { value: "unknown", label: t("responsibility.unknown") },
  ];
}

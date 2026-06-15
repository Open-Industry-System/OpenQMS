import { useTranslation } from "react-i18next";

export function useReviewStatusColor(): Record<string, string> {
  return {
    draft: "info",
    data_collected: "info",
    in_review: "warning",
    closed: "success",
  };
}

export function useReviewStatusMap(): Record<string, string> {
  const { t } = useTranslation("managementReview");
  return {
    draft: t("status.review.draft"),
    data_collected: t("status.review.data_collected"),
    in_review: t("status.review.in_review"),
    closed: t("status.review.closed"),
  };
}

export function useReportStatusColor(): Record<string, string> {
  return {
    none: "info",
    draft: "info",
    final: "success",
  };
}

export function useReportStatusMap(): Record<string, string> {
  const { t } = useTranslation("managementReview");
  return {
    none: t("status.report.none"),
    draft: t("status.report.draft"),
    final: t("status.report.final"),
  };
}

export function useOutputStatusColor(): Record<string, string> {
  return {
    pending: "info",
    in_progress: "warning",
    completed: "warning",
    verified: "success",
  };
}

export function useOutputStatusMap(): Record<string, string> {
  const { t } = useTranslation("managementReview");
  return {
    pending: t("status.output.pending"),
    in_progress: t("status.output.in_progress"),
    completed: t("status.output.completed"),
    verified: t("status.output.verified"),
  };
}

export function useCategoryLabels(): Record<string, string> {
  const { t } = useTranslation("managementReview");
  return {
    improvement_opportunity: t("category.improvement_opportunity"),
    system_change: t("category.system_change"),
    resource_need: t("category.resource_need"),
  };
}

export function useDataSources() {
  const { t } = useTranslation("managementReview");
  const autoDataSources = [
    { key: "quality_goals", title: t("dataSource.qualityGoals") },
    { key: "internal_audits", title: t("dataSource.internalAudits") },
    { key: "capa_stats", title: t("dataSource.capaStats") },
    { key: "fmea_risks", title: t("dataSource.fmeaRisks") },
    { key: "spc_capability", title: t("dataSource.spcCapability") },
    { key: "supplier_performance", title: t("dataSource.supplierPerformance") },
    { key: "previous_review_actions", title: t("dataSource.previousReviewActions") },
  ];

  const manualTextSources = [
    { key: "external_factors", title: t("dataSource.externalFactors") },
    { key: "resource_adequacy", title: t("dataSource.resourceAdequacy") },
  ];

  const manualRichSources = [
    { key: "customer_satisfaction", title: t("dataSource.customerSatisfaction") },
    { key: "equipment_monitoring", title: t("dataSource.equipmentMonitoring") },
    { key: "copq", title: t("dataSource.copq") },
    { key: "manufacturing_feasibility", title: t("dataSource.manufacturingFeasibility") },
  ];

  return { autoDataSources, manualTextSources, manualRichSources };
}
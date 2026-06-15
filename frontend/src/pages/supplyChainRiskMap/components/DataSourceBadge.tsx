import React from "react";
import { StatusBadge } from "../../../components/design";
import { useTranslation } from "react-i18next";

const DataSourceBadge: React.FC<{ source: string }> = ({ source }) => {
  const { t } = useTranslation("supplyChainRiskMap");

  const SOURCE_VARIANTS: Record<string, { label: string; status: string }> = {
    risk_evaluation: { label: t("dataSource.risk_evaluation"), status: "info" },
    erp_po: { label: t("dataSource.erp_po"), status: "success" },
    supplier_evaluation_fallback: { label: t("dataSource.supplier_evaluation_fallback"), status: "warning" },
    iqc_inspection: { label: t("dataSource.iqc_inspection"), status: "info" },
    missing: { label: t("dataSource.missing"), status: "info" },
  };

  const config = SOURCE_VARIANTS[source] ?? SOURCE_VARIANTS.missing;
  return <StatusBadge status={config.status} style={{ fontSize: 10, lineHeight: "16px" }}>{config.label}</StatusBadge>;
};

export default DataSourceBadge;

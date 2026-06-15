import React from "react";
import { Tag } from "antd";
import { useTranslation } from "react-i18next";

interface DataSourceBadgeProps {
  source: string;
}

const DataSourceBadge: React.FC<DataSourceBadgeProps> = ({ source }) => {
  const { t } = useTranslation("supplyChainRiskMap");

  const SOURCE_LABELS: Record<string, { label: string; color: string }> = {
    risk_evaluation: { label: t("dataSource.risk_evaluation"), color: "blue" },
    erp_po: { label: t("dataSource.erp_po"), color: "green" },
    supplier_evaluation_fallback: { label: t("dataSource.supplier_evaluation_fallback"), color: "orange" },
    iqc_inspection: { label: t("dataSource.iqc_inspection"), color: "purple" },
    missing: { label: t("dataSource.missing"), color: "default" },
  };

  const config = SOURCE_LABELS[source] ?? SOURCE_LABELS.missing;
  return <Tag color={config.color} style={{ fontSize: 10, lineHeight: "16px" }}>{config.label}</Tag>;
};

export default DataSourceBadge;

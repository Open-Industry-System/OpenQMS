import React from "react";
import { StatusBadge } from "../../../components/design";

const SOURCE_VARIANTS: Record<string, { label: string; status: string }> = {
  risk_evaluation: { label: "风险评分", status: "info" },
  erp_po: { label: "ERP", status: "success" },
  supplier_evaluation_fallback: { label: "供应商评价", status: "warning" },
  iqc_inspection: { label: "IQC", status: "info" },
  missing: { label: "无数据", status: "info" },
};

interface DataSourceBadgeProps {
  source: string;
}

const DataSourceBadge: React.FC<DataSourceBadgeProps> = ({ source }) => {
  const config = SOURCE_VARIANTS[source] ?? SOURCE_VARIANTS.missing;
  return <StatusBadge status={config.status} style={{ fontSize: 10, lineHeight: "16px" }}>{config.label}</StatusBadge>;
};

export default DataSourceBadge;

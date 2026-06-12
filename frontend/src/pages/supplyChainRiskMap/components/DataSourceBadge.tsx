import React from "react";
import { Tag } from "antd";

const SOURCE_LABELS: Record<string, { label: string; color: string }> = {
  risk_evaluation: { label: "风险评分", color: "blue" },
  erp_po: { label: "ERP", color: "green" },
  supplier_evaluation_fallback: { label: "供应商评价", color: "orange" },
  iqc_inspection: { label: "IQC", color: "purple" },
  missing: { label: "无数据", color: "default" },
};

interface DataSourceBadgeProps {
  source: string;
}

const DataSourceBadge: React.FC<DataSourceBadgeProps> = ({ source }) => {
  const config = SOURCE_LABELS[source] ?? SOURCE_LABELS.missing;
  return <Tag color={config.color} style={{ fontSize: 10, lineHeight: "16px" }}>{config.label}</Tag>;
};

export default DataSourceBadge;
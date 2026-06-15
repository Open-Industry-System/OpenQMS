import React from "react";
import { Scatter } from "@ant-design/charts";
import { useTranslation } from "react-i18next";
import type { RiskDashboard } from "../../../types";

interface Props {
  data: RiskDashboard["supplier_risk_points"];
}

const RiskMatrixChart: React.FC<Props> = ({ data }) => {
  const { t } = useTranslation("supplierRisk");
  const config = {
    data,
    xField: "quality_score",
    yField: "delivery_score",
    sizeField: "compliance_score",
    colorField: "risk_level",
    color: { low: "#52c41a", medium: "#faad14", high: "#fa8c16", critical: "#f5222d" },
    xAxis: { title: { text: t("riskMatrix.xAxis") }, min: 0, max: 100 },
    yAxis: { title: { text: t("riskMatrix.yAxis") }, min: 0, max: 100 },
    tooltip: { fields: ["supplier_name", "risk_score", "risk_level"] },
    shape: "circle",
  };
  return <Scatter {...config} />;
};

export default RiskMatrixChart;

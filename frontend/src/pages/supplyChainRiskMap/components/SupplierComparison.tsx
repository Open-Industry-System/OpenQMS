import React, { useEffect, useState } from "react";
import { Table, Empty, Spin } from "antd";
import { useTranslation } from "react-i18next";
import { riskMapApi } from "../../../api/supplyChainRiskMap";
import type { ComparisonResponse } from "../../../types";
import { DataCard } from "../../../components/design";
import DataSourceBadge from "./DataSourceBadge";

interface SupplierComparisonProps {
  supplierIds: string[];
  productLineCode: string | null;
  period: string;
}

const COLORS = ["#1890ff", "#52c41a", "#fa8c16", "#722ed1", "#eb2f96"];

const SupplierComparison: React.FC<SupplierComparisonProps> = ({ supplierIds, productLineCode, period }) => {
  const { t } = useTranslation("supplyChainRiskMap");
  const [data, setData] = useState<ComparisonResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const DIMENSION_LABELS: Record<string, string> = {
    risk_score: t("comparison.dimensions.risk_score"),
    quality_score: t("comparison.dimensions.quality_score"),
    delivery_score: t("comparison.dimensions.delivery_score"),
    compliance_score: t("comparison.dimensions.compliance_score"),
    erp_on_time_rate: t("comparison.dimensions.erp_on_time_rate"),
    purchase_amount_pct: t("comparison.dimensions.purchase_amount_pct"),
    open_scar_count: t("comparison.dimensions.open_scar_count"),
    ppm_value: t("comparison.dimensions.ppm_value"),
  };

  useEffect(() => {
    if (supplierIds.length < 2) {
      setData(null);
      return;
    }
    setLoading(true);
    riskMapApi.compare(supplierIds, {
      product_line_code: productLineCode ?? undefined,
      period,
    })
      .then((res) => setData(res.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [supplierIds, productLineCode, period]);

  if (loading) return <Spin />;
  if (!data || data.suppliers.length < 2) return <Empty description={t("comparison.selectMultiple")} />;

  const dimensionKeys = Object.keys(data.suppliers[0]?.dimensions ?? {});

  const columns = [
    { title: t("comparison.dimension"), dataIndex: "dimension", key: "dimension", width: 100 },
    ...data.suppliers.map((s, i) => ({
      title: (
        <span>
          <span style={{ display: "inline-block", width: 10, height: 10, borderRadius: "50%", backgroundColor: COLORS[i % COLORS.length], marginRight: 6 }} />
          {s.supplier_name}
        </span>
      ),
      dataIndex: s.supplier_id,
      key: s.supplier_id,
      align: "center" as const,
    })),
  ];

  const tableData = dimensionKeys.map((key) => {
    const row: Record<string, React.ReactNode> = { dimension: DIMENSION_LABELS[key] ?? key };
    data.suppliers.forEach((s) => {
      const dim = s.dimensions[key];
      if (!dim) {
        row[s.supplier_id] = "—";
        return;
      }
      const formatted = dim.raw_value !== null
        ? key.includes("rate") || key.includes("pct")
          ? `${dim.raw_value.toFixed(1)}%`
          : dim.raw_value.toFixed(1)
        : "—";
      row[s.supplier_id] = (
        <span>
          {formatted}
          <DataSourceBadge source={dim.source} />
        </span>
      );
    });
    return row;
  });

  return (
    <DataCard title={t("comparison.title")}>
      <Table
        className="qf-table"
        columns={columns}
        dataSource={tableData}
        pagination={false}
        size="small"
        rowKey="dimension"
      />
    </DataCard>
  );
};

export default SupplierComparison;

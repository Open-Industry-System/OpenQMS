import React, { useEffect, useState } from "react";
import { Table, Empty, Spin } from "antd";
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

const DIMENSION_LABELS: Record<string, string> = {
  risk_score: "风险分",
  quality_score: "质量分",
  delivery_score: "交付分",
  compliance_score: "合规分",
  erp_on_time_rate: "ERP准时率",
  purchase_amount_pct: "采购占比",
  open_scar_count: "开放SCAR",
  ppm_value: "PPM",
};

const SupplierComparison: React.FC<SupplierComparisonProps> = ({ supplierIds, productLineCode, period }) => {
  const [data, setData] = useState<ComparisonResponse | null>(null);
  const [loading, setLoading] = useState(false);

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
  if (!data || data.suppliers.length < 2) return <Empty description="选择2个或以上供应商进行对比" />;

  const dimensionKeys = Object.keys(data.suppliers[0]?.dimensions ?? {});

  const columns = [
    { title: "维度", dataIndex: "dimension", key: "dimension", width: 100 },
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
    <DataCard title="供应商对比">
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

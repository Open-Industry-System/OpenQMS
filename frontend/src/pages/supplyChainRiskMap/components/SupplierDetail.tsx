import React, { useEffect, useState } from "react";
import { Card, Descriptions, Spin, Empty } from "antd";
import { riskMapApi } from "../../../api/supplyChainRiskMap";
import type { SupplierDetailResponse } from "../../../types";
import DataSourceBadge from "./DataSourceBadge";

interface SupplierDetailProps {
  supplierId: string;
  productLineCode: string | null;
  period: string;
}

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

const SupplierDetail: React.FC<SupplierDetailProps> = ({ supplierId, productLineCode, period }) => {
  const [detail, setDetail] = useState<SupplierDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!supplierId) return;
    setLoading(true);
    riskMapApi.supplierDetail(supplierId, {
      product_line_code: productLineCode ?? undefined,
      period,
    })
      .then((res) => setDetail(res.data))
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [supplierId, productLineCode, period]);

  if (loading) return <Spin />;
  if (!detail) return <Empty description="选择供应商查看详情" />;

  return (
    <Card title={detail.supplier_name} size="small" style={{ marginBottom: 16 }}>
      <Descriptions column={1} size="small">
        <Descriptions.Item label="周期">{detail.period}</Descriptions.Item>
        {Object.entries(detail.dimensions).map(([key, dim]) => (
          <Descriptions.Item key={key} label={DIMENSION_LABELS[key] ?? key}>
            <span style={{ fontWeight: 500 }}>
              {dim.raw_value !== null ? (key.includes("rate") || key.includes("pct") ? `${dim.raw_value.toFixed(1)}%` : dim.raw_value.toFixed(1)) : "—"}
            </span>
            {dim.risk_index !== null && (
              <span style={{ fontSize: 11, color: "#999", marginLeft: 4 }}>
                (风险指数: {dim.risk_index.toFixed(0)})
              </span>
            )}
            <DataSourceBadge source={dim.source} />
          </Descriptions.Item>
        ))}
      </Descriptions>
      {detail.trend.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, color: "#666", marginBottom: 8 }}>趋势（最近6期）</div>
          <table style={{ width: "100%", fontSize: 11, borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", padding: 4 }}>周期</th>
                <th style={{ textAlign: "center", padding: 4 }}>风险</th>
                <th style={{ textAlign: "center", padding: 4 }}>质量</th>
                <th style={{ textAlign: "center", padding: 4 }}>交付</th>
                <th style={{ textAlign: "center", padding: 4 }}>合规</th>
              </tr>
            </thead>
            <tbody>
              {detail.trend.map((t) => (
                <tr key={t.period}>
                  <td style={{ padding: 4 }}>{t.period}</td>
                  <td style={{ textAlign: "center", padding: 4 }}>{t.risk_score.toFixed(1)}</td>
                  <td style={{ textAlign: "center", padding: 4 }}>{t.quality_score.toFixed(1)}</td>
                  <td style={{ textAlign: "center", padding: 4 }}>{t.delivery_score.toFixed(1)}</td>
                  <td style={{ textAlign: "center", padding: 4 }}>{t.compliance_score.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
};

export default SupplierDetail;
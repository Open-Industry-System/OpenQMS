import React, { useEffect, useState } from "react";
import { Card, Descriptions, Spin, Empty } from "antd";
import { useTranslation } from "react-i18next";
import { riskMapApi } from "../../../api/supplyChainRiskMap";
import type { SupplierDetailResponse } from "../../../types";
import DataSourceBadge from "./DataSourceBadge";

interface SupplierDetailProps {
  supplierId: string;
  productLineCode: string | null;
  period: string;
}

const SupplierDetail: React.FC<SupplierDetailProps> = ({ supplierId, productLineCode, period }) => {
  const { t } = useTranslation("supplyChainRiskMap");
  const [detail, setDetail] = useState<SupplierDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const DIMENSION_LABELS: Record<string, string> = {
    risk_score: t("detail.dimensions.risk_score"),
    quality_score: t("detail.dimensions.quality_score"),
    delivery_score: t("detail.dimensions.delivery_score"),
    compliance_score: t("detail.dimensions.compliance_score"),
    erp_on_time_rate: t("detail.dimensions.erp_on_time_rate"),
    purchase_amount_pct: t("detail.dimensions.purchase_amount_pct"),
    open_scar_count: t("detail.dimensions.open_scar_count"),
    ppm_value: t("detail.dimensions.ppm_value"),
  };

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
  if (!detail) return <Empty description={t("detail.selectSupplier")} />;

  return (
    <Card title={detail.supplier_name} size="small" style={{ marginBottom: 16 }}>
      <Descriptions column={1} size="small">
        <Descriptions.Item label={t("detail.period")}>{detail.period}</Descriptions.Item>
        {Object.entries(detail.dimensions).map(([key, dim]) => (
          <Descriptions.Item key={key} label={DIMENSION_LABELS[key] ?? key}>
            <span style={{ fontWeight: 500 }}>
              {dim.raw_value !== null ? (key.includes("rate") || key.includes("pct") ? `${dim.raw_value.toFixed(1)}%` : dim.raw_value.toFixed(1)) : "—"}
            </span>
            {dim.risk_index !== null && (
              <span style={{ fontSize: 11, color: "#999", marginLeft: 4 }}>
                {t("detail.riskIndex", { index: dim.risk_index.toFixed(0) })}
              </span>
            )}
            <DataSourceBadge source={dim.source} />
          </Descriptions.Item>
        ))}
      </Descriptions>
      {detail.trend.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, color: "#666", marginBottom: 8 }}>{t("detail.trendHeader")}</div>
          <table style={{ width: "100%", fontSize: 11, borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", padding: 4 }}>{t("detail.trendColumns.period")}</th>
                <th style={{ textAlign: "center", padding: 4 }}>{t("detail.trendColumns.risk")}</th>
                <th style={{ textAlign: "center", padding: 4 }}>{t("detail.trendColumns.quality")}</th>
                <th style={{ textAlign: "center", padding: 4 }}>{t("detail.trendColumns.delivery")}</th>
                <th style={{ textAlign: "center", padding: 4 }}>{t("detail.trendColumns.compliance")}</th>
              </tr>
            </thead>
            <tbody>
              {detail.trend.map((trend) => (
                <tr key={trend.period}>
                  <td style={{ padding: 4 }}>{trend.period}</td>
                  <td style={{ textAlign: "center", padding: 4 }}>{trend.risk_score.toFixed(1)}</td>
                  <td style={{ textAlign: "center", padding: 4 }}>{trend.quality_score.toFixed(1)}</td>
                  <td style={{ textAlign: "center", padding: 4 }}>{trend.delivery_score.toFixed(1)}</td>
                  <td style={{ textAlign: "center", padding: 4 }}>{trend.compliance_score.toFixed(1)}</td>
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

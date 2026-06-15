import { useEffect, useState } from "react";
import { Card, Tabs, Table, Tag, Spin, Row, Col } from "antd";
import { useTranslation } from "react-i18next";
import { Line } from "@ant-design/charts";
import { useParams } from "react-router-dom";
import { getSupplierQualityDetail, listCertifications, listEvaluations } from "../../../api/supplier";
import type { SupplierQualityDetailResponse, SupplierCertification, SupplierEvaluation } from "../../../types";

export default function SupplierDetailView() {
  const { t } = useTranslation("supplier");
  const { supplierId } = useParams<{ supplierId: string }>();
  const [data, setData] = useState<SupplierQualityDetailResponse | null>(null);
  const [certifications, setCertifications] = useState<SupplierCertification[]>([]);
  const [evaluations, setEvaluations] = useState<SupplierEvaluation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (supplierId) {
      loadDetail();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [supplierId]);

  const loadDetail = async () => {
    setLoading(true);
    try {
      const detail = await getSupplierQualityDetail(supplierId!);
      setData(detail);
      const [certs, evals] = await Promise.all([
        listCertifications(supplierId!),
        listEvaluations(supplierId!),
      ]);
      setCertifications(certs);
      setEvaluations(evals);
    } finally {
      setLoading(false);
    }
  };

  if (loading || !data) {
    return (
      <div style={{ textAlign: "center", padding: "100px 0" }}>
        <Spin size="large" />
      </div>
    );
  }

  const gradeColors: Record<string, string> = { A: "#52c41a", B: "#1677ff", C: "#faad14", D: "#ff4d4f" };

  const ppmTrendConfig = {
    data: data.ppm_trend,
    xField: "month",
    yField: "ppm",
    point: { size: 4 },
    smooth: true,
  };

  const acceptanceTrendConfig = {
    data: data.acceptance_trend.map((d) => ({ ...d, rate: d.rate * 100 })),
    xField: "month",
    yField: "rate",
    point: { size: 4 },
    smooth: true,
  };

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <Row gutter={16} align="middle">
          <Col flex="auto">
            <h2 style={{ margin: 0 }}>
              {data.supplier.name}
              <Tag color={gradeColors[data.stats.grade]} style={{ marginLeft: 8 }}>
                {t("detail.grade", { grade: data.stats.grade })}
              </Tag>
            </h2>
            <div style={{ color: "#888" }}>{data.supplier.supplier_no}</div>
          </Col>
          <Col>
            <Row gutter={24}>
              <Col style={{ textAlign: "center" }}>
                <div style={{ fontSize: 12, color: "#888" }}>{t("quality.kpi.totalScore")}</div>
                <div style={{ fontSize: 24, fontWeight: 700, color: "#1677ff" }}>
                  {data.stats.total_score.toFixed(0)}
                </div>
              </Col>
              <Col style={{ textAlign: "center" }}>
                <div style={{ fontSize: 12, color: "#888" }}>{t("detail.qualityScore")}</div>
                <div style={{ fontSize: 24, fontWeight: 700 }}>
                  {data.stats.quality_score.toFixed(0)}
                </div>
              </Col>
              <Col style={{ textAlign: "center" }}>
                <div style={{ fontSize: 12, color: "#888" }}>{t("detail.deliveryScore")}</div>
                <div style={{ fontSize: 24, fontWeight: 700 }}>
                  {data.stats.delivery_score.toFixed(0)}
                </div>
              </Col>
            </Row>
          </Col>
        </Row>
      </Card>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={12}>
          <Card title={t("quality.charts.ppmTrendMonthly")}>
            <Line {...ppmTrendConfig} />
          </Card>
        </Col>
        <Col span={12}>
          <Card title={t("quality.charts.acceptanceTrend")}>
            <Line {...acceptanceTrendConfig} />
          </Card>
        </Col>
      </Row>

      <Card>
        <Tabs
          items={[
            {
              key: "stats",
              label: t("quality.tabs.stats"),
              children: (
                <Row gutter={[16, 16]}>
                  <Col span={6}>
                    <div style={{ fontSize: 12, color: "#888" }}>{t("quality.kpi.ppm")}</div>
                    <div style={{ fontSize: 20, fontWeight: 600 }}>
                      {data.stats.ppm.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </div>
                  </Col>
                  <Col span={6}>
                    <div style={{ fontSize: 12, color: "#888" }}>{t("quality.kpi.batchAcceptanceRate")}</div>
                    <div style={{ fontSize: 20, fontWeight: 600 }}>
                      {(data.stats.batch_acceptance_rate * 100).toFixed(1)}%
                    </div>
                  </Col>
                  <Col span={6}>
                    <div style={{ fontSize: 12, color: "#888" }}>{t("quality.kpi.totalInspections")}</div>
                    <div style={{ fontSize: 20, fontWeight: 600 }}>{data.stats.total_inspections}</div>
                  </Col>
                  <Col span={6}>
                    <div style={{ fontSize: 12, color: "#888" }}>{t("quality.kpi.acceptedCount")}</div>
                    <div style={{ fontSize: 20, fontWeight: 600 }}>{data.stats.accepted_count}</div>
                  </Col>
                  <Col span={6}>
                    <div style={{ fontSize: 12, color: "#888" }}>{t("quality.kpi.scarCount")}</div>
                    <div style={{ fontSize: 20, fontWeight: 600 }}>{data.stats.scar_count}</div>
                  </Col>
                  <Col span={6}>
                    <div style={{ fontSize: 12, color: "#888" }}>{t("quality.kpi.openScar")}</div>
                    <div style={{ fontSize: 20, fontWeight: 600, color: data.stats.open_scar_count > 0 ? "#ff4d4f" : undefined }}>
                      {data.stats.open_scar_count}
                    </div>
                  </Col>
                </Row>
              ),
            },
            {
              key: "certifications",
              label: t("quality.tabs.certificates"),
              children: (
                <Table
                  dataSource={certifications}
                  columns={[
                    { title: t("table.certType"), dataIndex: "cert_type" },
                    { title: t("table.certNo"), dataIndex: "cert_no" },
                    { title: t("table.issuedBy"), dataIndex: "issued_by" },
                    { title: t("table.expiryDate"), dataIndex: "expiry_date" },
                  ]}
                  rowKey="cert_id"
                  pagination={false}
                  size="small"
                />
              ),
            },
            {
              key: "evaluations",
              label: t("quality.tabs.evalHistory"),
              children: (
                <Table
                  dataSource={evaluations}
                  columns={[
                    { title: t("form.evalPeriod"), dataIndex: "eval_period" },
                    { title: t("quality.column.evalType"), dataIndex: "eval_type" },
                    { title: t("quality.column.grade"), dataIndex: "grade", render: (g: string) => <Tag color={gradeColors[g]}>{g}</Tag> },
                    { title: t("quality.column.totalScore"), dataIndex: "total_score" },
                    { title: t("detail.qualityScore"), dataIndex: "quality_score" },
                    { title: t("detail.deliveryScore"), dataIndex: "delivery_score" },
                  ]}
                  rowKey="eval_id"
                  pagination={false}
                  size="small"
                />
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
}

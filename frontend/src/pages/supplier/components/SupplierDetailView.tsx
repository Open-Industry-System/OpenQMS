import { useEffect, useState } from "react";
import { Card, Tabs, Table, Tag, Spin, Row, Col } from "antd";
import { Line } from "@ant-design/charts";
import { useParams } from "react-router-dom";
import { getSupplierQualityDetail, listCertifications, listEvaluations } from "../../../api/supplier";
import type { SupplierQualityDetailResponse, SupplierCertification, SupplierEvaluation } from "../../../types";

export default function SupplierDetailView() {
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
                {data.stats.grade}级
              </Tag>
            </h2>
            <div style={{ color: "#888" }}>{data.supplier.supplier_no}</div>
          </Col>
          <Col>
            <Row gutter={24}>
              <Col style={{ textAlign: "center" }}>
                <div style={{ fontSize: 12, color: "#888" }}>综合得分</div>
                <div style={{ fontSize: 24, fontWeight: 700, color: "#1677ff" }}>
                  {data.stats.total_score.toFixed(0)}
                </div>
              </Col>
              <Col style={{ textAlign: "center" }}>
                <div style={{ fontSize: 12, color: "#888" }}>质量得分</div>
                <div style={{ fontSize: 24, fontWeight: 700 }}>
                  {data.stats.quality_score.toFixed(0)}
                </div>
              </Col>
              <Col style={{ textAlign: "center" }}>
                <div style={{ fontSize: 12, color: "#888" }}>交付得分</div>
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
          <Card title="PPM 月度趋势">
            <Line {...ppmTrendConfig} />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="批次合格率趋势">
            <Line {...acceptanceTrendConfig} />
          </Card>
        </Col>
      </Row>

      <Card>
        <Tabs
          items={[
            {
              key: "stats",
              label: "质量统计",
              children: (
                <Row gutter={[16, 16]}>
                  <Col span={6}>
                    <div style={{ fontSize: 12, color: "#888" }}>PPM</div>
                    <div style={{ fontSize: 20, fontWeight: 600 }}>
                      {data.stats.ppm.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </div>
                  </Col>
                  <Col span={6}>
                    <div style={{ fontSize: 12, color: "#888" }}>批次合格率</div>
                    <div style={{ fontSize: 20, fontWeight: 600 }}>
                      {(data.stats.batch_acceptance_rate * 100).toFixed(1)}%
                    </div>
                  </Col>
                  <Col span={6}>
                    <div style={{ fontSize: 12, color: "#888" }}>检验批次</div>
                    <div style={{ fontSize: 20, fontWeight: 600 }}>{data.stats.total_inspections}</div>
                  </Col>
                  <Col span={6}>
                    <div style={{ fontSize: 12, color: "#888" }}>合格批次</div>
                    <div style={{ fontSize: 20, fontWeight: 600 }}>{data.stats.accepted_count}</div>
                  </Col>
                  <Col span={6}>
                    <div style={{ fontSize: 12, color: "#888" }}>SCAR总数</div>
                    <div style={{ fontSize: 20, fontWeight: 600 }}>{data.stats.scar_count}</div>
                  </Col>
                  <Col span={6}>
                    <div style={{ fontSize: 12, color: "#888" }}>未关闭SCAR</div>
                    <div style={{ fontSize: 20, fontWeight: 600, color: data.stats.open_scar_count > 0 ? "#ff4d4f" : undefined }}>
                      {data.stats.open_scar_count}
                    </div>
                  </Col>
                </Row>
              ),
            },
            {
              key: "certifications",
              label: "资质证书",
              children: (
                <Table
                  dataSource={certifications}
                  columns={[
                    { title: "证书类型", dataIndex: "cert_type" },
                    { title: "证书编号", dataIndex: "cert_no" },
                    { title: "颁发机构", dataIndex: "issued_by" },
                    { title: "有效期", dataIndex: "expiry_date" },
                  ]}
                  rowKey="cert_id"
                  pagination={false}
                  size="small"
                />
              ),
            },
            {
              key: "evaluations",
              label: "评价历史",
              children: (
                <Table
                  dataSource={evaluations}
                  columns={[
                    { title: "评价周期", dataIndex: "eval_period" },
                    { title: "类型", dataIndex: "eval_type" },
                    { title: "评级", dataIndex: "grade", render: (g: string) => <Tag color={gradeColors[g]}>{g}</Tag> },
                    { title: "总分", dataIndex: "total_score" },
                    { title: "质量", dataIndex: "quality_score" },
                    { title: "交付", dataIndex: "delivery_score" },
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

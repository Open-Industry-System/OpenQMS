import { useEffect, useState } from "react";
import { Row, Col, Card, Table, Tag, Typography } from "antd";
import { useNavigate } from "react-router-dom";
import { getDashboard } from "../../api/dashboard";
import KPICard from "../../components/shared/KPICard";
import type { DashboardData } from "../../types";
import { useProductLineStore } from "../../store/productLineStore";

const { Title } = Typography;

export default function DashboardPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const productLine = useProductLineStore((s) => s.selected);

  useEffect(() => {
    getDashboard(productLine || undefined)
      .then(setData)
      .finally(() => setLoading(false));
  }, [productLine]);

  const kpi = data?.kpi;

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>
        质量仪表盘
      </Title>

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <KPICard title="FMEA 文档总数" value={kpi?.total_fmea ?? 0} color="#1677FF" />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KPICard title="已批准 FMEA" value={kpi?.approved_fmea ?? 0} color="#52C41A" />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KPICard title="开放 8D 报告" value={kpi?.open_capa ?? 0} color="#FAAD14" />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KPICard
            title="超期 8D"
            value={kpi?.overdue_capa ?? 0}
            color={kpi && kpi.overdue_capa > 0 ? "#FF4D4F" : "#52C41A"}
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} sm={12} lg={6}>
          <KPICard
            title="平均 RPN"
            value={kpi?.avg_rpn ?? 0}
            color={
              kpi && kpi.avg_rpn >= 100
                ? "#FF4D4F"
                : kpi && kpi.avg_rpn >= 50
                  ? "#FAAD14"
                  : "#52C41A"
            }
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KPICard
            title="高风险项 (RPN≥100)"
            value={kpi?.high_rpn_count ?? 0}
            color={kpi && kpi.high_rpn_count > 0 ? "#FF4D4F" : "#52C41A"}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KPICard title="8D 报告总数" value={kpi?.total_capa ?? 0} color="#1677FF" />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} sm={12} lg={6}>
          <div onClick={() => navigate("/special-characteristics?approval_status=submitted")} style={{ cursor: "pointer" }}>
            <KPICard
              title="待安全审批"
              value={kpi?.pending_safety_approval ?? 0}
              color={kpi && kpi.pending_safety_approval > 0 ? "#FF4D4F" : "#52C41A"}
            />
          </div>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <div onClick={() => navigate("/special-characteristics?suggested_only=true")} style={{ cursor: "pointer" }}>
            <KPICard
              title="安全建议待确认"
              value={kpi?.safety_suggestions ?? 0}
              color={kpi && kpi.safety_suggestions > 0 ? "#FAAD14" : "#52C41A"}
            />
          </div>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KPICard title="安全特性总数" value={kpi?.total_safety ?? 0} color="#1677FF" />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} sm={12} lg={6}>
          <KPICard title="管理评审总数" value={kpi?.management_review?.total_reviews ?? 0} color="#1677FF" />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <div onClick={() => navigate("/management-reviews")} style={{ cursor: "pointer" }}>
            <KPICard
              title="评审措施完成率"
              value={Math.round((kpi?.management_review?.completion_rate ?? 0) * 1000) / 10}
              suffix="%"
              color={
                (kpi?.management_review?.completion_rate ?? 0) >= 0.8
                  ? "#52C41A"
                  : (kpi?.management_review?.completion_rate ?? 0) >= 0.5
                    ? "#FAAD14"
                    : "#FF4D4F"
              }
            />
          </div>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KPICard
            title="待验证措施"
            value={kpi?.management_review?.pending_verification ?? 0}
            color={kpi && kpi.management_review && kpi.management_review.pending_verification > 0 ? "#FAAD14" : "#52C41A"}
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={24}>
          <Card title="数据概览" loading={loading}>
            <Table
              dataSource={[
                {
                  key: "fmea",
                  metric: "FMEA 文档",
                  total: kpi?.total_fmea ?? 0,
                  approved: kpi?.approved_fmea ?? 0,
                },
                {
                  key: "capa",
                  metric: "8D 报告",
                  total: kpi?.total_capa ?? 0,
                  open: kpi?.open_capa ?? 0,
                  overdue: kpi?.overdue_capa ?? 0,
                },
                {
                  key: "rpn",
                  metric: "风险指标",
                  avg_rpn: kpi?.avg_rpn ?? 0,
                  high_risk: kpi?.high_rpn_count ?? 0,
                },
              ]}
              columns={[
                { title: "指标", dataIndex: "metric", key: "metric" },
                { title: "总数", dataIndex: "total", key: "total", render: (v: number) => v ?? "-" },
                { title: "已批准", dataIndex: "approved", key: "approved", render: (v: number) => v ?? "-" },
                {
                  title: "进行中",
                  dataIndex: "open",
                  key: "open",
                  render: (v: number) =>
                    v !== undefined ? <Tag color="processing">{v}</Tag> : "-",
                },
                {
                  title: "超期",
                  dataIndex: "overdue",
                  key: "overdue",
                  render: (v: number) =>
                    v !== undefined && v > 0 ? (
                      <Tag color="error">{v}</Tag>
                    ) : v === 0 ? (
                      <Tag color="success">0</Tag>
                    ) : (
                      "-"
                    ),
                },
                {
                  title: "平均 RPN",
                  dataIndex: "avg_rpn",
                  key: "avg_rpn",
                  render: (v: number) => (v !== undefined ? v : "-"),
                },
                {
                  title: "高风险",
                  dataIndex: "high_risk",
                  key: "high_risk",
                  render: (v: number) =>
                    v !== undefined && v > 0 ? (
                      <Tag color="error">{v}</Tag>
                    ) : v === 0 ? (
                      <Tag color="success">0</Tag>
                    ) : (
                      "-"
                    ),
                },
              ]}
              pagination={false}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
}

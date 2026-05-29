import { useEffect, useState } from "react";
import { Row, Col, Card, List, Button, Tag, Typography, Space, Statistic } from "antd";
import {
  AlertOutlined,
  ClockCircleOutlined,
  WarningOutlined,
  RiseOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import {
  getDashboardSummary,
  getDashboardAlerts,
  getDashboardRecentActions,
} from "../../api/dashboard";
import type { DashboardSummary, DashboardAlerts, DashboardRecentAction } from "../../types";
import { useProductLineStore } from "../../store/productLineStore";

const { Title } = Typography;

export default function DashboardPage() {
  const navigate = useNavigate();
  const productLine = useProductLineStore((s) => s.selected);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [alerts, setAlerts] = useState<DashboardAlerts | null>(null);
  const [recentActions, setRecentActions] = useState<DashboardRecentAction[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      getDashboardSummary(productLine || undefined),
      getDashboardAlerts(productLine || undefined),
      getDashboardRecentActions(),
    ])
      .then(([s, a, r]) => {
        setSummary(s);
        setAlerts(a);
        setRecentActions(r);
      })
      .finally(() => setLoading(false));
  }, [productLine]);

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>
        质量仪表盘
      </Title>

      {/* 顶部指标卡 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable onClick={() => navigate("/capa?pending_action=true")}>
            <Statistic
              title="待办事项"
              value={summary?.pending_actions ?? 0}
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: (summary?.pending_actions ?? 0) > 0 ? "#FAAD14" : "#52C41A" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable onClick={() => navigate("/capa?overdue=true")}>
            <Statistic
              title="超期任务"
              value={summary?.overdue_tasks ?? 0}
              prefix={<AlertOutlined />}
              valueStyle={{ color: (summary?.overdue_tasks ?? 0) > 0 ? "#FF4D4F" : "#52C41A" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable onClick={() => navigate("/fmea?risk=high")}>
            <Statistic
              title="高风险项"
              value={summary?.high_risk_items ?? 0}
              prefix={<WarningOutlined />}
              valueStyle={{ color: (summary?.high_risk_items ?? 0) > 0 ? "#FF4D4F" : "#52C41A" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="本月趋势"
              value={summary?.month_trend ?? 0}
              prefix={<RiseOutlined />}
              valueStyle={{
                color: (summary?.month_trend ?? 0) >= 0 ? "#52C41A" : "#FF4D4F",
              }}
            />
          </Card>
        </Col>
      </Row>

      {/* 风险预警区 */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={8}>
          <Card title="高 RPN FMEA" size="small" loading={loading}>
            <List
              dataSource={alerts?.high_rpn_fmeas ?? []}
              locale={{ emptyText: "无高风险项" }}
              renderItem={(item) => (
                <List.Item
                  style={{ cursor: "pointer" }}
                  onClick={() => navigate(`/fmea/${item.fmea_id}`)}
                >
                  <List.Item.Meta
                    title={item.document_no}
                    description={item.node_name}
                  />
                  <Tag color="error">RPN={item.rpn}</Tag>
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="超期 CAPA" size="small" loading={loading}>
            <List
              dataSource={alerts?.overdue_capas ?? []}
              locale={{ emptyText: "无超期任务" }}
              renderItem={(item) => (
                <List.Item
                  style={{ cursor: "pointer" }}
                  onClick={() => navigate(`/capa/${item.report_id}`)}
                >
                  <List.Item.Meta
                    title={item.document_no}
                    description={`超期 ${item.overdue_days} 天`}
                  />
                  <Tag color="error">{item.overdue_days}天</Tag>
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="PPM 超标供应商" size="small" loading={loading}>
            <List
              dataSource={alerts?.high_ppm_suppliers ?? []}
              locale={{ emptyText: "无超标供应商" }}
              renderItem={(item) => (
                <List.Item
                  style={{ cursor: "pointer" }}
                  onClick={() => navigate(`/suppliers/${item.supplier_id}`)}
                >
                  <List.Item.Meta
                    title={item.supplier_name}
                    description={`PPM: ${item.ppm}`}
                  />
                  <Tag color="warning">PPM={item.ppm}</Tag>
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>

      {/* 底部：最近操作 + 快速入口 */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={16}>
          <Card title="最近操作" size="small" loading={loading}>
            <List
              dataSource={recentActions}
              locale={{ emptyText: "暂无操作记录" }}
              renderItem={(item) => {
                const typeMap: Record<string, { label: string; path: string }> = {
                  fmea_documents: { label: "FMEA", path: "/fmea" },
                  capa_eightd: { label: "CAPA", path: "/capa" },
                };
                const info = typeMap[item.table_name] || {
                  label: item.table_name,
                  path: "/",
                };
                return (
                  <List.Item
                    style={{ cursor: "pointer" }}
                    onClick={() => navigate(`${info.path}/${item.record_id}`)}
                  >
                    <List.Item.Meta
                      title={`${info.label} - ${item.entity_no}`}
                      description={`${item.action} · ${new Date(item.operated_at).toLocaleString("zh-CN")}`}
                    />
                  </List.Item>
                );
              }}
            />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="快速入口" size="small">
            <Space direction="vertical" style={{ width: "100%" }}>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                block
                onClick={() => navigate("/fmea")}
              >
                新建 FMEA
              </Button>
              <Button
                icon={<PlusOutlined />}
                block
                onClick={() => navigate("/capa")}
              >
                新建 CAPA
              </Button>
              <Button
                icon={<PlusOutlined />}
                block
                onClick={() => navigate("/customer-quality")}
              >
                新建客诉
              </Button>
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  );
}

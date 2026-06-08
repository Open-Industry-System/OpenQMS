import { useEffect, useState } from "react";
import { Row, Col, Card, Statistic, Table, Typography, Spin, App } from "antd";
import {
  InboxOutlined,
  ApartmentOutlined,
  FileTextOutlined,
  SafetyOutlined,
} from "@ant-design/icons";
import { getPLMDashboard } from "../../api/plm";
import type { PLMDashboard, PLMChangeOrder } from "../../types/plm";

const { Title } = Typography;

export default function PLMDashboardPage() {
  const { message } = App.useApp();
  const [data, setData] = useState<PLMDashboard | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getPLMDashboard()
      .then(setData)
      .catch(() => message.error("加载 PLM 看板数据失败"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div style={{ textAlign: "center", paddingTop: 120 }}>
        <Spin size="large" />
      </div>
    );
  }

  const recentColumns = [
    { title: "变更编号", dataIndex: "change_number", key: "change_number", width: 160 },
    { title: "标题", dataIndex: "title", key: "title", ellipsis: true },
    { title: "变更类型", dataIndex: "change_type", key: "change_type", width: 120 },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (s: string) => <span>{s}</span>,
    },
    { title: "优先级", dataIndex: "priority", key: "priority", width: 80 },
    {
      title: "更新时间",
      dataIndex: "source_updated_at",
      key: "source_updated_at",
      width: 170,
      render: (v: string | null) => (v ? new Date(v).toLocaleString("zh-CN") : "—"),
    },
  ];

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>
        PLM 集成看板
      </Title>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="零件总数"
              value={data?.part_count ?? 0}
              prefix={<InboxOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="BOM 条目"
              value={data?.bom_count ?? 0}
              prefix={<ApartmentOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="待处理 ECN"
              value={data?.pending_ecn_count ?? 0}
              prefix={<FileTextOutlined />}
              valueStyle={{ color: (data?.pending_ecn_count ?? 0) > 0 ? "#faad14" : undefined }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="待处理特殊特性"
              value={data?.pending_sc_count ?? 0}
              prefix={<SafetyOutlined />}
              valueStyle={{ color: (data?.pending_sc_count ?? 0) > 0 ? "#ff4d4f" : undefined }}
            />
          </Card>
        </Col>
      </Row>

      <Card title="最近变更">
        <Table<PLMChangeOrder>
          columns={recentColumns}
          dataSource={data?.recent_changes ?? []}
          rowKey="change_id"
          pagination={false}
          size="small"
        />
      </Card>
    </div>
  );
}

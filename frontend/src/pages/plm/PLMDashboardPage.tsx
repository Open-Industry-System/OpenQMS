import { useEffect, useState } from "react";
import { Row, Col, Card, Statistic, Table, Spin, App } from "antd";
import {
  InboxOutlined,
  ApartmentOutlined,
  FileTextOutlined,
  SafetyOutlined,
} from "@ant-design/icons";
import { getPLMDashboard } from "../../api/plm";
import { useProductLineStore } from "../../store/productLineStore";
import type { PLMDashboard, PLMChangeOrder } from "../../types/plm";
import { PageShell, DataCard, StatusBadge } from "../../components/design";

const statusVariant: Record<string, string> = {
  open: "info",
  in_review: "warning",
  approved: "success",
  implemented: "info",
  closed: "info",
  cancelled: "error",
};

export default function PLMDashboardPage() {
  const { message } = App.useApp();
  const productLine = useProductLineStore((s) => s.selected);
  const [data, setData] = useState<PLMDashboard | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getPLMDashboard({ product_line_code: productLine || undefined })
      .then(setData)
      .catch(() => message.error("加载 PLM 看板数据失败"))
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine]);

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
      render: (s: string) => (
        <StatusBadge status={statusVariant[s] || s}>{s}</StatusBadge>
      ),
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
    <PageShell title="PLM 集成看板">
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

      <DataCard title="最近变更">
        <Table<PLMChangeOrder>
          columns={recentColumns}
          dataSource={data?.recent_changes ?? []}
          rowKey="change_id"
          pagination={false}
          size="small"
          className="qf-table"
        />
      </DataCard>
    </PageShell>
  );
}

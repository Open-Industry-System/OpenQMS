import { useEffect, useState } from "react";
import {
  Table, Tag, Typography, Row, Col, Card, Statistic, App,
} from "antd";
import {
  CheckCircleOutlined, CloseCircleOutlined,
  ScheduleOutlined, CarryOutOutlined,
} from "@ant-design/icons";
import { getMESDashboard } from "../../api/mes";
import { useProductLineStore } from "../../store/productLineStore";
import type { MESDashboardData, MESEquipmentSummary } from "../../types/mes";

const { Title } = Typography;

const statusColors: Record<string, string> = {
  running: "success",
  idle: "default",
  down: "error",
  changeover: "warning",
};

const statusLabels: Record<string, string> = {
  running: "运行中",
  idle: "待机",
  down: "停机",
  changeover: "换模中",
};

export default function MESDashboardPage() {
  const { message } = App.useApp();
  const [data, setData] = useState<MESDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const productLine = useProductLineStore((s) => s.selected);

  const fetchData = (plCode?: string | null) => {
    setLoading(true);
    getMESDashboard(plCode || undefined)
      .then((res) => setData(res))
      .catch(() => message.error("加载 MES 仪表盘失败"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData(productLine);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine]);

  const columns = [
    {
      title: "设备名称",
      dataIndex: "equipment_name",
      key: "equipment_name",
      render: (v: string | null, record: MESEquipmentSummary) =>
        v || record.equipment_code,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (s: string) => (
        <Tag color={statusColors[s] || "default"}>
          {statusLabels[s] || s}
        </Tag>
      ),
    },
    {
      title: "可用率 (%)",
      dataIndex: "availability",
      key: "availability",
      width: 110,
      render: (v: number | null) =>
        v !== null ? `${v.toFixed(1)}%` : "—",
    },
    {
      title: "性能 (%)",
      dataIndex: "performance",
      key: "performance",
      width: 100,
      render: (v: number | null) =>
        v !== null ? `${v.toFixed(1)}%` : "—",
    },
    {
      title: "质量 (%)",
      dataIndex: "quality",
      key: "quality",
      width: 100,
      render: (v: number | null) =>
        v !== null ? `${v.toFixed(1)}%` : "—",
    },
    {
      title: "OEE (%)",
      dataIndex: "oee",
      key: "oee",
      width: 100,
      render: (v: number | null) =>
        v !== null ? `${v.toFixed(1)}%` : "—",
    },
  ];

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>
        MES 仪表盘
      </Title>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card loading={loading}>
            <Statistic
              title="运行设备"
              value={data?.running_count ?? 0}
              valueStyle={{ color: "#52c41a" }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card loading={loading}>
            <Statistic
              title="停机设备"
              value={data?.down_count ?? 0}
              valueStyle={{ color: "#ff4d4f" }}
              prefix={<CloseCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card loading={loading}>
            <Statistic
              title="计划产量"
              value={data?.total_planned ?? 0}
              prefix={<ScheduleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card loading={loading}>
            <Statistic
              title="实际产量"
              value={data?.total_actual ?? 0}
              prefix={<CarryOutOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Title level={5} style={{ marginBottom: 8 }}>
        设备状态
      </Title>
      <Table
        columns={columns}
        dataSource={data?.equipment_summary ?? []}
        rowKey={(r: MESEquipmentSummary) => `${r.connection_id}:${r.equipment_code}`}
        loading={loading}
        pagination={false}
        size="small"
      />
    </div>
  );
}

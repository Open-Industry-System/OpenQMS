import { useEffect, useState, useMemo } from "react";
import {
  Table, Row, Col, Card, Statistic, App,
} from "antd";
import {
  CheckCircleOutlined, CloseCircleOutlined,
  ScheduleOutlined, CarryOutOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { getMESDashboard } from "../../api/mes";
import { useProductLineStore } from "../../store/productLineStore";
import type { MESDashboardData, MESEquipmentSummary } from "../../types/mes";
import { PageShell, DataCard, StatusBadge } from "../../components/design";

const statusVariant: Record<string, string> = {
  running: "success",
  idle: "info",
  down: "error",
  changeover: "warning",
};

export default function MESDashboardPage() {
  const { t } = useTranslation("mes");
  const { message } = App.useApp();
  const [data, setData] = useState<MESDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const productLine = useProductLineStore((s) => s.selected);

  const statusLabels = useMemo(() => ({
    running: t("dashboard.equipmentStatusLabels.running"),
    idle: t("dashboard.equipmentStatusLabels.idle"),
    down: t("dashboard.equipmentStatusLabels.down"),
    changeover: t("dashboard.equipmentStatusLabels.changeover"),
  }), [t]);

  const fetchData = (plCode?: string | null) => {
    setLoading(true);
    getMESDashboard(plCode || undefined)
      .then((res) => setData(res))
      .catch(() => message.error(t("dashboard.errors.loadFailed")))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData(productLine);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine]);

  const columns = useMemo(() => [
    {
      title: t("dashboard.columns.equipmentName"),
      dataIndex: "equipment_name",
      key: "equipment_name",
      render: (v: string | null, record: MESEquipmentSummary) =>
        v || record.equipment_code,
    },
    {
      title: t("dashboard.columns.status"),
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (s: string) => (
        <StatusBadge status={statusVariant[s] || s}>
          {statusLabels[s as keyof typeof statusLabels] || s}
        </StatusBadge>
      ),
    },
    {
      title: t("dashboard.columns.availability"),
      dataIndex: "availability",
      key: "availability",
      width: 110,
      render: (v: number | null) =>
        v !== null ? `${v.toFixed(1)}%` : "—",
    },
    {
      title: t("dashboard.columns.performance"),
      dataIndex: "performance",
      key: "performance",
      width: 100,
      render: (v: number | null) =>
        v !== null ? `${v.toFixed(1)}%` : "—",
    },
    {
      title: t("dashboard.columns.quality"),
      dataIndex: "quality",
      key: "quality",
      width: 100,
      render: (v: number | null) =>
        v !== null ? `${v.toFixed(1)}%` : "—",
    },
    {
      title: t("dashboard.columns.oee", "OEE (%)"),
      dataIndex: "oee",
      key: "oee",
      width: 100,
      render: (v: number | null) =>
        v !== null ? `${v.toFixed(1)}%` : "—",
    },
  ], [t, statusLabels]);

  return (
    <PageShell title={t("dashboard.title")}>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card loading={loading}>
            <Statistic
              title={t("dashboard.stats.runningEquipment")}
              value={data?.running_count ?? 0}
              valueStyle={{ color: "#52c41a" }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card loading={loading}>
            <Statistic
              title={t("dashboard.stats.downEquipment")}
              value={data?.down_count ?? 0}
              valueStyle={{ color: "#ff4d4f" }}
              prefix={<CloseCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card loading={loading}>
            <Statistic
              title={t("dashboard.stats.plannedOutput")}
              value={data?.total_planned ?? 0}
              prefix={<ScheduleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card loading={loading}>
            <Statistic
              title={t("dashboard.stats.actualOutput")}
              value={data?.total_actual ?? 0}
              prefix={<CarryOutOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <DataCard title={t("dashboard.equipmentStatus")}>
        <Table
          columns={columns}
          dataSource={data?.equipment_summary ?? []}
          rowKey={(r: MESEquipmentSummary) => `${r.connection_id}:${r.equipment_code}`}
          loading={loading}
          pagination={false}
          size="small"
          className="qf-table"
        />
      </DataCard>
    </PageShell>
  );
}
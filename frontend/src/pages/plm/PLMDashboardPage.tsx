import { useEffect, useState } from "react";
import { Row, Col, Statistic, Table, Spin, App } from "antd";
import {
  InboxOutlined,
  ApartmentOutlined,
  FileTextOutlined,
  SafetyOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation("plm");
  const { message } = App.useApp();
  const productLine = useProductLineStore((s) => s.selected);
  const [data, setData] = useState<PLMDashboard | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getPLMDashboard({ product_line_code: productLine || undefined })
      .then(setData)
      .catch(() => message.error(t("dashboard.errors.loadFailed")))
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
    { title: t("dashboard.columns.changeNumber"), dataIndex: "change_number", key: "change_number", width: 160 },
    { title: t("dashboard.columns.title"), dataIndex: "title", key: "title", ellipsis: true },
    { title: t("dashboard.columns.changeType"), dataIndex: "change_type", key: "change_type", width: 120 },
    {
      title: t("dashboard.columns.status"),
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (s: string) => (
        <StatusBadge status={statusVariant[s] || s}>{s}</StatusBadge>
      ),
    },
    { title: t("dashboard.columns.priority"), dataIndex: "priority", key: "priority", width: 80 },
    {
      title: t("dashboard.columns.updatedAt"),
      dataIndex: "source_updated_at",
      key: "source_updated_at",
      width: 170,
      render: (v: string | null) => (v ? new Date(v).toLocaleString("zh-CN") : "—"),
    },
  ];

  return (
    <PageShell title={t("dashboard.title")}>
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <DataCard title={null}>
            <Statistic
              title={t("dashboard.stats.totalParts")}
              value={data?.part_count ?? 0}
              prefix={<InboxOutlined />}
            />
          </DataCard>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <DataCard title={null}>
            <Statistic
              title={t("dashboard.stats.bomItems")}
              value={data?.bom_count ?? 0}
              prefix={<ApartmentOutlined />}
            />
          </DataCard>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <DataCard title={null}>
            <Statistic
              title={t("dashboard.stats.pendingECNs")}
              value={data?.pending_ecn_count ?? 0}
              prefix={<FileTextOutlined />}
              valueStyle={{ color: (data?.pending_ecn_count ?? 0) > 0 ? "#faad14" : undefined }}
            />
          </DataCard>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <DataCard title={null}>
            <Statistic
              title={t("dashboard.stats.pendingSCs")}
              value={data?.pending_sc_count ?? 0}
              prefix={<SafetyOutlined />}
              valueStyle={{ color: (data?.pending_sc_count ?? 0) > 0 ? "#ff4d4f" : undefined }}
            />
          </DataCard>
        </Col>
      </Row>

      <DataCard title={t("dashboard.recentChanges")}>
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

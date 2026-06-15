import { useEffect, useMemo, useState } from "react";
import {
  Row, Col, Statistic, Spin, App,
  Button, Space,
} from "antd";
import {
  CheckCircleOutlined, CloseCircleOutlined,
  SyncOutlined, DollarOutlined,
  WarningOutlined, LinkOutlined,
} from "@ant-design/icons";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { fetchERPDashboard } from "../../api/erp";
import { useProductLineStore } from "../../store/productLineStore";
import { PageShell, DataCard, StatusBadge } from "../../components/design";
import type { ERPDashboardData } from "../../types/erp";
import { formatDateTime } from "../../utils/dateTime";

const syncStatusVariants: Record<string, string> = {
  completed: "success",
  failed: "error",
  running: "warning",
  pending: "warning",
};

export default function ERPDashboardPage() {
  const { t } = useTranslation("erp");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const productLine = useProductLineStore((s) => s.selected);
  const [data, setData] = useState<ERPDashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  const syncStatusLabels = useMemo((): Record<string, string> => ({
    completed: t("dashboard.syncStatus.completed", "已完成"),
    failed: t("dashboard.syncStatus.failed", "失败"),
    running: t("dashboard.syncStatus.running", "同步中"),
    pending: t("dashboard.syncStatus.pending", "待同步"),
  }), [t]);

  useEffect(() => {
    fetchERPDashboard()
      .then(setData)
      .catch(() => message.error(t("dashboard.errors.loadFailed", "加载 ERP 看板数据失败")))
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

  if (!data) {
    return <div style={{ padding: 24 }}>{t("dashboard.errors.loadFailed", "加载失败")}</div>;
  }

  return (
    <PageShell title={t("dashboard.title", "ERP 集成看板")}>
      {/* Sync Health */}
      <DataCard
        title={t("dashboard.syncHealth", "同步健康")}
        style={{ marginBottom: 16 }}
        extra={
          <Space>
            {data.sync_health.map((s) => (
              <StatusBadge
                key={s.data_type}
                status={syncStatusVariants[s.status] || "info"}
              >
                {s.data_type}: {syncStatusLabels[s.status] || s.status}
              </StatusBadge>
            ))}
          </Space>
        }
      >
        {data.sync_health.length === 0 ? (
          <span style={{ color: "#999" }}>{t("dashboard.noSyncData", "暂无同步数据")}</span>
        ) : (
          <Row gutter={[16, 8]}>
            {data.sync_health.map((s) => (
              <Col key={s.data_type} xs={24} sm={12} md={8} lg={6}>
                <Statistic
                  title={s.data_type}
                  value={s.last_sync ? formatDateTime(s.last_sync) : "—"}
                  valueStyle={{ fontSize: 14 }}
                />
              </Col>
            ))}
          </Row>
        )}
      </DataCard>

      {/* KPI Cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {data.kpis.map((kpi) => {
          let icon = <CheckCircleOutlined />;
          let color: string | undefined;
          if (kpi.status === "error") {
            icon = <CloseCircleOutlined />;
            color = "#ff4d4f";
          } else if (kpi.status === "warning") {
            icon = <WarningOutlined />;
            color = "#faad14";
          } else if (kpi.label.includes("成本") || kpi.label.includes("COQ")) {
            icon = <DollarOutlined />;
          }

          return (
            <Col key={kpi.label} xs={24} sm={12} lg={6}>
              <DataCard title={kpi.label}>
                <Statistic
                  value={kpi.value}
                  prefix={icon}
                  valueStyle={color ? { color } : undefined}
                />
              </DataCard>
            </Col>
          );
        })}
      </Row>

      {/* COQ Summary */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={12}>
          <DataCard title={t("dashboard.coqSummary", "COQ 成本摘要（本月）")}>
            {Object.keys(data.coq_summary).length === 0 ? (
              <span style={{ color: "#999" }}>{tc("noData", "暂无数据")}</span>
            ) : (
              <Row gutter={[16, 16]}>
                {Object.entries(data.coq_summary).map(([cat, amount]) => (
                  <Col key={cat} xs={24} sm={12}>
                    <Statistic
                      title={cat}
                      value={amount}
                      prefix="¥"
                      precision={2}
                    />
                  </Col>
                ))}
              </Row>
            )}
          </DataCard>
        </Col>

        {/* Quick Links */}
        <Col xs={24} lg={12}>
          <DataCard title={t("dashboard.quickLinks", "快速入口")}>
            <Space direction="vertical" style={{ width: "100%" }} size={8}>
              <Link to="/erp/connections">
                <Button icon={<LinkOutlined />} block>{t("dashboard.links.connections", "连接管理")}</Button>
              </Link>
              <Link to="/erp/master-data">
                <Button icon={<SyncOutlined />} block>{t("dashboard.links.masterData", "主数据管理")}</Button>
              </Link>
              <Link to="/erp/supply-chain">
                <Button icon={<WarningOutlined />} block>{t("dashboard.links.supplyChain", "供应链管理")}</Button>
              </Link>
              <Link to="/erp/traceability">
                <Button block>{t("dashboard.links.traceability", "批次追溯")}</Button>
              </Link>
            </Space>
          </DataCard>
        </Col>
      </Row>
    </PageShell>
  );
}
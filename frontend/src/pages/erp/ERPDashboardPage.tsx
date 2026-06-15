import { useEffect, useMemo, useState } from "react";
import {
  Row, Col, Card, Statistic, Tag, Typography, Spin, App,
  Button, Space,
} from "antd";
import {
  CheckCircleOutlined, CloseCircleOutlined,
  SyncOutlined, DollarOutlined,
  WarningOutlined, LinkOutlined,
} from "@ant-design/icons";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { formatDateTime } from "../../utils/dateTime";
import { fetchERPDashboard } from "../../api/erp";
import { useProductLineStore } from "../../store/productLineStore";
import type { ERPDashboardData } from "../../types/erp";

const { Title } = Typography;

const syncStatusColors: Record<string, string> = {
  completed: "success",
  failed: "error",
  running: "processing",
  pending: "warning",
};

export default function ERPDashboardPage() {
  const { t } = useTranslation("erp");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const productLine = useProductLineStore((s) => s.selected);
  const [data, setData] = useState<ERPDashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  const syncStatusLabels: Record<string, string> = useMemo(() => ({
    completed: t("syncStatus.completed"),
    failed: t("syncStatus.failed"),
    running: t("syncStatus.running"),
    pending: t("syncStatus.pending"),
  }), [t]);

  useEffect(() => {
    fetchERPDashboard()
      .then(setData)
      .catch(() => message.error(t("dashboard.errors.loadFailed")))
      .finally(() => setLoading(false));
  }, [productLine, message, t]);

  if (loading) {
    return (
      <div style={{ textAlign: "center", paddingTop: 120 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!data) {
    return <div style={{ padding: 24 }}>{t("dashboard.loadFailed")}</div>;
  }

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>
        {t("dashboard.title")}
      </Title>

      {/* Sync Health */}
      <Card
        title={t("dashboard.syncHealth")}
        style={{ marginBottom: 16 }}
        extra={
          <Space>
            {data.sync_health.map((s) => (
              <Tag
                key={s.data_type}
                color={syncStatusColors[s.status] || "default"}
              >
                {s.data_type}: {syncStatusLabels[s.status] || s.status}
              </Tag>
            ))}
          </Space>
        }
      >
        {data.sync_health.length === 0 ? (
          <span style={{ color: "#999" }}>{tc("empty.data")}</span>
        ) : (
          <Row gutter={[16, 8]}>
            {data.sync_health.map((s) => (
              <Col key={s.data_type} xs={24} sm={12} md={8} lg={6}>
                <Statistic
                  title={s.data_type}
                  value={s.last_sync
                    ? formatDateTime(s.last_sync)
                    : "—"}
                  valueStyle={{ fontSize: 14 }}
                />
              </Col>
            ))}
          </Row>
        )}
      </Card>

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
          } else if (kpi.label.toLowerCase().includes("cost") || kpi.label.includes("COQ")) {
            icon = <DollarOutlined />;
          }

          return (
            <Col key={kpi.label} xs={24} sm={12} lg={6}>
              <Card>
                <Statistic
                  title={kpi.label}
                  value={kpi.value}
                  prefix={icon}
                  valueStyle={color ? { color } : undefined}
                />
              </Card>
            </Col>
          );
        })}
      </Row>

      {/* COQ Summary */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={12}>
          <Card title={t("dashboard.coqSummary")}>
            {Object.keys(data.coq_summary).length === 0 ? (
              <span style={{ color: "#999" }}>{tc("empty.data")}</span>
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
          </Card>
        </Col>

        {/* Quick Links */}
        <Col xs={24} lg={12}>
          <Card title={t("dashboard.quickLinks")}>
            <Space direction="vertical" style={{ width: "100%" }} size={8}>
              <Link to="/erp/connections">
                <Button icon={<LinkOutlined />} block>{t("dashboard.links.connections")}</Button>
              </Link>
              <Link to="/erp/master-data">
                <Button icon={<SyncOutlined />} block>{t("dashboard.links.masterData")}</Button>
              </Link>
              <Link to="/erp/supply-chain">
                <Button icon={<WarningOutlined />} block>{t("dashboard.links.supplyChain")}</Button>
              </Link>
              <Link to="/erp/traceability">
                <Button block>{t("dashboard.links.traceability")}</Button>
              </Link>
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  );
}

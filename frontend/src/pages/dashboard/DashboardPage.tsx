import { useEffect, useState, useCallback } from "react";
import { Row, Col, Card, Button, Typography } from "antd";
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
import { useAuthStore } from "../../store/authStore";
import KPICard from "../../components/dashboard/KPICard";
import RiskList from "../../components/dashboard/RiskList";
import RecentActions from "../../components/dashboard/RecentActions";
import CollapsibleSection from "../../components/dashboard/CollapsibleSection";

const { Title } = Typography;

function formatTrend(trend: number | undefined): string {
  if (trend === undefined || trend === null) return "—";
  if (trend > 0) return `↑ ${trend}%`;
  if (trend < 0) return `↓ ${Math.abs(trend)}%`;
  return "—";
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const productLine = useProductLineStore((s) => s.selected);
  const user = useAuthStore((s) => s.user);
  const isViewer = user?.role === "viewer";

  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [alerts, setAlerts] = useState<DashboardAlerts | null>(null);
  const [recentActions, setRecentActions] = useState<DashboardRecentAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [summaryError, setSummaryError] = useState(false);
  const [alertsError, setAlertsError] = useState(false);
  const [actionsError, setActionsError] = useState(false);

  const fetchData = useCallback(() => {
    setLoading(true);
    setSummaryError(false);
    setAlertsError(false);
    setActionsError(false);

    getDashboardSummary(productLine || undefined)
      .then((s) => setSummary(s))
      .catch(() => setSummaryError(true))
      .finally(() => setLoading(false));

    getDashboardAlerts(productLine || undefined)
      .then((a) => setAlerts(a))
      .catch(() => setAlertsError(true))
      .finally(() => setLoading(false));

    getDashboardRecentActions()
      .then((r) => setRecentActions(r))
      .catch(() => setActionsError(true))
      .finally(() => setLoading(false));
  }, [productLine]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const pendingStatus = (summary?.pending_actions ?? 0) > 0 ? "warning" : "success";
  const overdueStatus = (summary?.overdue_tasks ?? 0) > 0 ? "danger" : "success";
  const highRiskStatus = (summary?.high_risk_items ?? 0) > 0 ? "danger" : "success";

  const trend = summary?.month_trend ?? 0;
  const trendStatus = trend > 0 ? "success" : trend < 0 ? "danger" : "success";

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>
        质量仪表盘
      </Title>

      {/* P0: KPI section */}
      <section aria-label="质量指标概览">
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} lg={6}>
            <KPICard
              title="待办事项"
              value={summary?.pending_actions ?? 0}
              status={pendingStatus}
              icon={<ClockCircleOutlined />}
              onClick={() => navigate("/capa?pending_action=true")}
              loading={loading}
              error={summaryError}
              onRetry={fetchData}
              disabled={isViewer}
            />
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <KPICard
              title="超期任务"
              value={summary?.overdue_tasks ?? 0}
              status={overdueStatus}
              icon={<AlertOutlined />}
              onClick={() => navigate("/capa?overdue=true")}
              loading={loading}
              error={summaryError}
              onRetry={fetchData}
              disabled={isViewer}
            />
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <KPICard
              title="高风险项"
              value={summary?.high_risk_items ?? 0}
              status={highRiskStatus}
              icon={<WarningOutlined />}
              onClick={() => navigate("/fmea?risk=high")}
              loading={loading}
              error={summaryError}
              onRetry={fetchData}
              disabled={isViewer}
            />
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <KPICard
              title="本月新增"
              value={summary?.month_trend ?? 0}
              status={trendStatus}
              subtitle={formatTrend(summary?.month_trend)}
              icon={<RiseOutlined />}
              loading={loading}
              error={summaryError}
              onRetry={fetchData}
              disabled={isViewer}
            />
          </Col>
        </Row>
      </section>

      {/* P1: 待处置事项 section */}
      <section aria-label="待处置事项" style={{ marginTop: 24 }}>
        <Title level={5}>待处置事项</Title>
        <Row gutter={[16, 16]} style={{ marginTop: 8 }}>
          <Col xs={24} lg={8}>
            <Card title="高 RPN FMEA" size="small">
              <RiskList
                data={alerts}
                category="fmea"
                loading={loading}
                error={alertsError}
                onRetry={fetchData}
                disabled={isViewer}
              />
            </Card>
          </Col>
          <Col xs={24} lg={8}>
            <Card title="超期 CAPA" size="small">
              <RiskList
                data={alerts}
                category="capa"
                loading={loading}
                error={alertsError}
                onRetry={fetchData}
                disabled={isViewer}
              />
            </Card>
          </Col>
          <Col xs={24} lg={8}>
            <Card title="PPM 超标供应商" size="small">
              <RiskList
                data={alerts}
                category="supplier"
                loading={loading}
                error={alertsError}
                onRetry={fetchData}
                disabled={isViewer}
              />
            </Card>
          </Col>
        </Row>
      </section>

      {/* P2: 最近操作 section */}
      <CollapsibleSection title="最近操作" collapseAt={767} style={{ marginTop: 24 }}>
        <Card size="small">
          <RecentActions
            data={recentActions}
            loading={loading}
            error={actionsError}
            onRetry={fetchData}
          />
        </Card>
      </CollapsibleSection>

      {/* P3: 快速入口 section */}
      <CollapsibleSection title="快速入口" collapseAt={767} hidden={isViewer} style={{ marginTop: 16 }}>
        <Card size="small">
          <Button type="default" icon={<PlusOutlined />} block onClick={() => navigate("/fmea")}>
            新建 FMEA
          </Button>
          <Button type="default" icon={<PlusOutlined />} block onClick={() => navigate("/capa")} style={{ marginTop: 8 }}>
            新建 CAPA
          </Button>
          <Button type="default" icon={<PlusOutlined />} block onClick={() => navigate("/customer-quality")} style={{ marginTop: 8 }}>
            新建客诉
          </Button>
        </Card>
      </CollapsibleSection>
    </div>
  );
}

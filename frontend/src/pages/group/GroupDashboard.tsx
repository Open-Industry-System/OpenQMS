import { useEffect, useState } from "react";
import { Card, Row, Col, Statistic, Spin, Typography } from "antd";
import {
  SafetyCertificateOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { usePermission } from "../../hooks/usePermission";
import { getGroupDashboard, type GroupDashboardResponse } from "../../api/group";

const { Title } = Typography;

export default function GroupDashboardPage() {
  const { canView } = usePermission();
  const { t } = useTranslation("group");
  const { t: tc } = useTranslation("common");
  const [data, setData] = useState<GroupDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!canView("group")) return;
    setLoading(true);
    getGroupDashboard()
      .then((res) => setData(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [canView]);

  if (!canView("group")) {
    return <div style={{ padding: 24 }}>{t("noPermission")}</div>;
  }

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: 48 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!data) {
    return <div style={{ padding: 24 }}>{tc("empty.data")}</div>;
  }

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>{t("dashboard.title")}</Title>

      {/* Totals row */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col span={4}>
          <Card>
            <Statistic title={t("dashboard.openFMEA")} value={data.totals.open_fmea_count} prefix={<SafetyCertificateOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic title={t("dashboard.openCAPA")} value={data.totals.open_capa_count} prefix={<WarningOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic title={t("dashboard.overdueCAPA")} value={data.totals.overdue_capa_count} prefix={<ClockCircleOutlined />} valueStyle={{ color: data.totals.overdue_capa_count > 0 ? "#cf1322" : undefined }} />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic title={t("dashboard.spcAlarms")} value={data.totals.active_spc_alarms} prefix={<WarningOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic title={t("dashboard.pendingIQC")} value={data.totals.pending_iqc_inspections} prefix={<ClockCircleOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic title={t("dashboard.openSCAR")} value={data.totals.open_scars} prefix={<CheckCircleOutlined />} />
          </Card>
        </Col>
      </Row>

      {/* Per-factory row */}
      <Title level={4}>{t("dashboard.factoryData")}</Title>
      <Row gutter={[16, 16]}>
        {data.factories.map((f) => (
          <Col key={f.factory_id} span={8}>
            <Card title={t("dashboard.factoryCardTitle", { factory_code: f.factory_code, factory_name: f.factory_name })} size="small">
              <Row gutter={[8, 8]}>
                <Col span={8}><Statistic title="FMEA" value={f.open_fmea_count} /></Col>
                <Col span={8}><Statistic title="CAPA" value={f.open_capa_count} /></Col>
                <Col span={8}><Statistic title={t("dashboard.overdueCAPA")} value={f.overdue_capa_count} valueStyle={{ color: f.overdue_capa_count > 0 ? "#cf1322" : undefined }} /></Col>
                <Col span={8}><Statistic title="SPC" value={f.active_spc_alarms} /></Col>
                <Col span={8}><Statistic title="IQC" value={f.pending_iqc_inspections} /></Col>
                <Col span={8}><Statistic title="SCAR" value={f.open_scars} /></Col>
              </Row>
            </Card>
          </Col>
        ))}
      </Row>
    </div>
  );
}

import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { formatDateTime } from "../../utils/dateTime";
import {
  Button, Space, Tag, Typography, Tabs, Card, Input,
  DatePicker, Table, App, Spin, Row, Col,
  Switch, Divider, Statistic, Empty,
} from "antd";
import {
  ArrowLeftOutlined, LockOutlined, UnlockOutlined,
  DeleteOutlined, PlusOutlined, CheckCircleOutlined,
  ExclamationCircleOutlined, UploadOutlined, SearchOutlined,
} from "@ant-design/icons";
import VersionPanel from "./VersionPanel";
import FMEAMatchPanel from "./components/FMEAMatchPanel";
import ImportExcelDialog from "../../components/shared/ImportExcelDialog";
import { importSamples, downloadSampleImportTemplate } from "../../api/spc";
import dayjs from "dayjs";
import * as echarts from "echarts";
import {
  getInspectionCharacteristic,
  getChartData,
  getCapability,
  listAlarms,
  addSampleBatch,
  lockControlLimits,
  acknowledgeAlarm,
  createCAPAFromAlarm,
  updateInspectionCharacteristic,
} from "../../api/spc";
import type {
  InspectionCharacteristic,
  ChartDataResponse,
  CapabilityResponse,
  SPCAlarm,
} from "../../types";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";
import { PageShell, StatusBadge } from "../../components/design";

const { Title, Text } = Typography;

const severityStatus: Record<string, string> = {
  critical: "fatal",
  major: "error",
  minor: "info",
};

function getGradeStatus(grade: string): string {
  if (grade.startsWith("A")) return "success";
  if (grade.startsWith("B")) return "info";
  if (grade.startsWith("C")) return "warning";
  return "error";
}

export default function SPCDetailPage() {
  const { t } = useTranslation("spc");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [ic, setIc] = useState<InspectionCharacteristic | null>(null);
  const [chartData, setChartData] = useState<ChartDataResponse | null>(null);
  const [capability, setCapability] = useState<CapabilityResponse | null>(null);
  const [alarms, setAlarms] = useState<SPCAlarm[]>([]);
  const [alarmTotal, setAlarmTotal] = useState(0);
  const [alarmPage, setAlarmPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState("chart");
  const [importOpen, setImportOpen] = useState(false);
  const [fmeaMatchPanelOpen, setFmeaMatchPanelOpen] = useState(false);
  const [selectedAlarmId, setSelectedAlarmId] = useState<string | null>(null);

  // Data entry form
  const [batchNo, setBatchNo] = useState("");
  const [sampledAt, setSampledAt] = useState<dayjs.Dayjs | null>(dayjs());
  const [sampleValues, setSampleValues] = useState<string[]>([""]);
  const [inspectedCount, setInspectedCount] = useState<string>("");
  const [defectCount, setDefectCount] = useState<string>("");

  // Chart refs
  const mainChartRef = useRef<HTMLDivElement>(null);
  const subChartRef = useRef<HTMLDivElement>(null);
  const mainChartInstance = useRef<echarts.ECharts | null>(null);
  const subChartInstance = useRef<echarts.ECharts | null>(null);

  const _user = useAuthStore((s) => s.user);
  const { canEdit } = usePermission();

  const chartTypeLabel = (type: string) => t(`chartType.${type}`, { defaultValue: type });

  const fetchAll = async () => {
    if (!id) return;
    setRefreshing(true);
    try {
      const icData = await getInspectionCharacteristic(id);
      setIc(icData);

      const isAttribute = ["p", "np", "c", "u"].includes(icData.chart_type);
      const [chart, cap, alarmRes] = await Promise.all([
        getChartData(id),
        isAttribute ? Promise.resolve(null) : getCapability(id).catch(() => null),
        listAlarms(id, { page: alarmPage, page_size: 20 }),
      ]);

      setChartData(chart);
      setCapability(cap);
      setAlarms(alarmRes.items);
      setAlarmTotal(alarmRes.total);
    } catch {
      message.error(t("detail.loadFailed"));
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    fetchAll();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, alarmPage]);

  // Initialize/update charts
  useEffect(() => {
    if (!chartData || activeTab !== "chart") return;

    if (mainChartRef.current && !mainChartInstance.current) {
      mainChartInstance.current = echarts.init(mainChartRef.current);
    }
    if (subChartRef.current && !subChartInstance.current) {
      subChartInstance.current = echarts.init(subChartRef.current);
    }

    const points = chartData.data_points;
    const xData = points.map((p) => p.batch_no);

    // Main chart (X-bar or I)
    const mainSeries = points.map((p, _idx) => ({
      value: p.x_value ?? 0,
      itemStyle: {
        color: p.alarm_flags.length > 0 ? "#ff4d4f" : "#1890ff",
      },
      emphasis: {
        itemStyle: { borderWidth: 2, borderColor: "#ff4d4f" },
      },
    }));

    const isVariableLimit = ["p", "u"].includes(chartData.chart_type);

    const mainOption: echarts.EChartsOption = {
      title: {
        text: chartData.chart_type === "xbar_r" ? t("detail.chart.xbarTitle") : t("detail.chart.iTitle"),
        left: "center",
        textStyle: { fontSize: 14 },
      },
      tooltip: { trigger: "axis" },
      grid: { left: 60, right: 30, top: 40, bottom: 30 },
      xAxis: {
        type: "category",
        data: xData,
        axisLabel: { rotate: 45, fontSize: 10 },
      },
      yAxis: { type: "value", scale: true },
      series: [
        {
          name: t("detail.chart.statisticValue"),
          type: "line",
          data: mainSeries,
          symbol: "circle",
          symbolSize: 8,
          lineStyle: { color: "#1890ff" },
          ...(isVariableLimit ? {} : {
            markLine: {
              silent: true,
              data: [
                ...(chartData.limits.ucl !== undefined
                  ? [{ yAxis: chartData.limits.ucl, name: t("detail.chart.ucl"), lineStyle: { color: "#ff4d4f" } }]
                  : []),
                ...(chartData.limits.lcl !== undefined
                  ? [{ yAxis: chartData.limits.lcl, name: t("detail.chart.lcl"), lineStyle: { color: "#ff4d4f" } }]
                  : []),
                ...(chartData.limits.cl !== undefined
                  ? [{ yAxis: chartData.limits.cl, name: t("detail.chart.cl"), lineStyle: { color: "#52c41a", type: "dashed" as const } }]
                  : []),
              ],
              label: { formatter: "{b}: {c}" },
            },
          }),
        },
        ...(isVariableLimit && chartData.limits.ucl_list ? [{
          name: t("detail.chart.ucl"),
          type: "line" as const,
          data: chartData.limits.ucl_list,
          lineStyle: { color: "#ff4d4f", type: "dashed" as const },
          symbol: "none",
        }] : []),
        ...(isVariableLimit && chartData.limits.lcl_list ? [{
          name: t("detail.chart.lcl"),
          type: "line" as const,
          data: chartData.limits.lcl_list,
          lineStyle: { color: "#ff4d4f", type: "dashed" as const },
          symbol: "none",
        }] : []),
        ...(isVariableLimit && chartData.limits.cl !== undefined ? [{
          name: t("detail.chart.cl"),
          type: "line" as const,
          data: chartData.data_points.map(() => chartData.limits.cl),
          lineStyle: { color: "#52c41a", type: "dashed" as const },
          symbol: "none",
        }] : []),
      ],
    };

    // Sub chart (R or MR)
    const subSeries = points.map((p) => ({
      value: p.r_value ?? 0,
      itemStyle: {
        color: p.alarm_flags.length > 0 ? "#ff4d4f" : "#faad14",
      },
    }));

    const subOption: echarts.EChartsOption = {
      title: {
        text: chartData.chart_type === "xbar_r" ? t("detail.chart.rTitle") : t("detail.chart.mrTitle"),
        left: "center",
        textStyle: { fontSize: 14 },
      },
      tooltip: { trigger: "axis" },
      grid: { left: 60, right: 30, top: 40, bottom: 30 },
      xAxis: {
        type: "category",
        data: xData,
        axisLabel: { rotate: 45, fontSize: 10 },
      },
      yAxis: { type: "value", scale: true },
      series: [
        {
          type: "line",
          data: subSeries,
          symbol: "circle",
          symbolSize: 6,
          lineStyle: { color: "#faad14" },
          markLine: {
            silent: true,
            data: [
              ...(chartData.limits.r_ucl !== undefined
                ? [{ yAxis: chartData.limits.r_ucl, name: `R_${t("detail.chart.ucl")}`, lineStyle: { color: "#ff4d4f" } }]
                : []),
              ...(chartData.limits.r_lcl !== undefined
                ? [{ yAxis: chartData.limits.r_lcl, name: `R_${t("detail.chart.lcl")}`, lineStyle: { color: "#ff4d4f" } }]
                : []),
              ...(chartData.limits.r_cl !== undefined
                ? [{ yAxis: chartData.limits.r_cl, name: `R_${t("detail.chart.cl")}`, lineStyle: { color: "#52c41a", type: "dashed" as const } }]
                : []),
            ],
            label: { formatter: "{b}: {c}" },
          },
        },
      ],
    };

    mainChartInstance.current?.setOption(mainOption, true);
    subChartInstance.current?.setOption(subOption, true);

    const handleResize = () => {
      mainChartInstance.current?.resize();
      subChartInstance.current?.resize();
    };
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, [chartData, activeTab, t]);

  // Cleanup chart instances on unmount
  useEffect(() => {
    return () => {
      mainChartInstance.current?.dispose();
      subChartInstance.current?.dispose();
      mainChartInstance.current = null;
      subChartInstance.current = null;
    };
  }, []);

  const handleLockToggle = async () => {
    if (!id || !ic) return;
    try {
      const updated = await lockControlLimits(id, !ic.control_limits_locked);
      setIc(updated);
      message.success(updated.control_limits_locked ? t("detail.lockSuccess") : t("detail.unlockSuccess"));
      fetchAll();
    } catch {
      message.error(t("detail.operationFailed"));
    }
  };

  const handleRuleToggle = async (ruleKey: string, checked: boolean) => {
    if (!id || !ic) return;
    const newConfig = { ...ic.rules_config, [ruleKey]: checked };
    try {
      const updated = await updateInspectionCharacteristic(id, { rules_config: newConfig });
      setIc(updated);
      message.success(t("detail.ruleUpdateSuccess"));
    } catch {
      message.error(t("detail.ruleUpdateFailed"));
    }
  };

  const handleAddSample = async () => {
    if (!id) return;
    if (!batchNo.trim()) {
      message.warning(t("detail.batchNoRequired"));
      return;
    }
    const isAttribute = ["p", "np", "c", "u"].includes(ic?.chart_type || "");
    if (isAttribute) {
      const n = parseInt(inspectedCount, 10);
      const d = parseInt(defectCount, 10);
      if (isNaN(n) || n <= 0) {
        message.warning(t("detail.inspectedCountRequired"));
        return;
      }
      if (isNaN(d) || d < 0) {
        message.warning(t("detail.defectCountNonNegative"));
        return;
      }
      if (d > n) {
        message.warning(t("detail.defectCountExceeds"));
        return;
      }
      try {
        await addSampleBatch(id, {
          batch_no: batchNo.trim(),
          sampled_at: sampledAt ? sampledAt.format("YYYY-MM-DDTHH:mm:ss") : dayjs().format("YYYY-MM-DDTHH:mm:ss"),
          inspected_count: n,
          defect_count: d,
        });
        message.success(t("detail.sampleEntrySuccess"));
        setBatchNo("");
        setInspectedCount("");
        setDefectCount("");
        fetchAll();
      } catch {
        message.error(t("detail.sampleEntryFailed"));
      }
      return;
    }
    const values = sampleValues
      .map((v) => parseFloat(v))
      .filter((v) => !isNaN(v));
    if (values.length === 0) {
      message.warning(t("detail.sampleValueRequired"));
      return;
    }
    try {
      await addSampleBatch(id, {
        batch_no: batchNo.trim(),
        sampled_at: sampledAt ? sampledAt.format("YYYY-MM-DDTHH:mm:ss") : dayjs().format("YYYY-MM-DDTHH:mm:ss"),
        values,
      });
      message.success(t("detail.sampleEntrySuccess"));
      setBatchNo("");
      setSampleValues([""]);
      fetchAll();
    } catch {
      message.error(t("detail.sampleEntryFailed"));
    }
  };

  const handleAcknowledge = async (alarmId: string) => {
    try {
      await acknowledgeAlarm(alarmId);
      message.success(t("detail.alarmAckSuccess"));
      fetchAll();
    } catch {
      message.error(t("detail.alarmAckFailed"));
    }
  };

  const handleCreateCAPA = async (alarmId: string) => {
    try {
      const result = await createCAPAFromAlarm(alarmId);
      message.success(t("detail.capaCreateSuccess", { docNo: result.document_number }));
      fetchAll();
    } catch {
      message.error(t("detail.capaCreateFailed"));
    }
  };

  const updateSampleValue = (index: number, value: string) => {
    setSampleValues((prev) => {
      const next = [...prev];
      next[index] = value;
      return next;
    });
  };

  const addSampleInput = () => {
    setSampleValues((prev) => [...prev, ""]);
  };

  const removeSampleInput = (index: number) => {
    setSampleValues((prev) => prev.filter((_, i) => i !== index));
  };

  const subgroupSize = ic?.subgroup_size || 5;

  const alarmColumns = [
    { title: t("detail.alarm.ruleNo"), dataIndex: "rule_no", key: "rule_no", width: 90 },
    {
      title: t("detail.alarm.triggeredAt"),
      dataIndex: "triggered_at",
      key: "triggered_at",
      width: 170,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: t("detail.alarm.severity"),
      dataIndex: "severity",
      key: "severity",
      width: 100,
      render: (s: string) => (
        <StatusBadge status={severityStatus[s] || "draft"}>
          {t(`detail.alarm.severityLevels.${s}`, { defaultValue: s })}
        </StatusBadge>
      ),
    },
    {
      title: t("detail.alarm.status"),
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (s: string) => (
        <StatusBadge status={s === "open" ? "error" : s === "acknowledged" ? "warning" : "success"}>
          {t(`detail.alarm.statuses.${s}`, { defaultValue: s })}
        </StatusBadge>
      ),
    },
    {
      title: t("detail.alarm.linkedCapa"),
      dataIndex: "linked_capa_id",
      key: "linked_capa_id",
      width: 120,
      render: (v: string | undefined) => <span style={{ fontFamily: "var(--qf-font-mono)" }}>{v || "-"}</span>,
    },
    {
      title: t("detail.alarm.linkedFmea"),
      dataIndex: "confirmed_fmea_id",
      key: "confirmed_fmea_id",
      width: 120,
      render: (_: unknown, record: SPCAlarm) =>
        record.confirmed_fmea_id ? (
          <Tag style={{ background: "var(--qf-cyan-dim)", color: "var(--qf-cyan)", borderColor: "var(--qf-cyan)" }}>
            {t("detail.alarm.linked")}
          </Tag>
        ) : (
          <Tag style={{ background: "var(--qf-bg-hover)", color: "var(--qf-text-secondary)", borderColor: "var(--qf-border)" }}>
            {t("detail.alarm.notLinked")}
          </Tag>
        ),
    },
    {
      title: tc("table.operations"),
      key: "actions",
      width: 240,
      render: (_: unknown, record: SPCAlarm) => (
        <Space>
          {record.status === "open" && canEdit('spc') && (
            <Button
              size="small"
              icon={<CheckCircleOutlined />}
              onClick={() => handleAcknowledge(record.alarm_id)}
            >
              {t("detail.alarm.confirm")}
            </Button>
          )}
          <Button
            size="small"
            icon={<SearchOutlined />}
            onClick={() => {
              setSelectedAlarmId(record.alarm_id);
              setFmeaMatchPanelOpen(true);
            }}
          >
            {t("detail.alarm.viewFmea")}
          </Button>
          {!record.linked_capa_id && canEdit('spc') && (
            <Button
              size="small"
              type="primary"
              icon={<ExclamationCircleOutlined />}
              onClick={() => handleCreateCAPA(record.alarm_id)}
            >
              {t("detail.alarm.createCapa")}
            </Button>
          )}
        </Space>
      ),
    },
  ];

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: 64 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!ic) {
    return (
      <div style={{ textAlign: "center", padding: 64 }}>
        <Title level={4}>{t("detail.notFound")}</Title>
        <Button onClick={() => navigate("/spc")}>{tc("actions.back")}</Button>
      </div>
    );
  }

  const headerTags = (
    <Space>
      <Tag style={{ background: "var(--qf-cyan-dim)", color: "var(--qf-cyan)", borderColor: "var(--qf-cyan)" }}>{ic.ic_code}</Tag>
      <Tag style={{ background: "var(--qf-bg-hover)", color: "var(--qf-text-secondary)", borderColor: "var(--qf-border)" }}>{chartTypeLabel(ic.chart_type)}</Tag>
      {chartData?.active_snapshot && (
        <Tag style={{ background: "var(--qf-blue-dim)", color: "var(--qf-blue)", borderColor: "var(--qf-blue)" }}>
          {t("detail.limitManagement.version")} v{chartData.active_snapshot.version_no}
        </Tag>
      )}
      <StatusBadge status={ic.control_limits_locked ? "success" : "warning"}>
        {ic.control_limits_locked ? t("detail.limitManagement.locked") : t("detail.limitManagement.auto")}
      </StatusBadge>
    </Space>
  );

  return (
    <PageShell
      title={
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/spc")}>{tc("actions.back")}</Button>
          <Title level={4} style={{ margin: 0, color: "var(--qf-text-primary)" }}>{ic.characteristic_name}</Title>
        </Space>
      }
      subtitle={headerTags}
      fullHeight
    >

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: "chart",
            label: t("detail.tabs.chart"),
            children: (
              <Row gutter={16}>
                <Col span={18}>
                  <Card loading={refreshing}>
                    <div ref={mainChartRef} style={{ width: "100%", height: 320 }} />
                  </Card>
                  <Card style={{ marginTop: 16 }} loading={refreshing}>
                    <div ref={subChartRef} style={{ width: "100%", height: 280 }} />
                  </Card>
                </Col>
                <Col span={6}>
                  <Card title={t("detail.basicInfo.title")} size="small">
                    <p>
                      <Text type="secondary">{t("detail.basicInfo.process_name")}:</Text> {ic.process_name}
                    </p>
                    <p>
                      <Text type="secondary">{t("detail.basicInfo.characteristic_name")}:</Text> {ic.characteristic_name}
                    </p>
                    <p>
                      <Text type="secondary">{t("detail.basicInfo.spec_upper")}:</Text> {ic.spec_upper}
                    </p>
                    <p>
                      <Text type="secondary">{t("detail.basicInfo.spec_lower")}:</Text> {ic.spec_lower}
                    </p>
                    <p>
                      <Text type="secondary">{t("detail.basicInfo.target_value")}:</Text> {ic.target_value ?? "-"}
                    </p>
                    <p>
                      <Text type="secondary">{t("detail.basicInfo.subgroup_size")}:</Text> {ic.subgroup_size}
                    </p>
                  </Card>

                  <Card title={t("detail.limitManagement.title")} size="small" style={{ marginTop: 16 }}>
                    <Button
                      type={ic.control_limits_locked ? "default" : "primary"}
                      icon={ic.control_limits_locked ? <UnlockOutlined /> : <LockOutlined />}
                      onClick={handleLockToggle}
                      disabled={!canEdit('spc')}
                      block
                    >
                      {ic.control_limits_locked ? t("detail.limitManagement.unlock") : t("detail.limitManagement.lock")}
                    </Button>
                    {id && (
                      <div style={{ marginTop: 8 }}>
                        <VersionPanel icId={id} onActivated={fetchAll} />
                      </div>
                    )}
                  </Card>

                  <Card title={t("detail.rules.title")} size="small" style={{ marginTop: 16 }}>
                    {["rule1", "rule2", "rule3", "rule4", "rule5", "rule6", "rule7", "rule8"].map((key) => (
                      <div
                        key={key}
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          marginBottom: 8,
                        }}
                      >
                        <Text style={{ fontSize: 12 }}>{t(`detail.rules.${key}`)}</Text>
                        <Switch
                          size="small"
                          checked={!!ic.rules_config[key]}
                          onChange={(checked) => handleRuleToggle(key, checked)}
                          disabled={!canEdit('spc')}
                        />
                      </div>
                    ))}
                  </Card>
                </Col>
              </Row>
            ),
          },
          ...(!["p", "np", "c", "u"].includes(ic?.chart_type || "") ? [
            {
              key: "capability",
              label: t("detail.tabs.capability"),
              children: capability ? (
                <div>
                  <Row gutter={16} style={{ marginBottom: 24 }}>
                    <Col>
                      <StatusBadge status={getGradeStatus(capability.grade)} style={{ fontSize: 14, padding: "6px 12px" }}>
                        {t("detail.capability.grade", { grade: capability.grade })}
                      </StatusBadge>
                    </Col>
                  </Row>
                  <Row gutter={[16, 16]}>
                    <Col span={6}>
                      <Card>
                        <Statistic title={t("detail.capability.cp")} value={capability.cp} precision={3} />
                      </Card>
                    </Col>
                    <Col span={6}>
                      <Card>
                        <Statistic title={t("detail.capability.cpk")} value={capability.cpk} precision={3} />
                      </Card>
                    </Col>
                    <Col span={6}>
                      <Card>
                        <Statistic title={t("detail.capability.pp")} value={capability.pp} precision={3} />
                      </Card>
                    </Col>
                    <Col span={6}>
                      <Card>
                        <Statistic title={t("detail.capability.ppk")} value={capability.ppk} precision={3} />
                      </Card>
                    </Col>
                    <Col span={6}>
                      <Card>
                        <Statistic title={t("detail.capability.cm")} value={capability.cm} precision={3} />
                      </Card>
                    </Col>
                    <Col span={6}>
                      <Card>
                        <Statistic title={t("detail.capability.cmk")} value={capability.cmk} precision={3} />
                      </Card>
                    </Col>
                    <Col span={6}>
                      <Card>
                        <Statistic title={t("detail.capability.theoretical_ppm")} value={capability.theoretical_ppm} precision={2} />
                      </Card>
                    </Col>
                    <Col span={6}>
                      <Card>
                        <Statistic title={t("detail.capability.actual_ppm")} value={capability.actual_ppm} precision={2} />
                      </Card>
                    </Col>
                  </Row>
                  <Card title={t("detail.capability.advice")} style={{ marginTop: 16 }}>
                    <Text>{capability.advice}</Text>
                  </Card>
                </div>
              ) : loading ? (
                <Spin size="large" style={{ display: "block", margin: "64px auto" }} />
              ) : (
                <Empty
                  description={t("detail.capability.empty")}
                  style={{ margin: "64px auto" }}
                />
              ),
            }
          ] : []),
          {
            key: "data",
            label: t("detail.tabs.data"),
            children: (
              <Tabs
                type="card"
                items={[
                  {
                    key: "single",
                    label: t("detail.dataEntry.single"),
                    children: (
                      <Card title={t("detail.dataEntry.single")}>
                        <Row gutter={16} style={{ marginBottom: 16 }}>
                          <Col span={8}>
                            <Text type="secondary">{t("detail.dataEntry.batchNo")}</Text>
                            <Input
                              value={batchNo}
                              onChange={(e) => setBatchNo(e.target.value)}
                              placeholder={t("detail.dataEntry.batchPlaceholder")}
                            />
                          </Col>
                          <Col span={8}>
                            <Text type="secondary">{t("detail.dataEntry.sampledAt")}</Text>
                            <DatePicker
                              showTime
                              style={{ width: "100%" }}
                              value={sampledAt}
                              onChange={setSampledAt}
                            />
                          </Col>
                        </Row>
                        {["p", "np", "c", "u"].includes(ic?.chart_type || "") ? (
                          <>
                            <Divider orientation="left">{t("detail.dataEntry.attributeEntry")}</Divider>
                            <Row gutter={[8, 8]}>
                              <Col span={6}>
                                <Input
                                  type="number"
                                  min={1}
                                  value={inspectedCount}
                                  onChange={(e) => setInspectedCount(e.target.value)}
                                  addonBefore={t("detail.dataEntry.inspectedCount")}
                                />
                              </Col>
                              <Col span={6}>
                                <Input
                                  type="number"
                                  min={0}
                                  value={defectCount}
                                  onChange={(e) => setDefectCount(e.target.value)}
                                  addonBefore={t("detail.dataEntry.defectCount")}
                                />
                              </Col>
                            </Row>
                          </>
                        ) : (
                          <>
                            <Divider orientation="left">
                              {t("detail.dataEntry.sampleValues", { size: subgroupSize })}
                            </Divider>
                            <Row gutter={[8, 8]}>
                              {sampleValues.map((val, idx) => (
                                <Col span={4} key={idx}>
                                  <Input
                                    type="number"
                                    step="0.01"
                                    value={val}
                                    onChange={(e) => updateSampleValue(idx, e.target.value)}
                                    addonBefore={`#${idx + 1}`}
                                    suffix={
                                      sampleValues.length > 1 ? (
                                        <Button
                                          type="text"
                                          size="small"
                                          danger
                                          icon={<DeleteOutlined />}
                                          onClick={() => removeSampleInput(idx)}
                                        />
                                      ) : null
                                    }
                                  />
                                </Col>
                              ))}
                            </Row>
                          </>
                        )}
                        <div style={{ marginTop: 16 }}>
                          {!["p", "np", "c", "u"].includes(ic?.chart_type || "") && (
                            <Button icon={<PlusOutlined />} onClick={addSampleInput} style={{ marginRight: 8 }}>
                              {t("detail.dataEntry.addSample")}
                            </Button>
                          )}
                          <Button type="primary" onClick={handleAddSample} disabled={!canEdit('spc')}>
                            {t("detail.dataEntry.submitBatch")}
                          </Button>
                        </div>
                      </Card>
                    ),
                  },
                  {
                    key: "batch",
                    label: t("detail.dataEntry.batch"),
                    children: (
                      <Card>
                        <Button icon={<UploadOutlined />} onClick={() => setImportOpen(true)}>
                          {t("detail.dataEntry.uploadExcel")}
                        </Button>
                        <ImportExcelDialog
                          open={importOpen}
                          onClose={() => setImportOpen(false)}
                          onImported={() => fetchAll()}
                          importFn={(file) => importSamples(id!, file)}
                          templateDownloadFn={() => downloadSampleImportTemplate(id!)}
                          hint={ic?.chart_type === "xbar_r" || ic?.chart_type === "imr"
                            ? t("detail.dataEntry.templateHintVariable", { extra: ic?.chart_type === "xbar_r" ? ", Sample Value 2, ..." : "" })
                            : t("detail.dataEntry.templateHintAttribute")}
                        />
                      </Card>
                    ),
                  },
                  {
                    key: "history",
                    label: t("detail.dataEntry.history"),
                    children: (
                      <Card>
                        <Table
                          dataSource={chartData?.data_points || []}
                          rowKey="batch_index"
                          size="small"
                          pagination={{ pageSize: 20 }}
                          columns={[
                            { title: t("detail.history.index"), dataIndex: "batch_index", width: 70 },
                            { title: t("detail.history.batchNo"), dataIndex: "batch_no" },
                            {
                              title: t("detail.history.sampledAt"),
                              dataIndex: "sampled_at",
                              render: (v: string) => formatDateTime(v),
                            },
                            {
                              title: t("detail.history.xValue"),
                              dataIndex: "x_value",
                              render: (v: number | undefined) => v?.toFixed(3) ?? "-",
                            },
                            {
                              title: t("detail.history.rValue"),
                              dataIndex: "r_value",
                              render: (v: number | undefined) => v?.toFixed(3) ?? "-",
                            },
                            {
                              title: t("detail.history.alarm"),
                              dataIndex: "alarm_flags",
                              render: (flags: number[]) =>
                                flags.length > 0 ? (
                                  <Tag color="red">{t("detail.history.rule", { rules: flags.join(", ") })}</Tag>
                                ) : (
                                  <Tag color="green">{t("detail.history.normal")}</Tag>
                                ),
                            },
                          ]}
                        />
                      </Card>
                    ),
                  },
                ]}
              />
            ),
          },
          {
            key: "alarms",
            label: t("detail.tabs.alarms"),
            children: (
              <Table
                className="qf-table"
                columns={alarmColumns}
                dataSource={alarms}
                rowKey="alarm_id"
                loading={refreshing}
                pagination={{
                  current: alarmPage,
                  total: alarmTotal,
                  pageSize: 20,
                  onChange: (p) => setAlarmPage(p),
                }}
              />
            ),
          },
        ]}
      />
      <FMEAMatchPanel
        alarmId={selectedAlarmId || ""}
        visible={fmeaMatchPanelOpen}
        onClose={() => setFmeaMatchPanelOpen(false)}
        onCreateCAPA={() => {
          if (selectedAlarmId) {
            handleCreateCAPA(selectedAlarmId);
            setFmeaMatchPanelOpen(false);
          }
        }}
        onConfirmed={fetchAll}
      />
    </PageShell>
  );
}

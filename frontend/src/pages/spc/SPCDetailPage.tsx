import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Button, Space, Tag, Typography, Tabs, Card, Form, Input,
  DatePicker, Table, Popconfirm, message, Spin, Row, Col,
  Switch, Upload, Divider, Badge, Statistic,
} from "antd";
import {
  ArrowLeftOutlined, LockOutlined, UnlockOutlined,
  DeleteOutlined, PlusOutlined, CheckCircleOutlined,
  ExclamationCircleOutlined, UploadOutlined,
} from "@ant-design/icons";
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
  SampleBatch,
} from "../../types";
import { useAuthStore } from "../../store/authStore";

const { Title, Text } = Typography;
const { TabPane } = Tabs;

const ruleLabels: Record<string, string> = {
  rule1: "规则1: 超出控制限",
  rule2: "规则2: 连续9点同侧",
  rule3: "规则3: 连续6点递增/递减",
  rule4: "规则4: 连续14点上下交替",
  rule5: "规则5: 连续3点中有2点在A区",
  rule6: "规则6: 连续5点中有4点在B区外",
  rule7: "规则7: 连续15点在C区内",
  rule8: "规则8: 连续8点在C区外",
};

const severityColors: Record<string, string> = {
  critical: "red",
  major: "orange",
  minor: "blue",
};

const severityLabels: Record<string, string> = {
  critical: "严重",
  major: "主要",
  minor: "轻微",
};

const statusLabels: Record<string, string> = {
  open: "未处理",
  acknowledged: "已确认",
  closed: "已关闭",
};

const chartTypeLabels: Record<string, string> = {
  xbar_r: "X-bar R",
  imr: "I-MR",
  histogram: "直方图",
  p: "P图",
  np: "NP图",
  c: "C图",
  u: "U图",
};

function getGradeColor(grade: string): string {
  if (grade.startsWith("A")) return "green";
  if (grade.startsWith("B")) return "blue";
  if (grade.startsWith("C")) return "orange";
  return "red";
}

export default function SPCDetailPage() {
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

  const user = useAuthStore((s) => s.user);
  const canEdit = user?.role !== "viewer";

  const fetchAll = async () => {
    if (!id) return;
    setRefreshing(true);
    try {
      const [icData, chart, cap, alarmRes] = await Promise.all([
        getInspectionCharacteristic(id),
        getChartData(id),
        getCapability(id),
        listAlarms(id, { page: alarmPage, page_size: 20 }),
      ]);
      setIc(icData);
      setChartData(chart);
      setCapability(cap);
      setAlarms(alarmRes.items);
      setAlarmTotal(alarmRes.total);
    } catch {
      message.error("加载数据失败");
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    fetchAll();
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
    const mainSeries = points.map((p, idx) => ({
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
        text: chartData.chart_type === "xbar_r" ? "X-bar 图" : "I 图 (单值图)",
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
          name: "统计值",
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
                  ? [{ yAxis: chartData.limits.ucl, name: "UCL", lineStyle: { color: "#ff4d4f" } }]
                  : []),
                ...(chartData.limits.lcl !== undefined
                  ? [{ yAxis: chartData.limits.lcl, name: "LCL", lineStyle: { color: "#ff4d4f" } }]
                  : []),
                ...(chartData.limits.cl !== undefined
                  ? [{ yAxis: chartData.limits.cl, name: "CL", lineStyle: { color: "#52c41a", type: "dashed" as const } }]
                  : []),
              ],
              label: { formatter: "{b}: {c}" },
            },
          }),
        },
        ...(isVariableLimit && chartData.limits.ucl_list ? [{
          name: "UCL",
          type: "line" as const,
          data: chartData.limits.ucl_list,
          lineStyle: { color: "#ff4d4f", type: "dashed" as const },
          symbol: "none",
        }] : []),
        ...(isVariableLimit && chartData.limits.lcl_list ? [{
          name: "LCL",
          type: "line" as const,
          data: chartData.limits.lcl_list,
          lineStyle: { color: "#ff4d4f", type: "dashed" as const },
          symbol: "none",
        }] : []),
        ...(isVariableLimit && chartData.limits.cl !== undefined ? [{
          name: "CL",
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
        text: chartData.chart_type === "xbar_r" ? "R 图 (极差图)" : "MR 图 (移动极差图)",
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
                ? [{ yAxis: chartData.limits.r_ucl, name: "R_UCL", lineStyle: { color: "#ff4d4f" } }]
                : []),
              ...(chartData.limits.r_lcl !== undefined
                ? [{ yAxis: chartData.limits.r_lcl, name: "R_LCL", lineStyle: { color: "#ff4d4f" } }]
                : []),
              ...(chartData.limits.r_cl !== undefined
                ? [{ yAxis: chartData.limits.r_cl, name: "R_CL", lineStyle: { color: "#52c41a", type: "dashed" as const } }]
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
  }, [chartData, activeTab]);

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
      message.success(updated.control_limits_locked ? "控制限已锁定" : "控制限已解锁");
      fetchAll();
    } catch {
      message.error("操作失败");
    }
  };

  const handleRuleToggle = async (ruleKey: string, checked: boolean) => {
    if (!id || !ic) return;
    const newConfig = { ...ic.rules_config, [ruleKey]: checked };
    try {
      const updated = await updateInspectionCharacteristic(id, { rules_config: newConfig });
      setIc(updated);
      message.success("规则设置已更新");
    } catch {
      message.error("更新失败");
    }
  };

  const handleAddSample = async () => {
    if (!id) return;
    if (!batchNo.trim()) {
      message.warning("请输入批次号");
      return;
    }
    const isAttribute = ["p", "np", "c", "u"].includes(ic?.chart_type || "");
    if (isAttribute) {
      const n = parseInt(inspectedCount, 10);
      const d = parseInt(defectCount, 10);
      if (isNaN(n) || n <= 0) {
        message.warning("检验数量必须大于0");
        return;
      }
      if (isNaN(d) || d < 0) {
        message.warning("不合格品数/缺陷数不能为负数");
        return;
      }
      if (d > n) {
        message.warning("不合格品数/缺陷数不能大于检验数量");
        return;
      }
      try {
        await addSampleBatch(id, {
          batch_no: batchNo.trim(),
          sampled_at: sampledAt ? sampledAt.format("YYYY-MM-DDTHH:mm:ss") : dayjs().format("YYYY-MM-DDTHH:mm:ss"),
          inspected_count: n,
          defect_count: d,
        });
        message.success("样本录入成功");
        setBatchNo("");
        setInspectedCount("");
        setDefectCount("");
        fetchAll();
      } catch {
        message.error("录入失败");
      }
      return;
    }
    const values = sampleValues
      .map((v) => parseFloat(v))
      .filter((v) => !isNaN(v));
    if (values.length === 0) {
      message.warning("请输入至少一个样本值");
      return;
    }
    try {
      await addSampleBatch(id, {
        batch_no: batchNo.trim(),
        sampled_at: sampledAt ? sampledAt.format("YYYY-MM-DDTHH:mm:ss") : dayjs().format("YYYY-MM-DDTHH:mm:ss"),
        values,
      });
      message.success("样本录入成功");
      setBatchNo("");
      setSampleValues([""]);
      fetchAll();
    } catch {
      message.error("录入失败");
    }
  };

  const handleAcknowledge = async (alarmId: string) => {
    try {
      await acknowledgeAlarm(alarmId);
      message.success("告警已确认");
      fetchAll();
    } catch {
      message.error("确认失败");
    }
  };

  const handleCreateCAPA = async (alarmId: string) => {
    try {
      const result = await createCAPAFromAlarm(alarmId);
      message.success(`8D 已创建: ${result.document_number}`);
      fetchAll();
    } catch {
      message.error("创建 8D 失败");
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
    { title: "规则编号", dataIndex: "rule_no", key: "rule_no", width: 90 },
    {
      title: "触发时间",
      dataIndex: "triggered_at",
      key: "triggered_at",
      width: 170,
      render: (v: string) => new Date(v).toLocaleString("zh-CN"),
    },
    {
      title: "严重等级",
      dataIndex: "severity",
      key: "severity",
      width: 100,
      render: (s: string) => (
        <Tag color={severityColors[s] || "default"}>{severityLabels[s] || s}</Tag>
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (s: string) => (
        <Badge
          status={s === "open" ? "error" : s === "acknowledged" ? "warning" : "success"}
          text={statusLabels[s] || s}
        />
      ),
    },
    {
      title: "关联 8D",
      dataIndex: "linked_capa_id",
      key: "linked_capa_id",
      width: 120,
      render: (v: string | undefined) => v || "-",
    },
    {
      title: "操作",
      key: "actions",
      width: 180,
      render: (_: unknown, record: SPCAlarm) => (
        <Space>
          {record.status === "open" && canEdit && (
            <Button
              size="small"
              icon={<CheckCircleOutlined />}
              onClick={() => handleAcknowledge(record.alarm_id)}
            >
              确认
            </Button>
          )}
          {!record.linked_capa_id && canEdit && (
            <Button
              size="small"
              type="primary"
              icon={<ExclamationCircleOutlined />}
              onClick={() => handleCreateCAPA(record.alarm_id)}
            >
              创建 8D
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
        <Title level={4}>检验特性未找到</Title>
        <Button onClick={() => navigate("/spc")}>返回列表</Button>
      </div>
    );
  }

  return (
    <div>
      {/* Top bar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
        }}
      >
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/spc")}>
            返回
          </Button>
          <Title level={4} style={{ margin: 0 }}>
            {ic.characteristic_name}
          </Title>
          <Tag color="blue">{ic.ic_code}</Tag>
          <Tag>{chartTypeLabels[ic.chart_type] || ic.chart_type}</Tag>
        </Space>
        <Space>
          <Tag color={ic.control_limits_locked ? "green" : "orange"}>
            {ic.control_limits_locked ? "控制限已锁定" : "控制限自动计算"}
          </Tag>
        </Space>
      </div>

      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        {/* Tab 1: 控制图 */}
        <TabPane tab="控制图" key="chart">
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
              <Card title="基本信息" size="small">
                <p>
                  <Text type="secondary">过程名称:</Text> {ic.process_name}
                </p>
                <p>
                  <Text type="secondary">特性名称:</Text> {ic.characteristic_name}
                </p>
                <p>
                  <Text type="secondary">规格上限:</Text> {ic.spec_upper}
                </p>
                <p>
                  <Text type="secondary">规格下限:</Text> {ic.spec_lower}
                </p>
                <p>
                  <Text type="secondary">目标值:</Text> {ic.target_value ?? "-"}
                </p>
                <p>
                  <Text type="secondary">子组大小:</Text> {ic.subgroup_size}
                </p>
              </Card>

              <Card title="控制限管理" size="small" style={{ marginTop: 16 }}>
                <Button
                  type={ic.control_limits_locked ? "default" : "primary"}
                  icon={ic.control_limits_locked ? <UnlockOutlined /> : <LockOutlined />}
                  onClick={handleLockToggle}
                  disabled={!canEdit}
                  block
                >
                  {ic.control_limits_locked ? "解锁控制限" : "锁定控制限"}
                </Button>
              </Card>

              <Card title="判异规则" size="small" style={{ marginTop: 16 }}>
                {Object.entries(ruleLabels).map(([key, label]) => (
                  <div
                    key={key}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      marginBottom: 8,
                    }}
                  >
                    <Text style={{ fontSize: 12 }}>{label}</Text>
                    <Switch
                      size="small"
                      checked={!!ic.rules_config[key]}
                      onChange={(checked) => handleRuleToggle(key, checked)}
                      disabled={!canEdit}
                    />
                  </div>
                ))}
              </Card>
            </Col>
          </Row>
        </TabPane>

        {/* Tab 2: 过程能力 */}
        {!(["p", "np", "c", "u"].includes(ic?.chart_type || "")) && (
        <TabPane tab="过程能力" key="capability">
          {capability ? (
            <div>
              <Row gutter={16} style={{ marginBottom: 24 }}>
                <Col>
                  <Tag color={getGradeColor(capability.grade)} style={{ fontSize: 18, padding: "8px 16px" }}>
                    等级: {capability.grade}
                  </Tag>
                </Col>
              </Row>
              <Row gutter={[16, 16]}>
                <Col span={6}>
                  <Card>
                    <Statistic title="Cp" value={capability.cp} precision={3} />
                  </Card>
                </Col>
                <Col span={6}>
                  <Card>
                    <Statistic title="Cpk" value={capability.cpk} precision={3} />
                  </Card>
                </Col>
                <Col span={6}>
                  <Card>
                    <Statistic title="Pp" value={capability.pp} precision={3} />
                  </Card>
                </Col>
                <Col span={6}>
                  <Card>
                    <Statistic title="Ppk" value={capability.ppk} precision={3} />
                  </Card>
                </Col>
                <Col span={6}>
                  <Card>
                    <Statistic title="Cm" value={capability.cm} precision={3} />
                  </Card>
                </Col>
                <Col span={6}>
                  <Card>
                    <Statistic title="Cmk" value={capability.cmk} precision={3} />
                  </Card>
                </Col>
                <Col span={6}>
                  <Card>
                    <Statistic title="理论 PPM" value={capability.theoretical_ppm} precision={2} />
                  </Card>
                </Col>
                <Col span={6}>
                  <Card>
                    <Statistic title="实际 PPM" value={capability.actual_ppm} precision={2} />
                  </Card>
                </Col>
              </Row>
              <Card title="分析建议" style={{ marginTop: 16 }}>
                <Text>{capability.advice}</Text>
              </Card>
            </div>
          ) : (
            <Spin size="large" style={{ display: "block", margin: "64px auto" }} />
          )}
        </TabPane>
        )}

        {/* Tab 3: 数据录入 */}
        <TabPane tab="数据录入" key="data">
          <Tabs type="card">
            <TabPane tab="单批录入" key="single">
              <Card title="录入新批次">
                <Row gutter={16} style={{ marginBottom: 16 }}>
                  <Col span={8}>
                    <Text type="secondary">批次号</Text>
                    <Input
                      value={batchNo}
                      onChange={(e) => setBatchNo(e.target.value)}
                      placeholder="如 BATCH-20260521-001"
                    />
                  </Col>
                  <Col span={8}>
                    <Text type="secondary">采样时间</Text>
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
                    <Divider orientation="left">属性数据录入</Divider>
                    <Row gutter={[8, 8]}>
                      <Col span={6}>
                        <Input
                          type="number"
                          min={1}
                          value={inspectedCount}
                          onChange={(e) => setInspectedCount(e.target.value)}
                          addonBefore="检验数量 n"
                        />
                      </Col>
                      <Col span={6}>
                        <Input
                          type="number"
                          min={0}
                          value={defectCount}
                          onChange={(e) => setDefectCount(e.target.value)}
                          addonBefore="不合格品数/缺陷数"
                        />
                      </Col>
                    </Row>
                  </>
                ) : (
                  <>
                    <Divider orientation="left">
                      样本值 (建议 {subgroupSize} 个)
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
                      添加样本
                    </Button>
                  )}
                  <Button type="primary" onClick={handleAddSample} disabled={!canEdit}>
                    提交批次
                  </Button>
                </div>
              </Card>
            </TabPane>

            <TabPane tab="批量导入" key="batch">
              <Card>
                <Upload.Dragger
                  name="file"
                  multiple={false}
                  beforeUpload={() => false}
                  disabled
                >
                  <p className="ant-upload-drag-icon">
                    <UploadOutlined />
                  </p>
                  <p className="ant-upload-text">点击或拖拽文件到此处上传</p>
                  <p className="ant-upload-hint">
                    支持 Excel (.xlsx) 或 CSV 格式，每行包含: 批次号, 采样时间, 样本值1, 样本值2, ...
                  </p>
                </Upload.Dragger>
                <Text type="secondary" style={{ display: "block", marginTop: 16 }}>
                  批量导入功能开发中，请使用单批录入。
                </Text>
              </Card>
            </TabPane>

            <TabPane tab="历史数据" key="history">
              <Card>
                <Table
                  dataSource={chartData?.data_points || []}
                  rowKey="batch_index"
                  size="small"
                  pagination={{ pageSize: 20 }}
                  columns={[
                    { title: "序号", dataIndex: "batch_index", width: 70 },
                    { title: "批次号", dataIndex: "batch_no" },
                    {
                      title: "采样时间",
                      dataIndex: "sampled_at",
                      render: (v: string) => new Date(v).toLocaleString("zh-CN"),
                    },
                    {
                      title: "均值/X值",
                      dataIndex: "x_value",
                      render: (v: number | undefined) => v?.toFixed(3) ?? "-",
                    },
                    {
                      title: "极差/MR值",
                      dataIndex: "r_value",
                      render: (v: number | undefined) => v?.toFixed(3) ?? "-",
                    },
                    {
                      title: "告警",
                      dataIndex: "alarm_flags",
                      render: (flags: number[]) =>
                        flags.length > 0 ? (
                          <Tag color="red">规则 {flags.join(", ")}</Tag>
                        ) : (
                          <Tag color="green">正常</Tag>
                        ),
                    },
                  ]}
                />
              </Card>
            </TabPane>
          </Tabs>
        </TabPane>

        {/* Tab 4: 告警记录 */}
        <TabPane tab="告警记录" key="alarms">
          <Table
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
        </TabPane>
      </Tabs>
    </div>
  );
}

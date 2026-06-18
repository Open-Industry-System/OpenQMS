import * as echarts from "echarts";
import { useState, useEffect, useCallback, useRef } from "react";
import {
  Card,
  Button,
  Space,
  Form,
  Input,
  Select,
  DatePicker,
  App,
  Tabs,
  Table,
  Modal,
  Popconfirm,
  Row,
  Col,
  Statistic,
  Typography,
} from "antd";
import {
  ArrowLeftOutlined,
  PlayCircleOutlined,
  CheckCircleOutlined,
  StopOutlined,
  PlusOutlined,
  DeleteOutlined,
  PrinterOutlined,
  EditOutlined,
  LinkOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";
import type { AuditPlan, AuditFinding, AuditChecklistItem, User } from "../../types";
import {
  getAuditPlan,
  updateAuditPlan,
  startAuditPlan,
  completeAuditPlan,
  cancelAuditPlan,
  listAuditFindings,
  createAuditFinding,
  closeAuditFinding,
  createCAPAFromFinding,
} from "../../api/audit";
import { listUsers } from "../../api/auth";
import dayjs from "dayjs";
import { formatDateTime } from "../../utils/dateTime";
import PageShell from "../../components/design/PageShell";
import DataCard from "../../components/design/DataCard";
import StatusBadge from "../../components/design/StatusBadge";
import { useAuditStatusMap, useFindingTypeMap, useFindingStatusMap, useResultOptions } from "./useOptions";

const { Option } = Select;
const { TextArea } = Input;
const { Text } = Typography;

const statusVariant = (s: string): string => {
  if (s === "completed") return "success";
  if (s === "in_progress") return "warning";
  if (s === "cancelled") return "info";
  return "info";
};

export default function InternalAuditDetailPage() {
  const { t } = useTranslation("internalAudit");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const _user = useAuthStore((s) => s.user);
  const { canEdit } = usePermission();
  const STATUS_MAP = useAuditStatusMap();
  const FINDING_TYPE_MAP = useFindingTypeMap();
  const FINDING_STATUS_MAP = useFindingStatusMap();
  const RESULT_OPTIONS = useResultOptions();

  const [plan, setPlan] = useState<AuditPlan | null>(null);
  const [_loading, setLoading] = useState(false);
  const [users, setUsers] = useState<User[]>([]);
  const [findings, setFindings] = useState<AuditFinding[]>([]);
  const [findingsLoading, setFindingsLoading] = useState(false);

  const [infoEditing, setInfoEditing] = useState(false);
  const [infoForm] = Form.useForm();

  const [findingModalOpen, setFindingModalOpen] = useState(false);
  const [findingForm] = Form.useForm();

  const chartRef = useRef<HTMLDivElement>(null);

  const fetchPlan = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const p = await getAuditPlan(id);
      setPlan(p);
    } catch {
      message.error(t("messages.loadPlansFailed", "加载审核计划失败"));
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const fetchFindings = useCallback(async () => {
    if (!id) return;
    setFindingsLoading(true);
    try {
      const resp = await listAuditFindings({ audit_id: id, page_size: 1000 });
      setFindings(resp.items);
    } catch {
      message.error(t("messages.loadFindingsFailed", "加载发现项失败"));
    } finally {
      setFindingsLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    fetchPlan();
    fetchFindings();
    listUsers().then(setUsers).catch(() => {});
  }, [fetchPlan, fetchFindings]);

  // ECharts pie chart for report tab
  useEffect(() => {
    if (!chartRef.current || findings.length === 0) return;
    let chartInstance: any = null;
    let isCancelled = false;

    const initChart = async () => {
      if (isCancelled || !chartRef.current) return;
      chartInstance = echarts.init(chartRef.current);
      const data = [
        { value: findings.filter((f) => f.finding_type === "major_nc").length, name: t("findingType.major_nc", "严重不符合") },
        { value: findings.filter((f) => f.finding_type === "minor_nc").length, name: t("findingType.minor_nc", "一般不符合") },
        { value: findings.filter((f) => f.finding_type === "ofi").length, name: t("findingType.ofi", "改进机会") },
        { value: findings.filter((f) => f.finding_type === "observation").length, name: t("findingType.observation", "观察项") },
      ].filter((d) => d.value > 0);
      chartInstance.setOption({
        tooltip: { trigger: "item" },
        legend: { bottom: 0 },
        series: [
          {
            type: "pie",
            radius: ["40%", "70%"],
            avoidLabelOverlap: false,
            itemStyle: { borderRadius: 6, borderColor: "#fff", borderWidth: 2 },
            label: { show: true, formatter: "{b}: {c}" },
            data,
          },
        ],
      });
    };

    initChart();
    return () => {
      isCancelled = true;
      if (chartInstance) {
        chartInstance.dispose();
      }
    };
  }, [findings, t]);

  const handleUpdateInfo = async (values: Record<string, unknown>) => {
    if (!id) return;
    try {
      await updateAuditPlan(id, {
        audit_scope: values.audit_scope as string,
        audit_criteria: values.audit_criteria as string,
        planned_date: values.planned_date ? (values.planned_date as dayjs.Dayjs).format("YYYY-MM-DD") : undefined,
        actual_date: values.actual_date ? (values.actual_date as dayjs.Dayjs).format("YYYY-MM-DD") : null,
        lead_auditor: values.lead_auditor as string,
        team_members: (values.team_members as string[])?.map((uid) => {
          const u = users.find((x) => x.user_id === uid);
          return { user_id: uid, username: u?.username || "" };
        }) || [],
      });
      message.success(tc("messages.saveSuccess", "更新成功"));
      setInfoEditing(false);
      fetchPlan();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed", "更新失败"));
    }
  };

  const handleStart = async () => {
    if (!id) return;
    try {
      await startAuditPlan(id);
      message.success(t("messages.auditStarted", "审核已开始"));
      fetchPlan();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed", "操作失败"));
    }
  };

  const handleComplete = async () => {
    if (!id) return;
    try {
      await completeAuditPlan(id);
      message.success(t("messages.auditCompleted", "审核已完成"));
      fetchPlan();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed", "操作失败"));
    }
  };

  const handleCancel = async () => {
    if (!id) return;
    try {
      await cancelAuditPlan(id);
      message.success(t("messages.planCancelled", "审核已取消"));
      fetchPlan();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed", "操作失败"));
    }
  };

  const handleChecklistChange = async (index: number, field: keyof AuditChecklistItem, value: string) => {
    if (!plan || !id) return;
    const newChecklist = [...plan.checklist];
    newChecklist[index] = { ...newChecklist[index], [field]: value };
    try {
      await updateAuditPlan(id, { checklist: newChecklist });
      setPlan({ ...plan, checklist: newChecklist });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.saveFailed", "保存失败"));
    }
  };

  const handleAddChecklistItem = async () => {
    if (!plan || !id) return;
    const newItem: AuditChecklistItem = {
      item_no: String(plan.checklist.length + 1),
      clause: "",
      question: "",
      result: "",
      evidence: "",
      note: "",
    };
    const newChecklist = [...plan.checklist, newItem];
    try {
      await updateAuditPlan(id, { checklist: newChecklist });
      setPlan({ ...plan, checklist: newChecklist });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.addFailed", "添加失败"));
    }
  };

  const handleDeleteChecklistItem = async (index: number) => {
    if (!plan || !id) return;
    const newChecklist = plan.checklist.filter((_, i) => i !== index);
    try {
      await updateAuditPlan(id, { checklist: newChecklist });
      setPlan({ ...plan, checklist: newChecklist });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.deleteFailed", "删除失败"));
    }
  };

  const handleCreateFinding = async (values: Record<string, unknown>) => {
    if (!id) return;
    try {
      await createAuditFinding({
        audit_id: id,
        clause_ref: values.clause_ref as string,
        finding_type: values.finding_type as "major_nc" | "minor_nc" | "ofi" | "observation",
        description: values.description as string,
        root_cause: null,
        correction: null,
        corrective_action: null,
        due_date: values.due_date ? (values.due_date as dayjs.Dayjs).format("YYYY-MM-DD") : null,
        customer_confirmed: false,
        customer_confirmation_date: null,
        customer_confirmation_attachments: [],
      });
      message.success(t("messages.findingCreated", "发现项已创建"));
      setFindingModalOpen(false);
      findingForm.resetFields();
      fetchFindings();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed", "创建失败"));
    }
  };

  const handleCloseFinding = async (findingId: string) => {
    try {
      await closeAuditFinding(findingId);
      message.success(t("messages.findingClosed", "发现项已关闭"));
      fetchFindings();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed", "关闭失败"));
    }
  };

  const handleCreateCAPA = async (findingId: string) => {
    try {
      const resp = await createCAPAFromFinding(findingId);
      message.success(t("messages.capaCreated", "CAPA 已创建: {{documentNo}}", { documentNo: resp.document_no }));
      fetchFindings();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || t("messages.createCapaFailed", "创建 CAPA 失败"));
    }
  };

  const handlePrint = () => {
    window.print();
  };

  if (!plan) {
    return (
      <div style={{ padding: 24 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/internal-audits")}>
          {tc("actions.back", "返回列表")}
        </Button>
        <div style={{ marginTop: 24 }}>{tc("status.loading", "加载中")}...</div>
      </div>
    );
  }

  const majorCount = findings.filter((f) => f.finding_type === "major_nc").length;
  const minorCount = findings.filter((f) => f.finding_type === "minor_nc").length;
  const ofiCount = findings.filter((f) => f.finding_type === "ofi").length;
  const _obsCount = findings.filter((f) => f.finding_type === "observation").length;
  const openCount = findings.filter((f) => f.status !== "closed").length;

  return (
    <PageShell
      title={
        <Space size={12}>
          {plan.audit_id.slice(0, 8).toUpperCase()}
          <StatusBadge status={statusVariant(plan.status)}>{STATUS_MAP[plan.status]}</StatusBadge>
        </Space>
      }
      subtitle={t("pageSubtitle.detail", "内部审核计划详情")}
      actions={
        <Space wrap>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/internal-audits")}>{tc("actions.back", "返回列表")}</Button>
          {plan.status === "planned" && canEdit('audit') && (
            <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleStart}>{t("actions.start", "开始")}</Button>
          )}
          {plan.status === "in_progress" && canEdit('audit') && (
            <Button type="primary" icon={<CheckCircleOutlined />} onClick={handleComplete}>{t("actions.complete", "完成")}</Button>
          )}
          {plan.status === "planned" && canEdit('audit') && (
            <Popconfirm title={t("confirm.cancel", "确认取消？")} onConfirm={handleCancel}>
              <Button danger icon={<StopOutlined />}>{tc("actions.cancel", "取消")}</Button>
            </Popconfirm>
          )}
        </Space>
      }
    >
      <DataCard title={t("card.basicInfo", "基本信息")}
        extra={
          canEdit('audit') && (
            <Button
              icon={<EditOutlined />}
              onClick={() => {
                if (infoEditing) {
                  infoForm.submit();
                } else {
                  infoForm.setFieldsValue({
                    audit_scope: plan.audit_scope,
                    audit_criteria: plan.audit_criteria,
                    planned_date: plan.planned_date ? dayjs(plan.planned_date) : null,
                    actual_date: plan.actual_date ? dayjs(plan.actual_date) : null,
                    lead_auditor: plan.lead_auditor,
                    team_members: plan.team_members?.map((m) => m.user_id) || [],
                  });
                  setInfoEditing(true);
                }
              }}
            >
              {infoEditing ? tc("actions.save", "保存") : tc("actions.edit", "编辑")}
            </Button>
          )
        }
      style={{ marginBottom: 24 }}
      >
        {infoEditing ? (
          <Form form={infoForm} layout="vertical" onFinish={handleUpdateInfo}>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="audit_scope" label={t("form.scope", "审核范围")} rules={[{ required: true }]}>
                  <TextArea rows={2} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="audit_criteria" label={t("form.criteria", "审核准则")} rules={[{ required: true }]}>
                  <TextArea rows={2} />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item name="planned_date" label={t("form.plannedDate", "计划日期")}>
                  <DatePicker style={{ width: "100%" }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="actual_date" label={t("form.actualDate", "实际日期")}>
                  <DatePicker style={{ width: "100%" }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="lead_auditor" label={t("form.leadAuditor", "审核组长")}>
                  <Select placeholder={t("placeholder.leadAuditor", "选择审核组长")} allowClear>
                    {users.map((u) => (
                      <Option key={u.user_id} value={u.user_id}>
                        {u.display_name || u.username}
                      </Option>
                    ))}
                  </Select>
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={24}>
                <Form.Item name="team_members" label={t("form.teamMembers", "审核组员")}>
                  <Select mode="multiple" placeholder={t("form.teamMembers", "选择组员")} allowClear>
                    {users.map((u) => (
                      <Option key={u.user_id} value={u.user_id}>
                        {u.display_name || u.username}
                      </Option>
                    ))}
                  </Select>
                </Form.Item>
              </Col>
            </Row>
          </Form>
        ) : (
          <Row gutter={24}>
            <Col span={6}>
              <Text type="secondary">{t("form.scope", "审核范围")}</Text>
              <div>{plan.audit_scope}</div>
            </Col>
            <Col span={6}>
              <Text type="secondary">{t("form.criteria", "审核准则")}</Text>
              <div>{plan.audit_criteria}</div>
            </Col>
            <Col span={4}>
              <Text type="secondary">{t("form.plannedDate", "计划日期")}</Text>
              <div>{plan.planned_date}</div>
            </Col>
            <Col span={4}>
              <Text type="secondary">{t("form.actualDate", "实际日期")}</Text>
              <div>{plan.actual_date ? formatDateTime(plan.actual_date) : "—"}</div>
            </Col>
            <Col span={4}>
              <Text type="secondary">{t("form.leadAuditor", "审核组长")}</Text>
              <div>
                {plan.lead_auditor
                  ? users.find((u) => u.user_id === plan.lead_auditor)?.display_name ||
                    users.find((u) => u.user_id === plan.lead_auditor)?.username ||
                    plan.lead_auditor.slice(0, 8)
                  : "—"}
              </div>
            </Col>
          </Row>
        )}
      </DataCard>

      <DataCard title={t("card.basicInfo", "审核详情")} noPadding>
        <Tabs
          defaultActiveKey="checklist"
          items={[
          {
            key: "checklist",
            label: t("tabs.checklist", "检查表"),
            children: (
              <Card
                extra={
                  canEdit('audit') && (
                    <Button type="primary" icon={<PlusOutlined />} onClick={handleAddChecklistItem}>
                      {t("actions.addChecklistItem", "添加检查项")}
                    </Button>
                  )
                }
              >
                <Table
                  className="qf-table"
                  rowKey={(record, index) => `${record.item_no}-${index}`}
                  dataSource={plan.checklist}
                  pagination={false}
                  size="small"
                  scroll={{ x: 1200 }}
                  columns={[
                    { title: t("table.serialNo", "序号"), dataIndex: "item_no", width: 60 },
                    { title: t("table.clause", "条款"), dataIndex: "clause", width: 120 },
                    { title: t("table.question", "检查问题"), dataIndex: "question", ellipsis: true },
                    {
                      title: t("table.result", "结果"),
                      dataIndex: "result",
                      width: 120,
                      render: (value: string, _record: AuditChecklistItem, index: number) => (
                        <Select
                          value={value || undefined}
                          placeholder={t("placeholder.selectResult", "选择结果")}
                          style={{ width: "100%" }}
                          allowClear
                          disabled={!canEdit('audit')}
                          onChange={(v) => handleChecklistChange(index, "result", v || "")}
                        >
                          {RESULT_OPTIONS.map((o) => (
                            <Option key={o.value} value={o.value}>
                              {o.label}
                            </Option>
                          ))}
                        </Select>
                      ),
                    },
                    {
                      title: t("table.evidence", "证据"),
                      dataIndex: "evidence",
                      render: (value: string, _record: AuditChecklistItem, index: number) => (
                        <Input
                          value={value}
                          placeholder={t("placeholder.evidence", "输入证据")}
                          disabled={!canEdit('audit')}
                          onChange={(e) => handleChecklistChange(index, "evidence", e.target.value)}
                        />
                      ),
                    },
                    {
                      title: t("table.note", "备注"),
                      dataIndex: "note",
                      render: (value: string, _record: AuditChecklistItem, index: number) => (
                        <Input
                          value={value}
                          placeholder={t("placeholder.note", "输入备注")}
                          disabled={!canEdit('audit')}
                          onChange={(e) => handleChecklistChange(index, "note", e.target.value)}
                        />
                      ),
                    },
                    {
                      title: tc("table.operations", "操作"),
                      width: 80,
                      render: (_: unknown, _record: AuditChecklistItem, index: number) =>
                        canEdit('audit') ? (
                          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDeleteChecklistItem(index)} />
                        ) : null,
                    },
                  ]}
                  rowClassName={(record) => (record.result === "不符合" /* backend stores Chinese result values */ ? "audit-row-nc" : "")}
                />
              </Card>
            ),
          },
          {
            key: "findings",
            label: t("tabs.findings", "发现项"),
            children: (
              <Card
                extra={
                  canEdit('audit') && (
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => setFindingModalOpen(true)}>
                      {t("actions.addFinding", "添加发现项")}
                    </Button>
                  )
                }
              >
                <Table
                  className="qf-table"
                  rowKey="finding_id"
                  dataSource={findings}
                  loading={findingsLoading}
                  pagination={false}
                  size="small"
                  columns={[
                    { title: t("table.clauseRef", "条款"), dataIndex: "clause_ref", width: 100, render: (v: string | null) => v || "—" },
                    {
                      title: t("table.auditType", "类型"),
                      dataIndex: "finding_type",
                      width: 100,
                      render: (type: string) => {
                        const cfg = FINDING_TYPE_MAP[type];
                        return <StatusBadge status={cfg?.color === "red" ? "error" : cfg?.color === "orange" ? "warning" : "info"}>{cfg?.label}</StatusBadge>;
                      },
                    },
                    { title: t("table.description", "描述"), dataIndex: "description", ellipsis: true },
                    {
                      title: t("table.status", "状态"),
                      dataIndex: "status",
                      width: 90,
                      render: (status: string) => {
                        const cfg = FINDING_STATUS_MAP[status];
                        return <StatusBadge status={cfg?.color === "red" ? "error" : cfg?.color === "success" ? "success" : cfg?.color === "processing" ? "warning" : "info"}>{cfg?.label}</StatusBadge>;
                      },
                    },
                    { title: t("table.dueDate", "截止日期"), dataIndex: "due_date", width: 110, render: (v: string | null) => v ? formatDateTime(v) : "—" },
                    {
                      title: t("table.capa", "CAPA"),
                      width: 120,
                      render: (_: unknown, record: AuditFinding) =>
                        record.capa_ref_id ? (
                          <Button
                            size="small"
                            type="link"
                            icon={<LinkOutlined />}
                            onClick={() => navigate(`/capa/${record.capa_ref_id}`)}
                            style={{ padding: 0 }}
                          >
                            {t("actions.viewCapa", "查看CAPA")}
                          </Button>
                        ) : (
                          <StatusBadge status="info">{tc("status.pending", "未关联")}</StatusBadge>
                        ),
                    },
                    {
                      title: tc("table.operations", "操作"),
                      width: 200,
                      render: (_: unknown, record: AuditFinding) => (
                        <Space size="small">
                          {record.status !== "closed" && canEdit('audit') && (
                            <Button size="small" icon={<CheckCircleOutlined />} onClick={() => handleCloseFinding(record.finding_id)}>
                              {t("actions.closeFinding", "关闭")}
                            </Button>
                          )}
                          {!record.capa_ref_id && canEdit('audit') && (
                            <Button size="small" onClick={() => handleCreateCAPA(record.finding_id)}>
                              {t("actions.createCapa", "创建CAPA")}
                            </Button>
                          )}
                        </Space>
                      ),
                    },
                  ]}
                />
              </Card>
            ),
          },
          {
            key: "report",
            label: t("tabs.report", "审核报告"),
            children: (
              <>
                <Space style={{ marginBottom: 16 }}>
                  <Button icon={<PrinterOutlined />} onClick={handlePrint}>
                    {t("actions.printReport", "打印报告")}
                  </Button>
                </Space>

                <Row gutter={16} style={{ marginBottom: 24 }}>
                  <Col span={4}>
                    <Card>
                      <Statistic title={t("stats.totalFindings", "发现项总数")} value={findings.length} />
                    </Card>
                  </Col>
                  <Col span={5}>
                    <Card>
                      <Statistic title={t("stats.majorNc", "严重不符合")} value={majorCount} valueStyle={{ color: "#ff4d4f" }} />
                    </Card>
                  </Col>
                  <Col span={5}>
                    <Card>
                      <Statistic title={t("stats.minorNc", "一般不符合")} value={minorCount} valueStyle={{ color: "#faad14" }} />
                    </Card>
                  </Col>
                  <Col span={5}>
                    <Card>
                      <Statistic title={t("stats.ofi", "改进机会")} value={ofiCount} valueStyle={{ color: "#1890ff" }} />
                    </Card>
                  </Col>
                  <Col span={5}>
                    <Card>
                      <Statistic title={t("stats.unclosed", "未关闭")} value={openCount} valueStyle={{ color: openCount > 0 ? "#ff4d4f" : "#52c41a" }} />
                    </Card>
                  </Col>
                </Row>

                <Row gutter={24}>
                  <Col span={12}>
                    <Card title={t("report.findingDistribution", "发现项分布")}>
                      <div ref={chartRef} style={{ width: "100%", height: 300 }} />
                    </Card>
                  </Col>
                  <Col span={12}>
                    <Card title={t("report.findingList", "发现项清单")}>
                      {findings.length === 0 ? (
                        <Text type="secondary">{t("report.noFindings", "暂无发现项")}</Text>
                      ) : (
                        <Space direction="vertical" style={{ width: "100%" }}>
                          {findings.map((f) => (
                            <div key={f.finding_id} style={{ padding: "8px 0", borderBottom: "1px solid #f0f0f0" }}>
                              <Space>
                                <StatusBadge status={FINDING_TYPE_MAP[f.finding_type]?.color === "red" ? "error" : FINDING_TYPE_MAP[f.finding_type]?.color === "orange" ? "warning" : "info"}>{FINDING_TYPE_MAP[f.finding_type]?.label}</StatusBadge>
                                <Text strong>{f.clause_ref || "—"}</Text>
                              </Space>
                              <div style={{ marginTop: 4 }}>{f.description}</div>
                              <div style={{ marginTop: 4 }}>
                                <Text type="secondary" style={{ fontSize: 12 }}>
                                  {t("report.statusLabel", "状态")}: {FINDING_STATUS_MAP[f.status]?.label} | {t("report.dueLabel", "截止")}: {f.due_date ? formatDateTime(f.due_date) : "—"}
                                </Text>
                              </div>
                            </div>
                          ))}
                        </Space>
                      )}
                    </Card>
                  </Col>
                </Row>
              </>
            ),
          },
        ]}
      />
      </DataCard>

      <Modal
        title={t("modal.addFinding", "添加发现项")}
        open={findingModalOpen}
        onCancel={() => {
          setFindingModalOpen(false);
          findingForm.resetFields();
        }}
        onOk={() => findingForm.submit()}
        width={560}
      >
        <Form form={findingForm} layout="vertical" onFinish={handleCreateFinding}>
          <Form.Item name="clause_ref" label={t("form.clauseRef", "条款编号")}>
            <Input placeholder={t("placeholder.clauseRef", "如 4.1, 8.5.1")} />
          </Form.Item>
          <Form.Item name="finding_type" label={t("form.findingType", "发现项类型")} rules={[{ required: true }]}>
            <Select placeholder={t("placeholder.findingType", "选择类型")}>
              <Option value="major_nc">{t("findingType.major_nc", "严重不符合")}</Option>
              <Option value="minor_nc">{t("findingType.minor_nc", "一般不符合")}</Option>
              <Option value="ofi">{t("findingType.ofi", "改进机会")}</Option>
              <Option value="observation">{t("findingType.observation", "观察项")}</Option>
            </Select>
          </Form.Item>
          <Form.Item name="description" label={t("form.description", "描述")} rules={[{ required: true }]}>
            <TextArea rows={3} placeholder={t("placeholder.description", "描述发现的问题")} />
          </Form.Item>
          <Form.Item name="due_date" label={t("form.dueDate", "截止日期")}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>

      <style>{`
        .audit-row-nc {
          background-color: #fff1f0 !important;
        }
        .audit-row-nc:hover > td {
          background-color: #ffccc7 !important;
        }
        @media print {
          .ant-layout-sider,
          .ant-layout-header,
          .ant-tabs-nav,
          button {
            display: none !important;
          }
        }
      `}</style>
    </PageShell>
  );
}
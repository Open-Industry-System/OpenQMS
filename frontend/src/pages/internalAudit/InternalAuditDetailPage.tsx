import * as echarts from "echarts";
import { useState, useEffect, useCallback, useRef } from "react";
import {
  Card,
  Button,
  Tag,
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
import {
  useAuditStatusMap,
  useAuditStatusColor,
  useFindingTypeMap,
  useFindingStatusMap,
  useResultOptions,
} from "./useOptions";

const { Option } = Select;
const { TextArea } = Input;
const { Title, Text } = Typography;

export default function InternalAuditDetailPage() {
  const { t } = useTranslation("internalAudit");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const _user = useAuthStore((s) => s.user);
  const { canEdit } = usePermission();

  const auditStatusMap = useAuditStatusMap();
  const auditStatusColor = useAuditStatusColor();
  const findingTypeMap = useFindingTypeMap();
  const findingStatusMap = useFindingStatusMap();
  const resultOptions = useResultOptions();

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
      message.error(t("messages.loadPlansFailed"));
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
      message.error(t("messages.loadFindingsFailed"));
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

  useEffect(() => {
    if (!chartRef.current || findings.length === 0) return;
    let chartInstance: any = null;
    let isCancelled = false;

    const initChart = async () => {
      if (isCancelled || !chartRef.current) return;
      chartInstance = echarts.init(chartRef.current);
      const data = [
        { value: findings.filter((f) => f.finding_type === "major_nc").length, name: findingTypeMap.major_nc.label },
        { value: findings.filter((f) => f.finding_type === "minor_nc").length, name: findingTypeMap.minor_nc.label },
        { value: findings.filter((f) => f.finding_type === "ofi").length, name: findingTypeMap.ofi.label },
        { value: findings.filter((f) => f.finding_type === "observation").length, name: findingTypeMap.observation.label },
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
  }, [findings, findingTypeMap]);

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
      message.success(tc("messages.operationSuccess"));
      setInfoEditing(false);
      fetchPlan();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || t("messages.updateFailed"));
    }
  };

  const handleStart = async () => {
    if (!id) return;
    try {
      await startAuditPlan(id);
      message.success(t("messages.auditStarted"));
      fetchPlan();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed"));
    }
  };

  const handleComplete = async () => {
    if (!id) return;
    try {
      await completeAuditPlan(id);
      message.success(t("messages.auditCompleted"));
      fetchPlan();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed"));
    }
  };

  const handleCancel = async () => {
    if (!id) return;
    try {
      await cancelAuditPlan(id);
      message.success(t("messages.planCancelled"));
      fetchPlan();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed"));
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
      message.error(err.response?.data?.detail || t("messages.saveFailed"));
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
      message.error(err.response?.data?.detail || t("messages.addFailed"));
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
      message.error(err.response?.data?.detail || t("messages.deleteFailed"));
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
      message.success(t("messages.findingCreated"));
      setFindingModalOpen(false);
      findingForm.resetFields();
      fetchFindings();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed"));
    }
  };

  const handleCloseFinding = async (findingId: string) => {
    try {
      await closeAuditFinding(findingId);
      message.success(t("messages.findingClosed"));
      fetchFindings();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed"));
    }
  };

  const handleCreateCAPA = async (findingId: string) => {
    try {
      const resp = await createCAPAFromFinding(findingId);
      message.success(t("messages.capaCreated", { documentNo: resp.document_no }));
      fetchFindings();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || t("messages.createCapaFailed"));
    }
  };

  const handlePrint = () => {
    window.print();
  };

  if (!plan) {
    return (
      <div style={{ padding: 24 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/internal-audits")}>
          {tc("actions.back")}
        </Button>
        <div style={{ marginTop: 24 }}>{tc("actions.loading")}...</div>
      </div>
    );
  }

  const majorCount = findings.filter((f) => f.finding_type === "major_nc").length;
  const minorCount = findings.filter((f) => f.finding_type === "minor_nc").length;
  const ofiCount = findings.filter((f) => f.finding_type === "ofi").length;
  const _obsCount = findings.filter((f) => f.finding_type === "observation").length;
  const openCount = findings.filter((f) => f.status !== "closed").length;

  return (
    <div>
      <Space style={{ marginBottom: 16 }} wrap>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/internal-audits")}>
          {tc("actions.back")}
        </Button>
        <Title level={4} style={{ margin: 0 }}>
          {plan.audit_id.slice(0, 8).toUpperCase()}
        </Title>
        <Tag color={auditStatusColor[plan.status]}>{auditStatusMap[plan.status]}</Tag>
        {plan.status === "planned" && canEdit('audit') && (
          <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleStart}>
            {t("actions.start")}
          </Button>
        )}
        {plan.status === "in_progress" && canEdit('audit') && (
          <Button type="primary" icon={<CheckCircleOutlined />} onClick={handleComplete}>
            {t("actions.complete")}
          </Button>
        )}
        {plan.status === "planned" && canEdit('audit') && (
          <Popconfirm title={t("confirm.cancel")} onConfirm={handleCancel}>
            <Button danger icon={<StopOutlined />}>{tc("actions.cancel")}</Button>
          </Popconfirm>
        )}
      </Space>

      <Card
        title={t("card.basicInfo")}
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
              {infoEditing ? tc("actions.save") : tc("actions.edit")}
            </Button>
          )
        }
        style={{ marginBottom: 24 }}
      >
        {infoEditing ? (
          <Form form={infoForm} layout="vertical" onFinish={handleUpdateInfo}>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="audit_scope" label={t("form.scope")} rules={[{ required: true }]}>
                  <TextArea rows={2} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="audit_criteria" label={t("form.criteria")} rules={[{ required: true }]}>
                  <TextArea rows={2} />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item name="planned_date" label={t("form.plannedDate")}>
                  <DatePicker style={{ width: "100%" }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="actual_date" label={t("form.actualDate")}>
                  <DatePicker style={{ width: "100%" }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="lead_auditor" label={t("form.leadAuditor")}>
                  <Select placeholder={t("placeholder.leadAuditor")} allowClear>
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
                <Form.Item name="team_members" label={t("form.teamMembers")}>
                  <Select mode="multiple" placeholder={t("placeholder.leadAuditor")} allowClear>
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
              <Text type="secondary">{t("form.scope")}</Text>
              <div>{plan.audit_scope}</div>
            </Col>
            <Col span={6}>
              <Text type="secondary">{t("form.criteria")}</Text>
              <div>{plan.audit_criteria}</div>
            </Col>
            <Col span={4}>
              <Text type="secondary">{t("form.plannedDate")}</Text>
              <div>{plan.planned_date}</div>
            </Col>
            <Col span={4}>
              <Text type="secondary">{t("form.actualDate")}</Text>
              <div>{plan.actual_date || "—"}</div>
            </Col>
            <Col span={4}>
              <Text type="secondary">{t("form.leadAuditor")}</Text>
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
      </Card>

      <Tabs
        defaultActiveKey="checklist"
        items={[
          {
            key: "checklist",
            label: t("tabs.checklist"),
            children: (
              <Card
                extra={
                  canEdit('audit') && (
                    <Button type="primary" icon={<PlusOutlined />} onClick={handleAddChecklistItem}>
                      {t("actions.addChecklistItem")}
                    </Button>
                  )
                }
              >
                <Table
                  rowKey={(record, index) => `${record.item_no}-${index}`}
                  dataSource={plan.checklist}
                  pagination={false}
                  size="small"
                  scroll={{ x: 1200 }}
                  columns={[
                    { title: t("table.serialNo"), dataIndex: "item_no", width: 60 },
                    { title: t("table.clause"), dataIndex: "clause", width: 120 },
                    { title: t("table.question"), dataIndex: "question", ellipsis: true },
                    {
                      title: t("table.result"),
                      dataIndex: "result",
                      width: 120,
                      render: (value: string, _record: AuditChecklistItem, index: number) => (
                        <Select
                          value={value || undefined}
                          placeholder={t("placeholder.selectResult")}
                          style={{ width: "100%" }}
                          allowClear
                          disabled={!canEdit('audit')}
                          onChange={(v) => handleChecklistChange(index, "result", v || "")}
                        >
                          {resultOptions.map((o) => (
                            <Option key={o.value} value={o.value}>
                              {o.label}
                            </Option>
                          ))}
                        </Select>
                      ),
                    },
                    {
                      title: t("table.evidence"),
                      dataIndex: "evidence",
                      render: (value: string, _record: AuditChecklistItem, index: number) => (
                        <Input
                          value={value}
                          placeholder={t("placeholder.evidence")}
                          disabled={!canEdit('audit')}
                          onChange={(e) => handleChecklistChange(index, "evidence", e.target.value)}
                        />
                      ),
                    },
                    {
                      title: t("table.note"),
                      dataIndex: "note",
                      render: (value: string, _record: AuditChecklistItem, index: number) => (
                        <Input
                          value={value}
                          placeholder={t("placeholder.note")}
                          disabled={!canEdit('audit')}
                          onChange={(e) => handleChecklistChange(index, "note", e.target.value)}
                        />
                      ),
                    },
                    {
                      title: t("table.operations"),
                      width: 80,
                      render: (_: unknown, _record: AuditChecklistItem, index: number) =>
                        canEdit('audit') ? (
                          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDeleteChecklistItem(index)} />
                        ) : null,
                    },
                  ]}
                  rowClassName={(record) => (record.result === t("resultOptions.nonConform.value") ? "audit-row-nc" : "")}
                />
              </Card>
            ),
          },
          {
            key: "findings",
            label: t("tabs.findings"),
            children: (
              <Card
                extra={
                  canEdit('audit') && (
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => setFindingModalOpen(true)}>
                      {t("actions.addFinding")}
                    </Button>
                  )
                }
              >
                <Table
                  rowKey="finding_id"
                  dataSource={findings}
                  loading={findingsLoading}
                  pagination={false}
                  size="small"
                  columns={[
                    { title: t("table.clauseRef"), dataIndex: "clause_ref", width: 100, render: (v: string | null) => v || "—" },
                    {
                      title: t("table.auditType"),
                      dataIndex: "finding_type",
                      width: 100,
                      render: (type: string) => {
                        const cfg = findingTypeMap[type];
                        return <Tag color={cfg?.color}>{cfg?.label}</Tag>;
                      },
                    },
                    { title: t("table.description"), dataIndex: "description", ellipsis: true },
                    {
                      title: t("table.status"),
                      dataIndex: "status",
                      width: 90,
                      render: (status: string) => {
                        const cfg = findingStatusMap[status];
                        return <Tag color={cfg?.color}>{cfg?.label}</Tag>;
                      },
                    },
                    { title: t("table.dueDate"), dataIndex: "due_date", width: 110, render: (v: string | null) => v || "—" },
                    {
                      title: t("table.capa"),
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
                            {t("actions.viewCapa")}
                          </Button>
                        ) : (
                          <Tag>{tc("empty.data")}</Tag>
                        ),
                    },
                    {
                      title: t("table.operations"),
                      width: 200,
                      render: (_: unknown, record: AuditFinding) => (
                        <Space size="small">
                          {record.status !== "closed" && canEdit('audit') && (
                            <Button size="small" icon={<CheckCircleOutlined />} onClick={() => handleCloseFinding(record.finding_id)}>
                              {t("actions.closeFinding")}
                            </Button>
                          )}
                          {!record.capa_ref_id && canEdit('audit') && (
                            <Button size="small" onClick={() => handleCreateCAPA(record.finding_id)}>
                              {t("actions.createCapa")}
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
            label: t("tabs.report"),
            children: (
              <>
                <Space style={{ marginBottom: 16 }}>
                  <Button icon={<PrinterOutlined />} onClick={handlePrint}>
                    {t("actions.printReport")}
                  </Button>
                </Space>

                <Row gutter={16} style={{ marginBottom: 24 }}>
                  <Col span={4}>
                    <Card>
                      <Statistic title={t("stats.totalFindings")} value={findings.length} />
                    </Card>
                  </Col>
                  <Col span={5}>
                    <Card>
                      <Statistic title={findingTypeMap.major_nc.label} value={majorCount} valueStyle={{ color: "#ff4d4f" }} />
                    </Card>
                  </Col>
                  <Col span={5}>
                    <Card>
                      <Statistic title={findingTypeMap.minor_nc.label} value={minorCount} valueStyle={{ color: "#faad14" }} />
                    </Card>
                  </Col>
                  <Col span={5}>
                    <Card>
                      <Statistic title={findingTypeMap.ofi.label} value={ofiCount} valueStyle={{ color: "#1890ff" }} />
                    </Card>
                  </Col>
                  <Col span={5}>
                    <Card>
                      <Statistic title={t("stats.unclosed")} value={openCount} valueStyle={{ color: openCount > 0 ? "#ff4d4f" : "#52c41a" }} />
                    </Card>
                  </Col>
                </Row>

                <Row gutter={24}>
                  <Col span={12}>
                    <Card title={t("report.findingDistribution")}>
                      <div ref={chartRef} style={{ width: "100%", height: 300 }} />
                    </Card>
                  </Col>
                  <Col span={12}>
                    <Card title={t("report.findingList")}>
                      {findings.length === 0 ? (
                        <Text type="secondary">{t("empty.noFinding")}</Text>
                      ) : (
                        <Space direction="vertical" style={{ width: "100%" }}>
                          {findings.map((f) => (
                            <div key={f.finding_id} style={{ padding: "8px 0", borderBottom: "1px solid #f0f0f0" }}>
                              <Space>
                                <Tag color={findingTypeMap[f.finding_type]?.color}>{findingTypeMap[f.finding_type]?.label}</Tag>
                                <Text strong>{f.clause_ref || "—"}</Text>
                              </Space>
                              <div style={{ marginTop: 4 }}>{f.description}</div>
                              <div style={{ marginTop: 4 }}>
                                <Text type="secondary" style={{ fontSize: 12 }}>
                                  {t("report.statusLabel")}: {findingStatusMap[f.status]?.label} | {t("report.dueLabel")}: {f.due_date || "—"}
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

      <Modal
        title={t("modal.addFinding")}
        open={findingModalOpen}
        onCancel={() => {
          setFindingModalOpen(false);
          findingForm.resetFields();
        }}
        onOk={() => findingForm.submit()}
        width={560}
      >
        <Form form={findingForm} layout="vertical" onFinish={handleCreateFinding}>
          <Form.Item name="clause_ref" label={t("form.clauseRef")}>
            <Input placeholder={t("placeholder.clauseRef")} />
          </Form.Item>
          <Form.Item name="finding_type" label={t("form.findingType")} rules={[{ required: true }]}>
            <Select placeholder={t("placeholder.findingType")}>
              <Option value="major_nc">{findingTypeMap.major_nc.label}</Option>
              <Option value="minor_nc">{findingTypeMap.minor_nc.label}</Option>
              <Option value="ofi">{findingTypeMap.ofi.label}</Option>
              <Option value="observation">{findingTypeMap.observation.label}</Option>
            </Select>
          </Form.Item>
          <Form.Item name="description" label={t("form.description")} rules={[{ required: true }]}>
            <TextArea rows={3} placeholder={t("placeholder.description")} />
          </Form.Item>
          <Form.Item name="due_date" label={t("form.dueDate")}>
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
    </div>
  );
}

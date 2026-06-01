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
  updateAuditFinding,
  closeAuditFinding,
  createCAPAFromFinding,
} from "../../api/audit";
import { listUsers } from "../../api/auth";
import dayjs from "dayjs";

const { Option } = Select;
const { TextArea } = Input;
const { Title, Text } = Typography;
const STATUS_MAP: Record<string, { label: string; color: string }> = {
  planned: { label: "待执行", color: "blue" },
  in_progress: { label: "进行中", color: "processing" },
  completed: { label: "已完成", color: "success" },
  cancelled: { label: "已取消", color: "default" },
};

const FINDING_TYPE_MAP: Record<string, { label: string; color: string }> = {
  major_nc: { label: "严重不符合", color: "red" },
  minor_nc: { label: "一般不符合", color: "orange" },
  ofi: { label: "改进机会", color: "blue" },
  observation: { label: "观察项", color: "default" },
};

const FINDING_STATUS_MAP: Record<string, { label: string; color: string }> = {
  open: { label: "开放", color: "red" },
  in_progress: { label: "处理中", color: "processing" },
  verified: { label: "已验证", color: "blue" },
  closed: { label: "已关闭", color: "success" },
};

const RESULT_OPTIONS = [
  { value: "符合", label: "符合" },
  { value: "不符合", label: "不符合" },
  { value: "不适用", label: "不适用" },
];

export default function InternalAuditDetailPage() {
  const { message } = App.useApp();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const { canEdit } = usePermission();

  const [plan, setPlan] = useState<AuditPlan | null>(null);
  const [loading, setLoading] = useState(false);
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
      message.error("加载审核计划失败");
    } finally {
      setLoading(false);
    }
  }, [id]);

  const fetchFindings = useCallback(async () => {
    if (!id) return;
    setFindingsLoading(true);
    try {
      const resp = await listAuditFindings({ audit_id: id, page_size: 1000 });
      setFindings(resp.items);
    } catch {
      message.error("加载发现项失败");
    } finally {
      setFindingsLoading(false);
    }
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
      const echarts = await import("echarts");
      if (isCancelled || !chartRef.current) return;
      chartInstance = echarts.init(chartRef.current);
      const data = [
        { value: findings.filter((f) => f.finding_type === "major_nc").length, name: "严重不符合" },
        { value: findings.filter((f) => f.finding_type === "minor_nc").length, name: "一般不符合" },
        { value: findings.filter((f) => f.finding_type === "ofi").length, name: "改进机会" },
        { value: findings.filter((f) => f.finding_type === "observation").length, name: "观察项" },
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
  }, [findings]);

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
      message.success("更新成功");
      setInfoEditing(false);
      fetchPlan();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "更新失败");
    }
  };

  const handleStart = async () => {
    if (!id) return;
    try {
      await startAuditPlan(id);
      message.success("审核已开始");
      fetchPlan();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "操作失败");
    }
  };

  const handleComplete = async () => {
    if (!id) return;
    try {
      await completeAuditPlan(id);
      message.success("审核已完成");
      fetchPlan();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "操作失败");
    }
  };

  const handleCancel = async () => {
    if (!id) return;
    try {
      await cancelAuditPlan(id);
      message.success("审核已取消");
      fetchPlan();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "操作失败");
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
      message.error(err.response?.data?.detail || "保存失败");
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
      message.error(err.response?.data?.detail || "添加失败");
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
      message.error(err.response?.data?.detail || "删除失败");
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
      message.success("发现项已创建");
      setFindingModalOpen(false);
      findingForm.resetFields();
      fetchFindings();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "创建失败");
    }
  };

  const handleCloseFinding = async (findingId: string) => {
    try {
      await closeAuditFinding(findingId);
      message.success("发现项已关闭");
      fetchFindings();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "关闭失败");
    }
  };

  const handleCreateCAPA = async (findingId: string) => {
    try {
      const resp = await createCAPAFromFinding(findingId);
      message.success(`CAPA 已创建: ${resp.document_no}`);
      fetchFindings();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "创建 CAPA 失败");
    }
  };

  const handlePrint = () => {
    window.print();
  };

  if (!plan) {
    return (
      <div style={{ padding: 24 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/internal-audits")}>
          返回列表
        </Button>
        <div style={{ marginTop: 24 }}>加载中...</div>
      </div>
    );
  }

  const majorCount = findings.filter((f) => f.finding_type === "major_nc").length;
  const minorCount = findings.filter((f) => f.finding_type === "minor_nc").length;
  const ofiCount = findings.filter((f) => f.finding_type === "ofi").length;
  const obsCount = findings.filter((f) => f.finding_type === "observation").length;
  const openCount = findings.filter((f) => f.status !== "closed").length;

  return (
    <div>
      <Space style={{ marginBottom: 16 }} wrap>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/internal-audits")}>
          返回列表
        </Button>
        <Title level={4} style={{ margin: 0 }}>
          {plan.audit_id.slice(0, 8).toUpperCase()}
        </Title>
        <Tag color={STATUS_MAP[plan.status]?.color}>{STATUS_MAP[plan.status]?.label}</Tag>
        {plan.status === "planned" && canEdit('audit') && (
          <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleStart}>
            开始
          </Button>
        )}
        {plan.status === "in_progress" && canEdit('audit') && (
          <Button type="primary" icon={<CheckCircleOutlined />} onClick={handleComplete}>
            完成
          </Button>
        )}
        {plan.status === "planned" && canEdit('audit') && (
          <Popconfirm title="确认取消？" onConfirm={handleCancel}>
            <Button danger icon={<StopOutlined />}>取消</Button>
          </Popconfirm>
        )}
      </Space>

      <Card
        title="基本信息"
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
              {infoEditing ? "保存" : "编辑"}
            </Button>
          )
        }
        style={{ marginBottom: 24 }}
      >
        {infoEditing ? (
          <Form form={infoForm} layout="vertical" onFinish={handleUpdateInfo}>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="audit_scope" label="审核范围" rules={[{ required: true }]}>
                  <TextArea rows={2} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="audit_criteria" label="审核准则" rules={[{ required: true }]}>
                  <TextArea rows={2} />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item name="planned_date" label="计划日期">
                  <DatePicker style={{ width: "100%" }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="actual_date" label="实际日期">
                  <DatePicker style={{ width: "100%" }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="lead_auditor" label="审核组长">
                  <Select placeholder="选择审核组长" allowClear>
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
                <Form.Item name="team_members" label="审核组员">
                  <Select mode="multiple" placeholder="选择组员" allowClear>
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
              <Text type="secondary">审核范围</Text>
              <div>{plan.audit_scope}</div>
            </Col>
            <Col span={6}>
              <Text type="secondary">审核准则</Text>
              <div>{plan.audit_criteria}</div>
            </Col>
            <Col span={4}>
              <Text type="secondary">计划日期</Text>
              <div>{plan.planned_date}</div>
            </Col>
            <Col span={4}>
              <Text type="secondary">实际日期</Text>
              <div>{plan.actual_date || "—"}</div>
            </Col>
            <Col span={4}>
              <Text type="secondary">审核组长</Text>
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
            label: "检查表",
            children: (
              <Card
                extra={
                  canEdit('audit') && (
                    <Button type="primary" icon={<PlusOutlined />} onClick={handleAddChecklistItem}>
                      添加检查项
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
                    { title: "序号", dataIndex: "item_no", width: 60 },
                    { title: "条款", dataIndex: "clause", width: 120 },
                    { title: "检查问题", dataIndex: "question", ellipsis: true },
                    {
                      title: "结果",
                      dataIndex: "result",
                      width: 120,
                      render: (value: string, _record: AuditChecklistItem, index: number) => (
                        <Select
                          value={value || undefined}
                          placeholder="选择结果"
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
                      title: "证据",
                      dataIndex: "evidence",
                      render: (value: string, _record: AuditChecklistItem, index: number) => (
                        <Input
                          value={value}
                          placeholder="输入证据"
                          disabled={!canEdit('audit')}
                          onChange={(e) => handleChecklistChange(index, "evidence", e.target.value)}
                        />
                      ),
                    },
                    {
                      title: "备注",
                      dataIndex: "note",
                      render: (value: string, _record: AuditChecklistItem, index: number) => (
                        <Input
                          value={value}
                          placeholder="输入备注"
                          disabled={!canEdit('audit')}
                          onChange={(e) => handleChecklistChange(index, "note", e.target.value)}
                        />
                      ),
                    },
                    {
                      title: "操作",
                      width: 80,
                      render: (_: unknown, _record: AuditChecklistItem, index: number) =>
                        canEdit('audit') ? (
                          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDeleteChecklistItem(index)} />
                        ) : null,
                    },
                  ]}
                  rowClassName={(record) => (record.result === "不符合" ? "audit-row-nc" : "")}
                />
              </Card>
            ),
          },
          {
            key: "findings",
            label: "发现项",
            children: (
              <Card
                extra={
                  canEdit('audit') && (
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => setFindingModalOpen(true)}>
                      添加发现项
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
                    { title: "条款", dataIndex: "clause_ref", width: 100, render: (v: string | null) => v || "—" },
                    {
                      title: "类型",
                      dataIndex: "finding_type",
                      width: 100,
                      render: (type: string) => {
                        const cfg = FINDING_TYPE_MAP[type];
                        return <Tag color={cfg?.color}>{cfg?.label}</Tag>;
                      },
                    },
                    { title: "描述", dataIndex: "description", ellipsis: true },
                    {
                      title: "状态",
                      dataIndex: "status",
                      width: 90,
                      render: (status: string) => {
                        const cfg = FINDING_STATUS_MAP[status];
                        return <Tag color={cfg?.color}>{cfg?.label}</Tag>;
                      },
                    },
                    { title: "截止日期", dataIndex: "due_date", width: 110, render: (v: string | null) => v || "—" },
                    {
                      title: "CAPA",
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
                            查看CAPA
                          </Button>
                        ) : (
                          <Tag>未关联</Tag>
                        ),
                    },
                    {
                      title: "操作",
                      width: 200,
                      render: (_: unknown, record: AuditFinding) => (
                        <Space size="small">
                          {record.status !== "closed" && canEdit('audit') && (
                            <Button size="small" icon={<CheckCircleOutlined />} onClick={() => handleCloseFinding(record.finding_id)}>
                              关闭
                            </Button>
                          )}
                          {!record.capa_ref_id && canEdit('audit') && (
                            <Button size="small" onClick={() => handleCreateCAPA(record.finding_id)}>
                              创建CAPA
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
            label: "审核报告",
            children: (
              <>
                <Space style={{ marginBottom: 16 }}>
                  <Button icon={<PrinterOutlined />} onClick={handlePrint}>
                    打印报告
                  </Button>
                </Space>

                <Row gutter={16} style={{ marginBottom: 24 }}>
                  <Col span={4}>
                    <Card>
                      <Statistic title="发现项总数" value={findings.length} />
                    </Card>
                  </Col>
                  <Col span={5}>
                    <Card>
                      <Statistic title="严重不符合" value={majorCount} valueStyle={{ color: "#ff4d4f" }} />
                    </Card>
                  </Col>
                  <Col span={5}>
                    <Card>
                      <Statistic title="一般不符合" value={minorCount} valueStyle={{ color: "#faad14" }} />
                    </Card>
                  </Col>
                  <Col span={5}>
                    <Card>
                      <Statistic title="改进机会" value={ofiCount} valueStyle={{ color: "#1890ff" }} />
                    </Card>
                  </Col>
                  <Col span={5}>
                    <Card>
                      <Statistic title="未关闭" value={openCount} valueStyle={{ color: openCount > 0 ? "#ff4d4f" : "#52c41a" }} />
                    </Card>
                  </Col>
                </Row>

                <Row gutter={24}>
                  <Col span={12}>
                    <Card title="发现项分布">
                      <div ref={chartRef} style={{ width: "100%", height: 300 }} />
                    </Card>
                  </Col>
                  <Col span={12}>
                    <Card title="发现项清单">
                      {findings.length === 0 ? (
                        <Text type="secondary">暂无发现项</Text>
                      ) : (
                        <Space direction="vertical" style={{ width: "100%" }}>
                          {findings.map((f) => (
                            <div key={f.finding_id} style={{ padding: "8px 0", borderBottom: "1px solid #f0f0f0" }}>
                              <Space>
                                <Tag color={FINDING_TYPE_MAP[f.finding_type]?.color}>{FINDING_TYPE_MAP[f.finding_type]?.label}</Tag>
                                <Text strong>{f.clause_ref || "—"}</Text>
                              </Space>
                              <div style={{ marginTop: 4 }}>{f.description}</div>
                              <div style={{ marginTop: 4 }}>
                                <Text type="secondary" style={{ fontSize: 12 }}>
                                  状态: {FINDING_STATUS_MAP[f.status]?.label} | 截止: {f.due_date || "—"}
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
        title="添加发现项"
        open={findingModalOpen}
        onCancel={() => {
          setFindingModalOpen(false);
          findingForm.resetFields();
        }}
        onOk={() => findingForm.submit()}
        width={560}
      >
        <Form form={findingForm} layout="vertical" onFinish={handleCreateFinding}>
          <Form.Item name="clause_ref" label="条款编号">
            <Input placeholder="如 4.1, 8.5.1" />
          </Form.Item>
          <Form.Item name="finding_type" label="发现项类型" rules={[{ required: true }]}>
            <Select placeholder="选择类型">
              <Option value="major_nc">严重不符合</Option>
              <Option value="minor_nc">一般不符合</Option>
              <Option value="ofi">改进机会</Option>
              <Option value="observation">观察项</Option>
            </Select>
          </Form.Item>
          <Form.Item name="description" label="描述" rules={[{ required: true }]}>
            <TextArea rows={3} placeholder="描述发现的问题" />
          </Form.Item>
          <Form.Item name="due_date" label="截止日期">
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

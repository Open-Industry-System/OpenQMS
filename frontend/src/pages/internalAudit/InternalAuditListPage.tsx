import { useState, useEffect, useCallback } from "react";
import {
  Card,
  Table,
  Button,
  Space,
  Modal,
  Form,
  Input,
  Select,
  DatePicker,
  App,
  Tabs,
  Row,
  Col,
  Statistic,
  Drawer,
  InputNumber,
  Popconfirm,
} from "antd";
import {
  PlusOutlined,
  ReloadOutlined,
  EyeOutlined,
  PlayCircleOutlined,
  CheckCircleOutlined,
  StopOutlined,
  TeamOutlined,
  EditOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";
import type { AuditPlan, AuditProgram, AuditStats, AuditChecklistItem, User } from "../../types";
import {
  listAuditPlans,
  listAuditPrograms,
  createAuditProgram,
  createAuditPlan,
  startAuditPlan,
  completeAuditPlan,
  cancelAuditPlan,
  getAuditStats,
  getChecklistTemplates,
  listAuditors,
  updateAuditorInfo,
} from "../../api/audit";
import { listUsers } from "../../api/auth";
import PageShell from "../../components/design/PageShell";
import DataCard from "../../components/design/DataCard";
import StatusBadge from "../../components/design/StatusBadge";
import { useAuditTypeMap, useAuditStatusMap, useAuditStatusColor } from "./useOptions";

const { Option } = Select;
const { TextArea } = Input;
const { RangePicker } = DatePicker;

const statusVariant = (status: string): string => {
  switch (status) {
    case "completed": return "success";
    case "in_progress": return "warning";
    case "cancelled": return "info";
    default: return "info";
  }
};

export default function InternalAuditListPage() {
  const { t } = useTranslation("internalAudit");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const navigate = useNavigate();
  const _user = useAuthStore((s) => s.user);
  const { canEdit, isAdmin } = usePermission();
  const TYPE_MAP = useAuditTypeMap();
  const STATUS_MAP = useAuditStatusMap();
  const STATUS_COLOR = useAuditStatusColor();

  const [plans, setPlans] = useState<AuditPlan[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [activeTab, setActiveTab] = useState("all");
  const [stats, setStats] = useState<AuditStats>({
    program_count: 0,
    planned_count: 0,
    in_progress_count: 0,
    completed_count: 0,
    open_findings: 0,
    major_nc_count: 0,
  });

  const [programModalOpen, setProgramModalOpen] = useState(false);
  const [planModalOpen, setPlanModalOpen] = useState(false);
  const [auditorDrawerOpen, setAuditorDrawerOpen] = useState(false);

  const [users, setUsers] = useState<User[]>([]);
  const [auditors, setAuditors] = useState<User[]>([]);
  const [programs, setPrograms] = useState<AuditProgram[]>([]);
  const [checklistTemplates, setChecklistTemplates] = useState<{ audit_type: string; name: string; items: AuditChecklistItem[] }[]>([]);

  const [filterYear, setFilterYear] = useState<number | undefined>();
  const [filterType, setFilterType] = useState<string | undefined>();
  const [filterDateRange, setFilterDateRange] = useState<[string, string] | null>(null);

  const [programForm] = Form.useForm();
  const [planForm] = Form.useForm();

  const fetchStats = useCallback(async () => {
    try {
      const s = await getAuditStats();
      setStats(s);
    } catch {
      // ignore
    }
  }, []);

  const fetchPlans = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page, page_size: pageSize };
      if (activeTab !== "all") params.status = activeTab;
      if (filterYear) params.year = filterYear;
      if (filterType) params.audit_type = filterType;
      if (filterDateRange) {
        params.planned_date_from = filterDateRange[0];
        params.planned_date_to = filterDateRange[1];
      }
      const resp = await listAuditPlans(params);
      setPlans(resp.items);
      setTotal(resp.total);
    } catch {
      message.error(t("messages.loadPlansFailed", "加载审核计划失败"));
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize, activeTab, filterYear, filterType, filterDateRange]);

  const _fetchPrograms = useCallback(async () => {
    try {
      message.error(t("messages.loadPlansFailed", "请导入 listAuditPrograms"));
    } catch {
      // ignore
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    fetchPlans();
  }, [fetchPlans]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  useEffect(() => {
    listUsers().then(setUsers).catch(() => {});
    listAuditors().then(setAuditors).catch(() => {});
    getChecklistTemplates().then(setChecklistTemplates).catch(() => {});
    listAuditPrograms({ page_size: 1000 }).then((resp) => setPrograms(resp.items)).catch(() => {});
  }, []);

  const handleRefresh = () => {
    fetchPlans();
    fetchStats();
  };

  const handleCreateProgram = async (values: Record<string, unknown>) => {
    try {
      await createAuditProgram({
        program_year: values.program_year as number,
        audit_type: values.audit_type as "system" | "process" | "product",
        scope: values.scope as string,
        criteria: values.criteria as string,
      });
      message.success(t("messages.programCreated", "方案创建成功"));
      setProgramModalOpen(false);
      programForm.resetFields();
      fetchStats();
      listAuditPrograms({ page_size: 1000 }).then((resp) => setPrograms(resp.items)).catch(() => {});
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed", "创建失败"));
    }
  };

  const handleCreatePlan = async (values: Record<string, unknown>) => {
    try {
      const program = programs.find((p) => p.program_id === values.program_id);
      const template = checklistTemplates.find((t) => t.audit_type === program?.audit_type);
      await createAuditPlan({
        program_id: values.program_id as string,
        audit_scope: values.audit_scope as string,
        audit_criteria: values.audit_criteria as string,
        planned_date: values.planned_date as string,
        actual_date: null,
        lead_auditor: values.lead_auditor as string,
        team_members: [],
        checklist: template?.items || [],
        audit_category: "internal",
      });
      message.success(t("messages.planCreated", "计划创建成功"));
      setPlanModalOpen(false);
      planForm.resetFields();
      fetchPlans();
      fetchStats();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed", "创建失败"));
    }
  };

  const handleStart = async (id: string) => {
    try {
      await startAuditPlan(id);
      message.success(t("messages.auditStarted", "审核已开始"));
      fetchPlans();
      fetchStats();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed", "操作失败"));
    }
  };

  const handleComplete = async (id: string) => {
    try {
      await completeAuditPlan(id);
      message.success(t("messages.auditCompleted", "审核已完成"));
      fetchPlans();
      fetchStats();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed", "操作失败"));
    }
  };

  const handleCancel = async (id: string) => {
    try {
      await cancelAuditPlan(id);
      message.success(t("messages.planCancelled", "计划已取消"));
      fetchPlans();
      fetchStats();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed", "操作失败"));
    }
  };

  const handleUpdateAuditor = async (userId: string, values: { is_auditor: boolean; qualifications: string[] }) => {
    try {
      await updateAuditorInfo(userId, {
        is_auditor: values.is_auditor,
        qualifications: values.qualifications,
      });
      message.success(t("messages.auditorUpdated", "审核员信息已更新"));
      const resp = await listAuditors();
      setAuditors(resp);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.updateFailed", "更新失败"));
    }
  };

  const columns = [
    {
      title: t("table.planNo", "计划编号"),
      dataIndex: "audit_id",
      width: 220,
      render: (id: string) => <span style={{ fontFamily: "monospace" }}>{id.slice(0, 8)}</span>,
    },
    {
      title: t("table.auditType", "类型"),
      dataIndex: "audit_type",
      width: 100,
      render: (type: string) => TYPE_MAP[type] || type,
    },
    {
      title: t("table.auditScope", "审核范围"),
      dataIndex: "audit_scope",
      ellipsis: true,
    },
    {
      title: t("table.plannedDate", "计划日期"),
      dataIndex: "planned_date",
      width: 120,
    },
    {
      title: t("table.leadAuditor", "审核组长"),
      dataIndex: "lead_auditor",
      width: 120,
      render: (leadAuditor: string | null) => {
        if (!leadAuditor) return "—";
        const u = users.find((x) => x.user_id === leadAuditor);
        return u?.display_name || u?.username || leadAuditor.slice(0, 8);
      },
    },
    {
      title: t("table.status", "状态"),
      dataIndex: "status",
      width: 100,
      render: (status: string) => {
        return <StatusBadge status={statusVariant(status)}>{STATUS_MAP[status]}</StatusBadge>;
      },
    },
    {
      title: t("table.findingCount", "发现项数"),
      dataIndex: "finding_count",
      width: 100,
      render: (_: unknown, _record: AuditPlan) => {
        return "—";
      },
    },
    {
      title: tc("table.operations", "操作"),
      width: 240,
      render: (_: unknown, _record: AuditPlan) => (
        <Space size="small" wrap>
          <Button size="small" icon={<EyeOutlined />} onClick={() => navigate(`/internal-audits/${_record.audit_id}`)}>
            {t("actions.viewDetail", "查看详情")}
          </Button>
          {_record.status === "planned" && canEdit('audit') && (
            <Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={() => handleStart(_record.audit_id)}>
              {t("actions.start", "开始")}
            </Button>
          )}
          {_record.status === "in_progress" && canEdit('audit') && (
            <Button size="small" type="primary" icon={<CheckCircleOutlined />} onClick={() => handleComplete(_record.audit_id)}>
              {t("actions.complete", "完成")}
            </Button>
          )}
          {_record.status === "planned" && canEdit('audit') && (
            <Popconfirm title={t("confirm.cancel", "确认取消？")} onConfirm={() => handleCancel(_record.audit_id)}>
              <Button size="small" danger icon={<StopOutlined />}>
                {tc("actions.cancel", "取消")}
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <PageShell
      title={t("pageTitle.list", "内部审核管理")}
      subtitle={t("pageTitle.list", "年度审核计划与执行跟踪")}
      actions={
        <Space>
          {canEdit('audit') && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setProgramModalOpen(true)}>
              {t("actions.newProgram", "新建方案")}
            </Button>
          )}
          {canEdit('audit') && (
            <Button icon={<PlusOutlined />} onClick={() => setPlanModalOpen(true)}>
              {t("actions.newPlan", "新建计划")}
            </Button>
          )}
          <Button icon={<TeamOutlined />} onClick={() => setAuditorDrawerOpen(true)}>
            {t("actions.auditorManagement", "审核员管理")}
          </Button>
          <Button icon={<ReloadOutlined />} onClick={handleRefresh}>
            {tc("actions.refresh", "刷新")}
          </Button>
        </Space>
      }
    >
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title={t("stats.annualPrograms", "年度方案数")} value={stats.program_count} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title={t("stats.plannedAudits", "待执行审核")} value={stats.planned_count} valueStyle={{ color: "#1890ff" }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title={t("stats.openFindings", "开放发现项")} value={stats.open_findings} valueStyle={{ color: "#faad14" }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title={t("stats.majorNc", "严重不符合项")} value={stats.major_nc_count} valueStyle={{ color: "#ff4d4f" }} />
          </Card>
        </Col>
      </Row>

      <DataCard title={t("table.planNo", "审核计划")}>
        <Space style={{ marginBottom: 16 }} wrap>
          <Select
            placeholder={t("placeholder.year", "选择年份")}
            allowClear
            style={{ width: 120 }}
            value={filterYear}
            onChange={(v) => setFilterYear(v || undefined)}
          >
            <Option value={2024}>2024</Option>
            <Option value={2025}>2025</Option>
            <Option value={2026}>2026</Option>
            <Option value={2027}>2027</Option>
          </Select>
          <Select
            placeholder={t("placeholder.auditType", "审核类型")}
            allowClear
            style={{ width: 140 }}
            value={filterType}
            onChange={(v) => setFilterType(v || undefined)}
          >
            <Option value="system">{TYPE_MAP.system}</Option>
            <Option value="process">{TYPE_MAP.process}</Option>
            <Option value="product">{TYPE_MAP.product}</Option>
          </Select>
          <RangePicker
            onChange={(dates) => {
              if (dates && dates[0] && dates[1]) {
                setFilterDateRange([dates[0].format("YYYY-MM-DD"), dates[1].format("YYYY-MM-DD")]);
              } else {
                setFilterDateRange(null);
              }
            }}
          />
        </Space>

        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            { label: t("tabs.all", "全部"), key: "all" },
            { label: t("tabs.planned", "待执行"), key: "planned" },
            { label: t("tabs.in_progress", "进行中"), key: "in_progress" },
            { label: t("tabs.completed", "已完成"), key: "completed" },
          ]}
        />

        <Table
          className="qf-table"
          rowKey="audit_id"
          columns={columns}
          dataSource={plans}
          loading={loading}
          pagination={{
            current: page,
            pageSize: pageSize,
            total: total,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps || 20);
            },
          }}
        />
      </DataCard>

      <Modal
        title={t("modal.newProgram", "新建方案")}
        open={programModalOpen}
        onCancel={() => {
          setProgramModalOpen(false);
          programForm.resetFields();
        }}
        onOk={() => programForm.submit()}
        width={600}
      >
        <Form form={programForm} layout="vertical" onFinish={handleCreateProgram}>
          <Form.Item name="program_year" label={t("form.year", "年度")} rules={[{ required: true, message: t("validation.yearRequired", "请输入年度") }]}>
            <InputNumber style={{ width: "100%" }} placeholder={t("placeholder.year", "如 2026")} min={2000} max={2100} />
          </Form.Item>
          <Form.Item name="audit_type" label={t("form.auditType", "审核类型")} rules={[{ required: true, message: t("validation.auditTypeRequired", "请选择审核类型") }]}>
            <Select placeholder={t("placeholder.auditType", "选择审核类型")}>
              <Option value="system">{TYPE_MAP.system}</Option>
              <Option value="process">{TYPE_MAP.process}</Option>
              <Option value="product">{TYPE_MAP.product}</Option>
            </Select>
          </Form.Item>
          <Form.Item name="scope" label={t("form.scope", "审核范围")} rules={[{ required: true, message: t("validation.scopeRequired", "请输入审核范围") }]}>
            <TextArea rows={3} placeholder={t("placeholder.scope", "描述审核覆盖的范围")} />
          </Form.Item>
          <Form.Item name="criteria" label={t("form.criteria", "审核准则")} rules={[{ required: true, message: t("validation.criteriaRequired", "请输入审核准则") }]}>
            <TextArea rows={3} placeholder={t("placeholder.criteria", "如 ISO 9001, IATF 16949 等")} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t("modal.newPlan", "新建计划")}
        open={planModalOpen}
        onCancel={() => {
          setPlanModalOpen(false);
          planForm.resetFields();
        }}
        onOk={() => planForm.submit()}
        width={600}
      >
        <Form form={planForm} layout="vertical" onFinish={handleCreatePlan}>
          <Form.Item name="program_id" label={t("form.program", "所属方案")} rules={[{ required: true, message: t("validation.programRequired", "请选择方案") }]}>
            <Select placeholder={t("placeholder.program", "选择审核方案")}>
              {programs.map((p) => (
                <Option key={p.program_id} value={p.program_id}>
                  {p.program_year} - {TYPE_MAP[p.audit_type]} ({p.scope.slice(0, 20)}...)
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="audit_scope" label={t("form.scope", "审核范围")} rules={[{ required: true, message: t("validation.scopeRequired", "请输入审核范围") }]}>
            <TextArea rows={2} placeholder={t("placeholder.scope", "本次审核的具体范围")} />
          </Form.Item>
          <Form.Item name="audit_criteria" label={t("form.criteria", "审核准则")} rules={[{ required: true, message: t("validation.criteriaRequired", "请输入审核准则") }]}>
            <TextArea rows={2} placeholder={t("placeholder.criteria", "本次审核依据的准则")} />
          </Form.Item>
          <Form.Item name="planned_date" label={t("form.plannedDate", "计划日期")} rules={[{ required: true, message: t("validation.plannedDateRequired", "请选择计划日期") }]}>
            <DatePicker style={{ width: "100%" }} placeholder={t("placeholder.plannedDate", "选择计划日期")} />
          </Form.Item>
          <Form.Item name="lead_auditor" label={t("form.leadAuditor", "审核组长")} rules={[{ required: true, message: t("validation.leadAuditorRequired", "请选择审核组长") }]}>
            <Select placeholder={t("placeholder.leadAuditor", "选择审核组长")}>
              {auditors.map((u) => (
                <Option key={u.user_id} value={u.user_id}>
                  {u.display_name || u.username}
                </Option>
              ))}
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={t("drawer.auditorManagement", "审核员管理")}
        open={auditorDrawerOpen}
        onClose={() => setAuditorDrawerOpen(false)}
        width={720}
      >
        <Table
          rowKey="user_id"
          dataSource={auditors}
          pagination={false}
          columns={[
            {
              title: t("auditorTable.username", "用户名"),
              dataIndex: "username",
            },
            {
              title: t("auditorTable.displayName", "显示名"),
              dataIndex: "display_name",
              render: (v: string | null) => v || "—",
            },
            {
              title: t("auditorTable.qualifications", "资格类型"),
              dataIndex: "qualifications",
              render: (_: unknown, record: User) => {
                const info = record.auditor_info;
                return info?.qualifications?.join(", ") || "—";
              },
            },
            {
              title: t("auditorTable.lastQualificationDate", "最近资格日期"),
              dataIndex: "last_qualification_date",
              render: (_: unknown, record: User) => {
                const info = record.auditor_info;
                return info?.last_qualification_date || "—";
              },
            },
            {
              title: tc("table.operations", "操作"),
              render: (_: unknown, record: User) => {
                if (!isAdmin) return null;
                return (
                  <Button
                    size="small"
                    icon={<EditOutlined />}
                    onClick={() => {
                      const info = record.auditor_info;
                      const values = {
                        is_auditor: info?.is_auditor ?? true,
                        qualifications: info?.qualifications || [],
                      };
                      const qStr = prompt(t("prompt.qualifications", "资格类型（逗号分隔）:"), values.qualifications.join(", "));
                      if (qStr !== null) {
                        handleUpdateAuditor(record.user_id, {
                          is_auditor: values.is_auditor,
                          qualifications: qStr.split(",").map((s) => s.trim()).filter(Boolean),
                        });
                      }
                    }}
                  >
                    {tc("actions.edit", "编辑")}
                  </Button>
                );
              },
            },
          ]}
        />
      </Drawer>
    </PageShell>
  );
}
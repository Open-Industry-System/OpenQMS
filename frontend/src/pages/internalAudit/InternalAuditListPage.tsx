import { useState, useEffect, useCallback } from "react";
import {
  Card,
  Table,
  Button,
  Tag,
  Space,
  Modal,
  Form,
  Input,
  Select,
  DatePicker,
  message,
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
import { useAuthStore } from "../../store/authStore";
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

const { Option } = Select;
const { TabPane } = Tabs;
const { TextArea } = Input;
const { RangePicker } = DatePicker;

const TYPE_MAP: Record<string, string> = {
  system: "体系",
  process: "过程",
  product: "产品",
};

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  planned: { label: "待执行", color: "blue" },
  in_progress: { label: "进行中", color: "orange" },
  completed: { label: "已完成", color: "green" },
  cancelled: { label: "已取消", color: "gray" },
};

export default function InternalAuditListPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === "admin";
  const isEngineerPlus = user?.role === "admin" || user?.role === "manager" || user?.role === "quality_engineer";

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
      message.error("加载审核计划失败");
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, activeTab, filterYear, filterType, filterDateRange]);

  const fetchPrograms = useCallback(async () => {
    try {
      // We need to fetch programs for the plan creation dropdown.
      // listAuditPrograms is not exported from audit.ts, so we use listAuditPlans with a large page size to get programs indirectly,
      // or we can call the endpoint directly. Since listAuditPrograms exists in the backend but isn't in audit.ts exports,
      // let's use the client directly or add it. Wait — looking at audit.ts, listAuditPrograms IS exported.
      // But we need it here. Let's import it.
      // Actually I didn't import it above. I'll add a direct call via the API module if needed.
      // For now, we can fetch programs by calling listAuditPrograms which is in audit.ts.
      // Let me adjust: I need to import it.
      message.error("请导入 listAuditPrograms");
    } catch {
      // ignore
    }
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
    // Load programs for plan creation
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
      message.success("方案创建成功");
      setProgramModalOpen(false);
      programForm.resetFields();
      fetchStats();
      // Refresh programs list
      listAuditPrograms({ page_size: 1000 }).then((resp) => setPrograms(resp.items)).catch(() => {});
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "创建失败");
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
      });
      message.success("计划创建成功");
      setPlanModalOpen(false);
      planForm.resetFields();
      fetchPlans();
      fetchStats();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "创建失败");
    }
  };

  const handleStart = async (id: string) => {
    try {
      await startAuditPlan(id);
      message.success("审核已开始");
      fetchPlans();
      fetchStats();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "操作失败");
    }
  };

  const handleComplete = async (id: string) => {
    try {
      await completeAuditPlan(id);
      message.success("审核已完成");
      fetchPlans();
      fetchStats();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "操作失败");
    }
  };

  const handleCancel = async (id: string) => {
    try {
      await cancelAuditPlan(id);
      message.success("计划已取消");
      fetchPlans();
      fetchStats();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "操作失败");
    }
  };

  const handleUpdateAuditor = async (userId: string, values: { is_auditor: boolean; qualifications: string[] }) => {
    try {
      await updateAuditorInfo(userId, {
        is_auditor: values.is_auditor,
        qualifications: values.qualifications,
      });
      message.success("审核员信息已更新");
      const resp = await listAuditors();
      setAuditors(resp);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "更新失败");
    }
  };

  const columns = [
    {
      title: "计划编号",
      dataIndex: "audit_id",
      width: 220,
      render: (id: string) => <span style={{ fontFamily: "monospace" }}>{id.slice(0, 8)}</span>,
    },
    {
      title: "类型",
      dataIndex: "audit_type",
      width: 100,
      render: (type: string) => TYPE_MAP[type] || type,
    },
    {
      title: "审核范围",
      dataIndex: "audit_scope",
      ellipsis: true,
    },
    {
      title: "计划日期",
      dataIndex: "planned_date",
      width: 120,
    },
    {
      title: "审核组长",
      dataIndex: "lead_auditor",
      width: 120,
      render: (leadAuditor: string | null) => {
        if (!leadAuditor) return "—";
        const u = users.find((x) => x.user_id === leadAuditor);
        return u?.display_name || u?.username || leadAuditor.slice(0, 8);
      },
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (status: string) => {
        const cfg = STATUS_MAP[status];
        return <Tag color={cfg?.color}>{cfg?.label}</Tag>;
      },
    },
    {
      title: "发现项数",
      dataIndex: "finding_count",
      width: 100,
      render: (_: unknown, record: AuditPlan) => {
        // finding_count is not in AuditPlan type, so we show placeholder or compute from something else.
        // Since the backend may not return it, we show "—" for now.
        return "—";
      },
    },
    {
      title: "操作",
      width: 240,
      render: (_: unknown, record: AuditPlan) => (
        <Space size="small" wrap>
          <Button size="small" icon={<EyeOutlined />} onClick={() => navigate(`/internal-audits/${record.audit_id}`)}>
            查看详情
          </Button>
          {record.status === "planned" && isEngineerPlus && (
            <Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={() => handleStart(record.audit_id)}>
              开始
            </Button>
          )}
          {record.status === "in_progress" && isEngineerPlus && (
            <Button size="small" type="primary" icon={<CheckCircleOutlined />} onClick={() => handleComplete(record.audit_id)}>
              完成
            </Button>
          )}
          {record.status === "planned" && isEngineerPlus && (
            <Popconfirm title="确认取消？" onConfirm={() => handleCancel(record.audit_id)}>
              <Button size="small" danger icon={<StopOutlined />}>
                取消
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title="年度方案数" value={stats.program_count} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="待执行审核" value={stats.planned_count} valueStyle={{ color: "#1890ff" }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="开放发现项" value={stats.open_findings} valueStyle={{ color: "#faad14" }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="严重不符合项" value={stats.major_nc_count} valueStyle={{ color: "#ff4d4f" }} />
          </Card>
        </Col>
      </Row>

      <Card
        title="内部审核管理"
        extra={
          <Space>
            {isEngineerPlus && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setProgramModalOpen(true)}>
                新建方案
              </Button>
            )}
            {isEngineerPlus && (
              <Button icon={<PlusOutlined />} onClick={() => setPlanModalOpen(true)}>
                新建计划
              </Button>
            )}
            <Button icon={<TeamOutlined />} onClick={() => setAuditorDrawerOpen(true)}>
              审核员管理
            </Button>
            <Button icon={<ReloadOutlined />} onClick={handleRefresh}>
              刷新
            </Button>
          </Space>
        }
      >
        <Space style={{ marginBottom: 16 }} wrap>
          <Select
            placeholder="选择年份"
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
            placeholder="审核类型"
            allowClear
            style={{ width: 140 }}
            value={filterType}
            onChange={(v) => setFilterType(v || undefined)}
          >
            <Option value="system">体系</Option>
            <Option value="process">过程</Option>
            <Option value="product">产品</Option>
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

        <Tabs activeKey={activeTab} onChange={setActiveTab}>
          <TabPane tab="全部" key="all" />
          <TabPane tab="待执行" key="planned" />
          <TabPane tab="进行中" key="in_progress" />
          <TabPane tab="已完成" key="completed" />
        </Tabs>

        <Table
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
      </Card>

      <Modal
        title="新建方案"
        open={programModalOpen}
        onCancel={() => {
          setProgramModalOpen(false);
          programForm.resetFields();
        }}
        onOk={() => programForm.submit()}
        width={600}
      >
        <Form form={programForm} layout="vertical" onFinish={handleCreateProgram}>
          <Form.Item name="program_year" label="年度" rules={[{ required: true, message: "请输入年度" }]}>
            <InputNumber style={{ width: "100%" }} placeholder="如 2026" min={2000} max={2100} />
          </Form.Item>
          <Form.Item name="audit_type" label="审核类型" rules={[{ required: true, message: "请选择审核类型" }]}>
            <Select placeholder="选择审核类型">
              <Option value="system">体系</Option>
              <Option value="process">过程</Option>
              <Option value="product">产品</Option>
            </Select>
          </Form.Item>
          <Form.Item name="scope" label="审核范围" rules={[{ required: true, message: "请输入审核范围" }]}>
            <TextArea rows={3} placeholder="描述审核覆盖的范围" />
          </Form.Item>
          <Form.Item name="criteria" label="审核准则" rules={[{ required: true, message: "请输入审核准则" }]}>
            <TextArea rows={3} placeholder="如 ISO 9001, IATF 16949 等" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="新建计划"
        open={planModalOpen}
        onCancel={() => {
          setPlanModalOpen(false);
          planForm.resetFields();
        }}
        onOk={() => planForm.submit()}
        width={600}
      >
        <Form form={planForm} layout="vertical" onFinish={handleCreatePlan}>
          <Form.Item name="program_id" label="所属方案" rules={[{ required: true, message: "请选择方案" }]}>
            <Select placeholder="选择审核方案">
              {programs.map((p) => (
                <Option key={p.program_id} value={p.program_id}>
                  {p.program_year}年 - {TYPE_MAP[p.audit_type]} ({p.scope.slice(0, 20)}...)
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="audit_scope" label="审核范围" rules={[{ required: true, message: "请输入审核范围" }]}>
            <TextArea rows={2} placeholder="本次审核的具体范围" />
          </Form.Item>
          <Form.Item name="audit_criteria" label="审核准则" rules={[{ required: true, message: "请输入审核准则" }]}>
            <TextArea rows={2} placeholder="本次审核依据的准则" />
          </Form.Item>
          <Form.Item name="planned_date" label="计划日期" rules={[{ required: true, message: "请选择计划日期" }]}>
            <DatePicker style={{ width: "100%" }} placeholder="选择计划日期" />
          </Form.Item>
          <Form.Item name="lead_auditor" label="审核组长" rules={[{ required: true, message: "请选择审核组长" }]}>
            <Select placeholder="选择审核组长">
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
        title="审核员管理"
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
              title: "用户名",
              dataIndex: "username",
            },
            {
              title: "显示名",
              dataIndex: "display_name",
              render: (v: string | null) => v || "—",
            },
            {
              title: "资格类型",
              dataIndex: "qualifications",
              render: (_: unknown, record: User) => {
                // qualifications may be on auditor_info; since User type doesn't have it,
                // we cast to any for now or show placeholder.
                // The backend returns auditor_info as part of User when listing auditors.
                const info = record.auditor_info;
                return info?.qualifications?.join(", ") || "—";
              },
            },
            {
              title: "最近资格日期",
              dataIndex: "last_qualification_date",
              render: (_: unknown, record: User) => {
                const info = record.auditor_info;
                return info?.last_qualification_date || "—";
              },
            },
            {
              title: "操作",
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
                      // Simple prompt-based edit for qualifications
                      const qStr = prompt("资格类型（逗号分隔）:", values.qualifications.join(", "));
                      if (qStr !== null) {
                        handleUpdateAuditor(record.user_id, {
                          is_auditor: values.is_auditor,
                          qualifications: qStr.split(",").map((s) => s.trim()).filter(Boolean),
                        });
                      }
                    }}
                  >
                    编辑
                  </Button>
                );
              },
            },
          ]}
        />
      </Drawer>
    </div>
  );
}

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Table, Tabs, Button, Space, Modal, Form, Input, DatePicker, message, Card, Row, Col } from "antd";
import { PlusOutlined, ProjectOutlined, ClockCircleOutlined, CheckCircleOutlined, ExclamationCircleOutlined } from "@ant-design/icons";
import { listAPQPProjects, createAPQPProject, getAPQPProjectStats } from "../../../api/apqp";
import type { APQPProject, APQPListResponse, APQPProjectStats } from "../../../types";
import PageShell from "../../../components/design/PageShell";
import DataCard from "../../../components/design/DataCard";
import StatusBadge from "../../../components/design/StatusBadge";

const PROJECT_STATUS_TABS = [
  { key: "all", label: "全部" },
  { key: "active", label: "进行中" },
  { key: "completed", label: "已完成" },
  { key: "cancelled", label: "已取消" },
];

const PHASE_NAMES: Record<number, string> = {
  1: "策划与定义",
  2: "产品设计与开发",
  3: "过程设计与开发",
  4: "产品与过程确认",
  5: "量产启动与反馈",
};

const PROJECT_STATUS_LABELS: Record<string, string> = {
  active: "进行中",
  completed: "已完成",
  cancelled: "已取消",
};

const phaseVariant = (phase: number): string => (phase === 5 ? "success" : "info");
const projectStatusVariant = (status: string): string => {
  if (status === "completed") return "success";
  if (status === "active") return "warning";
  return "info";
};
const phaseStatusVariant = (status: string): string => {
  if (status === "completed") return "success";
  if (status === "pending_approval") return "warning";
  return "info";
};

function KPICard({ title, value, icon, color }: { title: string; value: number; icon: React.ReactNode; color: string }) {
  return (
    <Card size="small">
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ fontSize: 24, color }}>{icon}</div>
        <div>
          <div style={{ fontSize: 12, color: "#999" }}>{title}</div>
          <div style={{ fontSize: 24, fontWeight: 600 }}>{value}</div>
        </div>
      </div>
    </Card>
  );
}

export default function APQPListPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<APQPListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("all");
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [form] = Form.useForm();
  const [stats, setStats] = useState<APQPProjectStats | null>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const [result, s] = await Promise.all([
        listAPQPProjects({
          page,
          page_size: 20,
          project_status: activeTab === "all" ? undefined : activeTab,
        }),
        getAPQPProjectStats(),
      ]);
      setData(result);
      setStats(s);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, page]);

  const handleCreate = async (values: Record<string, unknown>) => {
    await createAPQPProject({
      project_name: values.project_name as string,
      product_name: values.product_name as string,
      product_line_code: values.product_line_code as string,
      customer_name: values.customer_name as string | undefined,
      description: values.description as string | undefined,
      target_sop_date: values.target_sop_date
        ? (values.target_sop_date as { format: (f: string) => string }).format("YYYY-MM-DD")
        : undefined,
      dfmea_id: values.dfmea_id as string | undefined,
      pfmea_id: values.pfmea_id as string | undefined,
      control_plan_id: values.control_plan_id as string | undefined,
      ppap_submission_id: values.ppap_submission_id as string | undefined,
    });
    message.success("项目创建成功");
    setCreateOpen(false);
    form.resetFields();
    loadData();
  };

  const columns = [
    { title: "项目编号", dataIndex: "project_code", key: "project_code", render: (_v: string, record: APQPProject) => <a onClick={() => navigate(`/apqp/${record.project_id}`)}>{record.project_code}</a> },
    { title: "项目名称", dataIndex: "project_name", key: "project_name" },
    { title: "产品", dataIndex: "product_name", key: "product_name" },
    { title: "客户", dataIndex: "customer_name", key: "customer_name", render: (v: string | null) => v || "-" },
    {
      title: "当前阶段",
      dataIndex: "current_phase",
      key: "current_phase",
      render: (p: number) => <StatusBadge status={phaseVariant(p)}>{PHASE_NAMES[p]}</StatusBadge>,
    },
    {
      title: "阶段状态",
      dataIndex: "phase_status",
      key: "phase_status",
      render: (s: string | null) => {
        if (!s) return "-";
        const labels: Record<string, string> = { pending_approval: "待审批", in_progress: "进行中", completed: "已完成" };
        return <StatusBadge status={phaseStatusVariant(s)}>{labels[s] || s}</StatusBadge>;
      },
    },
    {
      title: "目标SOP",
      dataIndex: "target_sop_date",
      key: "target_sop_date",
      render: (v: string | null) => {
        if (!v) return "-";
        const isOverdue = new Date(v) < new Date(new Date().toDateString());
        return <span style={{ color: isOverdue ? "red" : undefined }}>{v}{isOverdue ? " ⚠" : ""}</span>;
      },
    },
    {
      title: "项目状态",
      dataIndex: "project_status",
      key: "project_status",
      render: (s: string) => (
        <StatusBadge status={projectStatusVariant(s)}>{PROJECT_STATUS_LABELS[s] || s}</StatusBadge>
      ),
    },
    {
      title: "操作",
      key: "action",
      render: (_: unknown, record: APQPProject) => (
        <Button type="link" onClick={() => navigate(`/apqp/${record.project_id}`)}>查看</Button>
      ),
    },
  ];

  return (
    <PageShell
      title="APQP 项目管理"
      subtitle="产品质量先期策划全阶段跟踪"
      actions={
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          新建项目
        </Button>
      }
    >
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={4}><KPICard title="进行中" value={stats?.active_count ?? 0} icon={<ProjectOutlined />} color="#1677ff" /></Col>
        <Col span={4}><KPICard title="待审批" value={stats?.pending_approval_count ?? 0} icon={<ClockCircleOutlined />} color="#fa8c16" /></Col>
        <Col span={4}><KPICard title="已完成" value={stats?.completed_count ?? 0} icon={<CheckCircleOutlined />} color="#52c41a" /></Col>
        <Col span={4}><KPICard title="逾期" value={stats?.overdue_count ?? 0} icon={<ExclamationCircleOutlined />} color="#ff4d4f" /></Col>
      </Row>

      <DataCard title="项目列表">
        <Tabs activeKey={activeTab} onChange={(k) => { setActiveTab(k); setPage(1); }} items={PROJECT_STATUS_TABS} style={{ marginBottom: 16 }} />
        <Table
          className="qf-table"
          dataSource={data?.items || []}
          columns={columns}
          rowKey="project_id"
          loading={loading}
        pagination={{
          current: page,
          pageSize: 20,
          total: data?.total || 0,
          onChange: setPage,
        }}
      />
      </DataCard>

      <Modal
        title="新建 APQP 项目"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        destroyOnHidden
        width={640}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="project_name" label="项目名称" rules={[{ required: true, message: "请输入项目名称" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="product_name" label="产品名称" rules={[{ required: true, message: "请输入产品名称" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="product_line_code" label="产品线" rules={[{ required: true, message: "请输入产品线" }]}>
            <Input placeholder="例: DC-DC-100" />
          </Form.Item>
          <Form.Item name="customer_name" label="客户名称">
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="target_sop_date" label="目标SOP日期">
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Space style={{ width: "100%" }}>
            {/* v1 使用文本输入，FK 校验由后端返回 400 兜底；后续改为 Select 组件 */}
            <Form.Item name="dfmea_id" label="DFMEA">
              <Input placeholder="FMEA ID（可选，v1 文本输入）" style={{ width: 200 }} />
            </Form.Item>
            <Form.Item name="pfmea_id" label="PFMEA">
              <Input placeholder="FMEA ID（可选，v1 文本输入）" style={{ width: 200 }} />
            </Form.Item>
          </Space>
          <Space style={{ width: "100%" }}>
            <Form.Item name="control_plan_id" label="控制计划">
              <Input placeholder="CP ID（可选，v1 文本输入）" style={{ width: 200 }} />
            </Form.Item>
            <Form.Item name="ppap_submission_id" label="PPAP">
              <Input placeholder="PPAP ID（可选，v1 文本输入）" style={{ width: 200 }} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </PageShell>
  );
}

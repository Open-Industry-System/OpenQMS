import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Table, Tabs, Button, Space, Modal, Form, Input, DatePicker, message, Row, Col, Tag } from "antd";
import { PlusOutlined, ProjectOutlined, ClockCircleOutlined, CheckCircleOutlined, ExclamationCircleOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { listAPQPProjects, createAPQPProject, getAPQPProjectStats } from "../../../api/apqp";
import type { APQPProject, APQPListResponse, APQPProjectStats } from "../../../types";
import PageShell from "../../../components/design/PageShell";
import DataCard from "../../../components/design/DataCard";
import StatusBadge from "../../../components/design/StatusBadge";

const PHASE_COLORS: Record<number, string> = {
  1: "blue",
  2: "cyan",
  3: "geekblue",
  4: "purple",
  5: "green",
};

function KPICard({ title, value, icon, color }: { title: string; value: number; icon: React.ReactNode; color: string }) {
  return (
    <DataCard title={null}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ fontSize: 24, color }}>{icon}</div>
        <div>
          <div style={{ fontSize: 12, color: "#999" }}>{title}</div>
          <div style={{ fontSize: 24, fontWeight: 600 }}>{value}</div>
        </div>
      </div>
    </DataCard>
  );
}

function useAPQPLabels(t: (key: string) => string) {
  const projectStatusTabs = [
    { key: "all", label: t("tab.all") },
    { key: "active", label: t("tab.active") },
    { key: "completed", label: t("tab.completed") },
    { key: "cancelled", label: t("tab.cancelled") },
  ];

  const phaseNames: Record<number, string> = {
    1: t("phase.1"),
    2: t("phase.2"),
    3: t("phase.3"),
    4: t("phase.4"),
    5: t("phase.5"),
  };

  const projectStatusLabels: Record<string, string> = {
    active: t("projectStatus.active"),
    completed: t("projectStatus.completed"),
    cancelled: t("projectStatus.cancelled"),
  };

  const phaseStatusRender = (s: string | null) => {
    if (s === "pending_approval") return <Tag color="orange">{t("phaseStatus.pendingApproval")}</Tag>;
    if (s === "in_progress") return <Tag color="blue">{t("phaseStatus.inProgress")}</Tag>;
    if (s === "completed") return <Tag color="green">{t("phaseStatus.completed")}</Tag>;
    return s || "-";
  };

  return { projectStatusTabs, phaseNames, projectStatusLabels, phaseStatusRender };
}

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

export default function APQPListPage() {
  const { t } = useTranslation("apqp");
  const { t: tc } = useTranslation("common");
  const navigate = useNavigate();
  const [data, setData] = useState<APQPListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("all");
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [form] = Form.useForm();
  const [stats, setStats] = useState<APQPProjectStats | null>(null);

  const { projectStatusTabs, phaseNames, projectStatusLabels, phaseStatusRender } = useAPQPLabels(t);

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
    message.success(t("message.createSuccess"));
    setCreateOpen(false);
    form.resetFields();
    loadData();
  };

  const columns = [
    { title: t("column.projectCode"), dataIndex: "project_code", key: "project_code", render: (_v: string, record: APQPProject) => <a onClick={() => navigate(`/apqp/${record.project_id}`)}>{record.project_code}</a> },
    { title: t("column.projectName"), dataIndex: "project_name", key: "project_name" },
    { title: t("column.product"), dataIndex: "product_name", key: "product_name" },
    { title: t("column.customer"), dataIndex: "customer_name", key: "customer_name", render: (v: string | null) => v || "-" },
    {
      title: t("column.currentPhase"),
      dataIndex: "current_phase",
      key: "current_phase",
      render: (p: number) => <StatusBadge status={phaseVariant(p)}>{phaseNames[p]}</StatusBadge>,
    },
    {
      title: t("column.phaseStatus"),
      dataIndex: "phase_status",
      key: "phase_status",
      render: (s: string | null) => {
        if (!s) return "-";
        const labels: Record<string, string> = { pending_approval: t("phaseStatus.pendingApproval"), in_progress: t("phaseStatus.inProgress"), completed: t("phaseStatus.completed") };
        return <StatusBadge status={phaseStatusVariant(s)}>{labels[s] || s}</StatusBadge>;
      },
    },
    {
      title: t("column.targetSOP"),
      dataIndex: "target_sop_date",
      key: "target_sop_date",
      render: (v: string | null) => {
        if (!v) return "-";
        const isOverdue = new Date(v) < new Date(new Date().toDateString());
        return <span style={{ color: isOverdue ? "red" : undefined }}>{v}{isOverdue ? ` ${t("label.overdue")}` : ""}</span>;
      },
    },
    {
      title: t("column.projectStatus"),
      dataIndex: "project_status",
      key: "project_status",
      render: (s: string) => (
        <StatusBadge status={projectStatusVariant(s)}>{projectStatusLabels[s] || s}</StatusBadge>
      ),
    },
    {
      title: t("column.action"),
      key: "action",
      render: (_: unknown, record: APQPProject) => (
        <Button type="link" onClick={() => navigate(`/apqp/${record.project_id}`)}>{tc("actions.view")}</Button>
      ),
    },
  ];

  return (
    <PageShell
      title={t("pageTitle.apqpProjectManagement")}
      subtitle={t("pageTitle.apqpProjectManagementSubtitle")}
      actions={
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          {t("pageTitle.newAPQPProject")}
        </Button>
      }
    >
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={4}><KPICard title={t("kpi.active")} value={stats?.active_count ?? 0} icon={<ProjectOutlined />} color="#1677ff" /></Col>
        <Col span={4}><KPICard title={t("kpi.pendingApproval")} value={stats?.pending_approval_count ?? 0} icon={<ClockCircleOutlined />} color="#fa8c16" /></Col>
        <Col span={4}><KPICard title={t("kpi.completed")} value={stats?.completed_count ?? 0} icon={<CheckCircleOutlined />} color="#52c41a" /></Col>
        <Col span={4}><KPICard title={t("kpi.overdue")} value={stats?.overdue_count ?? 0} icon={<ExclamationCircleOutlined />} color="#ff4d4f" /></Col>
      </Row>

      <DataCard title={t("card.projectList")}>
        <Tabs activeKey={activeTab} onChange={(k) => { setActiveTab(k); setPage(1); }} items={projectStatusTabs} style={{ marginBottom: 16 }} />
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
        title={t("pageTitle.newAPQPProject")}
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        destroyOnHidden
        width={640}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="project_name" label={t("form.projectName")} rules={[{ required: true, message: t("message.enterName") }]}>
            <Input />
          </Form.Item>
          <Form.Item name="product_name" label={t("form.productName")} rules={[{ required: true, message: t("message.enterProductName") }]}>
            <Input />
          </Form.Item>
          <Form.Item name="product_line_code" label={t("form.productLine")} rules={[{ required: true, message: t("message.enterProductLine") }]}>
            <Input placeholder={t("placeholder.productLine")} />
          </Form.Item>
          <Form.Item name="customer_name" label={t("form.customerName")}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label={t("form.description")}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="target_sop_date" label={t("form.targetSOPDate")}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Space style={{ width: "100%" }}>
            <Form.Item name="dfmea_id" label={t("form.dfmea")}>
              <Input placeholder={t("placeholder.fmeaOptional")} style={{ width: 200 }} />
            </Form.Item>
            <Form.Item name="pfmea_id" label={t("form.pfmea")}>
              <Input placeholder={t("placeholder.fmeaOptional")} style={{ width: 200 }} />
            </Form.Item>
          </Space>
          <Space style={{ width: "100%" }}>
            <Form.Item name="control_plan_id" label={t("form.controlPlan")}>
              <Input placeholder={t("placeholder.cpOptional")} style={{ width: 200 }} />
            </Form.Item>
            <Form.Item name="ppap_submission_id" label={t("form.ppap")}>
              <Input placeholder={t("placeholder.ppapOptional")} style={{ width: 200 }} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </PageShell>
  );
}

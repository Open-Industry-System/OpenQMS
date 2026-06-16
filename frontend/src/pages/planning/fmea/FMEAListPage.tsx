import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Table, Button, Tag, Form, Input, Select, Modal, App } from "antd";
import { PlusOutlined, FileTextOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { listFMEAs, createFMEA, updateFMEA } from "../../../api/fmea";
import type { FMEADocument, GraphNode, GraphEdge } from "../../../types";
import GenerationWizard from "../../../components/dfmea/GenerationWizard";
import { useAuthStore } from "../../../store/authStore";
import { usePermission } from "../../../hooks/usePermission";
import { useProductLineStore } from "../../../store/productLineStore";
import { PageShell, StatusBadge } from "../../../components/design";

export default function FMEAListPage() {
  const { t, i18n } = useTranslation("fmea");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();

  const typeLabels: Record<string, string> = {
    PFMEA: "PFMEA",
    DFMEA: "DFMEA",
  };

  const statusLabels: Record<string, string> = {
    draft: t("status.draft"),
    in_review: t("status.in_review"),
    approved: t("status.approved"),
    rework: t("status.rework"),
    archived: t("status.archived"),
  };
  const [data, setData] = useState<FMEADocument[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const _user = useAuthStore((s) => s.user);
  const { canEdit } = usePermission();
  const productLine = useProductLineStore((s) => s.selected);
  const [searchParams] = useSearchParams();

  const fetchData = (p: number = page) => {
    setLoading(true);
    const highRpn = searchParams.get("risk") === "high";
    const pendingApproval = searchParams.get("pending_approval") === "true";
    listFMEAs({
      page: p,
      page_size: 20,
      product_line: productLine || undefined,
      high_rpn: highRpn || undefined,
      status: pendingApproval ? "in_review" : undefined,
    })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine, searchParams]);

  const handleCreate = async (values: { title: string; document_no: string; fmea_type: string; problem_description?: string }) => {
    if (values.fmea_type === "DFMEA") {
      setModalOpen(false);
      setWizardOpen(true);
      return;
    }
    try {
      const fmea = await createFMEA(values);
      message.success(t("messages.createSuccess"));
      setModalOpen(false);
      form.resetFields();
      navigate(`/fmea/${fmea.fmea_id}`, { state: { showLessonsLearned: true, problemDescription: values.problem_description } });
    } catch {
      message.error(t("messages.createFailed"));
    }
  };

  const handleWizardComplete = async (skeleton: { nodes: GraphNode[]; edges: GraphEdge[] }) => {
    try {
      const fmea = await createFMEA({
        title: form.getFieldValue("title") || t("create.defaultTitle"),
        document_no: form.getFieldValue("document_no") || `DFMEA-${new Date().getFullYear()}-${String(Math.floor(Math.random() * 1000)).padStart(3, "0")}`,
        fmea_type: "DFMEA",
      });
      await updateFMEA(fmea.fmea_id, {
        graph_data: { nodes: skeleton.nodes, edges: skeleton.edges },
      });
      message.success(t("messages.dfmeaCreateSuccess"));
      setWizardOpen(false);
      form.resetFields();
      navigate(`/fmea/${fmea.fmea_id}`, { state: { showLessonsLearned: true, problemDescription: undefined } });
    } catch {
      message.error(t("messages.createFailed"));
    }
  };

  const columns = [
    {
      title: t("list.columns.documentNo"),
      dataIndex: "document_no",
      key: "document_no",
      width: 150,
      render: (v: string) => <span style={{ fontFamily: "var(--qf-font-mono)" }}>{v}</span>,
    },
    { title: t("list.columns.title"), dataIndex: "title", key: "title", ellipsis: true },
    {
      title: t("list.columns.type"),
      dataIndex: "fmea_type",
      key: "fmea_type",
      width: 90,
      render: (t: string) => (
        <Tag style={{ background: "var(--qf-cyan-dim)", color: "var(--qf-cyan)", borderColor: "var(--qf-cyan)" }}>
          {typeLabels[t] || t}
        </Tag>
      ),
    },
    {
      title: t("list.columns.status"),
      dataIndex: "status",
      key: "status",
      width: 110,
      render: (s: string) => <StatusBadge status={s}>{statusLabels[s] || s}</StatusBadge>,
    },
    {
      title: t("list.columns.version"),
      dataIndex: "version",
      key: "version",
      width: 70,
      render: (v: number) => <span className="qf-mono">v{v}</span>,
    },
    {
      title: t("list.columns.updatedAt"),
      dataIndex: "updated_at",
      key: "updated_at",
      width: 180,
      render: (v: string) => new Date(v).toLocaleString(i18n.language || "zh-CN"),
    },
    {
      title: t("list.columns.actions"),
      key: "actions",
      width: 100,
      render: (_: unknown, record: FMEADocument) => (
        <Button type="link" icon={<FileTextOutlined />} onClick={() => navigate(`/fmea/${record.fmea_id}`)}>
          {canEdit('fmea') ? tc("actions.edit") : tc("actions.view")}
        </Button>
      ),
    },
  ];

  const actions = canEdit('fmea') ? (
    <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
      {t("list.newFMEA")}
    </Button>
  ) : null;

  return (
    <PageShell title={t("list.title")} subtitle={t("list.subtitle")} actions={actions}>
      <Table
        className="qf-table"
        columns={columns}
        dataSource={data}
        rowKey="fmea_id"
        loading={loading}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => {
            setPage(p);
            fetchData(p);
          },
        }}
      />

      <Modal
        title={t("create.title")}
        open={modalOpen}
        onOk={() => form.submit()}
        onCancel={() => setModalOpen(false)}
        okButtonProps={{ className: "qf-btn-primary" }}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate} initialValues={{ fmea_type: "PFMEA" }}>
          <Form.Item name="fmea_type" label={t("create.type")} rules={[{ required: true, message: t("create.typeRequired") }]}>
            <Select
              options={[
                { value: "PFMEA", label: t("list.typeOption.pfmea") },
                { value: "DFMEA", label: t("list.typeOption.dfmea") },
              ]}
            />
          </Form.Item>
          <Form.Item name="document_no" label={t("create.documentNo")} rules={[{ required: true, message: t("create.documentNoRequired") }]}>
            <Input placeholder={t("create.documentNoPlaceholder")} />
          </Form.Item>
          <Form.Item name="title" label={t("create.titleLabel")} rules={[{ required: true, message: t("create.titleRequired") }]}>
            <Input placeholder={t("create.titlePlaceholder")} />
          </Form.Item>
          <Form.Item name="problem_description" label={t("create.problemDescription")}>
            <Input.TextArea rows={2} placeholder={t("create.problemDescriptionPlaceholder")} />
          </Form.Item>
        </Form>
      </Modal>

      <GenerationWizard
        open={wizardOpen}
        onCancel={() => setWizardOpen(false)}
        onComplete={handleWizardComplete}
      />
    </PageShell>
  );
}

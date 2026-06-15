import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Table, Button, Tag, Typography, Modal, Form, Input, Popconfirm, App } from "antd";
import { PlusOutlined, FileTextOutlined, DeleteOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { listControlPlans, createControlPlan, deleteControlPlan } from "../../../api/controlPlan";
import { batchValidationSummaries } from "../../../api/cpValidation";
import ValidationBadge from "../../../components/control-plan/ValidationBadge";
import type { ControlPlan } from "../../../types";
import type { ValidationSummary } from "../../../types/cpValidation";
import { useAuthStore } from "../../../store/authStore";
import { usePermission } from "../../../hooks/usePermission";
import { useProductLineStore } from "../../../store/productLineStore";

const { Title } = Typography;

const statusColors: Record<string, string> = {
  draft: "blue",
  approved: "green",
};

export default function ControlPlanListPage() {
  const { t } = useTranslation("controlPlan");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const [data, setData] = useState<ControlPlan[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const _user = useAuthStore((s) => s.user);
  const { canEdit } = usePermission();
  const productLine = useProductLineStore((s) => s.selected);
  const [validationMap, setValidationMap] = useState<Record<string, ValidationSummary>>({});

  const phaseLabels: Record<string, string> = {
    sample: t("phase.sample"),
    trial: t("phase.trial"),
    production: t("phase.production"),
  };

  const statusLabels: Record<string, string> = {
    draft: t("status.draft"),
    approved: t("status.approved"),
  };

  const fetchData = (p: number = page) => {
    setLoading(true);
    listControlPlans({ page: p, page_size: 20, product_line: productLine || undefined })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData(1);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine]);

  useEffect(() => {
    if (!data?.length) return;
    const fetchSummaries = async () => {
      try {
        const cpIds = data.map((cp) => cp.cp_id);
        const summaries = await batchValidationSummaries(cpIds);
        setValidationMap(summaries);
      } catch {
        // ignore fetch errors
      }
    };
    fetchSummaries();
  }, [data]);

  const handleCreate = async (values: { title: string; document_no: string }) => {
    try {
      const cp = await createControlPlan(values);
      message.success(t("message.createSuccess"));
      setModalOpen(false);
      form.resetFields();
      navigate(`/control-plans/${cp.cp_id}`);
    } catch {
      message.error(t("message.createFailed"));
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteControlPlan(id);
      message.success(tc("messages.deleteSuccess"));
      fetchData();
    } catch {
      message.error(tc("messages.deleteFailed"));
    }
  };

  const columns = [
    { title: t("column.documentNo"), dataIndex: "document_no", key: "document_no", width: 150 },
    { title: t("column.title"), dataIndex: "title", key: "title", ellipsis: true },
    {
      title: t("column.validationStatus"),
      key: "validation",
      width: 80,
      align: "center" as const,
      render: (_: unknown, record: ControlPlan) => {
        const summary = validationMap[record.cp_id];
        return (
          <ValidationBadge
            errorCount={summary?.error_count || 0}
            warningCount={summary?.warning_count || 0}
            total={summary?.total || 0}
            validated={Boolean(summary?.run_id)}
          />
        );
      },
    },
    {
      title: t("column.phase"),
      dataIndex: "phase",
      key: "phase",
      width: 100,
      render: (p: string) => phaseLabels[p] || p,
    },
    {
      title: t("column.status"),
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (s: string) => <Tag color={statusColors[s] || "default"}>{statusLabels[s] || s}</Tag>,
    },
    { title: t("column.version"), dataIndex: "version", key: "version", width: 80, render: (v: number) => `v${v}` },
    {
      title: t("column.updatedAt"),
      dataIndex: "updated_at",
      key: "updated_at",
      width: 170,
      render: (v: string) => new Date(v).toLocaleString(),
    },
    {
      title: t("column.actions"),
      key: "actions",
      width: 160,
      render: (_: unknown, record: ControlPlan) => (
        <>
          <Button type="link" icon={<FileTextOutlined />} onClick={() => navigate(`/control-plans/${record.cp_id}`)}>
            {tc("actions.edit")}
          </Button>
          {canEdit('planning') && (
            <Popconfirm title={tc("messages.confirmDelete")} onConfirm={() => handleDelete(record.cp_id)}>
              <Button type="link" danger icon={<DeleteOutlined />}>
                {tc("actions.delete")}
              </Button>
            </Popconfirm>
          )}
        </>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>{t("pageTitle.controlPlanList")}</Title>
        {canEdit('planning') && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
            {t("button.newControlPlan")}
          </Button>
        )}
      </div>

      <Table
        columns={columns}
        dataSource={data}
        rowKey="cp_id"
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
        title={t("pageTitle.newControlPlan")}
        open={modalOpen}
        onOk={() => form.submit()}
        onCancel={() => setModalOpen(false)}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="document_no" label={t("form.documentNo")} rules={[{ required: true, message: t("message.enterDocumentNo") }]}>
            <Input placeholder={t("placeholder.documentNo")} />
          </Form.Item>
          <Form.Item name="title" label={t("form.title")} rules={[{ required: true, message: t("message.enterTitle") }]}>
            <Input placeholder={t("placeholder.title")} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

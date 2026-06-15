import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Table, Button, Tag, Typography, Modal, Form, Input, Select, DatePicker, App } from "antd";
import { PlusOutlined, FileTextOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { listCAPAs, createCAPA } from "../../api/capa";
import type { CAPAReport } from "../../types";
import { useProductLineStore } from "../../store/productLineStore";
import dayjs from "dayjs";

const { Title } = Typography;

const severityColors: Record<string, string> = {
  fatal: "red", serious: "orange", general: "blue", minor: "default",
};

const severityOptions = ["fatal", "serious", "general", "minor"];

export default function CAPAListPage() {
  const { t } = useTranslation("capa");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const [data, setData] = useState<CAPAReport[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const productLine = useProductLineStore((s) => s.selected);
  const [searchParams] = useSearchParams();

  const fetchData = (p: number = page) => {
    setLoading(true);
    const overdue = searchParams.get("overdue") === "true";
    const pendingAction = searchParams.get("pending_action") === "true";
    listCAPAs({
      page: p,
      page_size: 20,
      product_line: productLine || undefined,
      overdue: overdue || undefined,
      pending_action: pendingAction || undefined,
    })
      .then((res) => { setData(res.items); setTotal(res.total); })
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(1); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine, searchParams]);

  const handleCreate = async (values: { title: string; document_no: string; severity: string; due_date?: dayjs.Dayjs; problem_description?: string }) => {
    try {
      const capa = await createCAPA({
        title: values.title,
        document_no: values.document_no,
        severity: values.severity,
        due_date: values.due_date?.format("YYYY-MM-DD"),
      });
      message.success(tc("messages.operationSuccess"));
      setModalOpen(false);
      form.resetFields();
      navigate(`/capa/${capa.report_id}`, { state: { showLessonsLearned: true, problemDescription: values.problem_description } });
    } catch { message.error(tc("messages.operationFailed")); }
  };

  const columns = [
    { title: t("fields.documentNo"), dataIndex: "document_no", key: "document_no", width: 150 },
    { title: t("fields.title"), dataIndex: "title", key: "title", ellipsis: true },
    {
      title: t("fields.currentStep"), dataIndex: "status", key: "status", width: 140,
      render: (s: string) => <Tag color="processing">{t(`status.${s}`, s)}</Tag>,
    },
    {
      title: t("fields.severity"), dataIndex: "severity", key: "severity", width: 90,
      render: (s: string) => <Tag color={severityColors[s] || "default"}>{t(`severity.${s}`, s)}</Tag>,
    },
    { title: t("fields.dueDate"), dataIndex: "due_date", key: "due_date", width: 110, render: (v: string | null) => v || "-" },
    {
      title: t("fields.createdAt"), dataIndex: "updated_at", key: "updated_at", width: 170,
      render: (v: string) => new Date(v).toLocaleString(),
    },
    {
      title: tc("table.operations"), key: "actions", width: 80,
      render: (_: unknown, record: CAPAReport) => (
        <Button type="link" icon={<FileTextOutlined />} onClick={() => navigate(`/capa/${record.report_id}`)}>
          {t("actions.handle")}
        </Button>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>{t("title")}</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>{t("actions.create")}</Button>
      </div>
      <Table columns={columns} dataSource={data} rowKey="report_id" loading={loading}
        pagination={{ current: page, total, pageSize: 20, onChange: (p) => { setPage(p); fetchData(p); } }}
      />
      <Modal title={t("actions.create")} open={modalOpen} onOk={() => form.submit()} onCancel={() => setModalOpen(false)}>
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="document_no" label={t("fields.documentNo")} rules={[{ required: true }]}>
            <Input placeholder="8D-2026-001" />
          </Form.Item>
          <Form.Item name="title" label={t("fields.title")} rules={[{ required: true }]}>
            <Input placeholder={t("fields.title")} />
          </Form.Item>
          <Form.Item name="severity" label={t("fields.severity")} initialValue="general">
            <Select options={severityOptions.map((v) => ({ value: v, label: t(`severity.${v}`) }))} />
          </Form.Item>
          <Form.Item name="due_date" label={t("fields.dueDate")}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="problem_description" label={t("fields.problemDescription")}>
            <Input.TextArea rows={2} placeholder={t("fields.problemDescription")} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Table, Button, Modal, Form, Input, Select, DatePicker, App } from "antd";
import { PlusOutlined, FileTextOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { listCAPAs, createCAPA } from "../../api/capa";
import type { CAPAReport } from "../../types";
import { useProductLineStore } from "../../store/productLineStore";
import { formatDateTime } from "../../utils/dateTime";
import PageShell from "../../components/design/PageShell";
import DataCard from "../../components/design/DataCard";
import StatusBadge from "../../components/design/StatusBadge";
import dayjs from "dayjs";

const statusLabels: Record<string, string> = {
  D1_TEAM: "D1 团队组建", D2_DESCRIPTION: "D2 问题描述",
  D3_INTERIM: "D3 临时措施", D4_ROOT_CAUSE: "D4 根因分析",
  D5_CORRECTION: "D5 永久措施", D6_VERIFICATION: "D6 实施验证",
  D7_PREVENTION: "D7 预防复发", D8_CLOSURE: "D8 关闭", ARCHIVED: "已归档",
};

const statusVariant = (s: string): string => {
  if (["D8_CLOSURE", "ARCHIVED"].includes(s)) return "success";
  if (s === "OVERDUE") return "error";
  return "warning";
};

const severityVariant = (s: string): string => {
  if (s === "致命") return "error";
  if (s === "严重") return "warning";
  if (s === "轻微") return "info";
  return "info";
};

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
      message.success(tc("messages.operationSuccess", "8D 报告创建成功"));
      setModalOpen(false);
      form.resetFields();
      navigate(`/capa/${capa.report_id}`, { state: { showLessonsLearned: true, problemDescription: values.problem_description } });
    } catch { message.error(tc("messages.operationFailed", "创建失败")); }
  };

  const columns = [
    { title: t("fields.documentNo", "报告编号"), dataIndex: "document_no", key: "document_no", width: 150 },
    { title: t("fields.title", "标题"), dataIndex: "title", key: "title", ellipsis: true },
    {
      title: t("fields.currentStep", "当前步骤"), dataIndex: "status", key: "status", width: 140,
      render: (s: string) => <StatusBadge status={statusVariant(s)}>{statusLabels[s] || s}</StatusBadge>,
    },
    {
      title: t("fields.severity", "严重等级"), dataIndex: "severity", key: "severity", width: 90,
      render: (s: string) => <StatusBadge status={severityVariant(s)}>{s}</StatusBadge>,
    },
    { title: t("fields.dueDate", "期限"), dataIndex: "due_date", key: "due_date", width: 110, render: (v: string | null) => v || "-" },
    {
      title: t("fields.createdAt", "更新时间"), dataIndex: "updated_at", key: "updated_at", width: 170,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: tc("table.operations", "操作"), key: "actions", width: 80,
      render: (_: unknown, record: CAPAReport) => (
        <Button type="link" icon={<FileTextOutlined />} onClick={() => navigate(`/capa/${record.report_id}`)}>
          {t("actions.handle", "处理")}
        </Button>
      ),
    },
  ];

  return (
    <PageShell
      title={t("title", "8D / CAPA")}
      subtitle={t("subtitle", "客诉与质量问题闭环追踪")}
      actions={
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>{t("actions.create", "新建 8D")}</Button>
      }
    >
      <DataCard title={t("listTitle", "8D 报告列表")} noPadding>
        <Table className="qf-table" columns={columns} dataSource={data} rowKey="report_id" loading={loading}
          pagination={{ current: page, total, pageSize: 20, onChange: (p) => { setPage(p); fetchData(p); } }}
        />
      </DataCard>
      <Modal title={t("actions.create", "新建 8D 报告")} open={modalOpen} onOk={() => form.submit()} onCancel={() => setModalOpen(false)}>
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="document_no" label={t("fields.documentNo", "报告编号")} rules={[{ required: true }]}>
            <Input placeholder="如 8D-2026-001" />
          </Form.Item>
          <Form.Item name="title" label={t("fields.title", "标题")} rules={[{ required: true }]}>
            <Input placeholder="如 焊接不良客诉" />
          </Form.Item>
          <Form.Item name="severity" label={t("fields.severity", "严重等级")} initialValue="一般">
            <Select options={["致命", "严重", "一般", "轻微"].map((v) => ({ value: v, label: v }))} />
          </Form.Item>
          <Form.Item name="due_date" label={t("fields.dueDate", "完成期限")}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="problem_description" label={t("fields.problemDescription", "问题描述（可选）")}>
            <Input.TextArea rows={2} placeholder="简述问题现象（可选，用于智能推荐）" />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}

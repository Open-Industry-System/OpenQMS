import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Table, Button, Modal, Form, Input, Select, DatePicker, App } from "antd";
import { PlusOutlined, FileTextOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { listCAPAs, createCAPA, listCapaSupplierOptions } from "../../api/capa";
import type { CAPAReport } from "../../types";
import { useProductLineStore } from "../../store/productLineStore";
import { usePermission } from "../../hooks/usePermission";
import { formatDateTime } from "../../utils/dateTime";
import PageShell from "../../components/design/PageShell";
import DataCard from "../../components/design/DataCard";
import StatusBadge from "../../components/design/StatusBadge";
import dayjs from "dayjs";

export default function CAPAListPage() {
  const { t } = useTranslation("capa");
  const { t: tc } = useTranslation("common");

  const statusLabels: Record<string, string> = {
    D1_TEAM: t("status.D1_TEAM"), D2_DESCRIPTION: t("status.D2_DESCRIPTION"),
    D3_INTERIM: t("status.D3_INTERIM"), D4_ROOT_CAUSE: t("status.D4_ROOT_CAUSE"),
    D5_CORRECTION: t("status.D5_CORRECTION"), D6_VERIFICATION: t("status.D6_VERIFICATION"),
    D7_PREVENTION: t("status.D7_PREVENTION"), D7_COMPLETED: t("status.D7_COMPLETED"),
    D8_GATE_PENDING: t("status.D8_GATE_PENDING"), D8_APPROVAL_PENDING: t("status.D8_APPROVAL_PENDING"),
    D8_CLOSURE: t("status.D8_CLOSURE"), ARCHIVED: t("status.ARCHIVED"),
  };

  const statusVariant = (s: string): string => {
    // StatusBadge 的 status 输入是 *alias 字符串*，经内部 switch 映射到 variant（success/warning/error/info/draft）。
    // 认识的 alias：success 类=approved/closed/done/completed/ok/pass；warning 类=in_review/rework/pending/processing/open；
    // error 类=high/fatal/critical/error/failed/reject/overdue；info 类=medium/normal/info。
    // 直接传 "success"/"warning" 不命中任何 case → 落 draft 变体。故返回 alias，而非 variant 名。
    if (["D8_CLOSURE", "ARCHIVED"].includes(s)) return "done";        // → success
    if (s === "D8_APPROVAL_PENDING") return "pending";                // → warning（待审批高亮）
    if (s === "OVERDUE") return "overdue";                            // → error
    if (["D7_COMPLETED", "D8_GATE_PENDING"].includes(s)) return "info";  // → info（进行中）
    return "processing";                                              // → warning（D1-D7 默认进行中）
  };

  const severityKeyToVariant: Record<string, string> = {
    fatal: "error", serious: "warning", general: "info", minor: "info",
  };
  const severityVariant = (s: string): string => {
    const keyMap: Record<string, string> = { "致命": "fatal", "严重": "serious", "一般": "general", "轻微": "minor" };
    return severityKeyToVariant[keyMap[s] || s] || "info";
  };
  const { message } = App.useApp();
  const [data, setData] = useState<CAPAReport[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [suppliers, setSuppliers] = useState<Array<{ supplier_id: string; supplier_no: string; name: string }>>([]);
  const [supplierLoadError, setSupplierLoadError] = useState<string | null>(null);
  const supplierSearchSeq = useRef(0);
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const productLine = useProductLineStore((s) => s.selected);
  const { canEdit } = usePermission();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    // Prefetch first page so the dropdown is non-empty; further options load via remote search.
    listCapaSupplierOptions({ page_size: 50 })
      .then((res) => {
        setSuppliers(res.items);
        setSupplierLoadError(null);
      })
      .catch(() => {
        setSuppliers([]);
        setSupplierLoadError(t("fields.supplierLoadFailed"));
      });
  }, [t]);

  const searchSuppliers = async (q: string) => {
    const seq = ++supplierSearchSeq.current;
    try {
      const res = await listCapaSupplierOptions({
        page_size: 50,
        search: q?.trim() || undefined,
      });
      // Drop stale responses (earlier request finished later).
      if (seq !== supplierSearchSeq.current) return;
      setSuppliers(res.items);
      setSupplierLoadError(null);
    } catch {
      if (seq !== supplierSearchSeq.current) return;
      // Keep existing options; surface error only if list is empty.
      if (suppliers.length === 0) {
        setSupplierLoadError(t("fields.supplierLoadFailed"));
      }
    }
  };

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

  const handleCreate = async (values: { title: string; document_no: string; severity: string; due_date?: dayjs.Dayjs; problem_description?: string; supplier_id?: string | null }) => {
    try {
      const payload: Parameters<typeof createCAPA>[0] = {
        title: values.title,
        document_no: values.document_no,
        severity: values.severity,
        due_date: values.due_date?.format("YYYY-MM-DD"),
        product_line_code: productLine || undefined,
        supplier_id: values.supplier_id || null,
      };
      const capa = await createCAPA(payload);
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
      render: (s: string) => <StatusBadge status={statusVariant(s)}>{statusLabels[s] || s}</StatusBadge>,
    },
    {
      title: t("fields.severity"), dataIndex: "severity", key: "severity", width: 90,
      render: (s: string) => <StatusBadge status={severityVariant(s)}>{s}</StatusBadge>,
    },
    { title: t("fields.dueDate"), dataIndex: "due_date", key: "due_date", width: 110, render: (v: string | null) => v || "-" },
    {
      title: t("fields.createdAt"), dataIndex: "updated_at", key: "updated_at", width: 170,
      render: (v: string) => formatDateTime(v),
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
    <PageShell
      title={t("title", "8D / CAPA")}
      subtitle={t("subtitle")}
      actions={
        canEdit("capa") ? (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)} data-e2e="capa-create">{t("actions.create")}</Button>
        ) : undefined
      }
    >
      <DataCard title={t("listTitle")} noPadding>
        <Table className="qf-table" columns={columns} dataSource={data} rowKey="report_id" loading={loading}
          onRow={(record) => ({ 'data-e2e': `row-${record.document_no}` } as any)}
          pagination={{ current: page, total, pageSize: 20, onChange: (p) => { setPage(p); fetchData(p); } }}
        />
      </DataCard>
      <Modal title={t("actions.create")} open={modalOpen} onOk={() => form.submit()} onCancel={() => setModalOpen(false)}>
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="document_no" label={t("fields.documentNo")} rules={[{ required: true }]}>
            <Input placeholder={t("fields.documentNoPlaceholder")} />
          </Form.Item>
          <Form.Item name="title" label={t("fields.title")} rules={[{ required: true }]}>
            <Input placeholder={t("fields.titlePlaceholder")} />
          </Form.Item>
          <Form.Item name="severity" label={t("fields.severity")} initialValue="一般">
            <Select options={[
                    { value: "致命", label: t("severity.fatal") },
                    { value: "严重", label: t("severity.serious") },
                    { value: "一般", label: t("severity.general") },
                    { value: "轻微", label: t("severity.minor") },
                  ]} />
          </Form.Item>
          <Form.Item name="due_date" label={t("fields.dueDate")}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item
            name="supplier_id"
            label={t("fields.supplier")}
            extra={supplierLoadError || undefined}
          >
            <Select
              allowClear
              showSearch
              filterOption={false}
              onSearch={searchSuppliers}
              disabled={!!supplierLoadError}
              placeholder={
                supplierLoadError
                  ? supplierLoadError
                  : t("fields.supplierPlaceholder")
              }
              options={suppliers.map((s) => ({ value: s.supplier_id, label: `${s.supplier_no} - ${s.name}` }))}
            />
          </Form.Item>
          <Form.Item name="problem_description" label={t("fields.problemDescription")}>
            <Input.TextArea rows={2} placeholder={t("fields.problemDescriptionPlaceholder")} />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}

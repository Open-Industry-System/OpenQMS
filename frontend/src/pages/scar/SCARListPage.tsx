import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Table, Tabs, Button, Select, Space, Modal, Form, Input, DatePicker, message } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { listSCARs, createSCAR } from "../../api/scar";
import { listSuppliers } from "../../api/supplier";
import type { SupplierSCAR, SCARListResponse, Supplier } from "../../types";
import PageShell from "../../components/design/PageShell";
import DataCard from "../../components/design/DataCard";
import StatusBadge from "../../components/design/StatusBadge";

const STATUS_TABS = ["all", "pending", "responded", "verified", "closed"];

const STATUS_MAP: Record<string, string | undefined> = {
  all: undefined,
  pending: "open,in_progress",
  responded: "responded",
  verified: "verified",
  closed: "closed",
};

export const STATUS_COLORS: Record<string, string> = {
  open: "default",
  in_progress: "processing",
  responded: "warning",
  verified: "success",
  closed: "default",
};

const statusVariant = (s: string): string => {
  if (["verified", "closed"].includes(s)) return "success";
  if (["responded", "in_progress"].includes(s)) return "warning";
  return "info";
};

export default function SCARListPage() {
  const { t } = useTranslation("scar");
  const { t: tc } = useTranslation("common");
  const navigate = useNavigate();
  const [data, setData] = useState<SCARListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("all");
  const [sourceType, setSourceType] = useState<string | undefined>();
  const [supplierId, setSupplierId] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [form] = Form.useForm();

  const loadData = async () => {
    setLoading(true);
    try {
      const result = await listSCARs({
        page,
        page_size: 20,
        status: STATUS_MAP[activeTab],
        source_type: sourceType,
        supplier_id: supplierId,
      });
      setData(result);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, sourceType, supplierId, page]);

  const handleCreate = async (values: Record<string, unknown>) => {
    await createSCAR({
      supplier_id: values.supplier_id as string,
      source_type: "manual",
      description: values.description as string,
      requested_action: values.requested_action as string | undefined,
      due_date: values.due_date ? (values.due_date as { format: (f: string) => string }).format("YYYY-MM-DD") : undefined,
    });
    message.success(t("messages.createSuccess"));
    setCreateOpen(false);
    form.resetFields();
    loadData();
  };

  const columns = [
    { title: t("table.scarNo"), dataIndex: "scar_no", key: "scar_no" },
    { title: t("table.supplier"), dataIndex: "supplier_name", key: "supplier_name", render: (v: string) => v || "-" },
    {
      title: t("table.source"),
      dataIndex: "source_type",
      key: "source_type",
      render: (v: string) => t(`source.${v}`, { defaultValue: v }),
    },
    {
      title: t("table.status"),
      dataIndex: "status",
      key: "status",
      render: (s: string) => <StatusBadge status={statusVariant(s)}>{t(`status.${s}`, { defaultValue: s })}</StatusBadge>,
    },
    { title: t("table.issuedDate"), dataIndex: "issued_date", key: "issued_date" },
    { title: t("table.dueDate"), dataIndex: "due_date", key: "due_date", render: (v: string) => v || "-" },
    {
      title: t("table.operations"),
      key: "action",
      render: (_: unknown, record: SupplierSCAR) => (
        <Button type="link" onClick={() => navigate(`/scars/${record.scar_id}`)}>
          {tc("actions.view")}
        </Button>
      ),
    },
  ];

  return (
    <PageShell
      title={t("pageTitle.list")}
      subtitle={t("pageTitle.subtitle")}
      actions={
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          {t("actions.newScar")}
        </Button>
      }
    >
      <DataCard title={t("card.list")}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
          <Tabs activeKey={activeTab} onChange={setActiveTab} items={STATUS_TABS.map(key => ({ key, label: t(`tabs.${key}`) }))} />
          <Space>
            <Select
              allowClear
              showSearch
              filterOption={false}
              placeholder={t("table.supplier")}
              style={{ width: 160 }}
              onSearch={async (search) => {
                const res = await listSuppliers({ search, page_size: 20 });
                setSuppliers(res.items);
              }}
              onChange={(v) => { setSupplierId(v); setPage(1); }}
              options={suppliers.map((s) => ({ value: s.supplier_id, label: s.name }))}
            />
            <Select
              allowClear
              placeholder={t("table.source")}
              style={{ width: 120 }}
              onChange={(v) => { setSourceType(v); setPage(1); }}
              options={[
                { value: "iqc", label: t("source.iqc") },
                { value: "complaint", label: t("source.complaint") },
                { value: "rma", label: t("source.rma", "RMA") },
                { value: "manual", label: t("source.manual") },
              ]}
            />
          </Space>
        </div>

        <Table
          className="qf-table"
          dataSource={data?.items || []}
          columns={columns}
          rowKey="scar_id"
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
        title={t("actions.newScar")}
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="supplier_id" label={t("descriptions.supplier")} rules={[{ required: true, message: t("validation.supplierRequired") }]}>
            <Select
              showSearch
              filterOption={false}
              onSearch={async (search) => {
                const res = await listSuppliers({ search, page_size: 20 });
                setSuppliers(res.items);
              }}
              options={suppliers.map((s) => ({ value: s.supplier_id, label: `${s.supplier_no} - ${s.name}` }))}
              placeholder={t("table.supplier")}
            />
          </Form.Item>
          <Form.Item name="description" label={t("descriptions.description")} rules={[{ required: true, message: t("validation.descriptionRequired") }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="requested_action" label={t("descriptions.requestedAction")}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="due_date" label={t("descriptions.dueDate")}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}

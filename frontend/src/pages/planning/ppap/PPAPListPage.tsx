import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Table, Tag, Tabs, Button, Select, Space, Modal, Form, Input, InputNumber, message, Card, Row, Col } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { listPPAPs, createPPAP } from "../../../api/ppap";
import { listSuppliers } from "../../../api/supplier";
import type { PPAPSubmission, PPAPListResponse, Supplier } from "../../../types";

const STATUS_MAP: Record<string, string | undefined> = {
  all: undefined,
  draft: "draft",
  under_review: "under_review",
  approved: "approved",
  rejected: "rejected",
};

export function usePPAPLabels(t: (key: string) => string) {
  const statusTabs = [
    { key: "all", label: t("tab.all") },
    { key: "draft", label: t("tab.draft") },
    { key: "under_review", label: t("tab.underReview") },
    { key: "approved", label: t("tab.approved") },
    { key: "rejected", label: t("tab.rejected") },
  ];

  const statusColors: Record<string, string> = {
    draft: "default",
    under_review: "processing",
    approved: "success",
    rejected: "error",
  };

  const statusLabels: Record<string, string> = {
    draft: t("status.draft"),
    under_review: t("status.underReview"),
    approved: t("status.approved"),
    rejected: t("status.rejected"),
  };

  const levelLabels: Record<number, string> = {
    1: t("level.1"),
    2: t("level.2"),
    3: t("level.3"),
    4: t("level.4"),
    5: t("level.5"),
  };

  return { statusTabs, statusColors, statusLabels, levelLabels };
}

export default function PPAPListPage() {
  const { t } = useTranslation("ppap");
  const { t: tc } = useTranslation("common");
  const navigate = useNavigate();
  const [data, setData] = useState<PPAPListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("all");
  const [supplierId, setSupplierId] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [form] = Form.useForm();
  const [kpis, setKpis] = useState({ total: 0, pending: 0, approved: 0, rejected: 0 });

  const { statusTabs, statusColors, statusLabels, levelLabels } = usePPAPLabels(t);

  const loadData = async () => {
    setLoading(true);
    try {
      const result = await listPPAPs({ page, page_size: 20, status: STATUS_MAP[activeTab], supplier_id: supplierId });
      setData(result);
      // Load KPI counts in parallel
      const [all, draftR, underReviewR, approvedR, rejectedR] = await Promise.all([
        listPPAPs({ page: 1, page_size: 1 }),
        listPPAPs({ page: 1, page_size: 1, status: "draft" }),
        listPPAPs({ page: 1, page_size: 1, status: "under_review" }),
        listPPAPs({ page: 1, page_size: 1, status: "approved" }),
        listPPAPs({ page: 1, page_size: 1, status: "rejected" }),
      ]);
      setKpis({ total: all.total, pending: draftR.total + underReviewR.total, approved: approvedR.total, rejected: rejectedR.total });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, supplierId, page]);

  const handleCreate = async (values: Record<string, unknown>) => {
    await createPPAP({
      supplier_id: values.supplier_id as string,
      part_no: values.part_no as string,
      part_name: values.part_name as string,
      submission_level: (values.submission_level as number) || 3,
      customer_name: values.customer_name as string | undefined,
    });
    message.success(t("message.createSuccess"));
    setCreateOpen(false);
    form.resetFields();
    loadData();
  };

  const columns = [
    { title: t("column.ppapNo"), dataIndex: "ppap_no", key: "ppap_no" },
    { title: t("column.supplier"), dataIndex: "supplier_name", key: "supplier_name", render: (v: string | null) => v || "-" },
    { title: t("column.partNo"), dataIndex: "part_no", key: "part_no" },
    { title: t("column.partName"), dataIndex: "part_name", key: "part_name" },
    {
      title: t("column.submissionLevel"),
      dataIndex: "submission_level",
      key: "submission_level",
      render: (v: number) => <Tag>{levelLabels[v] || v}</Tag>,
    },
    {
      title: t("column.status"),
      dataIndex: "status",
      key: "status",
      render: (s: string) => <Tag color={statusColors[s]}>{statusLabels[s] || s}</Tag>,
    },
    { title: t("column.revision"), dataIndex: "revision", key: "revision" },
    { title: t("column.createdAt"), dataIndex: "created_at", key: "created_at", render: (v: string) => v?.split("T")[0] || "-" },
    {
      title: t("column.action"),
      key: "action",
      render: (_: unknown, record: PPAPSubmission) => (
        <Button type="link" onClick={() => navigate(`/ppap/${record.submission_id}`)}>
          {tc("actions.view")}
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card size="small"><div style={{ color: "#999" }}>{t("kpi.total")}</div><div style={{ fontSize: 24, fontWeight: 600 }}>{kpis.total}</div></Card></Col>
        <Col span={6}><Card size="small"><div style={{ color: "#999" }}>{t("kpi.pending")}</div><div style={{ fontSize: 24, fontWeight: 600, color: "#1677ff" }}>{kpis.pending}</div></Card></Col>
        <Col span={6}><Card size="small"><div style={{ color: "#999" }}>{t("kpi.approved")}</div><div style={{ fontSize: 24, fontWeight: 600, color: "#52c41a" }}>{kpis.approved}</div></Card></Col>
        <Col span={6}><Card size="small"><div style={{ color: "#999" }}>{t("kpi.rejected")}</div><div style={{ fontSize: 24, fontWeight: 600, color: "#ff4d4f" }}>{kpis.rejected}</div></Card></Col>
      </Row>

      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={statusTabs} />
        <Space>
          <Select
            allowClear
            showSearch
            filterOption={false}
            placeholder={t("placeholder.searchSupplier")}
            style={{ width: 160 }}
            onSearch={async (search) => {
              const res = search ? await listSuppliers({ search, page_size: 20 }) : await listSuppliers({ page_size: 20 });
              setSuppliers(res.items);
            }}
            onChange={(v) => { setSupplierId(v); setPage(1); }}
            options={suppliers.map((s) => ({ value: s.supplier_id, label: s.name }))}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            {t("pageTitle.newPPAP")}
          </Button>
        </Space>
      </div>

      <Table
        dataSource={data?.items || []}
        columns={columns}
        rowKey="submission_id"
        loading={loading}
        pagination={{
          current: page,
          pageSize: 20,
          total: data?.total || 0,
          onChange: setPage,
        }}
      />

      <Modal
        title={t("pageTitle.newPPAP")}
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={handleCreate} initialValues={{ submission_level: 3 }}>
          <Form.Item name="supplier_id" label={t("form.supplier")} rules={[{ required: true, message: t("message.selectSupplier") }]}>
            <Select
              showSearch
              filterOption={false}
              onSearch={async (search) => {
                const res = search ? await listSuppliers({ search, page_size: 20 }) : await listSuppliers({ page_size: 20 });
                setSuppliers(res.items);
              }}
              options={suppliers.map((s) => ({ value: s.supplier_id, label: `${s.supplier_no} - ${s.name}` }))}
              placeholder={t("placeholder.searchSupplier")}
            />
          </Form.Item>
          <Form.Item name="part_no" label={t("form.partNo")} rules={[{ required: true, message: t("message.enterPartNo") }]}>
            <Input />
          </Form.Item>
          <Form.Item name="part_name" label={t("form.partName")} rules={[{ required: true, message: t("message.enterPartName") }]}>
            <Input />
          </Form.Item>
          <Form.Item name="submission_level" label={t("form.submissionLevel")} rules={[{ required: true }]}>
            <InputNumber min={1} max={5} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="customer_name" label={t("form.customerName")}>
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

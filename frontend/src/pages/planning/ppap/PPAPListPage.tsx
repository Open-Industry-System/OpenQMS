import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Table, Tag, Tabs, Button, Select, Space, Modal, Form, Input, InputNumber, message, Card, Row, Col } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { listPPAPs, createPPAP } from "../../../api/ppap";
import { listSuppliers } from "../../../api/supplier";
import type { PPAPSubmission, PPAPListResponse, Supplier } from "../../../types";

const STATUS_TABS = [
  { key: "all", label: "全部" },
  { key: "draft", label: "草稿" },
  { key: "under_review", label: "审查中" },
  { key: "approved", label: "已批准" },
  { key: "rejected", label: "已驳回" },
];

const STATUS_MAP: Record<string, string | undefined> = {
  all: undefined,
  draft: "draft",
  under_review: "under_review",
  approved: "approved",
  rejected: "rejected",
};

export const STATUS_COLORS: Record<string, string> = {
  draft: "default",
  under_review: "processing",
  approved: "success",
  rejected: "error",
};

export const STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  under_review: "审查中",
  approved: "已批准",
  rejected: "已驳回",
};

export const LEVEL_LABELS: Record<number, string> = {
  1: "Level 1",
  2: "Level 2",
  3: "Level 3",
  4: "Level 4",
  5: "Level 5",
};

export default function PPAPListPage() {
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

  useEffect(() => { loadData(); }, [activeTab, supplierId, page]);

  const handleCreate = async (values: Record<string, unknown>) => {
    await createPPAP({
      supplier_id: values.supplier_id as string,
      part_no: values.part_no as string,
      part_name: values.part_name as string,
      submission_level: (values.submission_level as number) || 3,
      customer_name: values.customer_name as string | undefined,
    });
    message.success("PPAP 创建成功");
    setCreateOpen(false);
    form.resetFields();
    loadData();
  };

  const columns = [
    { title: "PPAP编号", dataIndex: "ppap_no", key: "ppap_no" },
    { title: "供应商", dataIndex: "supplier_name", key: "supplier_name", render: (v: string | null) => v || "-" },
    { title: "零件号", dataIndex: "part_no", key: "part_no" },
    { title: "零件名称", dataIndex: "part_name", key: "part_name" },
    {
      title: "提交等级",
      dataIndex: "submission_level",
      key: "submission_level",
      render: (v: number) => <Tag>{LEVEL_LABELS[v] || v}</Tag>,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (s: string) => <Tag color={STATUS_COLORS[s]}>{STATUS_LABELS[s] || s}</Tag>,
    },
    { title: "版本", dataIndex: "revision", key: "revision" },
    { title: "创建时间", dataIndex: "created_at", key: "created_at", render: (v: string) => v?.split("T")[0] || "-" },
    {
      title: "操作",
      key: "action",
      render: (_: unknown, record: PPAPSubmission) => (
        <Button type="link" onClick={() => navigate(`/ppap/${record.submission_id}`)}>
          查看
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card size="small"><div style={{ color: "#999" }}>PPAP 总数</div><div style={{ fontSize: 24, fontWeight: 600 }}>{kpis.total}</div></Card></Col>
        <Col span={6}><Card size="small"><div style={{ color: "#999" }}>待审</div><div style={{ fontSize: 24, fontWeight: 600, color: "#1677ff" }}>{kpis.pending}</div></Card></Col>
        <Col span={6}><Card size="small"><div style={{ color: "#999" }}>已批准</div><div style={{ fontSize: 24, fontWeight: 600, color: "#52c41a" }}>{kpis.approved}</div></Card></Col>
        <Col span={6}><Card size="small"><div style={{ color: "#999" }}>已驳回</div><div style={{ fontSize: 24, fontWeight: 600, color: "#ff4d4f" }}>{kpis.rejected}</div></Card></Col>
      </Row>

      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={STATUS_TABS} />
        <Space>
          <Select
            allowClear
            showSearch
            filterOption={false}
            placeholder="筛选供应商"
            style={{ width: 160 }}
            onSearch={async (search) => {
              const res = search ? await listSuppliers({ search, page_size: 20 }) : await listSuppliers({ page_size: 20 });
              setSuppliers(res.items);
            }}
            onChange={(v) => { setSupplierId(v); setPage(1); }}
            options={suppliers.map((s) => ({ value: s.supplier_id, label: s.name }))}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新建 PPAP
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
        title="新建 PPAP"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleCreate} initialValues={{ submission_level: 3 }}>
          <Form.Item name="supplier_id" label="供应商" rules={[{ required: true, message: "请选择供应商" }]}>
            <Select
              showSearch
              filterOption={false}
              onSearch={async (search) => {
                const res = search ? await listSuppliers({ search, page_size: 20 }) : await listSuppliers({ page_size: 20 });
                setSuppliers(res.items);
              }}
              options={suppliers.map((s) => ({ value: s.supplier_id, label: `${s.supplier_no} - ${s.name}` }))}
              placeholder="搜索供应商"
            />
          </Form.Item>
          <Form.Item name="part_no" label="零件号" rules={[{ required: true, message: "请输入零件号" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="part_name" label="零件名称" rules={[{ required: true, message: "请输入零件名称" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="submission_level" label="提交等级" rules={[{ required: true }]}>
            <InputNumber min={1} max={5} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="customer_name" label="客户名称">
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

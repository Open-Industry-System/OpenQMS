import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Table, Tag, Tabs, Button, Select, Space, Modal, Form, Input, DatePicker, message } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { listSCARs, createSCAR } from "../../api/scar";
import { listSuppliers } from "../../api/supplier";
import type { SupplierSCAR, SCARListResponse, Supplier } from "../../types";

const STATUS_TABS = [
  { key: "all", label: "全部" },
  { key: "pending", label: "待处理" },
  { key: "responded", label: "已回复" },
  { key: "verified", label: "已验证" },
  { key: "closed", label: "已关闭" },
];

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

export const STATUS_LABELS: Record<string, string> = {
  open: "待处理",
  in_progress: "处理中",
  responded: "已回复",
  verified: "已验证",
  closed: "已关闭",
};

export const SOURCE_LABELS: Record<string, string> = {
  iqc: "IQC拒收",
  complaint: "客诉",
  rma: "RMA",
  manual: "手动创建",
};

export default function SCARListPage() {
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
    message.success("SCAR 创建成功");
    setCreateOpen(false);
    form.resetFields();
    loadData();
  };

  const columns = [
    { title: "SCAR编号", dataIndex: "scar_no", key: "scar_no" },
    { title: "供应商", dataIndex: "supplier_name", key: "supplier_name", render: (v: string) => v || "-" },
    {
      title: "来源",
      dataIndex: "source_type",
      key: "source_type",
      render: (v: string) => SOURCE_LABELS[v] || v,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (s: string) => <Tag color={STATUS_COLORS[s]}>{STATUS_LABELS[s] || s}</Tag>,
    },
    { title: "发出日期", dataIndex: "issued_date", key: "issued_date" },
    { title: "到期日", dataIndex: "due_date", key: "due_date", render: (v: string) => v || "-" },
    {
      title: "操作",
      key: "action",
      render: (_: unknown, record: SupplierSCAR) => (
        <Button type="link" onClick={() => navigate(`/scars/${record.scar_id}`)}>
          查看
        </Button>
      ),
    },
  ];

  return (
    <div>
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
              const res = await listSuppliers({ search, page_size: 20 });
              setSuppliers(res.items);
            }}
            onChange={(v) => { setSupplierId(v); setPage(1); }}
            options={suppliers.map((s) => ({ value: s.supplier_id, label: s.name }))}
          />
          <Select
            allowClear
            placeholder="来源类型"
            style={{ width: 120 }}
            onChange={(v) => { setSourceType(v); setPage(1); }}
            options={[
              { value: "iqc", label: "IQC拒收" },
              { value: "complaint", label: "客诉" },
              { value: "rma", label: "RMA" },
              { value: "manual", label: "手动创建" },
            ]}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新建 SCAR
          </Button>
        </Space>
      </div>

      <Table
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

      <Modal
        title="新建 SCAR"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="supplier_id" label="供应商" rules={[{ required: true, message: "请选择供应商" }]}>
            <Select
              showSearch
              filterOption={false}
              onSearch={async (search) => {
                const res = await listSuppliers({ search, page_size: 20 });
                setSuppliers(res.items);
              }}
              options={suppliers.map((s) => ({ value: s.supplier_id, label: `${s.supplier_no} - ${s.name}` }))}
              placeholder="搜索供应商"
            />
          </Form.Item>
          <Form.Item name="description" label="问题描述" rules={[{ required: true, message: "请输入问题描述" }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="requested_action" label="要求措施">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="due_date" label="到期日">
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Table, Button, Tag, Typography, Modal, Form, Input, message } from "antd";
import { PlusOutlined, FileTextOutlined } from "@ant-design/icons";
import { listFMEAs, createFMEA } from "../../api/fmea";
import type { FMEADocument } from "../../types";

const { Title } = Typography;

const statusColors: Record<string, string> = {
  draft: "default",
  in_review: "processing",
  approved: "success",
  rework: "warning",
  archived: "default",
};

const statusLabels: Record<string, string> = {
  draft: "草稿",
  in_review: "审核中",
  approved: "已批准",
  rework: "返工中",
  archived: "已归档",
};

export default function FMEAListPage() {
  const [data, setData] = useState<FMEADocument[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const navigate = useNavigate();

  const fetchData = (p: number = page) => {
    setLoading(true);
    listFMEAs({ page: p, page_size: 20 })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleCreate = async (values: { title: string; document_no: string }) => {
    try {
      const fmea = await createFMEA({ ...values, fmea_type: "PFMEA" });
      message.success("FMEA 创建成功");
      setModalOpen(false);
      form.resetFields();
      navigate(`/fmea/${fmea.fmea_id}`);
    } catch {
      message.error("创建失败");
    }
  };

  const columns = [
    { title: "文档编号", dataIndex: "document_no", key: "document_no", width: 150 },
    { title: "标题", dataIndex: "title", key: "title", ellipsis: true },
    { title: "类型", dataIndex: "fmea_type", key: "fmea_type", width: 80 },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (s: string) => <Tag color={statusColors[s] || "default"}>{statusLabels[s] || s}</Tag>,
    },
    { title: "版本", dataIndex: "version", key: "version", width: 60, render: (v: number) => `v${v}` },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      key: "updated_at",
      width: 180,
      render: (v: string) => new Date(v).toLocaleString("zh-CN"),
    },
    {
      title: "操作",
      key: "actions",
      width: 100,
      render: (_: unknown, record: FMEADocument) => (
        <Button type="link" icon={<FileTextOutlined />} onClick={() => navigate(`/fmea/${record.fmea_id}`)}>
          编辑
        </Button>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>FMEA 管理</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
          新建 PFMEA
        </Button>
      </div>

      <Table
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
        title="新建 PFMEA"
        open={modalOpen}
        onOk={() => form.submit()}
        onCancel={() => setModalOpen(false)}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="document_no" label="文档编号" rules={[{ required: true, message: "请输入文档编号" }]}>
            <Input placeholder="如 PFMEA-2026-001" />
          </Form.Item>
          <Form.Item name="title" label="标题" rules={[{ required: true, message: "请输入标题" }]}>
            <Input placeholder="如 SMT焊接工序PFMEA" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

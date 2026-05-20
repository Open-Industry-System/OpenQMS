import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Table, Button, Tag, Typography, Modal, Form, Input, Select, message } from "antd";
import { PlusOutlined, FileTextOutlined } from "@ant-design/icons";
import { listFMEAs, createFMEA, updateFMEA } from "../../api/fmea";
import type { FMEADocument, GraphNode, GraphEdge } from "../../types";
import GenerationWizard from "../../components/dfmea/GenerationWizard";
import { useAuthStore } from "../../store/authStore";

const { Title } = Typography;

const statusColors: Record<string, string> = {
  draft: "default",
  in_review: "processing",
  approved: "success",
  rework: "warning",
  archived: "default",
};

const typeLabels: Record<string, string> = {
  PFMEA: "PFMEA",
  DFMEA: "DFMEA",
};

const typeColors: Record<string, string> = {
  PFMEA: "blue",
  DFMEA: "green",
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
  const [wizardOpen, setWizardOpen] = useState(false);
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const canEdit = user?.role !== "viewer";

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

  const handleCreate = async (values: { title: string; document_no: string; fmea_type: string }) => {
    if (values.fmea_type === "DFMEA") {
      setModalOpen(false);
      setWizardOpen(true);
      return;
    }
    try {
      const fmea = await createFMEA(values);
      message.success("FMEA 创建成功");
      setModalOpen(false);
      form.resetFields();
      navigate(`/fmea/${fmea.fmea_id}`);
    } catch {
      message.error("创建失败");
    }
  };

  const handleWizardComplete = async (skeleton: { nodes: GraphNode[]; edges: GraphEdge[] }) => {
    try {
      const fmea = await createFMEA({
        title: form.getFieldValue("title") || "新DFMEA",
        document_no: form.getFieldValue("document_no") || `DFMEA-${new Date().getFullYear()}-${String(Math.floor(Math.random() * 1000)).padStart(3, "0")}`,
        fmea_type: "DFMEA",
      });
      await updateFMEA(fmea.fmea_id, {
        graph_data: { nodes: skeleton.nodes, edges: skeleton.edges },
      });
      message.success("DFMEA 创建成功");
      setWizardOpen(false);
      form.resetFields();
      navigate(`/fmea/${fmea.fmea_id}`);
    } catch {
      message.error("创建失败");
    }
  };

  const columns = [
    { title: "文档编号", dataIndex: "document_no", key: "document_no", width: 150 },
    { title: "标题", dataIndex: "title", key: "title", ellipsis: true },
    {
      title: "类型",
      dataIndex: "fmea_type",
      key: "fmea_type",
      width: 80,
      render: (t: string) => <Tag color={typeColors[t] || "default"}>{typeLabels[t] || t}</Tag>,
    },
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
        {canEdit && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
            新建 FMEA
          </Button>
        )}
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
        title="新建 FMEA"
        open={modalOpen}
        onOk={() => form.submit()}
        onCancel={() => setModalOpen(false)}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate} initialValues={{ fmea_type: "PFMEA" }}>
          <Form.Item name="fmea_type" label="FMEA 类型" rules={[{ required: true, message: "请选择 FMEA 类型" }]}>
            <Select
              options={[
                { value: "PFMEA", label: "PFMEA - 过程失效模式分析" },
                { value: "DFMEA", label: "DFMEA - 设计失效模式分析" },
              ]}
            />
          </Form.Item>
          <Form.Item name="document_no" label="文档编号" rules={[{ required: true, message: "请输入文档编号" }]}>
            <Input placeholder="如 PFMEA-2026-001" />
          </Form.Item>
          <Form.Item name="title" label="标题" rules={[{ required: true, message: "请输入标题" }]}>
            <Input placeholder="如 SMT焊接工序PFMEA" />
          </Form.Item>
        </Form>
      </Modal>

      <GenerationWizard
        open={wizardOpen}
        onCancel={() => setWizardOpen(false)}
        onComplete={handleWizardComplete}
      />
    </div>
  );
}

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Table, Button, Tag, Typography, Modal, Form, Input, Popconfirm, App } from "antd";
import { PlusOutlined, FileTextOutlined, DeleteOutlined } from "@ant-design/icons";
import { listControlPlans, createControlPlan, deleteControlPlan } from "../../api/controlPlan";
import type { ControlPlan } from "../../types";
import { useAuthStore } from "../../store/authStore";

const { Title } = Typography;

const phaseLabels: Record<string, string> = {
  sample: "样件",
  trial: "试生产",
  production: "生产",
};

const statusColors: Record<string, string> = {
  draft: "blue",
  approved: "green",
};

const statusLabels: Record<string, string> = {
  draft: "草稿",
  approved: "已批准",
};

export default function ControlPlanListPage() {
  const { message } = App.useApp();
  const [data, setData] = useState<ControlPlan[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const canEdit = user?.role !== "viewer";

  const fetchData = (p: number = page) => {
    setLoading(true);
    listControlPlans({ page: p, page_size: 20 })
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
      const cp = await createControlPlan(values);
      message.success("控制计划创建成功");
      setModalOpen(false);
      form.resetFields();
      navigate(`/control-plans/${cp.cp_id}`);
    } catch {
      message.error("创建失败");
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteControlPlan(id);
      message.success("删除成功");
      fetchData();
    } catch {
      message.error("删除失败");
    }
  };

  const columns = [
    { title: "编号", dataIndex: "document_no", key: "document_no", width: 150 },
    { title: "标题", dataIndex: "title", key: "title", ellipsis: true },
    {
      title: "阶段",
      dataIndex: "phase",
      key: "phase",
      width: 100,
      render: (p: string) => phaseLabels[p] || p,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (s: string) => <Tag color={statusColors[s] || "default"}>{statusLabels[s] || s}</Tag>,
    },
    { title: "版本", dataIndex: "version", key: "version", width: 80, render: (v: number) => `v${v}` },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      key: "updated_at",
      width: 170,
      render: (v: string) => new Date(v).toLocaleString("zh-CN"),
    },
    {
      title: "操作",
      key: "actions",
      width: 160,
      render: (_: unknown, record: ControlPlan) => (
        <>
          <Button type="link" icon={<FileTextOutlined />} onClick={() => navigate(`/control-plans/${record.cp_id}`)}>
            编辑
          </Button>
          {canEdit && (
            <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.cp_id)}>
              <Button type="link" danger icon={<DeleteOutlined />}>
                删除
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
        <Title level={4} style={{ margin: 0 }}>控制计划</Title>
        {canEdit && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
            新建控制计划
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
        title="新建控制计划"
        open={modalOpen}
        onOk={() => form.submit()}
        onCancel={() => setModalOpen(false)}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="document_no" label="文档编号" rules={[{ required: true, message: "请输入文档编号" }]}>
            <Input placeholder="如 CP-2026-001" />
          </Form.Item>
          <Form.Item name="title" label="标题" rules={[{ required: true, message: "请输入标题" }]}>
            <Input placeholder="如 SMT焊接控制计划" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

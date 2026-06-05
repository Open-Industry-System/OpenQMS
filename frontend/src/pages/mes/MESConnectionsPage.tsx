import { useEffect, useState } from "react";
import {
  Table, Button, Tag, Typography, Modal, Form, Input, Select, App, Space,
} from "antd";
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ApiOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import {
  listConnections, createConnection, updateConnection, deleteConnection,
  testConnection, manualSync,
} from "../../api/mes";
import type { MESConnection, MESConnectionCreate } from "../../types/mes";

const { Title } = Typography;

const typeLabels: Record<string, string> = {
  mock: "Mock",
  rest: "REST API",
};

export default function MESConnectionsPage() {
  const { message, modal: modalConfirm } = App.useApp();
  const [data, setData] = useState<MESConnection[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form] = Form.useForm();

  const fetchData = (p: number = page) => {
    setLoading(true);
    listConnections(p, 20)
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error("加载连接列表失败"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCreate = async (values: MESConnectionCreate) => {
    try {
      await createConnection(values);
      message.success("连接创建成功");
      setModalOpen(false);
      form.resetFields();
      fetchData(1);
    } catch {
      message.error("创建失败");
    }
  };

  const handleUpdate = async (values: Partial<MESConnectionCreate>) => {
    if (!editingId) return;
    try {
      await updateConnection(editingId, values);
      message.success("连接更新成功");
      setModalOpen(false);
      setEditingId(null);
      form.resetFields();
      fetchData(page);
    } catch {
      message.error("更新失败");
    }
  };

  const handleDelete = (id: string, name: string) => {
    modalConfirm.confirm({
      title: "确认删除",
      content: `确定删除连接 "${name}" 吗？`,
      onOk: async () => {
        try {
          await deleteConnection(id);
          message.success("删除成功");
          fetchData(page);
        } catch {
          message.error("删除失败");
        }
      },
    });
  };

  const handleTest = async (id: string) => {
    try {
      const res = await testConnection(id);
      if (res.success) {
        message.success(`连接测试成功: ${res.message || "OK"}`);
      } else {
        message.error(`连接测试失败: ${res.message || "Error"}`);
      }
    } catch {
      message.error("连接测试失败");
    }
  };

  const handleSync = async (id: string) => {
    try {
      const res = await manualSync(id);
      if (res.success) {
        message.success(`同步成功: ${res.message || "OK"}`);
      } else {
        message.error(`同步失败: ${res.message || "Error"}`);
      }
    } catch {
      message.error("同步失败");
    }
  };

  const openCreate = () => {
    setEditingId(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEdit = (record: MESConnection) => {
    setEditingId(record.connection_id);
    form.setFieldsValue({
      name: record.name,
      connector_type: record.connector_type,
      product_line_code: record.product_line_code,
    });
    setModalOpen(true);
  };

  const columns = [
    { title: "连接名称", dataIndex: "name", key: "name", ellipsis: true },
    {
      title: "类型",
      dataIndex: "connector_type",
      key: "connector_type",
      width: 100,
      render: (t: string) => typeLabels[t] || t,
    },
    {
      title: "状态",
      dataIndex: "is_active",
      key: "is_active",
      width: 80,
      render: (active: boolean) => (
        <Tag color={active ? "success" : "error"}>
          {active ? "正常" : "停用"}
        </Tag>
      ),
    },
    {
      title: "产线",
      dataIndex: "product_line_code",
      key: "product_line_code",
      width: 120,
      render: (v: string | null) => v || "—",
    },
    {
      title: "操作",
      key: "actions",
      width: 220,
      render: (_: unknown, record: MESConnection) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEdit(record)}
          >
            编辑
          </Button>
          <Button
            type="link"
            size="small"
            icon={<ApiOutlined />}
            onClick={() => handleTest(record.connection_id)}
          >
            测试
          </Button>
          <Button
            type="link"
            size="small"
            icon={<SyncOutlined />}
            onClick={() => handleSync(record.connection_id)}
          >
            同步
          </Button>
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(record.connection_id, record.name)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>MES 连接管理</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新建连接
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={data}
        rowKey="connection_id"
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
        title={editingId ? "编辑连接" : "新建连接"}
        open={modalOpen}
        onOk={() => form.submit()}
        onCancel={() => {
          setModalOpen(false);
          setEditingId(null);
          form.resetFields();
        }}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={editingId ? handleUpdate : handleCreate}
        >
          <Form.Item
            name="name"
            label="连接名称"
            rules={[{ required: true, message: "请输入连接名称" }]}
          >
            <Input placeholder="如 产线A-MES" />
          </Form.Item>
          <Form.Item
            name="connector_type"
            label="连接器类型"
            rules={[{ required: true, message: "请选择连接器类型" }]}
          >
            <Select
              options={[
                { value: "mock", label: "Mock - 模拟数据" },
                { value: "rest", label: "REST API" },
              ]}
            />
          </Form.Item>
          <Form.Item name="product_line_code" label="产线代码">
            <Input placeholder="如 DC-DC-100" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

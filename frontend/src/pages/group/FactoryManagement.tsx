import { useEffect, useState } from "react";
import { Table, Button, Modal, Form, Input, Switch, message, Space, Popconfirm } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import { listFactories, createFactory, updateFactory, deactivateFactory, type Factory } from "../../api/group";

export default function FactoryManagementPage() {
  const [factories, setFactories] = useState<Factory[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editItem, setEditItem] = useState<Factory | null>(null);
  const [form] = Form.useForm();

  const fetchFactories = () => {
    setLoading(true);
    listFactories()
      .then((res) => setFactories(res.data.items))
      .catch(() => message.error("加载工厂列表失败"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchFactories(); }, []);

  const handleCreate = () => {
    setEditItem(null);
    form.resetFields();
    form.setFieldsValue({ is_active: true });
    setModalOpen(true);
  };

  const handleEdit = (record: Factory) => {
    setEditItem(record);
    form.setFieldsValue({
      code: record.code,
      name: record.name,
      location: record.location || "",
      is_active: record.is_active,
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editItem) {
        await updateFactory(editItem.id, values);
        message.success("更新成功");
      } else {
        await createFactory(values);
        message.success("创建成功");
      }
      setModalOpen(false);
      fetchFactories();
    } catch {
      // validation error or API error
    }
  };

  const handleDeactivate = async (id: string) => {
    try {
      await deactivateFactory(id);
      message.success("已停用");
      fetchFactories();
    } catch {
      message.error("停用失败");
    }
  };

  const columns: ColumnsType<Factory> = [
    { title: "工厂编码", dataIndex: "code", key: "code", width: 120 },
    { title: "工厂名称", dataIndex: "name", key: "name", width: 200 },
    { title: "地点", dataIndex: "location", key: "location", width: 200, render: (v: string) => v || "-" },
    {
      title: "状态", dataIndex: "is_active", key: "is_active", width: 80,
      render: (v: boolean) => v ? "启用" : "停用",
    },
    {
      title: "操作", key: "actions", width: 160,
      render: (_, record) => (
        <Space>
          <Button type="link" size="small" onClick={() => handleEdit(record)}>编辑</Button>
          {record.is_active && (
            <Popconfirm title="确定停用该工厂？" onConfirm={() => handleDeactivate(record.id)}>
              <Button type="link" size="small" danger>停用</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <h2>工厂管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>新建工厂</Button>
      </div>

      <Table
        columns={columns}
        dataSource={factories}
        rowKey="id"
        loading={loading}
        pagination={false}
      />

      <Modal
        title={editItem ? "编辑工厂" : "新建工厂"}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          {!editItem && (
            <Form.Item name="code" label="工厂编码" rules={[{ required: true, message: "请输入工厂编码" }]}>
              <Input placeholder="如 BJ-01" maxLength={20} />
            </Form.Item>
          )}
          <Form.Item name="name" label="工厂名称" rules={[{ required: true, message: "请输入工厂名称" }]}>
            <Input placeholder="如 北京工厂" maxLength={100} />
          </Form.Item>
          <Form.Item name="location" label="地点">
            <Input placeholder="如 北京市朝阳区" maxLength={200} />
          </Form.Item>
          {editItem && (
            <Form.Item name="is_active" label="启用" valuePropName="checked">
              <Switch />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  );
}
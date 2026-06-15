import { useEffect, useState, useCallback } from "react";
import { Table, Button, Modal, Form, Input, Switch, message, Space, Popconfirm } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import { useTranslation } from "react-i18next";
import { listFactories, createFactory, updateFactory, deactivateFactory, type Factory } from "../../api/group";

export default function FactoryManagementPage() {
  const { t } = useTranslation("group");
  const { t: tc } = useTranslation("common");
  const [factories, setFactories] = useState<Factory[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editItem, setEditItem] = useState<Factory | null>(null);
  const [form] = Form.useForm();

  const fetchFactories = useCallback(() => {
    setLoading(true);
    listFactories()
      .then((res) => setFactories(res.data.items))
      .catch(() => message.error(t("factoryManagement.messages.loadFailed")))
      .finally(() => setLoading(false));
  }, [t]);

  useEffect(() => { fetchFactories(); }, [fetchFactories]);

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
        message.success(t("factoryManagement.messages.updateSuccess"));
      } else {
        await createFactory(values);
        message.success(t("factoryManagement.messages.createSuccess"));
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
      message.success(t("factoryManagement.messages.deactivateSuccess"));
      fetchFactories();
    } catch {
      message.error(t("factoryManagement.messages.deactivateFailed"));
    }
  };

  const columns: ColumnsType<Factory> = [
    { title: t("factoryManagement.columns.code"), dataIndex: "code", key: "code", width: 120 },
    { title: t("factoryManagement.columns.name"), dataIndex: "name", key: "name", width: 200 },
    { title: t("factoryManagement.columns.location"), dataIndex: "location", key: "location", width: 200, render: (v: string) => v || "-" },
    {
      title: t("factoryManagement.columns.status"), dataIndex: "is_active", key: "is_active", width: 80,
      render: (v: boolean) => v ? t("factoryManagement.status.active") : t("factoryManagement.status.inactive"),
    },
    {
      title: tc("table.operations"), key: "actions", width: 160,
      render: (_, record) => (
        <Space>
          <Button type="link" size="small" onClick={() => handleEdit(record)}>{tc("actions.edit")}</Button>
          {record.is_active && (
            <Popconfirm title={t("factoryManagement.confirmDeactivate")} onConfirm={() => handleDeactivate(record.id)}>
              <Button type="link" size="small" danger>{t("factoryManagement.deactivate")}</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <h2>{t("factoryManagement.title")}</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>{tc("actions.create")}</Button>
      </div>

      <Table
        columns={columns}
        dataSource={factories}
        rowKey="id"
        loading={loading}
        pagination={false}
      />

      <Modal
        title={editItem ? t("factoryManagement.editFactory") : t("factoryManagement.newFactory")}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          {!editItem && (
            <Form.Item name="code" label={t("factoryManagement.form.code")} rules={[{ required: true, message: t("factoryManagement.rules.codeRequired") }]}>
              <Input placeholder={t("factoryManagement.placeholders.code")} maxLength={20} />
            </Form.Item>
          )}
          <Form.Item name="name" label={t("factoryManagement.form.name")} rules={[{ required: true, message: t("factoryManagement.rules.nameRequired") }]}>
            <Input placeholder={t("factoryManagement.placeholders.name")} maxLength={100} />
          </Form.Item>
          <Form.Item name="location" label={t("factoryManagement.form.location")}>
            <Input placeholder={t("factoryManagement.placeholders.location")} maxLength={200} />
          </Form.Item>
          {editItem && (
            <Form.Item name="is_active" label={t("factoryManagement.form.isActive")} valuePropName="checked">
              <Switch />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  );
}

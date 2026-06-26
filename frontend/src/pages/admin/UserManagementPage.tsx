import { useState, useEffect, useCallback } from "react";
import { Table, Button, Modal, Form, Input, Select, Tag, Space, App } from "antd";
import { useTranslation } from "react-i18next";
import { PlusOutlined } from "@ant-design/icons";
import { PageShell } from "../../components/design";
import { listUsers, registerUser } from "../../api/auth";
import { listRoles } from "../../api/admin";
import type { User, RoleOption } from "../../types";

export default function UserManagementPage() {
  const { t } = useTranslation("users");
  const { message } = App.useApp();
  const [rows, setRows] = useState<User[]>([]);
  const [roles, setRoles] = useState<RoleOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    try { setRows(await listUsers()); } finally { setLoading(false); }
  }, []);

  const loadRoles = useCallback(async () => {
    try { setRoles(await listRoles()); } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); loadRoles(); }, [load, loadRoles]);

  const onSubmit = async () => {
    const values = await form.validateFields();
    try {
      await registerUser(values);
      message.success(t("messages.created"));
      setOpen(false); form.resetFields(); await load();
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t("messages.createFailed"));
    }
  };

  const columns = [
    { title: t("fields.username"), dataIndex: "username" },
    { title: t("fields.display_name"), dataIndex: "display_name" },
    { title: t("fields.email"), dataIndex: "email" },
    { title: t("fields.role_key"), dataIndex: "role_key" },
    {
      title: t("fields.is_active"),
      dataIndex: "is_active",
      render: (v: boolean) => <Tag color={v ? "green" : "default"}>{v ? t("active") : t("inactive")}</Tag>,
    },
    {
      title: t("fields.factories"),
      dataIndex: "factories",
      render: (fs?: { code?: string }[]) => (fs || []).map((f) => f.code).join(", "),
    },
  ];

  return (
    <PageShell title={t("title")}>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setOpen(true); }}>
          {t("create")}
        </Button>
      </Space>
      <Table rowKey="user_id" columns={columns} dataSource={rows} loading={loading} pagination={{ pageSize: 20 }} />
      <Modal title={t("createModalTitle")} open={open} onOk={onSubmit} onCancel={() => setOpen(false)} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item name="username" label={t("fields.username")} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="password" label={t("fields.password")} rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="display_name" label={t("fields.display_name")}>
            <Input />
          </Form.Item>
          <Form.Item name="email" label={t("fields.email")}>
            <Input />
          </Form.Item>
          <Form.Item name="role_key" label={t("fields.role_key")} rules={[{ required: true }]}>
            <Select options={roles.map((r) => ({ value: r.role_key, label: r.name_zh || r.role_key }))} />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}

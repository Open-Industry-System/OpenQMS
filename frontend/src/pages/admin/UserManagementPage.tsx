import { useState, useEffect, useCallback } from "react";
import { Table, Button, Modal, Form, Input, Select, Tag, Space, App, Switch } from "antd";
import { useTranslation } from "react-i18next";
import { PlusOutlined, EditOutlined } from "@ant-design/icons";
import { PageShell } from "../../components/design";
import {
  listUsers, registerUser, updateUser, deleteUser, listAssignableRoles, listFactories,
} from "../../api/auth";
import { useAuthStore } from "../../store/authStore";
import type { User, AssignableRoleOption, RegisterRequest, UserUpdateRequest, Factory } from "../../types";

/**
 * 把后端 422/400 错误转成可渲染字符串（同创建弹窗）。避免 React 因对象子节点崩溃。
 */
function formatRegisterError(e: unknown): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (typeof (d as { msg?: string })?.msg === "string" ? (d as { msg: string }).msg : ""))
      .filter(Boolean)
      .join("; ");
  }
  return "";
}

const NONE_DEFAULT = "__none__"; // Select 值代表 default_factory_id = null

export default function UserManagementPage() {
  const { t } = useTranslation("users");
  const { message, modal } = App.useApp();
  const meId = useAuthStore((s) => s.user?.user_id);
  const [rows, setRows] = useState<User[]>([]);
  const [roles, setRoles] = useState<AssignableRoleOption[]>([]);
  const [factories, setFactories] = useState<Factory[]>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [saving, setSaving] = useState(false);
  const [editFactoryIds, setEditFactoryIds] = useState<string[]>([]);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    try { setRows(await listUsers()); } finally { setLoading(false); }
  }, []);

  const loadOptions = useCallback(async () => {
    try { setRoles(await listAssignableRoles()); } catch { /* ignore */ }
    try { setFactories(await listFactories()); } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); loadOptions(); }, [load, loadOptions]);

  const onSubmitCreate = async () => {
    const values = await createForm.validateFields();
    const payload: RegisterRequest = {
      ...values,
      display_name: values.display_name?.trim() || undefined,
      email: values.email?.trim() || undefined,
    };
    try {
      await registerUser(payload);
      message.success(t("messages.created"));
      setCreateOpen(false); createForm.resetFields(); await load();
    } catch (e) {
      message.error(formatRegisterError(e) || t("messages.createFailed"));
    }
  };

  const openEdit = (u: User) => {
    setEditing(u);
    const factoryIds = (u.factories || []).map((f) => f.id);
    setEditFactoryIds(factoryIds);
    const defaultId = u.factory_scope?.default_factory_id ?? null;
    editForm.setFieldsValue({
      display_name: u.display_name ?? "",
      email: u.email ?? "",
      role_key: u.role_key,
      is_active: u.is_active,
      factory_ids: factoryIds,
      default_factory_id: defaultId ?? NONE_DEFAULT,
      password: "",
    });
    setEditOpen(true);
  };

  const onSubmitEdit = async () => {
    if (!editing) return;
    const values = await editForm.validateFields();
    const payload: UserUpdateRequest = {};
    if ((values.display_name ?? "") !== (editing.display_name ?? ""))
      payload.display_name = (values.display_name as string)?.trim() || null;
    if ((values.email ?? "") !== (editing.email ?? ""))
      payload.email = (values.email as string)?.trim() || null;
    if (values.role_key !== editing.role_key) payload.role_key = values.role_key;
    if (values.is_active !== editing.is_active) payload.is_active = values.is_active;
    const newFactoryIds = (values.factory_ids as string[]) || [];
    const oldFactoryIds = (editing.factories || []).map((f) => f.id);
    const setChanged = JSON.stringify([...newFactoryIds].sort()) !== JSON.stringify([...oldFactoryIds].sort());
    if (setChanged) payload.factory_ids = newFactoryIds;
    const newDefault = values.default_factory_id === NONE_DEFAULT ? null : values.default_factory_id;
    const oldDefault = editing.factory_scope?.default_factory_id ?? null;
    if (newDefault !== oldDefault) payload.default_factory_id = newDefault;
    if (values.password && values.password.trim()) payload.password = values.password;

    setSaving(true);
    try {
      await updateUser(editing.user_id, payload);
      message.success(t("messages.updated"));
      setEditOpen(false); setEditing(null); await load();
    } catch (e) {
      message.error(formatRegisterError(e) || t("messages.updateFailed"));
    } finally {
      setSaving(false);
    }
  };

  const onToggleActive = async (u: User) => {
    try {
      await updateUser(u.user_id, { is_active: !u.is_active });
      message.success(t("messages.updated"));
      await load();
    } catch (e) {
      message.error(formatRegisterError(e) || t("messages.updateFailed"));
    }
  };

  const onDelete = (u: User) => {
    modal.confirm({
      title: t("confirmDeleteTitle"),
      content: t("confirmDeleteContent"),
      onOk: async () => {
        try {
          await deleteUser(u.user_id);
          message.success(t("messages.deleted"));
          await load();
        } catch (e) {
          message.error(formatRegisterError(e) || t("messages.deleteFailed"));
        }
      },
    });
  };

  const columns = [
    { title: t("fields.username"), dataIndex: "username" },
    { title: t("fields.display_name"), dataIndex: "display_name" },
    { title: t("fields.email"), dataIndex: "email" },
    { title: t("fields.role_key"), dataIndex: "role_key" },
    {
      title: t("fields.is_active"), dataIndex: "is_active",
      render: (v: boolean) => <Tag color={v ? "green" : "default"}>{v ? t("active") : t("inactive")}</Tag>,
    },
    {
      title: t("fields.factories"), dataIndex: "factories",
      render: (fs?: { code?: string }[]) => (fs || []).map((f) => f.code).join(", "),
    },
    {
      title: t("actions"), key: "actions", width: 220,
      render: (_: unknown, u: User) => {
        const isSelf = u.user_id === meId;
        return (
          <Space>
            <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(u)}>{t("edit")}</Button>
            <Button size="small" disabled={isSelf} onClick={() => onToggleActive(u)}>
              {u.is_active ? t("deactivate") : t("activate")}
            </Button>
            <Button size="small" danger disabled={isSelf} onClick={() => onDelete(u)}>{t("delete")}</Button>
          </Space>
        );
      },
    },
  ];

  const factoryOptions = factories.map((f) => ({ value: f.id, label: `${f.code} - ${f.name}` }));
  const defaultOptions = [
    { value: NONE_DEFAULT, label: t("noDefaultFactory") },
    ...factories.filter((f) => editFactoryIds.includes(f.id)).map((f) => ({ value: f.id, label: `${f.code} - ${f.name}` })),
  ];

  return (
    <PageShell title={t("title")}>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>{t("create")}</Button>
      </Space>
      <Table rowKey="user_id" columns={columns} dataSource={rows} loading={loading} pagination={{ pageSize: 20 }} />

      <Modal title={t("createModalTitle")} open={createOpen} onOk={onSubmitCreate} onCancel={() => setCreateOpen(false)} destroyOnHidden>
        <Form form={createForm} layout="vertical">
          <Form.Item name="username" label={t("fields.username")} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="password" label={t("fields.password")} rules={[{ required: true }]}><Input.Password /></Form.Item>
          <Form.Item name="display_name" label={t("fields.display_name")}><Input /></Form.Item>
          <Form.Item name="email" label={t("fields.email")}><Input /></Form.Item>
          <Form.Item name="role_key" label={t("fields.role_key")} rules={[{ required: true }]}>
            <Select options={roles.map((r) => ({ value: r.role_key, label: r.name_zh || r.role_key }))} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title={t("editModalTitle")} open={editOpen} onOk={onSubmitEdit} onCancel={() => { setEditOpen(false); setEditing(null); }}
        confirmLoading={saving} destroyOnHidden>
        <Form form={editForm} layout="vertical" onValuesChange={(changed) => {
          if ("factory_ids" in changed) setEditFactoryIds(changed.factory_ids as string[] || []);
        }}>
          <Form.Item name="display_name" label={t("fields.display_name")}><Input /></Form.Item>
          <Form.Item name="email" label={t("fields.email")}><Input /></Form.Item>
          <Form.Item name="role_key" label={t("fields.role_key")} rules={[{ required: true }]}>
            <Select options={roles.map((r) => ({ value: r.role_key, label: r.name_zh || r.role_key }))} />
          </Form.Item>
          <Form.Item name="is_active" label={t("fields.is_active")} valuePropName="checked"><Switch /></Form.Item>
          <Form.Item name="factory_ids" label={t("fields.factories")}>
            <Select mode="multiple" options={factoryOptions} placeholder="" />
          </Form.Item>
          <Form.Item name="default_factory_id" label={t("fields.defaultFactory")}>
            <Select options={defaultOptions} />
          </Form.Item>
          <Form.Item name="password" label={t("fields.password")} extra={t("passwordHint")}>
            <Input.Password placeholder={t("passwordHint")} />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}

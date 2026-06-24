import { useState, useEffect } from "react";
import { Table, Button, Modal, Form, Input, Tag, Space, App } from "antd";
import { useTranslation } from "react-i18next";
import { PlusOutlined } from "@ant-design/icons";
import { PageShell } from "../../components/design";
import { listProductTypes, createProductType, updateProductType, deleteProductType } from "../../api/productType";
import type { ProductType } from "../../types";

export default function ProductTypePage() {
  const { t } = useTranslation("productType");
  const { message, modal } = App.useApp();
  const [rows, setRows] = useState<ProductType[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<ProductType | null>(null);
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try { setRows(await listProductTypes()); } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const onSubmit = async () => {
    const values = await form.validateFields();
    try {
      if (editing) { await updateProductType(editing.code, values); message.success(t("messages.updated")); }
      else { await createProductType(values); message.success(t("messages.created")); }
      setOpen(false); form.resetFields(); await load();
    } catch (e: any) { message.error(e?.response?.data?.detail || "error"); }
  };

  const onDeactivate = (row: ProductType) => {
    modal.confirm({
      title: t("messages.deleteConfirm"),
      onOk: async () => {
        try { await deleteProductType(row.code); message.success(t("messages.deactivated")); await load(); }
        catch (e: any) { message.error(t("messages.refused", { detail: e?.response?.data?.detail || "" })); }
      },
    });
  };

  const columns = [
    { title: t("fields.code"), dataIndex: "code" },
    { title: t("fields.name"), dataIndex: "name" },
    { title: t("fields.description"), dataIndex: "description" },
    { title: t("fields.is_active"), dataIndex: "is_active", render: (v: boolean) => <Tag color={v ? "green" : "default"}>{v ? "ON" : "OFF"}</Tag> },
    { title: "", render: (_: unknown, row: ProductType) => (
      <Space>
        <Button size="small" onClick={() => { setEditing(row); form.setFieldsValue(row); setOpen(true); }}>{t("actions.edit")}</Button>
        <Button size="small" danger onClick={() => onDeactivate(row)}>{t("actions.delete")}</Button>
      </Space>
    ) },
  ];

  return (
    <PageShell title={t("title")} actions={<Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); setOpen(true); }}>{t("actions.create")}</Button>}>
      <Table rowKey="code" dataSource={rows} columns={columns} loading={loading} />
      <Modal open={open} title={editing ? t("actions.edit") : t("actions.create")} onCancel={() => setOpen(false)} onOk={onSubmit}>
        <Form form={form} layout="vertical">
          <Form.Item name="code" label={t("fields.code")} rules={[{ required: true }]}><Input disabled={!!editing} /></Form.Item>
          <Form.Item name="name" label={t("fields.name")} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label={t("fields.description")}><Input.TextArea /></Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}

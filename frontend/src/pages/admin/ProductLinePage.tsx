import { useState, useEffect } from "react";
import { Table, Button, Modal, Form, Input, Tag, Space, App, Select } from "antd";
import { useTranslation } from "react-i18next";
import { PlusOutlined } from "@ant-design/icons";
import { PageShell } from "../../components/design";
import { listProductLines, createProductLine, updateProductLine, deleteProductLine } from "../../api/productLine";
import { listProductTypes } from "../../api/productType";
import type { ProductLine, ProductType } from "../../types";

export default function ProductLinePage() {
  const { t } = useTranslation("productType");
  const { message, modal } = App.useApp();
  const [rows, setRows] = useState<ProductLine[]>([]);
  const [types, setTypes] = useState<ProductType[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<ProductLine | null>(null);
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const [lines, productTypes] = await Promise.all([listProductLines(), listProductTypes()]);
      setRows(lines);
      setTypes(productTypes);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const typeName = (code: string | null) => {
    if (!code) return null;
    return types.find((t) => t.code === code)?.name ?? code;
  };

  const onSubmit = async () => {
    const values = await form.validateFields();
    try {
      if (editing) {
        await updateProductLine(editing.code, { ...values, product_type_code: values.product_type_code ?? null });
        message.success(t("messages.updated"));
      } else {
        await createProductLine({ ...values, product_type_code: values.product_type_code ?? null });
        message.success(t("messages.created"));
      }
      setOpen(false); form.resetFields(); await load();
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || "error");
    }
  };

  const onDeactivate = (row: ProductLine) => {
    modal.confirm({
      title: t("messages.deleteConfirm"),
      onOk: async () => {
        try { await deleteProductLine(row.code); message.success(t("messages.deactivated")); await load(); }
        catch (e) {
          const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "";
          message.error(t("messages.refused", { detail }));
        }
      },
    });
  };

  const columns = [
    { title: t("fields.code"), dataIndex: "code" },
    { title: t("fields.name"), dataIndex: "name" },
    { title: t("productLine.fields.product_type_code"), dataIndex: "product_type_code", render: (code: string | null) => typeName(code) ?? "-" },
    { title: t("fields.is_active"), dataIndex: "is_active", render: (v: boolean) => <Tag color={v ? "green" : "default"}>{v ? "ON" : "OFF"}</Tag> },
    { title: "", render: (_: unknown, row: ProductLine) => (
      <Space>
        <Button size="small" onClick={() => { setEditing(row); form.setFieldsValue(row); setOpen(true); }}>{t("actions.edit")}</Button>
        <Button size="small" danger onClick={() => onDeactivate(row)}>{t("actions.delete")}</Button>
      </Space>
    ) },
  ];

  return (
    <PageShell title={t("productLine.title")} actions={<Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); setOpen(true); }}>{t("actions.create")}</Button>}>
      <Table rowKey="code" dataSource={rows} columns={columns} loading={loading} />
      <Modal open={open} title={editing ? t("actions.edit") : t("actions.create")} onCancel={() => setOpen(false)} onOk={onSubmit}>
        <Form form={form} layout="vertical">
          <Form.Item name="code" label={t("fields.code")} rules={[{ required: true }]}><Input disabled={!!editing} /></Form.Item>
          <Form.Item name="name" label={t("fields.name")} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="product_type_code" label={t("productLine.fields.product_type_code")}>
            <Select
              allowClear
              placeholder={t("productLine.assignType")}
              options={types.map((type) => ({ value: type.code, label: `${type.code} - ${type.name}` }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}

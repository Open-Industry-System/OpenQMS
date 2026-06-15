import { useEffect, useMemo, useState } from "react";
import {
  Table, Button, Tag, Typography, Modal, Form, Input, Select, App, Space,
} from "antd";
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ApiOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import {
  listConnections, createConnection, updateConnection, deleteConnection,
  testConnection, manualSync,
} from "../../api/mes";
import type { MESConnection, MESConnectionCreate } from "../../types/mes";

const { Title } = Typography;

export default function MESConnectionsPage() {
  const { t } = useTranslation("mes");
  const { t: tc } = useTranslation("common");
  const { message, modal: modalConfirm } = App.useApp();
  const [data, setData] = useState<MESConnection[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form] = Form.useForm();

  const connectorOptions = useMemo(() => [
    { value: "mock", label: t("connections.connector.mock") },
    { value: "rest", label: t("connections.connector.rest") },
  ], [t]);

  const fetchData = (p: number = page) => {
    setLoading(true);
    listConnections(p, 20)
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error(t("connections.messages.loadFailed")))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCreate = async (values: MESConnectionCreate) => {
    try {
      await createConnection(values);
      message.success(t("connections.messages.createSuccess"));
      setModalOpen(false);
      form.resetFields();
      fetchData(1);
    } catch {
      message.error(t("connections.messages.createFailed"));
    }
  };

  const handleUpdate = async (values: Partial<MESConnectionCreate>) => {
    if (!editingId) return;
    try {
      await updateConnection(editingId, values);
      message.success(t("connections.messages.updateSuccess"));
      setModalOpen(false);
      setEditingId(null);
      form.resetFields();
      fetchData(page);
    } catch {
      message.error(t("connections.messages.updateFailed"));
    }
  };

  const handleDelete = (id: string, name: string) => {
    modalConfirm.confirm({
      title: t("connections.deleteConfirm.title"),
      content: t("connections.deleteConfirm.content", { name }),
      onOk: async () => {
        try {
          await deleteConnection(id);
          message.success(t("connections.messages.deleteSuccess"));
          fetchData(page);
        } catch {
          message.error(t("connections.messages.deleteFailed"));
        }
      },
    });
  };

  const handleTest = async (id: string) => {
    try {
      const res = await testConnection(id);
      if (res.ok) {
        message.success(t("connections.messages.testSuccess"));
      } else {
        message.error(t("connections.messages.testFailedWithError", { error: res.error || "Unknown error" }));
      }
    } catch {
      message.error(t("connections.messages.testFailed"));
    }
  };

  const handleSync = async (id: string) => {
    try {
      await manualSync(id);
      message.success(t("connections.messages.syncTriggered"));
    } catch {
      message.error(t("connections.messages.syncFailed"));
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
    { title: t("connections.columns.name"), dataIndex: "name", key: "name", ellipsis: true },
    {
      title: t("connections.columns.type"),
      dataIndex: "connector_type",
      key: "connector_type",
      width: 100,
      render: (type: string) => {
        const option = connectorOptions.find((o) => o.value === type);
        return option?.label || type;
      },
    },
    {
      title: t("connections.columns.status"),
      dataIndex: "is_active",
      key: "is_active",
      width: 80,
      render: (active: boolean) => (
        <Tag color={active ? "success" : "error"}>
          {active ? t("connections.status.active") : t("connections.status.inactive")}
        </Tag>
      ),
    },
    {
      title: t("connections.columns.productLine"),
      dataIndex: "product_line_code",
      key: "product_line_code",
      width: 120,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("connections.columns.actions"),
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
            {tc("actions.edit")}
          </Button>
          <Button
            type="link"
            size="small"
            icon={<ApiOutlined />}
            onClick={() => handleTest(record.connection_id)}
          >
            {t("connections.test")}
          </Button>
          <Button
            type="link"
            size="small"
            icon={<SyncOutlined />}
            onClick={() => handleSync(record.connection_id)}
          >
            {t("connections.sync")}
          </Button>
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(record.connection_id, record.name)}
          >
            {tc("actions.delete")}
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>{t("connections.title")}</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          {t("connections.create")}
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
        title={editingId ? t("connections.modal.editTitle") : t("connections.modal.createTitle")}
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
            label={t("connections.form.name")}
            rules={[{ required: true, message: t("connections.form.nameRequired") }]}
          >
            <Input placeholder={t("connections.form.namePlaceholder")} />
          </Form.Item>
          <Form.Item
            name="connector_type"
            label={t("connections.form.connectorType")}
            rules={[{ required: true, message: t("connections.form.connectorTypeRequired") }]}
          >
            <Select options={connectorOptions} />
          </Form.Item>
          <Form.Item name="product_line_code" label={t("connections.form.productLineCode")}>
            <Input placeholder={t("connections.form.productLineCodePlaceholder")} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

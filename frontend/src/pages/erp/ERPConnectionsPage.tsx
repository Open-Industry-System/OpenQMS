import { useEffect, useMemo, useState } from "react";
import {
  Table, Button, Tag, Typography, Modal, Form, Input, Select, App, Space,
  InputNumber,
} from "antd";
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ApiOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { formatDateTime } from "../../utils/dateTime";
import {
  fetchERPConnections, createERPConnection, updateERPConnection,
  deleteERPConnection, testERPConnection, triggerERPSync,
} from "../../api/erp";
import type { ERPConnection } from "../../types/erp";
import { usePermission } from "../../hooks/usePermission";

const { Title } = Typography;

export default function ERPConnectionsPage() {
  const { t } = useTranslation("erp");
  const { t: tc } = useTranslation("common");
  const { message, modal: modalConfirm } = App.useApp();
  const { canCreate, canEdit, canAdmin } = usePermission();
  const canCreateErp = canCreate("erp");
  const canEditErp = canEdit("erp");
  const canAdminErp = canAdmin("erp");
  const [data, setData] = useState<ERPConnection[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form] = Form.useForm();
  const [testLoading, setTestLoading] = useState<Record<string, boolean>>({});
  const [syncLoading, setSyncLoading] = useState<Record<string, boolean>>({});
  const [connectorType, setConnectorType] = useState<string | null>(null);

  const connectorOptions = useMemo(() => [
    { value: "mock", label: t("connections.connector.mock") },
    { value: "rest", label: t("connections.connector.rest") },
    { value: "sap", label: t("connections.connector.notImplemented", { name: "SAP" }), disabled: true },
    { value: "oracle_ebs", label: t("connections.connector.notImplemented", { name: "Oracle EBS" }), disabled: true },
    { value: "kingdee", label: t("connections.connector.notImplemented", { name: "Kingdee" }), disabled: true },
    { value: "yonyou", label: t("connections.connector.notImplemented", { name: "Yonyou" }), disabled: true },
  ], [t]);

  const fetchData = (p: number = page) => {
    setLoading(true);
    fetchERPConnections(p, 20)
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

  const handleCreate = async (values: {
    name: string;
    connector_type: string;
    product_line_code?: string;
    config_base_url?: string;
    config_port?: number;
    config_api_key?: string;
  }) => {
    const { config_base_url, config_port, config_api_key, ...rest } = values;
    const config: Record<string, unknown> = {};
    if (config_base_url) config.base_url = config_base_url;
    if (config_port) config.port = config_port;
    if (config_api_key) config.api_key = config_api_key;
    try {
      await createERPConnection({ ...rest, config });
      message.success(t("connections.messages.createSuccess"));
      setModalOpen(false);
      form.resetFields();
      setConnectorType(null);
      fetchData(1);
    } catch {
      message.error(t("connections.messages.createFailed"));
    }
  };

  const handleUpdate = async (values: {
    name?: string;
    connector_type?: string;
    product_line_code?: string;
    config_base_url?: string;
    config_port?: number;
    config_api_key?: string;
  }) => {
    if (!editingId) return;
    const { config_base_url, config_port, config_api_key, ...rest } = values;
    const config: Record<string, unknown> = {};
    if (config_base_url) config.base_url = config_base_url;
    if (config_port) config.port = config_port;
    if (config_api_key) config.api_key = config_api_key;
    try {
      await updateERPConnection(editingId, { ...rest, config });
      message.success(t("connections.messages.updateSuccess"));
      setModalOpen(false);
      setEditingId(null);
      form.resetFields();
      setConnectorType(null);
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
          await deleteERPConnection(id);
          message.success(t("connections.messages.deleteSuccess"));
          fetchData(page);
        } catch {
          message.error(t("connections.messages.deleteFailed"));
        }
      },
    });
  };

  const handleTest = async (id: string) => {
    setTestLoading((prev) => ({ ...prev, [id]: true }));
    try {
      const res = await testERPConnection(id);
      if (res.success) {
        message.success(t("connections.messages.testSuccess"));
      } else {
        message.error(res.message ? `${t("connections.messages.testFailed")}: ${res.message}` : t("connections.messages.testFailed"));
      }
    } catch {
      message.error(t("connections.messages.testFailed"));
    } finally {
      setTestLoading((prev) => ({ ...prev, [id]: false }));
    }
  };

  const handleSync = async (id: string) => {
    setSyncLoading((prev) => ({ ...prev, [id]: true }));
    try {
      await triggerERPSync(id);
      message.success(t("connections.messages.syncTriggered"));
    } catch {
      message.error(t("connections.messages.syncFailed"));
    } finally {
      setSyncLoading((prev) => ({ ...prev, [id]: false }));
    }
  };

  const openCreate = () => {
    setEditingId(null);
    form.resetFields();
    setConnectorType(null);
    setModalOpen(true);
  };

  const openEdit = (record: ERPConnection) => {
    setEditingId(record.connection_id);
    const cfg = record.config as Record<string, unknown>;
    form.setFieldsValue({
      name: record.name,
      connector_type: record.connector_type,
      product_line_code: record.product_line_code,
      config_base_url: cfg?.base_url,
      config_port: cfg?.port,
      config_api_key: cfg?.api_key,
    });
    setConnectorType(record.connector_type);
    setModalOpen(true);
  };

  const showRestConfig = connectorType === "rest";

  const columns = useMemo(() => [
    { title: t("connections.columns.name"), dataIndex: "name", key: "name", ellipsis: true },
    {
      title: t("connections.columns.type"),
      dataIndex: "connector_type",
      key: "connector_type",
      width: 140,
      render: (type: string) => {
        const option = connectorOptions.find((o) => o.value === type);
        return option?.label || type;
      },
    },
    {
      title: t("connections.columns.productLineCode"),
      dataIndex: "product_line_code",
      key: "product_line_code",
      width: 120,
      render: (v: string | null) => v || "—",
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
      title: t("connections.columns.createdAt"),
      dataIndex: "created_at",
      key: "created_at",
      width: 170,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: t("connections.columns.actions"),
      key: "actions",
      width: 260,
      render: (_: unknown, record: ERPConnection) => (
        <Space size="small">
          {canEditErp && (
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              onClick={() => openEdit(record)}
            >
              {tc("actions.edit")}
            </Button>
          )}
          {canEditErp && (
            <>
              <Button
                type="link"
                size="small"
                icon={<ApiOutlined />}
                loading={testLoading[record.connection_id]}
                onClick={() => handleTest(record.connection_id)}
              >
                {t("connections.test")}
              </Button>
              <Button
                type="link"
                size="small"
                icon={<SyncOutlined />}
                loading={syncLoading[record.connection_id]}
                onClick={() => handleSync(record.connection_id)}
              >
                {t("connections.sync")}
              </Button>
            </>
          )}
          {canAdminErp && (
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => handleDelete(record.connection_id, record.name)}
            >
              {tc("actions.delete")}
            </Button>
          )}
        </Space>
      ),
    },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [canEditErp, canAdminErp, testLoading, syncLoading, t, tc, connectorOptions]);

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginBottom: 16,
        }}
      >
        <Title level={4} style={{ margin: 0 }}>
          {t("connections.title")}
        </Title>
        {canCreateErp && (
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            {t("connections.create")}
          </Button>
        )}
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
          setConnectorType(null);
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
            <Select
              onChange={(v) => setConnectorType(v)}
              options={connectorOptions}
            />
          </Form.Item>
          <Form.Item
            name="product_line_code"
            label={t("connections.form.productLineCode")}
            rules={[{ required: true, message: t("connections.form.productLineCodeRequired") }]}
          >
            <Input placeholder={t("connections.form.productLineCodePlaceholder")} />
          </Form.Item>
          {showRestConfig && (
            <>
              <Form.Item name="config_base_url" label={t("connections.form.baseUrl")}>
                <Input placeholder={t("connections.form.baseUrlPlaceholder")} />
              </Form.Item>
              <Form.Item name="config_port" label={t("connections.form.port")}>
                <InputNumber
                  style={{ width: "100%" }}
                  placeholder={t("connections.form.portPlaceholder")}
                  min={1}
                  max={65535}
                />
              </Form.Item>
              <Form.Item name="config_api_key" label={t("connections.form.apiKey")}>
                <Input.Password placeholder={t("connections.form.apiKeyPlaceholder")} />
              </Form.Item>
            </>
          )}
        </Form>
      </Modal>
    </div>
  );
}

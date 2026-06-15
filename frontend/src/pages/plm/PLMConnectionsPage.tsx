import { useEffect, useMemo, useState } from "react";
import {
  Table, Button, Modal, Form, Input, Select, App, Space,
  InputNumber,
} from "antd";
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ApiOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import {
  getPLMConnections, createPLMConnection, updatePLMConnection,
  deletePLMConnection, testPLMConnection, syncPLMConnection,
} from "../../api/plm";
import type { PLMConnection, PLMConnectionCreate, PLMConnectionUpdate } from "../../types/plm";
import { usePermission } from "../../hooks/usePermission";
import { PageShell, DataCard, StatusBadge } from "../../components/design";

const typeLabels: Record<string, string> = {
  mock: "Mock",
  rest: "REST API",
  siemens_tc: "Siemens Teamcenter",
  dassault_enovia: "Dassault ENOVIA",
  ptc_windchill: "PTC Windchill",
};

export default function PLMConnectionsPage() {
  const { t } = useTranslation("plm");
  const { t: tc } = useTranslation("common");
  const { message, modal: modalConfirm } = App.useApp();
  const { canCreate, canEdit, canAdmin } = usePermission();
  const canCreatePlm = canCreate("plm");
  const canEditPlm = canEdit("plm");
  const canAdminPlm = canAdmin("plm");
  const [data, setData] = useState<PLMConnection[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form] = Form.useForm();
  const [testLoading, setTestLoading] = useState<Record<string, boolean>>({});
  const [syncLoading, setSyncLoading] = useState<Record<string, boolean>>({});

  const connectorOptions = useMemo(() => [
    { value: "mock", label: t("connections.connector.mock") },
    { value: "rest", label: t("connections.connector.rest"), disabled: true },
    { value: "siemens_tc", label: t("connections.connector.siemens_tc"), disabled: true },
    { value: "dassault_enovia", label: t("connections.connector.dassault_enovia"), disabled: true },
    { value: "ptc_windchill", label: t("connections.connector.ptc_windchill"), disabled: true },
  ], [t]);

  const fetchData = (p: number = page) => {
    setLoading(true);
    getPLMConnections(p, 20)
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

  const handleCreate = async (values: PLMConnectionCreate & { config_port?: number }) => {
    const { config_port, ...rest } = values;
    const config: Record<string, unknown> = {};
    if (config_port) config.port = config_port;
    try {
      await createPLMConnection({ ...rest, config });
      message.success(t("connections.messages.createSuccess"));
      setModalOpen(false);
      form.resetFields();
      fetchData(1);
    } catch {
      message.error(t("connections.messages.createFailed"));
    }
  };

  const handleUpdate = async (
    values: PLMConnectionUpdate & { config_port?: number },
  ) => {
    if (!editingId) return;
    const { config_port, ...rest } = values;
    const payload: PLMConnectionUpdate = { ...rest };
    if (config_port !== undefined) {
      payload.config = { port: config_port };
    }
    try {
      await updatePLMConnection(editingId, payload);
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
          await deletePLMConnection(id);
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
      const res = await testPLMConnection(id);
      if (res.status === "ok") {
        message.success(t("connections.messages.testSuccess", { count: res.parts_count ?? 0 }));
      } else {
        message.error(res.error ? `${t("connections.messages.testFailed")}: ${res.error}` : t("connections.messages.testFailed"));
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
      const res = await syncPLMConnection(id);
      message.success(t("connections.messages.syncTriggered", { count: res.synced_jobs }));
    } catch {
      message.error(t("connections.messages.syncFailed"));
    } finally {
      setSyncLoading((prev) => ({ ...prev, [id]: false }));
    }
  };

  const openCreate = () => {
    setEditingId(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEdit = (record: PLMConnection) => {
    setEditingId(record.connection_id);
    form.setFieldsValue({
      name: record.name,
      connector_type: record.connector_type,
      product_line_code: record.product_line_code,
      config_port: (record.config as Record<string, unknown>)?.port,
    });
    setModalOpen(true);
  };

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
        <StatusBadge status={active ? "ok" : "error"}>
          {active ? t("connections.status.active") : t("connections.status.inactive")}
        </StatusBadge>
      ),
    },
    {
      title: t("connections.columns.createdAt"),
      dataIndex: "created_at",
      key: "created_at",
      width: 170,
      render: (v: string) => new Date(v).toLocaleString("zh-CN"),
    },
    {
      title: t("connections.columns.actions"),
      key: "actions",
      width: 260,
      render: (_: unknown, record: PLMConnection) => (
        <Space size="small">
          {canEditPlm && (
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              onClick={() => openEdit(record)}
            >
              {tc("actions.edit")}
            </Button>
          )}
          {canEditPlm && (
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
          {canAdminPlm && (
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
  ], [canEditPlm, canAdminPlm, testLoading, syncLoading, t, tc, connectorOptions]);

  return (
    <PageShell
      title={t("connections.title")}
      actions={
        canCreatePlm && (
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            {t("connections.new")}
          </Button>
        )
      }
    >
      <DataCard title={t("connections.listTitle")}>
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
          className="qf-table"
        />
      </DataCard>

      <Modal
        title={editingId ? t("connections.editTitle") : t("connections.newTitle")}
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
          <Form.Item
            name="product_line_code"
            label={t("connections.form.productLineCode")}
            rules={[{ required: true, message: t("connections.form.productLineCodeRequired") }]}
          >
            <Input placeholder={t("connections.form.productLineCodePlaceholder")} />
          </Form.Item>
          <Form.Item name="config_port" label={t("connections.form.port")}>
            <InputNumber
              style={{ width: "100%" }}
              placeholder={t("connections.form.portPlaceholder")}
              min={1}
              max={65535}
            />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}

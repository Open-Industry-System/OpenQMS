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
  fetchERPConnections, createERPConnection, updateERPConnection,
  deleteERPConnection, testERPConnection, triggerERPSync,
} from "../../api/erp";
import type { ERPConnection } from "../../types/erp";
import { usePermission } from "../../hooks/usePermission";
import { PageShell, DataCard, StatusBadge } from "../../components/design";
import { formatDateTime } from "../../utils/dateTime";

export default function ERPConnectionsPage() {
  const { t } = useTranslation("erp");
  const { t: tc } = useTranslation("common");

  const typeLabels: Record<string, string> = {
    mock: t("connections.typeLabels.mock", "Mock"),
    rest: t("connections.typeLabels.rest", "REST API"),
    sap: t("connections.typeLabels.sap", "SAP"),
    oracle_ebs: t("connections.typeLabels.oracle_ebs", "Oracle EBS"),
    kingdee: t("connections.typeLabels.kingdee", "金蝶"),
    yonyou: t("connections.typeLabels.yonyou", "用友"),
  };
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
    { value: "mock", label: t("connections.connector.mock", "Mock - 模拟数据") },
    { value: "rest", label: t("connections.connector.rest", "REST API") },
    { value: "sap", label: t("connections.connector.sap", "SAP - 未实现"), disabled: true },
    { value: "oracle_ebs", label: t("connections.connector.oracle_ebs", "Oracle EBS - 未实现"), disabled: true },
    { value: "kingdee", label: t("connections.connector.kingdee", "金蝶 - 未实现"), disabled: true },
    { value: "yonyou", label: t("connections.connector.yonyou", "用友 - 未实现"), disabled: true },
  ], [t]);

  const fetchData = (p: number = page) => {
    setLoading(true);
    fetchERPConnections(p, 20)
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error(t("connections.messages.loadFailed", "加载连接列表失败")))
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
      message.success(t("connections.messages.createSuccess", "连接创建成功"));
      setModalOpen(false);
      form.resetFields();
      setConnectorType(null);
      fetchData(1);
    } catch {
      message.error(t("connections.messages.createFailed", "创建失败"));
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
      message.success(t("connections.messages.updateSuccess", "连接更新成功"));
      setModalOpen(false);
      setEditingId(null);
      form.resetFields();
      setConnectorType(null);
      fetchData(page);
    } catch {
      message.error(t("connections.messages.updateFailed", "更新失败"));
    }
  };

  const handleDelete = (id: string, name: string) => {
    modalConfirm.confirm({
      title: t("connections.deleteConfirm.title", "确认删除"),
      content: t("connections.deleteConfirm.content", '确定删除连接 "{{name}}" 吗？', { name }),
      onOk: async () => {
        try {
          await deleteERPConnection(id);
          message.success(t("connections.messages.deleteSuccess", "删除成功"));
          fetchData(page);
        } catch {
          message.error(t("connections.messages.deleteFailed", "删除失败"));
        }
      },
    });
  };

  const handleTest = async (id: string) => {
    setTestLoading((prev) => ({ ...prev, [id]: true }));
    try {
      const res = await testERPConnection(id);
      if (res.success) {
        message.success(t("connections.messages.testSuccess", "连接测试成功"));
      } else {
        message.error(res.message
          ? t("connections.messages.testFailedWithMsg", "连接测试失败: {{message}}", { message: res.message })
          : t("connections.messages.testFailed", "连接测试失败"));
      }
    } catch {
      message.error(t("connections.messages.testFailed", "连接测试失败"));
    } finally {
      setTestLoading((prev) => ({ ...prev, [id]: false }));
    }
  };

  const handleSync = async (id: string) => {
    setSyncLoading((prev) => ({ ...prev, [id]: true }));
    try {
      await triggerERPSync(id);
      message.success(t("connections.messages.syncTriggered", "同步已触发，后台将在 30 秒内开始执行"));
    } catch {
      message.error(t("connections.messages.syncFailed", "同步触发失败"));
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
    { title: t("connections.columns.name", "连接名称"), dataIndex: "name", key: "name", ellipsis: true },
    {
      title: t("connections.columns.type", "类型"),
      dataIndex: "connector_type",
      key: "connector_type",
      width: 140,
      render: (v: string) => typeLabels[v] || v,
    },
    {
      title: t("connections.columns.productLine", "产线代码"),
      dataIndex: "product_line_code",
      key: "product_line_code",
      width: 120,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("connections.columns.status", "状态"),
      dataIndex: "is_active",
      key: "is_active",
      width: 80,
      render: (active: boolean) => (
        <StatusBadge status={active ? "ok" : "error"}>
          {active ? t("connections.status.active", "正常") : t("connections.status.inactive", "停用")}
        </StatusBadge>
      ),
    },
    {
      title: t("connections.columns.createdAt", "创建时间"),
      dataIndex: "created_at",
      key: "created_at",
      width: 170,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: tc("table.operations", "操作"),
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
              {tc("actions.edit", "编辑")}
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
                {t("connections.actions.test", "测试")}
              </Button>
              <Button
                type="link"
                size="small"
                icon={<SyncOutlined />}
                loading={syncLoading[record.connection_id]}
                onClick={() => handleSync(record.connection_id)}
              >
                {t("connections.actions.sync", "同步")}
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
              {tc("actions.delete", "删除")}
            </Button>
          )}
        </Space>
      ),
    },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [canEditErp, canAdminErp, testLoading, syncLoading, t, tc]);

  return (
    <PageShell
      title={t("connections.title", "ERP 连接管理")}
      actions={
        canCreateErp && (
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            {t("connections.actions.create", "新建连接")}
          </Button>
        )
      }
    >
      <DataCard title={t("connections.cardTitle", "连接列表")}>
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
        title={editingId ? t("connections.modal.editTitle", "编辑连接") : t("connections.modal.createTitle", "新建连接")}
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
            label={t("connections.form.name", "连接名称")}
            rules={[{ required: true, message: t("connections.form.nameRequired", "请输入连接名称") }]}
          >
            <Input placeholder={t("connections.form.namePlaceholder", "如 ERP-SAP-01")} />
          </Form.Item>
          <Form.Item
            name="connector_type"
            label={t("connections.form.connectorType", "连接器类型")}
            rules={[{ required: true, message: t("connections.form.connectorTypeRequired", "请选择连接器类型") }]}
          >
            <Select
              onChange={(v) => setConnectorType(v)}
              options={connectorOptions}
            />
          </Form.Item>
          <Form.Item
            name="product_line_code"
            label={t("connections.form.productLineCode", "产线代码")}
            rules={[{ required: true, message: t("connections.form.productLineCodeRequired", "请输入产线代码") }]}
          >
            <Input placeholder={t("connections.form.productLineCodePlaceholder", "如 DC-DC-100")} />
          </Form.Item>
          {showRestConfig && (
            <>
              <Form.Item name="config_base_url" label="Base URL">
                <Input placeholder={t("connections.form.baseUrlPlaceholder", "如 https://erp.example.com/api")} />
              </Form.Item>
              <Form.Item name="config_port" label={t("connections.form.port", "端口号")}>
                <InputNumber
                  style={{ width: "100%" }}
                  placeholder={t("connections.form.portPlaceholder", "如 8080")}
                  min={1}
                  max={65535}
                />
              </Form.Item>
              <Form.Item name="config_api_key" label="API Key">
                <Input.Password placeholder={t("connections.form.apiKeyPlaceholder", "API 密钥")} />
              </Form.Item>
            </>
          )}
        </Form>
      </Modal>
    </PageShell>
  );
}
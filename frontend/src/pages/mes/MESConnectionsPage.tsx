import { useEffect, useState, useMemo } from "react";
import {
  Table, Button, Modal, Form, Input, Select, App, Space,
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
import { PageShell, StatusBadge } from "../../components/design";

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

  const typeLabels = useMemo(() => ({
    mock: t("connections.connector.mock", "Mock - 模拟数据"),
    rest: t("connections.connector.rest", "REST API"),
  }), [t]);

  const connectorTypeOptions = useMemo(() => [
    { value: "mock", label: t("connections.connector.mock", "Mock - 模拟数据") },
    { value: "rest", label: t("connections.connector.rest", "REST API") },
  ], [t]);

  const statusLabels = useMemo(() => ({
    active: t("connections.status.active", "正常"),
    inactive: t("connections.status.inactive", "停用"),
  }), [t]);

  const fetchData = (p: number = page) => {
    setLoading(true);
    listConnections(p, 20)
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

  const handleCreate = async (values: MESConnectionCreate) => {
    try {
      await createConnection(values);
      message.success(t("connections.messages.createSuccess", "连接创建成功"));
      setModalOpen(false);
      form.resetFields();
      fetchData(1);
    } catch {
      message.error(t("connections.messages.createFailed", "创建失败"));
    }
  };

  const handleUpdate = async (values: Partial<MESConnectionCreate>) => {
    if (!editingId) return;
    try {
      await updateConnection(editingId, values);
      message.success(t("connections.messages.updateSuccess", "连接更新成功"));
      setModalOpen(false);
      setEditingId(null);
      form.resetFields();
      fetchData(page);
    } catch {
      message.error(t("connections.messages.updateFailed", "更新失败"));
    }
  };

  const handleDelete = (id: string, name: string) => {
    modalConfirm.confirm({
      title: t("connections.deleteConfirm.title", "确认删除"),
      content: t("connections.deleteConfirm.content", "确定删除连接 \"{{name}}\" 吗？", { name }),
      onOk: async () => {
        try {
          await deleteConnection(id);
          message.success(tc("messages.deleteSuccess", "删除成功"));
          fetchData(page);
        } catch {
          message.error(tc("messages.operationFailed", "删除失败"));
        }
      },
    });
  };

  const handleTest = async (id: string) => {
    try {
      const res = await testConnection(id);
      if (res.ok) {
        message.success(t("connections.messages.testSuccess", "连接测试成功"));
      } else {
        message.error(t("connections.messages.testFailedWithError", "连接测试失败: {{error}}", { error: res.error || "Unknown error" }));
      }
    } catch {
      message.error(t("connections.messages.testFailed", "连接测试失败"));
    }
  };

  const handleSync = async (id: string) => {
    try {
      await manualSync(id);
      message.success(t("connections.messages.syncTriggered", "同步已触发，后台将在 30 秒内开始执行"));
    } catch {
      message.error(t("connections.messages.syncFailed", "同步触发失败"));
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

  const columns = useMemo(() => [
    { title: t("connections.columns.name", "连接名称"), dataIndex: "name", key: "name", ellipsis: true },
    {
      title: t("connections.columns.type", "类型"),
      dataIndex: "connector_type",
      key: "connector_type",
      width: 100,
      render: (ct: string) => typeLabels[ct as keyof typeof typeLabels] || ct,
    },
    {
      title: t("connections.columns.status", "状态"),
      dataIndex: "is_active",
      key: "is_active",
      width: 80,
      render: (active: boolean) => (
        <StatusBadge status={active ? "completed" : "failed"}>
          {active ? statusLabels.active : statusLabels.inactive}
        </StatusBadge>
      ),
    },
    {
      title: t("connections.columns.productLine", "产线"),
      dataIndex: "product_line_code",
      key: "product_line_code",
      width: 120,
      render: (v: string | null) => v || "—",
    },
    {
      title: tc("table.operations", "操作"),
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
            {tc("actions.edit", "编辑")}
          </Button>
          <Button
            type="link"
            size="small"
            icon={<ApiOutlined />}
            onClick={() => handleTest(record.connection_id)}
          >
            {t("connections.test", "测试")}
          </Button>
          <Button
            type="link"
            size="small"
            icon={<SyncOutlined />}
            onClick={() => handleSync(record.connection_id)}
          >
            {t("connections.sync", "同步")}
          </Button>
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(record.connection_id, record.name)}
          >
            {tc("actions.delete", "删除")}
          </Button>
        </Space>
      ),
    },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [t, tc, typeLabels, statusLabels]);

  return (
    <PageShell
      title={t("connections.title", "MES 连接管理")}
      actions={
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          {t("connections.create", "新建连接")}
        </Button>
      }
    >
      <Table
        className="qf-table"
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
        title={editingId ? t("connections.modal.editTitle", "编辑连接") : t("connections.modal.createTitle", "新建连接")}
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
            label={t("connections.form.name", "连接名称")}
            rules={[{ required: true, message: t("connections.form.nameRequired", "请输入连接名称") }]}
          >
            <Input placeholder={t("connections.form.namePlaceholder", "如 产线A-MES")} />
          </Form.Item>
          <Form.Item
            name="connector_type"
            label={t("connections.form.connectorType", "连接器类型")}
            rules={[{ required: true, message: t("connections.form.connectorTypeRequired", "请选择连接器类型") }]}
          >
            <Select options={connectorTypeOptions} />
          </Form.Item>
          <Form.Item name="product_line_code" label={t("connections.form.productLineCode", "产线代码")}>
            <Input placeholder={t("connections.form.productLineCodePlaceholder", "如 DC-DC-100")} />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}
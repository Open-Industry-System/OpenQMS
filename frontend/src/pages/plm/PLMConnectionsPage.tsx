import { useEffect, useMemo, useState } from "react";
import {
  Table, Button, Tag, Typography, Modal, Form, Input, Select, App, Space,
  InputNumber,
} from "antd";
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ApiOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import {
  getPLMConnections, createPLMConnection, updatePLMConnection,
  deletePLMConnection, testPLMConnection, syncPLMConnection,
} from "../../api/plm";
import type { PLMConnection, PLMConnectionCreate, PLMConnectionUpdate } from "../../types/plm";
import { usePermission } from "../../hooks/usePermission";

const { Title } = Typography;

const typeLabels: Record<string, string> = {
  mock: "Mock",
  rest: "REST API",
  siemens_tc: "Siemens Teamcenter",
  dassault_enovia: "Dassault ENOVIA",
  ptc_windchill: "PTC Windchill",
};

export default function PLMConnectionsPage() {
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

  const fetchData = (p: number = page) => {
    setLoading(true);
    getPLMConnections(p, 20)
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error("加载连接列表失败"))
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
      message.success("连接创建成功");
      setModalOpen(false);
      form.resetFields();
      fetchData(1);
    } catch {
      message.error("创建失败");
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
      message.success("连接更新成功");
      setModalOpen(false);
      setEditingId(null);
      form.resetFields();
      fetchData(page);
    } catch {
      message.error("更新失败");
    }
  };

  const handleDelete = (id: string, name: string) => {
    modalConfirm.confirm({
      title: "确认删除",
      content: `确定删除连接 "${name}" 吗？`,
      onOk: async () => {
        try {
          await deletePLMConnection(id);
          message.success("删除成功");
          fetchData(page);
        } catch {
          message.error("删除失败");
        }
      },
    });
  };

  const handleTest = async (id: string) => {
    setTestLoading((prev) => ({ ...prev, [id]: true }));
    try {
      const res = await testPLMConnection(id);
      if (res.status === "ok") {
        message.success(`连接测试成功，读取 ${res.parts_count ?? 0} 个物料`);
      } else {
        message.error(res.error ? `连接测试失败: ${res.error}` : "连接测试失败");
      }
    } catch {
      message.error("连接测试失败");
    } finally {
      setTestLoading((prev) => ({ ...prev, [id]: false }));
    }
  };

  const handleSync = async (id: string) => {
    setSyncLoading((prev) => ({ ...prev, [id]: true }));
    try {
      const res = await syncPLMConnection(id);
      message.success(`同步已触发，共 ${res.synced_jobs} 个任务`);
    } catch {
      message.error("同步触发失败");
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
    { title: "连接名称", dataIndex: "name", key: "name", ellipsis: true },
    {
      title: "类型",
      dataIndex: "connector_type",
      key: "connector_type",
      width: 140,
      render: (t: string) => typeLabels[t] || t,
    },
    {
      title: "产线代码",
      dataIndex: "product_line_code",
      key: "product_line_code",
      width: 120,
      render: (v: string | null) => v || "—",
    },
    {
      title: "状态",
      dataIndex: "is_active",
      key: "is_active",
      width: 80,
      render: (active: boolean) => (
        <Tag color={active ? "success" : "error"}>
          {active ? "正常" : "停用"}
        </Tag>
      ),
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      key: "created_at",
      width: 170,
      render: (v: string) => new Date(v).toLocaleString("zh-CN"),
    },
    {
      title: "操作",
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
              编辑
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
                测试
              </Button>
              <Button
                type="link"
                size="small"
                icon={<SyncOutlined />}
                loading={syncLoading[record.connection_id]}
                onClick={() => handleSync(record.connection_id)}
              >
                同步
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
              删除
            </Button>
          )}
        </Space>
      ),
    },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [canEditPlm, canAdminPlm, testLoading, syncLoading]);

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
          PLM 连接管理
        </Title>
        {canCreatePlm && (
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建连接
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
        title={editingId ? "编辑连接" : "新建连接"}
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
            label="连接名称"
            rules={[{ required: true, message: "请输入连接名称" }]}
          >
            <Input placeholder="如 PLM-Teamcenter-01" />
          </Form.Item>
          <Form.Item
            name="connector_type"
            label="连接器类型"
            rules={[{ required: true, message: "请选择连接器类型" }]}
          >
            <Select
              options={[
                { value: "mock", label: "Mock - 模拟数据" },
                { value: "rest", label: "REST API - 未实现", disabled: true },
                { value: "siemens_tc", label: "Siemens Teamcenter - 未实现", disabled: true },
                { value: "dassault_enovia", label: "Dassault ENOVIA - 未实现", disabled: true },
                { value: "ptc_windchill", label: "PTC Windchill - 未实现", disabled: true },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="product_line_code"
            label="产线代码"
            rules={[{ required: true, message: "请输入产线代码" }]}
          >
            <Input placeholder="如 DC-DC-100" />
          </Form.Item>
          <Form.Item name="config_port" label="端口号">
            <InputNumber
              style={{ width: "100%" }}
              placeholder="如 8080"
              min={1}
              max={65535}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

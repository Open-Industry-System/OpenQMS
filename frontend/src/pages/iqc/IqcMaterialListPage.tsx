import { useState, useEffect, useCallback, useRef } from "react";
import {
  Card,
  Table,
  Button,
  Tag,
  Space,
  Input,
  App,
  Modal,
  Form,
  InputNumber,
  Select,
  Popconfirm,
} from "antd";
import {
  PlusOutlined,
  ReloadOutlined,
  EditOutlined,
  DeleteOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";
import type { IqcMaterial } from "../../types";
import { listMaterials, createMaterial, updateMaterial, deleteMaterial, importMaterials, downloadMaterialImportTemplate } from "../../api/iqc";
import ImportExcelDialog from "../../components/shared/ImportExcelDialog";

const { Option } = Select;

export default function IqcMaterialListPage() {
  const { message } = App.useApp();
  const user = useAuthStore((s) => s.user);
  const { canEdit, isAdmin } = usePermission();

  const [materials, setMaterials] = useState<IqcMaterial[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [search, setSearch] = useState("");

  const [importOpen, setImportOpen] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingMaterial, setEditingMaterial] = useState<IqcMaterial | null>(null);
  const [form] = Form.useForm();

  const fetchMaterials = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page, page_size: pageSize };
      if (search) params.search = search;
      const resp = await listMaterials(params);
      setMaterials(resp.items);
      setTotal(resp.total);
    } catch {
      message.error("加载物料列表失败");
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, search, message]);

  useEffect(() => {
    fetchMaterials();
  }, [fetchMaterials]);

  const handleRefresh = () => fetchMaterials();

  const handleQuery = () => {
    setPage(1);
    fetchMaterials();
  };

  const handleOpenCreate = () => {
    setEditingMaterial(null);
    form.resetFields();
    setModalOpen(true);
  };

  const handleOpenEdit = (mat: IqcMaterial) => {
    setEditingMaterial(mat);
    form.setFieldsValue(mat);
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editingMaterial) {
        await updateMaterial(editingMaterial.material_id, values);
        message.success("物料已更新");
      } else {
        await createMaterial(values);
        message.success("物料已创建");
      }
      setModalOpen(false);
      fetchMaterials();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      if (err.response?.data?.detail) {
        message.error(err.response.data.detail);
      }
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteMaterial(id);
      message.success("物料已删除");
      fetchMaterials();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "删除失败");
    }
  };

  const columns = [
    {
      title: "物料号",
      dataIndex: "part_no",
      width: 140,
      render: (no: string) => <span style={{ fontFamily: "monospace" }}>{no}</span>,
    },
    {
      title: "物料名称",
      dataIndex: "part_name",
      ellipsis: true,
    },
    {
      title: "规格",
      dataIndex: "part_spec",
      width: 160,
      render: (v: string | null) => v || "—",
    },
    {
      title: "类型",
      dataIndex: "material_type",
      width: 100,
      render: (v: string) => <Tag>{v === "raw" ? "原材料" : v}</Tag>,
    },
    {
      title: "默认AQL",
      dataIndex: "default_aql",
      width: 100,
      render: (v: number | null) => v ?? "—",
    },
    {
      title: "检验水平",
      dataIndex: "default_inspection_level",
      width: 100,
      render: (v: string | null) => v || "—",
    },
    {
      title: "单位",
      dataIndex: "unit",
      width: 80,
      render: (v: string | null) => v || "—",
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 80,
      render: (status: string) => (
        <Tag color={status === "active" ? "green" : "default"}>
          {status === "active" ? "启用" : "停用"}
        </Tag>
      ),
    },
    {
      title: "操作",
      width: 150,
      render: (_: unknown, record: IqcMaterial) => (
        <Space size="small">
          {canEdit('iqc') && (
            <Button
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleOpenEdit(record)}
            >
              编辑
            </Button>
          )}
          {isAdmin && (
            <Popconfirm
              title="确认删除该物料？"
              onConfirm={() => handleDelete(record.material_id)}
            >
              <Button size="small" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Card
        title="物料管理"
        extra={
          <Space>
            {canEdit('iqc') && (
              <Button type="primary" icon={<PlusOutlined />} onClick={handleOpenCreate}>
                新增物料
              </Button>
            )}
            {canEdit('iqc') && (
              <Button icon={<UploadOutlined />} onClick={() => setImportOpen(true)}>
                导入物料
              </Button>
            )}
            <Button icon={<ReloadOutlined />} onClick={handleRefresh}>
              刷新
            </Button>
          </Space>
        }
      >
        <Space style={{ marginBottom: 16 }}>
          <Input
            placeholder="搜索物料号 / 物料名称"
            allowClear
            style={{ width: 280 }}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onPressEnter={handleQuery}
          />
          <Button type="primary" onClick={handleQuery}>
            查询
          </Button>
        </Space>

        <Table
          rowKey="material_id"
          columns={columns}
          dataSource={materials}
          loading={loading}
          pagination={{
            current: page,
            pageSize: pageSize,
            total: total,
            showSizeChanger: true,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps || 20);
            },
          }}
        />
      </Card>

      <Modal
        title={editingMaterial ? "编辑物料" : "新增物料"}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        okText="保存"
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="part_no"
            label="物料号"
            rules={[{ required: true, message: "请输入物料号" }]}
          >
            <Input disabled={!!editingMaterial} placeholder="如: RES-0805-10K" />
          </Form.Item>
          <Form.Item
            name="part_name"
            label="物料名称"
            rules={[{ required: true, message: "请输入物料名称" }]}
          >
            <Input placeholder="如: 0805贴片电阻 10KΩ" />
          </Form.Item>
          <Form.Item name="part_spec" label="规格型号">
            <Input placeholder="如: ±1% 1/8W" />
          </Form.Item>
          <Form.Item name="material_type" label="物料类型" initialValue="raw">
            <Select>
              <Option value="raw">原材料</Option>
              <Option value="component">元器件</Option>
              <Option value="part">零件</Option>
              <Option value="other">其他</Option>
            </Select>
          </Form.Item>
          <Form.Item name="default_aql" label="默认AQL">
            <InputNumber min={0} step={0.1} style={{ width: "100%" }} placeholder="如: 0.65" />
          </Form.Item>
          <Form.Item name="default_inspection_level" label="默认检验水平">
            <Select allowClear placeholder="选择检验水平">
              <Option value="I">I</Option>
              <Option value="II">II</Option>
              <Option value="III">III</Option>
              <Option value="S-1">S-1</Option>
              <Option value="S-2">S-2</Option>
              <Option value="S-3">S-3</Option>
              <Option value="S-4">S-4</Option>
            </Select>
          </Form.Item>
          <Form.Item name="unit" label="单位">
            <Input placeholder="如: pcs, kg, m" />
          </Form.Item>
        </Form>
      </Modal>

      <ImportExcelDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={() => fetchMaterials()}
        importFn={(file) => importMaterials(file)}
        templateDownloadFn={downloadMaterialImportTemplate}
        hint="每行: 物料号*, 名称*, 规格, 类型, 默认AQL, 检验水平, 单位, 产品线"
      />
    </div>
  );
}

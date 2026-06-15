import { useState, useEffect, useCallback, useMemo } from "react";
import {
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
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";
import type { IqcMaterial } from "../../types";
import { listMaterials, createMaterial, updateMaterial, deleteMaterial, importMaterials, downloadMaterialImportTemplate } from "../../api/iqc";
import ImportExcelDialog from "../../components/shared/ImportExcelDialog";
import { PageShell, DataCard, StatusBadge } from "../../components/design";

const { Option } = Select;

export default function IqcMaterialListPage() {
  const { t } = useTranslation("iqc");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const _user = useAuthStore((s) => s.user);
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
      message.error(t("messages.loadMaterialListFailed"));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, search, message, t]);

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

  const handleOpenEdit = useCallback((mat: IqcMaterial) => {
    setEditingMaterial(mat);
    form.setFieldsValue(mat);
    setModalOpen(true);
  }, [form]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editingMaterial) {
        await updateMaterial(editingMaterial.material_id, values);
        message.success(t("messages.materialUpdated"));
      } else {
        await createMaterial(values);
        message.success(t("messages.materialCreated"));
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

  const handleDelete = useCallback(async (id: string) => {
    try {
      await deleteMaterial(id);
      message.success(t("messages.materialDeleted"));
      fetchMaterials();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed"));
    }
  }, [t, message, fetchMaterials, tc]);

  const columns = useMemo(
    () => [
      {
        title: t("table.partNo"),
        dataIndex: "part_no",
        width: 140,
        render: (no: string) => <span style={{ fontFamily: "monospace" }}>{no}</span>,
      },
      {
        title: t("table.partName"),
        dataIndex: "part_name",
        ellipsis: true,
      },
      {
        title: t("table.specification"),
        dataIndex: "part_spec",
        width: 160,
        render: (v: string | null) => v || "—",
      },
      {
        title: t("table.type"),
        dataIndex: "material_type",
        width: 100,
        render: (v: string) => {
          const labels: Record<string, string> = {
            raw: t("materialType.raw"),
            component: t("materialType.component"),
            part: t("materialType.part"),
            other: t("materialType.other"),
          };
          return <StatusBadge status="info">{labels[v] || v}</StatusBadge>;
        },
      },
      {
        title: t("table.defaultAql"),
        dataIndex: "default_aql",
        width: 100,
        render: (v: number | null) => v ?? "—",
      },
      {
        title: t("table.defaultInspectionLevel"),
        dataIndex: "default_inspection_level",
        width: 100,
        render: (v: string | null) => v || "—",
      },
      {
        title: t("table.unit"),
        dataIndex: "unit",
        width: 80,
        render: (v: string | null) => v || "—",
      },
      {
        title: t("table.status"),
        dataIndex: "status",
        width: 80,
        render: (status: string) => (
          <StatusBadge status={status === "active" ? "closed" : "normal"}>
            {status === "active" ? tc("status.active") : tc("status.inactive")}
          </StatusBadge>
        ),
      },
      {
        title: t("table.operations"),
        width: 150,
        render: (_: unknown, record: IqcMaterial) => (
          <Space size="small">
            {canEdit('iqc') && (
              <Button
                size="small"
                icon={<EditOutlined />}
                onClick={() => handleOpenEdit(record)}
              >
                {tc("actions.edit")}
              </Button>
            )}
            {isAdmin && (
              <Popconfirm
                title={t("list.confirmDeleteMaterial")}
                onConfirm={() => handleDelete(record.material_id)}
              >
                <Button size="small" danger icon={<DeleteOutlined />}>
                  {tc("actions.delete")}
                </Button>
              </Popconfirm>
            )}
          </Space>
        ),
      },
    ],
    [t, tc, canEdit, isAdmin, handleDelete, handleOpenEdit]
  );

  return (
    <PageShell
      title={t("pageTitle.materialList")}
      actions={
        <Space>
          {canEdit('iqc') && (
            <Button type="primary" icon={<PlusOutlined />} onClick={handleOpenCreate}>
              {t("actions.newMaterial")}
            </Button>
          )}
          {canEdit('iqc') && (
            <Button icon={<UploadOutlined />} onClick={() => setImportOpen(true)}>
              {t("actions.importMaterial")}
            </Button>
          )}
          <Button icon={<ReloadOutlined />} onClick={handleRefresh}>
            {tc("actions.refresh")}
          </Button>
        </Space>
      }
    >
      <DataCard title={t("pageTitle.materialList")}>
        <Space style={{ marginBottom: 16 }}>
          <Input
            placeholder={t("placeholder.materialSearch")}
            allowClear
            style={{ width: 280 }}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onPressEnter={handleQuery}
          />
          <Button type="primary" onClick={handleQuery}>
            {tc("actions.search")}
          </Button>
        </Space>

        <Table
          className="qf-table"
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
      </DataCard>

      <Modal
        title={editingMaterial ? t("modal.editMaterial") : t("modal.newMaterial")}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        okText={tc("actions.save")}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="part_no"
            label={t("form.partNo")}
            rules={[{ required: true, message: t("validation.enterPartNo") }]}
          >
            <Input disabled={!!editingMaterial} placeholder={t("placeholder.partNoExample")} />
          </Form.Item>
          <Form.Item
            name="part_name"
            label={t("form.partName")}
            rules={[{ required: true, message: t("validation.enterPartName") }]}
          >
            <Input placeholder={t("placeholder.partNameExample")} />
          </Form.Item>
          <Form.Item name="part_spec" label={t("form.specification")}>
            <Input placeholder={t("placeholder.specExample")} />
          </Form.Item>
          <Form.Item name="material_type" label={t("form.materialType")} initialValue="raw">
            <Select>
              <Option value="raw">{t("materialType.raw")}</Option>
              <Option value="component">{t("materialType.component")}</Option>
              <Option value="part">{t("materialType.part")}</Option>
              <Option value="other">{t("materialType.other")}</Option>
            </Select>
          </Form.Item>
          <Form.Item name="default_aql" label={t("form.defaultAql")}>
            <InputNumber min={0} step={0.1} style={{ width: "100%" }} placeholder={t("placeholder.aqlExample")} />
          </Form.Item>
          <Form.Item name="default_inspection_level" label={t("form.defaultInspectionLevel")}>
            <Select allowClear placeholder={t("placeholder.selectInspectionLevel")}>
              <Option value="I">I</Option>
              <Option value="II">II</Option>
              <Option value="III">III</Option>
              <Option value="S-1">S-1</Option>
              <Option value="S-2">S-2</Option>
              <Option value="S-3">S-3</Option>
              <Option value="S-4">S-4</Option>
            </Select>
          </Form.Item>
          <Form.Item name="unit" label={t("form.unit")}>
            <Input placeholder={t("placeholder.unitExample")} />
          </Form.Item>
        </Form>
      </Modal>

      <ImportExcelDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={() => fetchMaterials()}
        importFn={(file) => importMaterials(file)}
        templateDownloadFn={downloadMaterialImportTemplate}
        hint={t("import.materialHint")}
      />
    </PageShell>
  );
}

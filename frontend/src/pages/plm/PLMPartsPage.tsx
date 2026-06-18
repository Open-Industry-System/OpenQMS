import { useEffect, useState, useCallback } from "react";
import {
  Table,
  Input,
  Button,
  Tag,
  Drawer,
  Descriptions,
  App,
  Space,
  Modal,
  Form,
  Select,
  Checkbox,
} from "antd";
import { useTranslation } from "react-i18next";
import {
  getPLMParts,
  getPLMBOMTree,
  importBOMToFMEA,
  confirmPLMPartSC,
} from "../../api/plm";
import { usePermission } from "../../hooks/usePermission";
import { useProductLineStore } from "../../store/productLineStore";
import { PageShell, DataCard, StatusBadge } from "../../components/design";
import type {
  PLMPart,
  PLMBOMTreeNode,
  PLMPartConfirmSCRequest,
} from "../../types/plm";

export default function PLMPartsPage() {
  const { t } = useTranslation("plm");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const { canEdit, canCreate } = usePermission();
  const canEditPlm = canEdit("plm");
  const canCreateSc = canCreate("special_characteristic");
  const productLine = useProductLineStore((s) => s.selected);
  const [data, setData] = useState<PLMPart[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [drawerPart, setDrawerPart] = useState<PLMPart | null>(null);
  const [bomPart, setBomPart] = useState<PLMPart | null>(null);
  const [bomItems, setBomItems] = useState<PLMBOMTreeNode[]>([]);
  const [bomLoading, setBomLoading] = useState(false);
  const [scPart, setScPart] = useState<PLMPart | null>(null);
  const [scLoading, setScLoading] = useState(false);
  const [bomQueryForm] = Form.useForm();
  const [bomImportForm] = Form.useForm();
  const [scForm] = Form.useForm<PLMPartConfirmSCRequest>();

  const fetchData = useCallback((p: number, q: string, plCode?: string | null) => {
    setLoading(true);
    getPLMParts({
      page: p,
      page_size: 20,
      search: q || undefined,
      product_line_code: plCode || undefined,
    })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error(t("parts.messages.loadFailed")))
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setPage(1);
    fetchData(1, search, productLine);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine]);

  const handleSearch = (value: string) => {
    setSearch(value);
    setPage(1);
    fetchData(1, value, productLine);
  };

  const getPendingScLinks = (part: PLMPart) =>
    (part.sc_links || []).filter((link) => link.status === "pending");

  const openBomModal = (part: PLMPart) => {
    const revision = part.revision || "A";
    setBomPart(part);
    setBomItems([]);
    bomQueryForm.setFieldsValue({
      revision,
      bom_revision: revision,
    });
    bomImportForm.setFieldsValue({
      fmea_id: "",
      overwrite: false,
    });
  };

  const queryBom = async () => {
    if (!bomPart) return;
    const values = await bomQueryForm.validateFields(["revision", "bom_revision"]);
    setBomLoading(true);
    try {
      const res = await getPLMBOMTree(bomPart.connection_id, bomPart.part_number, {
        revision: values.revision,
        bom_revision: values.bom_revision,
      });
      setBomItems(res.items);
    } catch {
      message.error(t("parts.messages.queryBomFailed"));
    } finally {
      setBomLoading(false);
    }
  };

  const handleImportBom = async () => {
    if (!bomPart) return;
    const queryValues = await bomQueryForm.validateFields(["revision", "bom_revision"]);
    const importValues = await bomImportForm.validateFields();
    setBomLoading(true);
    try {
      await importBOMToFMEA(
        bomPart.connection_id,
        bomPart.part_number,
        { fmea_id: importValues.fmea_id, overwrite: importValues.overwrite },
        { revision: queryValues.revision, bom_revision: queryValues.bom_revision },
      );
      message.success(t("parts.messages.importFMEASuccess"));
      setBomPart(null);
    } catch {
      message.error(t("parts.messages.importFMEAFailed"));
    } finally {
      setBomLoading(false);
    }
  };

  const openScModal = (part: PLMPart) => {
    const pendingLinks = getPendingScLinks(part);
    setScPart(part);
    scForm.setFieldsValue({
      characteristic_type: pendingLinks.length === 1
        ? pendingLinks[0].characteristic_type as PLMPartConfirmSCRequest["characteristic_type"]
        : undefined,
      fmea_id: "",
      node_id: "",
    });
  };

  const handleConfirmSc = async () => {
    if (!scPart) return;
    const values: PLMPartConfirmSCRequest = await scForm.validateFields();
    setScLoading(true);
    try {
      await confirmPLMPartSC(scPart.part_id, values);
      message.success(t("parts.messages.scConfirmed"));
      setScPart(null);
      fetchData(page, search, productLine);
    } catch {
      message.error(t("parts.messages.scConfirmFailed"));
    } finally {
      setScLoading(false);
    }
  };

  const columns = [
    { title: t("parts.columns.partNumber"), dataIndex: "part_number", key: "part_number", width: 160 },
    { title: t("parts.columns.name"), dataIndex: "name", key: "name", ellipsis: true },
    { title: t("parts.columns.revision"), dataIndex: "revision", key: "revision", width: 80 },
    {
      title: t("parts.columns.status"),
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (s: string) => <StatusBadge status={s}>{s}</StatusBadge>,
    },
    {
      title: t("parts.columns.safetyRelated"),
      dataIndex: "is_safety_related",
      key: "is_safety_related",
      width: 80,
      render: (v: boolean) => (v ? <Tag color="red">{tc("yes")}</Tag> : tc("no")),
    },
    {
      title: t("parts.columns.keyCharacteristic"),
      dataIndex: "is_key_characteristic",
      key: "is_key_characteristic",
      width: 80,
      render: (v: boolean) => (v ? <Tag color="orange">{tc("yes")}</Tag> : tc("no")),
    },
    {
      title: t("parts.columns.actions"),
      key: "actions",
      width: 220,
      render: (_: unknown, record: PLMPart) => {
        const hasPendingScLink = getPendingScLinks(record).length > 0;
        return (
          <Space size={4}>
            <Button type="link" size="small" onClick={() => setDrawerPart(record)}>{tc("actions.detail")}</Button>
            <Button type="link" size="small" onClick={() => openBomModal(record)}>BOM</Button>
            {canEditPlm && (
              <Button type="link" size="small" onClick={() => openBomModal(record)}>{t("parts.actions.importFMEA")}</Button>
            )}
            {canEditPlm && canCreateSc && hasPendingScLink && (
              <Button type="link" size="small" onClick={() => openScModal(record)}>{t("parts.actions.confirmSC")}</Button>
            )}
          </Space>
        );
      },
    },
  ];

  const bomColumns = [
    { title: t("parts.bom.columns.parentPartNumber"), dataIndex: "parent_part_number", key: "parent_part_number" },
    { title: t("parts.bom.columns.parentRevision"), dataIndex: "parent_revision", key: "parent_revision", width: 90 },
    { title: t("parts.bom.columns.childPartNumber"), dataIndex: "child_part_number", key: "child_part_number" },
    { title: t("parts.bom.columns.childRevision"), dataIndex: "child_revision", key: "child_revision", width: 90 },
    { title: t("parts.bom.columns.quantity"), dataIndex: "quantity", key: "quantity", width: 90 },
    { title: t("parts.bom.columns.level"), dataIndex: "level", key: "level", width: 80 },
    { title: t("parts.bom.columns.bomRevision"), dataIndex: "bom_revision", key: "bom_revision", width: 100 },
  ];

  return (
    <PageShell
      title={t("parts.title")}
      actions={
        <Input.Search
          placeholder={t("parts.searchPlaceholder")}
          allowClear
          onSearch={handleSearch}
          style={{ width: 280 }}
        />
      }
    >
      <DataCard title={t("parts.listTitle")}>
        <Table
          columns={columns}
          dataSource={data}
          rowKey="part_id"
          loading={loading}
          pagination={{
            current: page,
            total,
            pageSize: 20,
            onChange: (p) => {
              setPage(p);
              fetchData(p, search, productLine);
            },
          }}
          className="qf-table"
        />
      </DataCard>

      <Drawer
        title={t("parts.drawer.title")}
        open={!!drawerPart}
        onClose={() => setDrawerPart(null)}
        width={520}
      >
        {drawerPart && (
          <Descriptions bordered column={1} size="small">
            <Descriptions.Item label={t("parts.drawer.labels.partNumber")}>{drawerPart.part_number}</Descriptions.Item>
            <Descriptions.Item label={t("parts.drawer.labels.name")}>{drawerPart.name}</Descriptions.Item>
            <Descriptions.Item label={t("parts.drawer.labels.revision")}>{drawerPart.revision}</Descriptions.Item>
            <Descriptions.Item label={t("parts.drawer.labels.status")}>{drawerPart.status}</Descriptions.Item>
            <Descriptions.Item label={t("parts.drawer.labels.material")}>{drawerPart.material || "—"}</Descriptions.Item>
            <Descriptions.Item label={t("parts.drawer.labels.specification")}>{drawerPart.specification || "—"}</Descriptions.Item>
            <Descriptions.Item label={t("parts.drawer.labels.safetyRelated")}>
              {drawerPart.is_safety_related ? tc("yes") : tc("no")}
            </Descriptions.Item>
            <Descriptions.Item label={t("parts.drawer.labels.keyCharacteristic")}>
              {drawerPart.is_key_characteristic ? tc("yes") : tc("no")}
            </Descriptions.Item>
            <Descriptions.Item label={t("parts.drawer.labels.externalId")}>{drawerPart.external_id}</Descriptions.Item>
            <Descriptions.Item label={t("parts.drawer.labels.productLineCode")}>
              {drawerPart.product_line_code || "—"}
            </Descriptions.Item>
            <Descriptions.Item label={t("parts.drawer.labels.updatedAt")}>
              {drawerPart.source_updated_at
                ? new Date(drawerPart.source_updated_at).toLocaleString("zh-CN")
                : "—"}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>

      <Modal
        title={t("parts.bom.modalTitle", { partNumber: bomPart?.part_number ?? "" })}
        open={!!bomPart}
        onCancel={() => setBomPart(null)}
        footer={null}
        width={900}
      >
        <Form form={bomQueryForm} layout="inline" style={{ marginBottom: 16 }}>
          <Form.Item name="revision" label={t("parts.bom.partRevision")} rules={[{ required: true, message: t("parts.bom.partRevisionRequired") }]}>
            <Input style={{ width: 120 }} />
          </Form.Item>
          <Form.Item name="bom_revision" label={t("parts.bom.bomRevision")} rules={[{ required: true, message: t("parts.bom.bomRevisionRequired") }]}>
            <Input style={{ width: 120 }} />
          </Form.Item>
          <Form.Item>
            <Button onClick={queryBom} loading={bomLoading}>{t("parts.bom.query")}</Button>
          </Form.Item>
        </Form>
        <Table
          columns={bomColumns}
          dataSource={bomItems}
          rowKey={(record) => `${record.parent_part_number}-${record.child_part_number}-${record.level}`}
          loading={bomLoading}
          pagination={false}
          size="small"
        />
        {canEditPlm && (
          <Form form={bomImportForm} layout="inline" style={{ marginTop: 16 }}>
            <Form.Item name="fmea_id" label={t("parts.bom.import.fmeaId")} rules={[{ required: true, message: t("parts.bom.import.fmeaIdRequired") }]}>
              <Input style={{ width: 260 }} />
            </Form.Item>
            <Form.Item name="overwrite" valuePropName="checked">
              <Checkbox>{t("parts.bom.import.overwrite")}</Checkbox>
            </Form.Item>
            <Form.Item>
              <Button type="primary" onClick={handleImportBom} loading={bomLoading}>{t("parts.bom.import.import")}</Button>
            </Form.Item>
          </Form>
        )}
      </Modal>

      <Modal
        title={t("parts.sc.modalTitle", { partNumber: scPart?.part_number ?? "" })}
        open={!!scPart}
        onCancel={() => setScPart(null)}
        onOk={handleConfirmSc}
        confirmLoading={scLoading}
        okText={tc("actions.confirm")}
        cancelText={tc("actions.cancel")}
      >
        <Form form={scForm} layout="vertical">
          <Form.Item name="characteristic_type" label={t("parts.sc.characteristicType")} rules={[{ required: true, message: t("parts.sc.characteristicTypeRequired") }]}>
            <Select
              options={(scPart ? getPendingScLinks(scPart) : []).map((link) => ({
                value: link.characteristic_type,
                label: link.characteristic_type === "safety" ? t("parts.sc.safety") : t("parts.sc.key"),
              }))}
            />
          </Form.Item>
          <Form.Item name="fmea_id" label={t("parts.sc.fmeaId")} rules={[{ required: true, message: t("parts.sc.fmeaIdRequired") }]}>
            <Input />
          </Form.Item>
          <Form.Item name="node_id" label={t("parts.sc.nodeId")} rules={[{ required: true, message: t("parts.sc.nodeIdRequired") }]}>
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}

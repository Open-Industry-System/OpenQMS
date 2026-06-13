import { useEffect, useState, useCallback } from "react";
import {
  Table,
  Input,
  Button,
  Typography,
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
import {
  getPLMParts,
  getPLMBOMTree,
  importBOMToFMEA,
  confirmPLMPartSC,
} from "../../api/plm";
import { usePermission } from "../../hooks/usePermission";
import { useProductLineStore } from "../../store/productLineStore";
import type {
  PLMPart,
  PLMBOMTreeNode,
  PLMPartConfirmSCRequest,
} from "../../types/plm";

const { Title } = Typography;

export default function PLMPartsPage() {
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
      .catch(() => message.error("加载零件列表失败"))
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
      message.error("查询 BOM 失败");
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
      message.success("BOM 已导入 FMEA");
      setBomPart(null);
    } catch {
      message.error("导入 FMEA 失败");
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
      message.success("特殊特性已确认");
      setScPart(null);
      fetchData(page, search, productLine);
    } catch {
      message.error("确认特殊特性失败");
    } finally {
      setScLoading(false);
    }
  };

  const columns = [
    { title: "零件号", dataIndex: "part_number", key: "part_number", width: 160 },
    { title: "名称", dataIndex: "name", key: "name", ellipsis: true },
    { title: "版本", dataIndex: "revision", key: "revision", width: 80 },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (s: string) => <Tag>{s}</Tag>,
    },
    {
      title: "安全件",
      dataIndex: "is_safety_related",
      key: "is_safety_related",
      width: 80,
      render: (v: boolean) => (v ? <Tag color="red">是</Tag> : "否"),
    },
    {
      title: "关键特性",
      dataIndex: "is_key_characteristic",
      key: "is_key_characteristic",
      width: 80,
      render: (v: boolean) => (v ? <Tag color="orange">是</Tag> : "否"),
    },
    {
      title: "操作",
      key: "actions",
      width: 220,
      render: (_: unknown, record: PLMPart) => {
        const hasPendingScLink = getPendingScLinks(record).length > 0;
        return (
          <Space size={4}>
            <Button type="link" size="small" onClick={() => setDrawerPart(record)}>详情</Button>
            <Button type="link" size="small" onClick={() => openBomModal(record)}>BOM</Button>
            {canEditPlm && (
              <Button type="link" size="small" onClick={() => openBomModal(record)}>导入 FMEA</Button>
            )}
            {canEditPlm && canCreateSc && hasPendingScLink && (
              <Button type="link" size="small" onClick={() => openScModal(record)}>确认SC</Button>
            )}
          </Space>
        );
      },
    },
  ];

  const bomColumns = [
    { title: "父零件号", dataIndex: "parent_part_number", key: "parent_part_number" },
    { title: "父版本", dataIndex: "parent_revision", key: "parent_revision", width: 90 },
    { title: "子零件号", dataIndex: "child_part_number", key: "child_part_number" },
    { title: "子版本", dataIndex: "child_revision", key: "child_revision", width: 90 },
    { title: "数量", dataIndex: "quantity", key: "quantity", width: 90 },
    { title: "层级", dataIndex: "level", key: "level", width: 80 },
    { title: "BOM 版本", dataIndex: "bom_revision", key: "bom_revision", width: 100 },
  ];

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginBottom: 16,
          alignItems: "center",
        }}
      >
        <Title level={4} style={{ margin: 0 }}>
          PLM 零件列表
        </Title>
        <Input.Search
          placeholder="搜索零件号或名称"
          allowClear
          onSearch={handleSearch}
          style={{ width: 280 }}
        />
      </div>

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
      />

      <Drawer
        title="零件详情"
        open={!!drawerPart}
        onClose={() => setDrawerPart(null)}
        width={520}
      >
        {drawerPart && (
          <Descriptions bordered column={1} size="small">
            <Descriptions.Item label="零件号">{drawerPart.part_number}</Descriptions.Item>
            <Descriptions.Item label="名称">{drawerPart.name}</Descriptions.Item>
            <Descriptions.Item label="版本">{drawerPart.revision}</Descriptions.Item>
            <Descriptions.Item label="状态">{drawerPart.status}</Descriptions.Item>
            <Descriptions.Item label="材质">{drawerPart.material || "—"}</Descriptions.Item>
            <Descriptions.Item label="规格">{drawerPart.specification || "—"}</Descriptions.Item>
            <Descriptions.Item label="安全件">
              {drawerPart.is_safety_related ? "是" : "否"}
            </Descriptions.Item>
            <Descriptions.Item label="关键特性">
              {drawerPart.is_key_characteristic ? "是" : "否"}
            </Descriptions.Item>
            <Descriptions.Item label="外部 ID">{drawerPart.external_id}</Descriptions.Item>
            <Descriptions.Item label="产线代码">
              {drawerPart.product_line_code || "—"}
            </Descriptions.Item>
            <Descriptions.Item label="PLM 更新时间">
              {drawerPart.source_updated_at
                ? new Date(drawerPart.source_updated_at).toLocaleString("zh-CN")
                : "—"}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>

      <Modal
        title={bomPart ? `BOM：${bomPart.part_number}` : "BOM"}
        open={!!bomPart}
        onCancel={() => setBomPart(null)}
        footer={null}
        width={900}
      >
        <Form form={bomQueryForm} layout="inline" style={{ marginBottom: 16 }}>
          <Form.Item name="revision" label="零件版本" rules={[{ required: true, message: "请输入零件版本" }]}>
            <Input style={{ width: 120 }} />
          </Form.Item>
          <Form.Item name="bom_revision" label="BOM 版本" rules={[{ required: true, message: "请输入 BOM 版本" }]}>
            <Input style={{ width: 120 }} />
          </Form.Item>
          <Form.Item>
            <Button onClick={queryBom} loading={bomLoading}>查询 BOM</Button>
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
            <Form.Item name="fmea_id" label="FMEA ID" rules={[{ required: true, message: "请输入 FMEA ID" }]}>
              <Input style={{ width: 260 }} />
            </Form.Item>
            <Form.Item name="overwrite" valuePropName="checked">
              <Checkbox>覆盖已有节点</Checkbox>
            </Form.Item>
            <Form.Item>
              <Button type="primary" onClick={handleImportBom} loading={bomLoading}>导入 FMEA</Button>
            </Form.Item>
          </Form>
        )}
      </Modal>

      <Modal
        title={scPart ? `确认特殊特性：${scPart.part_number}` : "确认特殊特性"}
        open={!!scPart}
        onCancel={() => setScPart(null)}
        onOk={handleConfirmSc}
        confirmLoading={scLoading}
        okText="确认"
        cancelText="取消"
      >
        <Form form={scForm} layout="vertical">
          <Form.Item name="characteristic_type" label="特性类型" rules={[{ required: true, message: "请选择特性类型" }]}>
            <Select
              options={(scPart ? getPendingScLinks(scPart) : []).map((link) => ({
                value: link.characteristic_type,
                label: link.characteristic_type === "safety" ? "安全特性" : "关键特性",
              }))}
            />
          </Form.Item>
          <Form.Item name="fmea_id" label="FMEA ID" rules={[{ required: true, message: "请输入 FMEA ID" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="node_id" label="节点 ID" rules={[{ required: true, message: "请输入节点 ID" }]}>
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

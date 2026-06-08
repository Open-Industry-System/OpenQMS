import { useEffect, useState, useCallback } from "react";
import { Table, Input, Button, Typography, Tag, Drawer, Descriptions, App } from "antd";
import { getPLMParts } from "../../api/plm";
import { useProductLineStore } from "../../store/productLineStore";
import type { PLMPart } from "../../types/plm";

const { Title } = Typography;

export default function PLMPartsPage() {
  const { message } = App.useApp();
  const productLine = useProductLineStore((s) => s.selected);
  const [data, setData] = useState<PLMPart[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [drawerPart, setDrawerPart] = useState<PLMPart | null>(null);

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
  }, []);

  useEffect(() => {
    fetchData(1, search, productLine);
  }, [productLine]);

  const handleSearch = (value: string) => {
    setSearch(value);
    setPage(1);
    fetchData(1, value, productLine);
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
      width: 80,
      render: (_: unknown, record: PLMPart) => (
        <Button type="link" size="small" onClick={() => setDrawerPart(record)}>详情</Button>
      ),
    },
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
    </div>
  );
}

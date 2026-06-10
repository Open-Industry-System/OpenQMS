import { useEffect, useState } from "react";
import {
  Table, Tag, Button, Typography, App, Space, Input, Tabs,
} from "antd";
import {
  fetchERPSuppliers,
  fetchERPCustomers,
  fetchERPMaterials,
  fetchERPLocations,
  linkERPSupplier,
  unlinkERPSupplier,
  linkERPCustomer,
  unlinkERPCustomer,
} from "../../api/erp";
import type {
  ERPSupplier,
  ERPCustomer,
  ERPMaterial,
  ERPLocation,
} from "../../types/erp";

const { Title } = Typography;

// ─── Suppliers Tab ───

const linkStatusColor = (v: string) => {
  switch (v) {
    case "linked": return "green";
    case "pending": return "orange";
    default: return "red";
  }
};

const linkStatusLabel = (v: string) => {
  switch (v) {
    case "linked": return "已关联";
    case "pending": return "待关联";
    case "unlinked": return "未关联";
    default: return v;
  }
};

function SuppliersTab() {
  const { message } = App.useApp();
  const [data, setData] = useState<ERPSupplier[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);

  const fetchData = (p: number) => {
    setLoading(true);
    fetchERPSuppliers({ page: p, page_size: 20 })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error("加载供应商失败"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(1); }, []);

  const handleLink = async (record: ERPSupplier) => {
    try {
      await linkERPSupplier(record.erp_supplier_id, record.erp_supplier_id);
      message.success("关联成功");
      fetchData(page);
    } catch {
      message.error("关联失败");
    }
  };

  const handleUnlink = async (record: ERPSupplier) => {
    try {
      await unlinkERPSupplier(record.erp_supplier_id);
      message.success("取消关联成功");
      fetchData(page);
    } catch {
      message.error("取消关联失败");
    }
  };

  const columns = [
    { title: "供应商编码", dataIndex: "supplier_code", key: "supplier_code", width: 140 },
    { title: "名称", dataIndex: "name", key: "name", ellipsis: true },
    { title: "状态", dataIndex: "status", key: "status", width: 100, render: (v: string) => <Tag>{v}</Tag> },
    {
      title: "关联状态",
      dataIndex: "link_status",
      key: "link_status",
      width: 110,
      render: (v: string) => <Tag color={linkStatusColor(v)}>{linkStatusLabel(v)}</Tag>,
    },
    {
      title: "操作",
      key: "actions",
      width: 140,
      render: (_: unknown, record: ERPSupplier) => (
        <Space size={4}>
          {record.link_status !== "linked" && (
            <Button type="link" size="small" onClick={() => handleLink(record)}>关联</Button>
          )}
          {record.link_status === "linked" && (
            <Button type="link" size="small" danger onClick={() => handleUnlink(record)}>取消关联</Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <Table
      columns={columns}
      dataSource={data}
      rowKey="erp_supplier_id"
      loading={loading}
      pagination={{
        current: page,
        total,
        pageSize: 20,
        onChange: (p) => { setPage(p); fetchData(p); },
      }}
    />
  );
}

// ─── Customers Tab ───

function CustomersTab() {
  const { message } = App.useApp();
  const [data, setData] = useState<ERPCustomer[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);

  const fetchData = (p: number) => {
    setLoading(true);
    fetchERPCustomers({ page: p, page_size: 20 })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error("加载客户失败"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(1); }, []);

  const handleLink = async (record: ERPCustomer) => {
    try {
      await linkERPCustomer(record.erp_customer_id, record.erp_customer_id);
      message.success("关联成功");
      fetchData(page);
    } catch {
      message.error("关联失败");
    }
  };

  const handleUnlink = async (record: ERPCustomer) => {
    try {
      await unlinkERPCustomer(record.erp_customer_id);
      message.success("取消关联成功");
      fetchData(page);
    } catch {
      message.error("取消关联失败");
    }
  };

  const columns = [
    { title: "客户编码", dataIndex: "customer_code", key: "customer_code", width: 140 },
    { title: "名称", dataIndex: "name", key: "name", ellipsis: true },
    { title: "状态", dataIndex: "status", key: "status", width: 100, render: (v: string) => <Tag>{v}</Tag> },
    {
      title: "关联状态",
      dataIndex: "link_status",
      key: "link_status",
      width: 110,
      render: (v: string) => <Tag color={linkStatusColor(v)}>{linkStatusLabel(v)}</Tag>,
    },
    {
      title: "操作",
      key: "actions",
      width: 140,
      render: (_: unknown, record: ERPCustomer) => (
        <Space size={4}>
          {record.link_status !== "linked" && (
            <Button type="link" size="small" onClick={() => handleLink(record)}>关联</Button>
          )}
          {record.link_status === "linked" && (
            <Button type="link" size="small" danger onClick={() => handleUnlink(record)}>取消关联</Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <Table
      columns={columns}
      dataSource={data}
      rowKey="erp_customer_id"
      loading={loading}
      pagination={{
        current: page,
        total,
        pageSize: 20,
        onChange: (p) => { setPage(p); fetchData(p); },
      }}
    />
  );
}

// ─── Materials Tab ───

function MaterialsTab() {
  const { message } = App.useApp();
  const [data, setData] = useState<ERPMaterial[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");

  const fetchData = (p: number, q: string) => {
    setLoading(true);
    fetchERPMaterials({ page: p, page_size: 20 })
      .then((res) => {
        if (q) {
          const filtered = res.items.filter(
            (item) =>
              item.material_code.toLowerCase().includes(q.toLowerCase()) ||
              item.name.toLowerCase().includes(q.toLowerCase()),
          );
          setData(filtered);
          setTotal(filtered.length);
        } else {
          setData(res.items);
          setTotal(res.total);
        }
      })
      .catch(() => message.error("加载物料失败"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(1, ""); }, []);

  const handleSearch = (value: string) => {
    setSearch(value);
    setPage(1);
    fetchData(1, value);
  };

  const columns = [
    { title: "物料编码", dataIndex: "material_code", key: "material_code", width: 140 },
    { title: "名称", dataIndex: "name", key: "name", ellipsis: true },
    { title: "规格", dataIndex: "specification", key: "specification", width: 140, render: (v: string | null) => v || "—" },
    { title: "单位", dataIndex: "unit", key: "unit", width: 70, render: (v: string | null) => v || "—" },
    {
      title: "采购件",
      dataIndex: "is_purchased",
      key: "is_purchased",
      width: 80,
      render: (v: boolean) => v ? <Tag color="blue">是</Tag> : "否",
    },
    {
      title: "自制件",
      dataIndex: "is_manufactured",
      key: "is_manufactured",
      width: 80,
      render: (v: boolean) => v ? <Tag color="green">是</Tag> : "否",
    },
    { title: "状态", dataIndex: "status", key: "status", width: 90, render: (v: string) => <Tag>{v}</Tag> },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
        <Input.Search
          placeholder="搜索物料编码或名称"
          allowClear
          onSearch={handleSearch}
          style={{ width: 280 }}
        />
      </div>
      <Table
        columns={columns}
        dataSource={data}
        rowKey="material_id"
        loading={loading}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => { setPage(p); fetchData(p, search); },
        }}
      />
    </div>
  );
}

// ─── Locations Tab ───

const locationTypeLabel: Record<string, string> = {
  warehouse: "仓库",
  zone: "库区",
  bin: "库位",
  line: "产线",
};

function LocationsTab() {
  const { message } = App.useApp();
  const [data, setData] = useState<ERPLocation[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);

  const fetchData = (p: number) => {
    setLoading(true);
    fetchERPLocations({ page: p, page_size: 20 })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error("加载库位失败"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(1); }, []);

  const columns = [
    { title: "库位编码", dataIndex: "location_code", key: "location_code", width: 140 },
    { title: "仓库编码", dataIndex: "warehouse_code", key: "warehouse_code", width: 120, render: (v: string | null) => v || "—" },
    { title: "库区编码", dataIndex: "zone_code", key: "zone_code", width: 120, render: (v: string | null) => v || "—" },
    {
      title: "类型",
      dataIndex: "location_type",
      key: "location_type",
      width: 100,
      render: (v: string) => <Tag>{locationTypeLabel[v] || v}</Tag>,
    },
    {
      title: "启用",
      dataIndex: "is_enabled",
      key: "is_enabled",
      width: 80,
      render: (v: boolean) => v ? <Tag color="green">是</Tag> : <Tag color="red">否</Tag>,
    },
  ];

  return (
    <Table
      columns={columns}
      dataSource={data}
      rowKey="location_id"
      loading={loading}
      pagination={{
        current: page,
        total,
        pageSize: 20,
        onChange: (p) => { setPage(p); fetchData(p); },
      }}
    />
  );
}

// ─── Main Page ───

const tabItems = [
  { key: "suppliers", label: "供应商", children: <SuppliersTab /> },
  { key: "customers", label: "客户", children: <CustomersTab /> },
  { key: "materials", label: "物料", children: <MaterialsTab /> },
  { key: "locations", label: "库位", children: <LocationsTab /> },
];

export default function ERPMasterDataPage() {
  const [activeTab, setActiveTab] = useState("suppliers");

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>ERP 主数据</Title>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
      />
    </div>
  );
}

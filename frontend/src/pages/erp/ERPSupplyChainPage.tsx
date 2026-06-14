import { useEffect, useState } from "react";
import {
  Table, App, Select, Tabs,
} from "antd";
import {
  fetchERPPurchaseOrders,
  fetchERPInventoryBalances,
} from "../../api/erp";
import { useProductLineStore } from "../../store/productLineStore";
import { PageShell, DataCard, StatusBadge } from "../../components/design";
import type { ERPPurchaseOrder, ERPInventoryBalance } from "../../types/erp";

// ─── Purchase Orders Tab ───

const poStatusVariant: Record<string, string> = {
  draft: "info",
  submitted: "info",
  confirmed: "warning",
  partially_received: "info",
  received: "success",
  closed: "info",
};

const poStatusLabel: Record<string, string> = {
  draft: "草稿",
  submitted: "已提交",
  confirmed: "已确认",
  partially_received: "部分收货",
  received: "已收货",
  closed: "已关闭",
};

function PurchaseOrdersTab() {
  const { message } = App.useApp();
  const productLine = useProductLineStore((s) => s.selected);
  const [data, setData] = useState<ERPPurchaseOrder[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>("");

  const fetchData = (p: number, status?: string, plCode?: string | null) => {
    setLoading(true);
    fetchERPPurchaseOrders({ page: p, page_size: 20, product_line_code: plCode || undefined })
      .then((res) => {
        if (status) {
          const filtered = res.items.filter((item) => item.status === status);
          setData(filtered);
          setTotal(filtered.length);
        } else {
          setData(res.items);
          setTotal(res.total);
        }
      })
      .catch(() => message.error("加载采购订单失败"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(1, statusFilter || undefined, productLine); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine]);

  const handleStatusChange = (value: string) => {
    setStatusFilter(value);
    setPage(1);
    fetchData(1, value || undefined, productLine);
  };

  const columns = [
    { title: "采购单号", dataIndex: "po_number", key: "po_number", width: 140 },
    { title: "行号", dataIndex: "line_number", key: "line_number", width: 80 },
    { title: "供应商编码", dataIndex: "supplier_code", key: "supplier_code", width: 130, render: (v: string | null) => v || "—" },
    { title: "物料编码", dataIndex: "material_code", key: "material_code", width: 130, render: (v: string | null) => v || "—" },
    {
      title: "数量",
      dataIndex: "quantity",
      key: "quantity",
      width: 90,
      render: (v: number | null) => v ?? "—",
    },
    {
      title: "已收货",
      dataIndex: "received_quantity",
      key: "received_quantity",
      width: 90,
      render: (v: number | null) => v ?? "—",
    },
    { title: "批次号", dataIndex: "lot_no", key: "lot_no", width: 130, render: (v: string | null) => v || "—" },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 110,
      render: (s: string) => (
        <StatusBadge status={poStatusVariant[s] || s}>
          {poStatusLabel[s] || s}
        </StatusBadge>
      ),
    },
    {
      title: "交货日期",
      dataIndex: "delivery_date",
      key: "delivery_date",
      width: 120,
      render: (v: string | null) => v || "—",
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
        <Select
          placeholder="筛选状态"
          allowClear
          style={{ width: 140 }}
          value={statusFilter || undefined}
          onChange={handleStatusChange}
          options={Object.entries(poStatusLabel).map(([value, label]) => ({ value, label }))}
        />
      </div>
      <DataCard title="采购订单">
        <Table
          columns={columns}
          dataSource={data}
          rowKey="po_id"
          loading={loading}
          pagination={{
            current: page,
            total,
            pageSize: 20,
            onChange: (p) => { setPage(p); fetchData(p, statusFilter || undefined, productLine); },
          }}
          className="qf-table"
        />
      </DataCard>
    </div>
  );
}

// ─── Inventory Balances Tab ───

const invStatusVariant: Record<string, string> = {
  available: "success",
  restricted: "warning",
  blocked: "error",
  in_inspection: "info",
};

const invStatusLabel: Record<string, string> = {
  available: "可用",
  restricted: "受限",
  blocked: "冻结",
  in_inspection: "检验中",
};

function InventoryBalancesTab() {
  const { message } = App.useApp();
  const productLine = useProductLineStore((s) => s.selected);
  const [data, setData] = useState<ERPInventoryBalance[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);

  const fetchData = (p: number, plCode?: string | null) => {
    setLoading(true);
    fetchERPInventoryBalances({ page: p, page_size: 20, product_line_code: plCode || undefined })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error("加载库存余额失败"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(1, productLine); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine]);

  const columns = [
    { title: "物料编码", dataIndex: "material_code", key: "material_code", width: 140 },
    { title: "库位编码", dataIndex: "location_code", key: "location_code", width: 130 },
    { title: "批次号", dataIndex: "lot_no", key: "lot_no", width: 130 },
    { title: "供应商批次号", dataIndex: "supplier_lot_no", key: "supplier_lot_no", width: 130, render: (v: string | null) => v || "—" },
    {
      title: "数量",
      dataIndex: "quantity",
      key: "quantity",
      width: 100,
      render: (v: number | null) => v ?? "—",
    },
    { title: "单位", dataIndex: "unit", key: "unit", width: 70, render: (v: string | null) => v || "—" },
    {
      title: "库存状态",
      dataIndex: "inventory_status",
      key: "inventory_status",
      width: 110,
      render: (v: string) => (
        <StatusBadge status={invStatusVariant[v] || v}>
          {invStatusLabel[v] || v}
        </StatusBadge>
      ),
    },
  ];

  return (
    <DataCard title="库存余额">
      <Table
        columns={columns}
        dataSource={data}
        rowKey="balance_id"
        loading={loading}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => { setPage(p); fetchData(p, productLine); },
        }}
        className="qf-table"
      />
    </DataCard>
  );
}

// ─── Main Page ───

const tabItems = [
  { key: "purchase_orders", label: "采购订单", children: <PurchaseOrdersTab /> },
  { key: "inventory", label: "库存余额", children: <InventoryBalancesTab /> },
];

export default function ERPSupplyChainPage() {
  const [activeTab, setActiveTab] = useState("purchase_orders");

  return (
    <PageShell title="ERP 供应链">
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
      />
    </PageShell>
  );
}

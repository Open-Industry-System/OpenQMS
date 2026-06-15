import { useEffect, useMemo, useState } from "react";
import {
  Table, Tag, Typography, App, Select, Tabs,
} from "antd";
import { useTranslation } from "react-i18next";
import {
  fetchERPPurchaseOrders,
  fetchERPInventoryBalances,
} from "../../api/erp";
import { useProductLineStore } from "../../store/productLineStore";
import type { ERPPurchaseOrder, ERPInventoryBalance } from "../../types/erp";

const { Title } = Typography;

// ─── Purchase Orders Tab ───

const poStatusColor: Record<string, string> = {
  draft: "default",
  submitted: "blue",
  confirmed: "processing",
  partially_received: "cyan",
  received: "success",
  closed: "default",
};

function usePOStatusLabel() {
  const { t } = useTranslation("erp");
  return useMemo(() => ({
    draft: t("supplyChain.poStatus.draft"),
    submitted: t("supplyChain.poStatus.submitted"),
    confirmed: t("supplyChain.poStatus.confirmed"),
    partially_received: t("supplyChain.poStatus.partiallyReceived"),
    received: t("supplyChain.poStatus.received"),
    closed: t("supplyChain.poStatus.closed"),
  }), [t]);
}

function PurchaseOrdersTab() {
  const { t } = useTranslation("erp");
  const poStatusLabel = usePOStatusLabel();
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
      .catch(() => message.error(t("supplyChain.messages.loadPurchaseOrdersFailed")))
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
    { title: t("supplyChain.columns.poNumber"), dataIndex: "po_number", key: "po_number", width: 140 },
    { title: t("supplyChain.columns.lineNumber"), dataIndex: "line_number", key: "line_number", width: 80 },
    { title: t("supplyChain.columns.supplierCode"), dataIndex: "supplier_code", key: "supplier_code", width: 130, render: (v: string | null) => v || "—" },
    { title: t("supplyChain.columns.materialCode"), dataIndex: "material_code", key: "material_code", width: 130, render: (v: string | null) => v || "—" },
    {
      title: t("supplyChain.columns.quantity"),
      dataIndex: "quantity",
      key: "quantity",
      width: 90,
      render: (v: number | null) => v ?? "—",
    },
    {
      title: t("supplyChain.columns.receivedQuantity"),
      dataIndex: "received_quantity",
      key: "received_quantity",
      width: 90,
      render: (v: number | null) => v ?? "—",
    },
    { title: t("supplyChain.columns.lotNo"), dataIndex: "lot_no", key: "lot_no", width: 130, render: (v: string | null) => v || "—" },
    {
      title: t("supplyChain.columns.status"),
      dataIndex: "status",
      key: "status",
      width: 110,
      render: (s: string) => (
        <Tag color={poStatusColor[s] || "default"}>
          {poStatusLabel[s as keyof typeof poStatusLabel] || s}
        </Tag>
      ),
    },
    {
      title: t("supplyChain.columns.deliveryDate"),
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
          placeholder={t("supplyChain.filterStatusPlaceholder")}
          allowClear
          style={{ width: 140 }}
          value={statusFilter || undefined}
          onChange={handleStatusChange}
          options={Object.entries(poStatusLabel).map(([value, label]) => ({ value, label }))}
        />
      </div>
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
      />
    </div>
  );
}

// ─── Inventory Balances Tab ───

const invStatusColor: Record<string, string> = {
  available: "green",
  restricted: "orange",
  blocked: "red",
  in_inspection: "blue",
};

function useInvStatusLabel() {
  const { t } = useTranslation("erp");
  return useMemo(() => ({
    available: t("supplyChain.inventoryStatus.available"),
    restricted: t("supplyChain.inventoryStatus.restricted"),
    blocked: t("supplyChain.inventoryStatus.blocked"),
    in_inspection: t("supplyChain.inventoryStatus.inInspection"),
  }), [t]);
}

function InventoryBalancesTab() {
  const { t } = useTranslation("erp");
  const invStatusLabel = useInvStatusLabel();
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
      .catch(() => message.error(t("supplyChain.messages.loadInventoryFailed")))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(1, productLine); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine]);

  const columns = [
    { title: t("supplyChain.columns.materialCode"), dataIndex: "material_code", key: "material_code", width: 140 },
    { title: t("supplyChain.columns.locationCode"), dataIndex: "location_code", key: "location_code", width: 130 },
    { title: t("supplyChain.columns.lotNo"), dataIndex: "lot_no", key: "lot_no", width: 130 },
    { title: t("supplyChain.columns.supplierLotNo"), dataIndex: "supplier_lot_no", key: "supplier_lot_no", width: 130, render: (v: string | null) => v || "—" },
    {
      title: t("supplyChain.columns.quantity"),
      dataIndex: "quantity",
      key: "quantity",
      width: 100,
      render: (v: number | null) => v ?? "—",
    },
    { title: t("supplyChain.columns.unit"), dataIndex: "unit", key: "unit", width: 70, render: (v: string | null) => v || "—" },
    {
      title: t("supplyChain.columns.inventoryStatus"),
      dataIndex: "inventory_status",
      key: "inventory_status",
      width: 110,
      render: (v: string) => (
        <Tag color={invStatusColor[v] || "default"}>
          {invStatusLabel[v as keyof typeof invStatusLabel] || v}
        </Tag>
      ),
    },
  ];

  return (
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
    />
  );
}

// ─── Main Page ───

export default function ERPSupplyChainPage() {
  const { t } = useTranslation("erp");
  const [activeTab, setActiveTab] = useState("purchase_orders");

  const tabItems = [
    { key: "purchase_orders", label: t("supplyChain.tabs.purchaseOrders"), children: <PurchaseOrdersTab /> },
    { key: "inventory", label: t("supplyChain.tabs.inventory"), children: <InventoryBalancesTab /> },
  ];

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>{t("supplyChain.title")}</Title>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
      />
    </div>
  );
}

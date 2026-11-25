import { useEffect, useMemo, useState } from "react";
import {
  Table, App, Select, Tabs,
} from "antd";
import { useTranslation } from "react-i18next";
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

function PurchaseOrdersTab() {
  const { t } = useTranslation("erp");
  const { message } = App.useApp();
  const productLine = useProductLineStore((s) => s.selected);
  const [data, setData] = useState<ERPPurchaseOrder[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>("");

  const poStatusLabel = useMemo((): Record<string, string> => ({
    draft: t("supplyChain.purchaseOrders.status.draft"),
    submitted: t("supplyChain.purchaseOrders.status.submitted"),
    confirmed: t("supplyChain.purchaseOrders.status.confirmed"),
    partially_received: t("supplyChain.purchaseOrders.status.partiallyReceived"),
    received: t("supplyChain.purchaseOrders.status.received"),
    closed: t("supplyChain.purchaseOrders.status.closed"),
  }), [t]);

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
      .catch(() => message.error(t("supplyChain.purchaseOrders.errors.loadFailed")))
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
    { title: t("supplyChain.purchaseOrders.columns.poNumber"), dataIndex: "po_number", key: "po_number", width: 140 },
    { title: t("supplyChain.purchaseOrders.columns.lineNumber"), dataIndex: "line_number", key: "line_number", width: 80 },
    { title: t("supplyChain.purchaseOrders.columns.supplierCode"), dataIndex: "supplier_code", key: "supplier_code", width: 130, render: (v: string | null) => v || "—" },
    { title: t("supplyChain.purchaseOrders.columns.materialCode"), dataIndex: "material_code", key: "material_code", width: 130, render: (v: string | null) => v || "—" },
    {
      title: t("supplyChain.purchaseOrders.columns.quantity"),
      dataIndex: "quantity",
      key: "quantity",
      width: 90,
      render: (v: number | null) => v ?? "—",
    },
    {
      title: t("supplyChain.purchaseOrders.columns.receivedQuantity"),
      dataIndex: "received_quantity",
      key: "received_quantity",
      width: 90,
      render: (v: number | null) => v ?? "—",
    },
    { title: t("supplyChain.purchaseOrders.columns.lotNo"), dataIndex: "lot_no", key: "lot_no", width: 130, render: (v: string | null) => v || "—" },
    {
      title: t("supplyChain.purchaseOrders.columns.status"),
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
      title: t("supplyChain.purchaseOrders.columns.deliveryDate"),
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
          placeholder={t("supplyChain.purchaseOrders.filterPlaceholder")}
          allowClear
          style={{ width: 140 }}
          value={statusFilter || undefined}
          onChange={handleStatusChange}
          options={Object.entries(poStatusLabel).map(([value, label]) => ({ value, label }))}
        />
      </div>
      <DataCard title={t("supplyChain.purchaseOrders.cardTitle")}>
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

function InventoryBalancesTab() {
  const { t } = useTranslation("erp");
  const { message } = App.useApp();
  const productLine = useProductLineStore((s) => s.selected);
  const [data, setData] = useState<ERPInventoryBalance[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);

  const invStatusLabel = useMemo((): Record<string, string> => ({
    available: t("supplyChain.inventory.status.available"),
    restricted: t("supplyChain.inventory.status.restricted"),
    blocked: t("supplyChain.inventory.status.blocked"),
    in_inspection: t("supplyChain.inventory.status.inInspection"),
  }), [t]);

  const fetchData = (p: number, plCode?: string | null) => {
    setLoading(true);
    fetchERPInventoryBalances({ page: p, page_size: 20, product_line_code: plCode || undefined })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error(t("supplyChain.inventory.errors.loadFailed")))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(1, productLine); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine]);

  const columns = [
    { title: t("supplyChain.inventory.columns.materialCode"), dataIndex: "material_code", key: "material_code", width: 140 },
    { title: t("supplyChain.inventory.columns.locationCode"), dataIndex: "location_code", key: "location_code", width: 130 },
    { title: t("supplyChain.inventory.columns.lotNo"), dataIndex: "lot_no", key: "lot_no", width: 130 },
    { title: t("supplyChain.inventory.columns.supplierLotNo"), dataIndex: "supplier_lot_no", key: "supplier_lot_no", width: 130, render: (v: string | null) => v || "—" },
    {
      title: t("supplyChain.inventory.columns.quantity"),
      dataIndex: "quantity",
      key: "quantity",
      width: 100,
      render: (v: number | null) => v ?? "—",
    },
    { title: t("supplyChain.inventory.columns.unit"), dataIndex: "unit", key: "unit", width: 70, render: (v: string | null) => v || "—" },
    {
      title: t("supplyChain.inventory.columns.inventoryStatus"),
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
    <DataCard title={t("supplyChain.inventory.cardTitle")}>
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

export default function ERPSupplyChainPage() {
  const { t } = useTranslation("erp");
  const [activeTab, setActiveTab] = useState("purchase_orders");

  const tabItems = [
    { key: "purchase_orders", label: t("supplyChain.tabs.purchaseOrders"), children: <PurchaseOrdersTab /> },
    { key: "inventory", label: t("supplyChain.tabs.inventory"), children: <InventoryBalancesTab /> },
  ];

  return (
    <PageShell title={t("supplyChain.title")}>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
      />
    </PageShell>
  );
}
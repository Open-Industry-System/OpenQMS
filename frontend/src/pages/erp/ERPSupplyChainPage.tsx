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
    draft: t("supplyChain.purchaseOrders.status.draft", "草稿"),
    submitted: t("supplyChain.purchaseOrders.status.submitted", "已提交"),
    confirmed: t("supplyChain.purchaseOrders.status.confirmed", "已确认"),
    partially_received: t("supplyChain.purchaseOrders.status.partiallyReceived", "部分收货"),
    received: t("supplyChain.purchaseOrders.status.received", "已收货"),
    closed: t("supplyChain.purchaseOrders.status.closed", "已关闭"),
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
      .catch(() => message.error(t("supplyChain.purchaseOrders.errors.loadFailed", "加载采购订单失败")))
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
    { title: t("supplyChain.purchaseOrders.columns.poNumber", "采购单号"), dataIndex: "po_number", key: "po_number", width: 140 },
    { title: t("supplyChain.purchaseOrders.columns.lineNumber", "行号"), dataIndex: "line_number", key: "line_number", width: 80 },
    { title: t("supplyChain.purchaseOrders.columns.supplierCode", "供应商编码"), dataIndex: "supplier_code", key: "supplier_code", width: 130, render: (v: string | null) => v || "—" },
    { title: t("supplyChain.purchaseOrders.columns.materialCode", "物料编码"), dataIndex: "material_code", key: "material_code", width: 130, render: (v: string | null) => v || "—" },
    {
      title: t("supplyChain.purchaseOrders.columns.quantity", "数量"),
      dataIndex: "quantity",
      key: "quantity",
      width: 90,
      render: (v: number | null) => v ?? "—",
    },
    {
      title: t("supplyChain.purchaseOrders.columns.receivedQuantity", "已收货"),
      dataIndex: "received_quantity",
      key: "received_quantity",
      width: 90,
      render: (v: number | null) => v ?? "—",
    },
    { title: t("supplyChain.purchaseOrders.columns.lotNo", "批次号"), dataIndex: "lot_no", key: "lot_no", width: 130, render: (v: string | null) => v || "—" },
    {
      title: t("supplyChain.purchaseOrders.columns.status", "状态"),
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
      title: t("supplyChain.purchaseOrders.columns.deliveryDate", "交货日期"),
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
          placeholder={t("supplyChain.purchaseOrders.filterPlaceholder", "筛选状态")}
          allowClear
          style={{ width: 140 }}
          value={statusFilter || undefined}
          onChange={handleStatusChange}
          options={Object.entries(poStatusLabel).map(([value, label]) => ({ value, label }))}
        />
      </div>
      <DataCard title={t("supplyChain.purchaseOrders.cardTitle", "采购订单")}>
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
    available: t("supplyChain.inventory.status.available", "可用"),
    restricted: t("supplyChain.inventory.status.restricted", "受限"),
    blocked: t("supplyChain.inventory.status.blocked", "冻结"),
    in_inspection: t("supplyChain.inventory.status.inInspection", "检验中"),
  }), [t]);

  const fetchData = (p: number, plCode?: string | null) => {
    setLoading(true);
    fetchERPInventoryBalances({ page: p, page_size: 20, product_line_code: plCode || undefined })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error(t("supplyChain.inventory.errors.loadFailed", "加载库存余额失败")))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(1, productLine); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine]);

  const columns = [
    { title: t("supplyChain.inventory.columns.materialCode", "物料编码"), dataIndex: "material_code", key: "material_code", width: 140 },
    { title: t("supplyChain.inventory.columns.locationCode", "库位编码"), dataIndex: "location_code", key: "location_code", width: 130 },
    { title: t("supplyChain.inventory.columns.lotNo", "批次号"), dataIndex: "lot_no", key: "lot_no", width: 130 },
    { title: t("supplyChain.inventory.columns.supplierLotNo", "供应商批次号"), dataIndex: "supplier_lot_no", key: "supplier_lot_no", width: 130, render: (v: string | null) => v || "—" },
    {
      title: t("supplyChain.inventory.columns.quantity", "数量"),
      dataIndex: "quantity",
      key: "quantity",
      width: 100,
      render: (v: number | null) => v ?? "—",
    },
    { title: t("supplyChain.inventory.columns.unit", "单位"), dataIndex: "unit", key: "unit", width: 70, render: (v: string | null) => v || "—" },
    {
      title: t("supplyChain.inventory.columns.inventoryStatus", "库存状态"),
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
    <DataCard title={t("supplyChain.inventory.cardTitle", "库存余额")}>
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
    { key: "purchase_orders", label: t("supplyChain.tabs.purchaseOrders", "采购订单"), children: <PurchaseOrdersTab /> },
    { key: "inventory", label: t("supplyChain.tabs.inventory", "库存余额"), children: <InventoryBalancesTab /> },
  ];

  return (
    <PageShell title={t("supplyChain.title", "ERP 供应链")}>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
      />
    </PageShell>
  );
}
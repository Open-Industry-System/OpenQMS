import { useEffect, useState, useCallback, useMemo } from "react";
import {
  Table,
  Tabs,
  Statistic,
  Row,
  Col,
  App,
} from "antd";
import { useTranslation } from "react-i18next";
import {
  fetchERPSalesOrders,
  fetchERPShipments,
  fetchERPCostRecords,
} from "../../api/erp";
import { useProductLineStore } from "../../store/productLineStore";
import type {
  ERPSalesOrder,
  ERPShipment,
  ERPCostRecord,
} from "../../types/erp";
import { PageShell, DataCard, StatusBadge } from "../../components/design";

const soStatusVariant: Record<string, string> = {
  confirmed: "success",
  open: "warning",
  cancelled: "error",
  delivered: "info",
};

const linkStatusVariant: Record<string, string> = {
  linked: "success",
  pending: "warning",
  unlinked: "info",
  error: "error",
};

const costCategoryColors: Record<string, string> = {
  prevention: "#52c41a",
  appraisal: "#1890ff",
  internal_failure: "#fa8c16",
  external_failure: "#f5222d",
};

/* ─── Sales Orders Tab ─── */

function SalesOrdersTab() {
  const { t } = useTranslation("erp");
  const { message } = App.useApp();
  const [data, setData] = useState<ERPSalesOrder[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const productLine = useProductLineStore((s) => s.selected);

  const fetchData = useCallback(
    (p: number, plCode?: string | null) => {
      setLoading(true);
      fetchERPSalesOrders({ page: p, page_size: 20, product_line_code: plCode || undefined })
        .then((res) => {
          setData(res.items);
          setTotal(res.total);
        })
        .catch(() => message.error(t("salesAndCost.salesOrders.errors.loadFailed", "加载销售订单失败")))
        .finally(() => setLoading(false));
    },
    [message, t],
  );

  useEffect(() => {
    fetchData(1, productLine);
  }, [productLine, fetchData]);

  const columns = [
    {
      title: t("salesAndCost.salesOrders.columns.soNumber", "销售订单号"),
      dataIndex: "so_number",
      key: "so_number",
      width: 160,
    },
    {
      title: t("salesAndCost.salesOrders.columns.lineNumber", "行号"),
      dataIndex: "line_number",
      key: "line_number",
      width: 80,
    },
    {
      title: t("salesAndCost.salesOrders.columns.customerCode", "客户编码"),
      dataIndex: "customer_code",
      key: "customer_code",
      width: 140,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("salesAndCost.salesOrders.columns.materialCode", "物料编码"),
      dataIndex: "material_code",
      key: "material_code",
      width: 140,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("salesAndCost.salesOrders.columns.quantity", "数量"),
      dataIndex: "quantity",
      key: "quantity",
      width: 100,
      render: (v: number | null) => v?.toLocaleString() ?? "—",
    },
    {
      title: t("salesAndCost.salesOrders.columns.unitPrice", "单价"),
      dataIndex: "unit_price",
      key: "unit_price",
      width: 100,
      render: (v: number | null) =>
        v != null ? `¥${v.toFixed(2)}` : "—",
    },
    {
      title: t("salesAndCost.salesOrders.columns.status", "状态"),
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (v: string) => (
        <StatusBadge status={soStatusVariant[v] || "info"}>{v}</StatusBadge>
      ),
    },
    {
      title: t("salesAndCost.salesOrders.columns.deliveryDate", "交货日期"),
      dataIndex: "delivery_date",
      key: "delivery_date",
      width: 120,
      render: (v: string | null) => v || "—",
    },
  ];

  return (
    <DataCard title={t("salesAndCost.salesOrders.cardTitle", "销售订单")}>
      <Table
        className="qf-table"
        columns={columns}
        dataSource={data}
        rowKey="so_id"
        loading={loading}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => {
            setPage(p);
            fetchData(p, productLine);
          },
        }}
      />
    </DataCard>
  );
}

/* ─── Shipments Tab ─── */

function ShipmentsTab() {
  const { t } = useTranslation("erp");
  const { message } = App.useApp();
  const [data, setData] = useState<ERPShipment[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const productLine = useProductLineStore((s) => s.selected);

  const fetchData = useCallback(
    (p: number, plCode?: string | null) => {
      setLoading(true);
      fetchERPShipments({ page: p, page_size: 20, product_line_code: plCode || undefined })
        .then((res) => {
          setData(res.items);
          setTotal(res.total);
        })
        .catch(() => message.error(t("salesAndCost.shipments.errors.loadFailed", "加载发货记录失败")))
        .finally(() => setLoading(false));
    },
    [message, t],
  );

  useEffect(() => {
    fetchData(1, productLine);
  }, [productLine, fetchData]);

  const columns = [
    {
      title: t("salesAndCost.shipments.columns.shipmentNumber", "发货单号"),
      dataIndex: "shipment_number",
      key: "shipment_number",
      width: 140,
    },
    {
      title: t("salesAndCost.shipments.columns.customerCode", "客户编码"),
      dataIndex: "customer_code",
      key: "customer_code",
      width: 140,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("salesAndCost.shipments.columns.materialCode", "物料编码"),
      dataIndex: "material_code",
      key: "material_code",
      width: 140,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("salesAndCost.shipments.columns.lotNo", "批次号"),
      dataIndex: "lot_no",
      key: "lot_no",
      width: 140,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("salesAndCost.shipments.columns.quantity", "数量"),
      dataIndex: "quantity",
      key: "quantity",
      width: 100,
      render: (v: number | null) => v?.toLocaleString() ?? "—",
    },
    {
      title: t("salesAndCost.shipments.columns.shipmentDate", "发货日期"),
      dataIndex: "shipment_date",
      key: "shipment_date",
      width: 120,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("salesAndCost.shipments.columns.linkStatus", "关联状态"),
      dataIndex: "link_status",
      key: "link_status",
      width: 100,
      render: (v: string) => (
        <StatusBadge status={linkStatusVariant[v] || "info"}>{v}</StatusBadge>
      ),
    },
  ];

  return (
    <DataCard title={t("salesAndCost.shipments.cardTitle", "发货记录")}>
      <Table
        className="qf-table"
        columns={columns}
        dataSource={data}
        rowKey="erp_shipment_id"
        loading={loading}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => {
            setPage(p);
            fetchData(p, productLine);
          },
        }}
      />
    </DataCard>
  );
}

/* ─── Cost Records Tab ─── */

function CostRecordsTab() {
  const { t } = useTranslation("erp");
  const { message } = App.useApp();
  const [data, setData] = useState<ERPCostRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const productLine = useProductLineStore((s) => s.selected);

  const costCategoryLabels = useMemo((): Record<string, string> => ({
    prevention: t("salesAndCost.costRecords.categories.prevention", "预防成本"),
    appraisal: t("salesAndCost.costRecords.categories.appraisal", "鉴定成本"),
    internal_failure: t("salesAndCost.costRecords.categories.internalFailure", "内部损失"),
    external_failure: t("salesAndCost.costRecords.categories.externalFailure", "外部损失"),
  }), [t]);

  const fetchData = useCallback(
    (p: number, plCode?: string | null) => {
      setLoading(true);
      fetchERPCostRecords({ page: p, page_size: 20, product_line_code: plCode || undefined })
        .then((res) => {
          setData(res.items);
          setTotal(res.total);
        })
        .catch(() => message.error(t("salesAndCost.costRecords.errors.loadFailed", "加载成本记录失败")))
        .finally(() => setLoading(false));
    },
    [message, t],
  );

  useEffect(() => {
    fetchData(1, productLine);
  }, [productLine, fetchData]);

  // Aggregate COQ summary from current page data
  const coqSummary = data.reduce<Record<string, number>>((acc, rec) => {
    const cat = rec.cost_category;
    acc[cat] = (acc[cat] || 0) + rec.amount;
    return acc;
  }, {});

  const columns = [
    {
      title: t("salesAndCost.costRecords.columns.category", "成本类别"),
      dataIndex: "cost_category",
      key: "cost_category",
      width: 120,
      render: (v: string) => costCategoryLabels[v] || v,
    },
    {
      title: t("salesAndCost.costRecords.columns.type", "成本类型"),
      dataIndex: "cost_type",
      key: "cost_type",
      width: 140,
    },
    {
      title: t("salesAndCost.costRecords.columns.amount", "金额"),
      dataIndex: "amount",
      key: "amount",
      width: 120,
      render: (v: number) => `¥${v.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}`,
    },
    {
      title: t("salesAndCost.costRecords.columns.currency", "货币"),
      dataIndex: "currency",
      key: "currency",
      width: 80,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("salesAndCost.costRecords.columns.period", "期间"),
      dataIndex: "period_month",
      key: "period_month",
      width: 100,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("salesAndCost.costRecords.columns.sourceDocument", "来源单据"),
      dataIndex: "source_document_no",
      key: "source_document_no",
      width: 140,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("salesAndCost.costRecords.columns.description", "描述"),
      dataIndex: "description",
      key: "description",
      ellipsis: true,
      render: (v: string | null) => v || "—",
    },
  ];

  return (
    <DataCard title={t("salesAndCost.costRecords.cardTitle", "成本记录")}>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {Object.entries(coqSummary).map(([cat, amount]) => (
          <Col key={cat} span={6}>
            <Statistic
              title={costCategoryLabels[cat] || cat}
              value={amount}
              prefix="¥"
              precision={2}
              valueStyle={{ color: costCategoryColors[cat] }}
            />
          </Col>
        ))}
      </Row>
      <Table
        className="qf-table"
        columns={columns}
        dataSource={data}
        rowKey="cost_id"
        loading={loading}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => {
            setPage(p);
            fetchData(p, productLine);
          },
        }}
      />
    </DataCard>
  );
}

/* ─── Main Page ─── */

export default function ERPSalesAndCostPage() {
  const { t } = useTranslation("erp");
  const [activeTab, setActiveTab] = useState("sales_orders");

  return (
    <PageShell title={t("salesAndCost.title", "销售与成本")}>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          { key: "sales_orders", label: t("salesAndCost.tabs.salesOrders", "销售订单"), children: <SalesOrdersTab /> },
          { key: "shipments", label: t("salesAndCost.tabs.shipments", "发货记录"), children: <ShipmentsTab /> },
          { key: "cost_records", label: t("salesAndCost.tabs.costRecords", "成本记录"), children: <CostRecordsTab /> },
        ]}
      />
    </PageShell>
  );
}
import { useEffect, useState, useCallback, useMemo } from "react";
import {
  Table,
  Tag,
  Typography,
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

const { Title } = Typography;

const soStatusColors: Record<string, string> = {
  confirmed: "green",
  open: "blue",
  cancelled: "red",
  delivered: "default",
};

const linkStatusColors: Record<string, string> = {
  linked: "green",
  pending: "orange",
  unlinked: "default",
  error: "red",
};

const costCategoryColors: Record<string, string> = {
  prevention: "#52c41a",
  appraisal: "#1890ff",
  internal_failure: "#fa8c16",
  external_failure: "#f5222d",
};

function useCostCategoryLabels() {
  const { t } = useTranslation("erp");
  return useMemo(() => ({
    prevention: t("salesAndCost.costCategory.prevention"),
    appraisal: t("salesAndCost.costCategory.appraisal"),
    internal_failure: t("salesAndCost.costCategory.internalFailure"),
    external_failure: t("salesAndCost.costCategory.externalFailure"),
  }), [t]);
}

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
        .catch(() => message.error(t("salesAndCost.messages.loadSalesOrdersFailed")))
        .finally(() => setLoading(false));
    },
    [message, t],
  );

  useEffect(() => {
    fetchData(1, productLine);
  }, [productLine, fetchData]);

  const columns = [
    {
      title: t("salesAndCost.columns.soNumber"),
      dataIndex: "so_number",
      key: "so_number",
      width: 160,
    },
    {
      title: t("salesAndCost.columns.lineNumber"),
      dataIndex: "line_number",
      key: "line_number",
      width: 80,
    },
    {
      title: t("salesAndCost.columns.customerCode"),
      dataIndex: "customer_code",
      key: "customer_code",
      width: 140,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("salesAndCost.columns.materialCode"),
      dataIndex: "material_code",
      key: "material_code",
      width: 140,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("salesAndCost.columns.quantity"),
      dataIndex: "quantity",
      key: "quantity",
      width: 100,
      render: (v: number | null) => v?.toLocaleString() ?? "—",
    },
    {
      title: t("salesAndCost.columns.unitPrice"),
      dataIndex: "unit_price",
      key: "unit_price",
      width: 100,
      render: (v: number | null) =>
        v != null ? `¥${v.toFixed(2)}` : "—",
    },
    {
      title: t("salesAndCost.columns.status"),
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (v: string) => (
        <Tag color={soStatusColors[v] || "default"}>{v}</Tag>
      ),
    },
    {
      title: t("salesAndCost.columns.deliveryDate"),
      dataIndex: "delivery_date",
      key: "delivery_date",
      width: 120,
      render: (v: string | null) => v || "—",
    },
  ];

  return (
    <Table
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
        .catch(() => message.error(t("salesAndCost.messages.loadShipmentsFailed")))
        .finally(() => setLoading(false));
    },
    [message, t],
  );

  useEffect(() => {
    fetchData(1, productLine);
  }, [productLine, fetchData]);

  const columns = [
    {
      title: t("salesAndCost.columns.shipmentNumber"),
      dataIndex: "shipment_number",
      key: "shipment_number",
      width: 140,
    },
    {
      title: t("salesAndCost.columns.customerCode"),
      dataIndex: "customer_code",
      key: "customer_code",
      width: 140,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("salesAndCost.columns.materialCode"),
      dataIndex: "material_code",
      key: "material_code",
      width: 140,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("salesAndCost.columns.lotNo"),
      dataIndex: "lot_no",
      key: "lot_no",
      width: 140,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("salesAndCost.columns.quantity"),
      dataIndex: "quantity",
      key: "quantity",
      width: 100,
      render: (v: number | null) => v?.toLocaleString() ?? "—",
    },
    {
      title: t("salesAndCost.columns.shipmentDate"),
      dataIndex: "shipment_date",
      key: "shipment_date",
      width: 120,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("salesAndCost.columns.linkStatus"),
      dataIndex: "link_status",
      key: "link_status",
      width: 100,
      render: (v: string) => (
        <Tag color={linkStatusColors[v] || "default"}>{v}</Tag>
      ),
    },
  ];

  return (
    <Table
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
  );
}

/* ─── Cost Records Tab ─── */

function CostRecordsTab() {
  const { t } = useTranslation("erp");
  const costCategoryLabels = useCostCategoryLabels();
  const { message } = App.useApp();
  const [data, setData] = useState<ERPCostRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const productLine = useProductLineStore((s) => s.selected);

  const fetchData = useCallback(
    (p: number, plCode?: string | null) => {
      setLoading(true);
      fetchERPCostRecords({ page: p, page_size: 20, product_line_code: plCode || undefined })
        .then((res) => {
          setData(res.items);
          setTotal(res.total);
        })
        .catch(() => message.error(t("salesAndCost.messages.loadCostRecordsFailed")))
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
      title: t("salesAndCost.columns.costCategory"),
      dataIndex: "cost_category",
      key: "cost_category",
      width: 120,
      render: (v: string) => costCategoryLabels[v as keyof typeof costCategoryLabels] || v,
    },
    {
      title: t("salesAndCost.columns.costType"),
      dataIndex: "cost_type",
      key: "cost_type",
      width: 140,
    },
    {
      title: t("salesAndCost.columns.amount"),
      dataIndex: "amount",
      key: "amount",
      width: 120,
      render: (v: number) => `¥${v.toLocaleString(undefined, { minimumFractionDigits: 2 })}`,
    },
    {
      title: t("salesAndCost.columns.currency"),
      dataIndex: "currency",
      key: "currency",
      width: 80,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("salesAndCost.columns.period"),
      dataIndex: "period_month",
      key: "period_month",
      width: 100,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("salesAndCost.columns.sourceDocument"),
      dataIndex: "source_document_no",
      key: "source_document_no",
      width: 140,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("salesAndCost.columns.description"),
      dataIndex: "description",
      key: "description",
      ellipsis: true,
      render: (v: string | null) => v || "—",
    },
  ];

  return (
    <>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {Object.entries(coqSummary).map(([cat, amount]) => (
          <Col key={cat} span={6}>
            <Statistic
              title={costCategoryLabels[cat as keyof typeof costCategoryLabels] || cat}
              value={amount}
              prefix="¥"
              precision={2}
              valueStyle={{ color: costCategoryColors[cat] }}
            />
          </Col>
        ))}
      </Row>
      <Table
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
    </>
  );
}

/* ─── Main Page ─── */

export default function ERPSalesAndCostPage() {
  const { t } = useTranslation("erp");
  const [activeTab, setActiveTab] = useState("sales_orders");

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>
        {t("salesAndCost.title")}
      </Title>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          { key: "sales_orders", label: t("salesAndCost.tabs.salesOrders"), children: <SalesOrdersTab /> },
          { key: "shipments", label: t("salesAndCost.tabs.shipments"), children: <ShipmentsTab /> },
          { key: "cost_records", label: t("salesAndCost.tabs.costRecords"), children: <CostRecordsTab /> },
        ]}
      />
    </div>
  );
}

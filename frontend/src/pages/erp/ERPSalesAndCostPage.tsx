import { useEffect, useState, useCallback } from "react";
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

const costCategoryLabels: Record<string, string> = {
  prevention: "预防成本",
  appraisal: "鉴定成本",
  internal_failure: "内部损失",
  external_failure: "外部损失",
};

const costCategoryColors: Record<string, string> = {
  prevention: "#52c41a",
  appraisal: "#1890ff",
  internal_failure: "#fa8c16",
  external_failure: "#f5222d",
};

/* ─── Sales Orders Tab ─── */

function SalesOrdersTab() {
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
        .catch(() => message.error("加载销售订单失败"))
        .finally(() => setLoading(false));
    },
    [message],
  );

  useEffect(() => {
    fetchData(1, productLine);
  }, [productLine, fetchData]);

  const columns = [
    {
      title: "销售订单号",
      dataIndex: "so_number",
      key: "so_number",
      width: 160,
    },
    {
      title: "行号",
      dataIndex: "line_number",
      key: "line_number",
      width: 80,
    },
    {
      title: "客户编码",
      dataIndex: "customer_code",
      key: "customer_code",
      width: 140,
      render: (v: string | null) => v || "—",
    },
    {
      title: "物料编码",
      dataIndex: "material_code",
      key: "material_code",
      width: 140,
      render: (v: string | null) => v || "—",
    },
    {
      title: "数量",
      dataIndex: "quantity",
      key: "quantity",
      width: 100,
      render: (v: number | null) => v?.toLocaleString() ?? "—",
    },
    {
      title: "单价",
      dataIndex: "unit_price",
      key: "unit_price",
      width: 100,
      render: (v: number | null) =>
        v != null ? `¥${v.toFixed(2)}` : "—",
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (v: string) => (
        <Tag color={soStatusColors[v] || "default"}>{v}</Tag>
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
        .catch(() => message.error("加载发货记录失败"))
        .finally(() => setLoading(false));
    },
    [message],
  );

  useEffect(() => {
    fetchData(1, productLine);
  }, [productLine, fetchData]);

  const columns = [
    {
      title: "发货单号",
      dataIndex: "shipment_number",
      key: "shipment_number",
      width: 140,
    },
    {
      title: "客户编码",
      dataIndex: "customer_code",
      key: "customer_code",
      width: 140,
      render: (v: string | null) => v || "—",
    },
    {
      title: "物料编码",
      dataIndex: "material_code",
      key: "material_code",
      width: 140,
      render: (v: string | null) => v || "—",
    },
    {
      title: "批次号",
      dataIndex: "lot_no",
      key: "lot_no",
      width: 140,
      render: (v: string | null) => v || "—",
    },
    {
      title: "数量",
      dataIndex: "quantity",
      key: "quantity",
      width: 100,
      render: (v: number | null) => v?.toLocaleString() ?? "—",
    },
    {
      title: "发货日期",
      dataIndex: "shipment_date",
      key: "shipment_date",
      width: 120,
      render: (v: string | null) => v || "—",
    },
    {
      title: "关联状态",
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
        .catch(() => message.error("加载成本记录失败"))
        .finally(() => setLoading(false));
    },
    [message],
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
      title: "成本类别",
      dataIndex: "cost_category",
      key: "cost_category",
      width: 120,
      render: (v: string) => costCategoryLabels[v] || v,
    },
    {
      title: "成本类型",
      dataIndex: "cost_type",
      key: "cost_type",
      width: 140,
    },
    {
      title: "金额",
      dataIndex: "amount",
      key: "amount",
      width: 120,
      render: (v: number) => `¥${v.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}`,
    },
    {
      title: "货币",
      dataIndex: "currency",
      key: "currency",
      width: 80,
      render: (v: string | null) => v || "—",
    },
    {
      title: "期间",
      dataIndex: "period_month",
      key: "period_month",
      width: 100,
      render: (v: string | null) => v || "—",
    },
    {
      title: "来源单据",
      dataIndex: "source_document_no",
      key: "source_document_no",
      width: 140,
      render: (v: string | null) => v || "—",
    },
    {
      title: "描述",
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
  const [activeTab, setActiveTab] = useState("sales_orders");

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>
        销售与成本
      </Title>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          { key: "sales_orders", label: "销售订单", children: <SalesOrdersTab /> },
          { key: "shipments", label: "发货记录", children: <ShipmentsTab /> },
          { key: "cost_records", label: "成本记录", children: <CostRecordsTab /> },
        ]}
      />
    </div>
  );
}

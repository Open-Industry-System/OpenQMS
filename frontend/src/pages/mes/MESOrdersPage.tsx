import { useEffect, useState } from "react";
import {
  Table, Tag, Typography, Select, App,
} from "antd";
import { listProductionOrders } from "../../api/mes";
import type { MESProductionOrder } from "../../types/mes";

const { Title } = Typography;

const statusColors: Record<string, string> = {
  planned: "blue",
  in_progress: "processing",
  completed: "success",
  closed: "default",
};

const statusLabels: Record<string, string> = {
  planned: "计划中",
  in_progress: "进行中",
  completed: "已完成",
  closed: "已关闭",
};

export default function MESOrdersPage() {
  const { message } = App.useApp();
  const [data, setData] = useState<MESProductionOrder[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>("");

  const fetchData = (p: number = page, status?: string) => {
    setLoading(true);
    listProductionOrders(p, 20, status)
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error("加载生产工单失败"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData(1, statusFilter || undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  const handleStatusChange = (value: string) => {
    setStatusFilter(value);
    setPage(1);
  };

  const columns = [
    { title: "工单号", dataIndex: "order_no", key: "order_no", width: 140 },
    {
      title: "产品型号",
      dataIndex: "product_model",
      key: "product_model",
      ellipsis: true,
      render: (v: string | null) => v || "—",
    },
    {
      title: "计划数量",
      dataIndex: "planned_qty",
      key: "planned_qty",
      width: 100,
      render: (v: number | null) => v ?? "—",
    },
    {
      title: "实际数量",
      dataIndex: "actual_qty",
      key: "actual_qty",
      width: 100,
      render: (v: number | null) => v ?? "—",
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (s: string) => (
        <Tag color={statusColors[s] || "default"}>
          {statusLabels[s] || s}
        </Tag>
      ),
    },
    {
      title: "开始时间",
      dataIndex: "started_at",
      key: "started_at",
      width: 170,
      render: (v: string | null) =>
        v ? new Date(v).toLocaleString("zh-CN") : "—",
    },
    {
      title: "完成时间",
      dataIndex: "completed_at",
      key: "completed_at",
      width: 170,
      render: (v: string | null) =>
        v ? new Date(v).toLocaleString("zh-CN") : "—",
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16, alignItems: "center" }}>
        <Title level={4} style={{ margin: 0 }}>生产工单</Title>
        <Select
          placeholder="筛选状态"
          allowClear
          style={{ width: 140 }}
          value={statusFilter || undefined}
          onChange={handleStatusChange}
          options={[
            { value: "planned", label: "计划中" },
            { value: "in_progress", label: "进行中" },
            { value: "completed", label: "已完成" },
            { value: "closed", label: "已关闭" },
          ]}
        />
      </div>

      <Table
        columns={columns}
        dataSource={data}
        rowKey="order_id"
        loading={loading}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => {
            setPage(p);
            fetchData(p, statusFilter || undefined);
          },
        }}
      />
    </div>
  );
}

import { useEffect, useState, useMemo } from "react";
import {
  Table, Select, App,
} from "antd";
import { useTranslation } from "react-i18next";
import { listProductionOrders } from "../../api/mes";
import { useProductLineStore } from "../../store/productLineStore";
import type { MESProductionOrder } from "../../types/mes";
import { PageShell, DataCard, StatusBadge } from "../../components/design";
import { formatDateTime } from "../../utils/dateTime";

const statusVariant: Record<string, string> = {
  planned: "info",
  in_progress: "warning",
  completed: "success",
  closed: "info",
};

export default function MESOrdersPage() {
  const { t } = useTranslation("mes");
  const { message } = App.useApp();
  const [data, setData] = useState<MESProductionOrder[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const productLine = useProductLineStore((s) => s.selected);

  const statusLabels = useMemo(() => ({
    planned: t("orders.status.planned"),
    in_progress: t("orders.status.inProgress"),
    completed: t("orders.status.completed"),
    closed: t("orders.status.closed"),
  }), [t]);

  const statusFilterOptions = useMemo(() => [
    { value: "planned", label: t("orders.status.planned") },
    { value: "in_progress", label: t("orders.status.inProgress") },
    { value: "completed", label: t("orders.status.completed") },
    { value: "closed", label: t("orders.status.closed") },
  ], [t]);

  const fetchData = (p: number = page, currentStatus?: string, plCode?: string | null) => {
    setLoading(true);
    listProductionOrders(p, 20, plCode || undefined, currentStatus || undefined)
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error(t("orders.messages.loadFailed")))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData(1, statusFilter || undefined, productLine);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, productLine]);

  const handleStatusChange = (value: string) => {
    setStatusFilter(value);
    setPage(1);
  };

  const columns = useMemo(() => [
    { title: t("orders.columns.orderNo"), dataIndex: "order_no", key: "order_no", width: 140 },
    {
      title: t("orders.columns.productModel"),
      dataIndex: "product_model",
      key: "product_model",
      ellipsis: true,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("orders.columns.plannedQty"),
      dataIndex: "planned_qty",
      key: "planned_qty",
      width: 100,
      render: (v: number | null) => v ?? "—",
    },
    {
      title: t("orders.columns.actualQty"),
      dataIndex: "actual_qty",
      key: "actual_qty",
      width: 100,
      render: (v: number | null) => v ?? "—",
    },
    {
      title: t("orders.columns.status"),
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (s: string) => (
        <StatusBadge status={statusVariant[s] || s}>
          {statusLabels[s as keyof typeof statusLabels] || s}
        </StatusBadge>
      ),
    },
    {
      title: t("orders.columns.startedAt"),
      dataIndex: "started_at",
      key: "started_at",
      width: 170,
      render: (v: string | null) => v ? formatDateTime(v) : "—",
    },
    {
      title: t("orders.columns.completedAt"),
      dataIndex: "completed_at",
      key: "completed_at",
      width: 170,
      render: (v: string | null) => v ? formatDateTime(v) : "—",
    },
  ], [t, statusLabels]);

  return (
    <PageShell
      title={t("orders.title")}
      actions={
        <Select
          placeholder={t("orders.filterPlaceholder")}
          allowClear
          style={{ width: 140 }}
          value={statusFilter || undefined}
          onChange={handleStatusChange}
          options={statusFilterOptions}
        />
      }
    >
      <DataCard title={t("orders.title")}>
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
              fetchData(p, statusFilter || undefined, productLine);
            },
          }}
          className="qf-table"
        />
      </DataCard>
    </PageShell>
  );
}
import { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Table, Button, Space, Select, Tag, Card } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { usePermission } from "../../hooks/usePermission";
import { useProductLineStore } from "../../store/productLineStore";
import { listManagementReviews } from "../../api/managementReview";
import type { ManagementReview } from "../../types";
import { useReviewStatusMap, useReviewStatusColor } from "./useOptions";

export default function ManagementReviewListPage() {
  const { t } = useTranslation("managementReview");
  const { t: tc } = useTranslation("common");
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { canEdit } = usePermission();
  const { selected: selectedPL } = useProductLineStore();

  const statusMap = useReviewStatusMap();
  const statusColor = useReviewStatusColor();

  const [data, setData] = useState<ManagementReview[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(Number(searchParams.get("page")) || 1);
  const [statusFilter, setStatusFilter] = useState(searchParams.get("status") || undefined);

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await listManagementReviews({
        page,
        page_size: 20,
        status: statusFilter,
        product_line_code: selectedPL || undefined,
      });
      setData(res.items);
      setTotal(res.total);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const params = new URLSearchParams();
    if (page > 1) params.set("page", String(page));
    if (statusFilter) params.set("status", statusFilter);
    setSearchParams(params, { replace: true });
    fetchData();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, statusFilter, selectedPL]);

  const columns = [
    { title: t("table.docNo"), dataIndex: "doc_no", key: "doc_no", width: 140 },
    { title: t("table.title"), dataIndex: "title", key: "title" },
    { title: t("table.reviewDate"), dataIndex: "review_date", key: "review_date", width: 120 },
    {
      title: t("table.status"), dataIndex: "status", key: "status", width: 120,
      render: (s: string) => {
        const info = statusMap[s] ? { color: statusColor[s], label: statusMap[s] } : { color: "default", label: s };
        return <Tag color={info.color}>{info.label}</Tag>;
      },
    },
    {
      title: t("table.productLine"), dataIndex: "product_line_code", key: "product_line_code", width: 120,
      render: (v: string | null) => v || t("descriptions.allPlants"),
    },
    {
      title: t("table.operations"), key: "action", width: 80,
      render: (_: unknown, record: ManagementReview) => (
        <Button type="link" onClick={() => navigate(`/management-reviews/${record.review_id}`)}>{tc("actions.view")}</Button>
      ),
    },
  ];

  return (
    <Card title={t("pageTitle.list")}>
      <Space style={{ marginBottom: 16 }}>
        {canEdit('management_review') && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate("/management-reviews/new")}>{t("actions.newReview")}</Button>
        )}
        <Select
          allowClear placeholder={t("table.status")} style={{ width: 150 }}
          value={statusFilter}
          onChange={(v) => { setStatusFilter(v); setPage(1); }}
        >
          {Object.entries(statusMap).map(([k, v]) => (
            <Select.Option key={k} value={k}>{v}</Select.Option>
          ))}
        </Select>
      </Space>
      <Table
        rowKey="review_id" columns={columns} dataSource={data} loading={loading}
        pagination={{ total, current: page, pageSize: 20, onChange: setPage }}
      />
    </Card>
  );
}

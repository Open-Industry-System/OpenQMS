import { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Table, Button, Space, Select, Tag, Card } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { usePermission } from "../../hooks/usePermission";
import { useProductLineStore } from "../../store/productLineStore";
import { listManagementReviews } from "../../api/managementReview";
import type { ManagementReview } from "../../types";

const statusMap: Record<string, { color: string; label: string }> = {
  draft: { color: "blue", label: "草稿" },
  data_collected: { color: "cyan", label: "数据已汇总" },
  in_review: { color: "orange", label: "评审中" },
  closed: { color: "green", label: "已关闭" },
};

export default function ManagementReviewListPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { canEdit } = usePermission();
  const { selected: selectedPL } = useProductLineStore();

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
    { title: "编号", dataIndex: "doc_no", key: "doc_no", width: 140 },
    { title: "主题", dataIndex: "title", key: "title" },
    { title: "评审日期", dataIndex: "review_date", key: "review_date", width: 120 },
    {
      title: "状态", dataIndex: "status", key: "status", width: 120,
      render: (s: string) => {
        const info = statusMap[s] || { color: "default", label: s };
        return <Tag color={info.color}>{info.label}</Tag>;
      },
    },
    {
      title: "产品线", dataIndex: "product_line_code", key: "product_line_code", width: 120,
      render: (v: string | null) => v || "全厂",
    },
    {
      title: "操作", key: "action", width: 80,
      render: (_: unknown, record: ManagementReview) => (
        <Button type="link" onClick={() => navigate(`/management-reviews/${record.review_id}`)}>查看</Button>
      ),
    },
  ];

  return (
    <Card title="管理评审">
      <Space style={{ marginBottom: 16 }}>
        {canEdit('management_review') && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate("/management-reviews/new")}>新建评审</Button>
        )}
        <Select
          allowClear placeholder="状态筛选" style={{ width: 150 }}
          value={statusFilter}
          onChange={(v) => { setStatusFilter(v); setPage(1); }}
        >
          {Object.entries(statusMap).map(([k, v]) => (
            <Select.Option key={k} value={k}>{v.label}</Select.Option>
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
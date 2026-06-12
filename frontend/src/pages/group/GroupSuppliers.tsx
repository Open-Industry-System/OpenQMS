import { useEffect, useState } from "react";
import { Table, Spin, Typography, Tag } from "antd";
import { getSharedSuppliers, type SharedSupplierResponse } from "../../api/group";
import { usePermission } from "../../hooks/usePermission";

const { Title } = Typography;

export default function GroupSuppliersPage() {
  const { canView } = usePermission();
  const [suppliers, setSuppliers] = useState<SharedSupplierResponse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!canView("group")) return;
    setLoading(true);
    getSharedSuppliers()
      .then((res) => setSuppliers(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [canView]);

  if (!canView("group")) {
    return <div style={{ padding: 24 }}>您没有集团管理权限</div>;
  }

  const columns = [
    {
      title: "供应商名称",
      dataIndex: "name",
      key: "name",
      width: 200,
    },
    {
      title: "简称",
      dataIndex: "short_name",
      key: "short_name",
      width: 120,
      render: (v: string | null) => v || "-",
    },
    {
      title: "统一信用代码",
      dataIndex: "unified_credit_code",
      key: "unified_credit_code",
      width: 180,
      render: (v: string | null) => v || "-",
    },
    {
      title: "行业",
      dataIndex: "industry",
      key: "industry",
      width: 120,
      render: (v: string | null) => v || "-",
    },
    {
      title: "各厂评价",
      key: "evaluations",
      render: (_: unknown, record: SharedSupplierResponse) => (
        <span>
          {record.factory_evaluations.map((e) => (
            <Tag key={e.factory_code}>
              {e.factory_code}: {e.grade}({e.total_score.toFixed(1)})
            </Tag>
          ))}
        </span>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>共享供应商</Title>
      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 48 }}><Spin size="large" /></div>
      ) : (
        <Table
          columns={columns}
          dataSource={suppliers}
          rowKey="name"
          pagination={{ pageSize: 20 }}
        />
      )}
    </div>
  );
}
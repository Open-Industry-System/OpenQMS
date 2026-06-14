import { useEffect, useState } from "react";
import { Table, Spin } from "antd";
import { getFactoryComparison, type FactoryComparisonResponse } from "../../api/group";
import { usePermission } from "../../hooks/usePermission";
import { PageShell, DataCard } from "../../components/design";

export default function FactoryComparisonPage() {
  const { canView } = usePermission();
  const [data, setData] = useState<FactoryComparisonResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!canView("group")) return;
    setLoading(true);
    getFactoryComparison()
      .then((res) => setData(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [canView]);

  if (!canView("group")) {
    return <div style={{ padding: 24 }}>您没有集团管理权限</div>;
  }

  if (loading) {
    return <div style={{ display: "flex", justifyContent: "center", padding: 48 }}><Spin size="large" /></div>;
  }

  if (!data) {
    return <div style={{ padding: 24 }}>暂无数据</div>;
  }

  const columns = [
    { title: "工厂编码", dataIndex: "factory_code", key: "factory_code", fixed: "left" as const, width: 100 },
    { title: "工厂名称", dataIndex: "factory_name", key: "factory_name", fixed: "left" as const, width: 150 },
    ...data.metric_names.map((name) => ({
      title: name,
      key: name,
      width: 120,
      render: (_: unknown, record: { metrics: Record<string, number> }) => record.metrics[name] ?? "-",
    })),
  ];

  return (
    <PageShell title="工厂对比">
      <DataCard title="对比指标">
        <Table
          columns={columns}
          dataSource={data.factories}
          rowKey="factory_id"
          scroll={{ x: "max-content" }}
          pagination={false}
          className="qf-table"
        />
      </DataCard>
    </PageShell>
  );
}

import { useEffect, useState } from "react";
import { Table, Spin, Tag } from "antd";
import { getCrossFactoryAudits, type CrossFactoryAuditResponse } from "../../api/group";
import { usePermission } from "../../hooks/usePermission";
import { PageShell, DataCard, StatusBadge } from "../../components/design";

export default function GroupAuditsPage() {
  const { canView } = usePermission();
  const [audits, setAudits] = useState<CrossFactoryAuditResponse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!canView("group")) return;
    setLoading(true);
    getCrossFactoryAudits()
      .then((res) => setAudits(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [canView]);

  if (!canView("group")) {
    return <div style={{ padding: 24 }}>您没有集团管理权限</div>;
  }

  const columns = [
    {
      title: "审核编号",
      dataIndex: "program_no",
      key: "program_no",
      width: 150,
    },
    {
      title: "审核类型",
      dataIndex: "audit_type",
      key: "audit_type",
      width: 120,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (status: string) => (
        <StatusBadge status={status}>{status}</StatusBadge>
      ),
    },
    {
      title: "涉及工厂",
      key: "factories",
      render: (_: unknown, record: CrossFactoryAuditResponse) => (
        <span>
          {record.target_factory_codes.map((code) => (
            <Tag key={code}>{code}</Tag>
          ))}
        </span>
      ),
    },
    {
      title: "发现项数",
      dataIndex: "finding_count",
      key: "finding_count",
      width: 100,
    },
  ];

  return (
    <PageShell title="跨厂审核">
      <DataCard title="审核列表">
        {loading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: 48 }}><Spin size="large" /></div>
        ) : (
          <Table
            columns={columns}
            dataSource={audits}
            rowKey="program_id"
            pagination={{ pageSize: 20 }}
            className="qf-table"
          />
        )}
      </DataCard>
    </PageShell>
  );
}

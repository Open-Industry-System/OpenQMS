import { useEffect, useState } from "react";
import { Table, Spin, Typography, Tag } from "antd";
import { getCrossFactoryAudits, type CrossFactoryAuditResponse } from "../../api/group";
import { usePermission } from "../../hooks/usePermission";

const { Title } = Typography;

const statusColors: Record<string, string> = {
  planned: "blue",
  in_progress: "orange",
  completed: "green",
  cancelled: "red",
};

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
        <Tag color={statusColors[status] || "default"}>{status}</Tag>
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
    <div style={{ padding: 24 }}>
      <Title level={3}>跨厂审核</Title>
      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 48 }}><Spin size="large" /></div>
      ) : (
        <Table
          columns={columns}
          dataSource={audits}
          rowKey="program_id"
          pagination={{ pageSize: 20 }}
        />
      )}
    </div>
  );
}
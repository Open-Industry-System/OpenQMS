import { useEffect, useState } from "react";
import { Table, Spin, Typography, Tag } from "antd";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation("group");
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
    return <div style={{ padding: 24 }}>{t("noPermission")}</div>;
  }

  const columns = [
    {
      title: t("audits.columns.programNo"),
      dataIndex: "program_no",
      key: "program_no",
      width: 150,
    },
    {
      title: t("audits.columns.auditType"),
      dataIndex: "audit_type",
      key: "audit_type",
      width: 120,
    },
    {
      title: t("audits.columns.status"),
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (status: string) => (
        <Tag color={statusColors[status] || "default"}>{status}</Tag>
      ),
    },
    {
      title: t("audits.columns.factories"),
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
      title: t("audits.columns.findingCount"),
      dataIndex: "finding_count",
      key: "finding_count",
      width: 100,
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>{t("audits.title")}</Title>
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

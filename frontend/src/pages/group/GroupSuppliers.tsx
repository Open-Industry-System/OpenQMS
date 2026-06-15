import { useEffect, useState } from "react";
import { Table, Spin, Typography, Tag } from "antd";
import { useTranslation } from "react-i18next";
import { getSharedSuppliers, type SharedSupplierResponse } from "../../api/group";
import { usePermission } from "../../hooks/usePermission";

const { Title } = Typography;

export default function GroupSuppliersPage() {
  const { canView } = usePermission();
  const { t } = useTranslation("group");
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
    return <div style={{ padding: 24 }}>{t("noPermission")}</div>;
  }

  const columns = [
    {
      title: t("suppliers.columns.name"),
      dataIndex: "name",
      key: "name",
      width: 200,
    },
    {
      title: t("suppliers.columns.shortName"),
      dataIndex: "short_name",
      key: "short_name",
      width: 120,
      render: (v: string | null) => v || "-",
    },
    {
      title: t("suppliers.columns.unifiedCreditCode"),
      dataIndex: "unified_credit_code",
      key: "unified_credit_code",
      width: 180,
      render: (v: string | null) => v || "-",
    },
    {
      title: t("suppliers.columns.industry"),
      dataIndex: "industry",
      key: "industry",
      width: 120,
      render: (v: string | null) => v || "-",
    },
    {
      title: t("suppliers.columns.evaluations"),
      key: "evaluations",
      render: (_: unknown, record: SharedSupplierResponse) => (
        <span>
          {record.factory_evaluations.map((e) => (
            <Tag key={e.factory_code}>
              {t("suppliers.evaluationTag", {
                factory_code: e.factory_code,
                grade: e.grade,
                score: e.total_score.toFixed(1),
              })}
            </Tag>
          ))}
        </span>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>{t("suppliers.title")}</Title>
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

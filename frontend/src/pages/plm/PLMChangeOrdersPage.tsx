import { useEffect, useState, useMemo } from "react";
import { Table, Button, Tag, Typography, App } from "antd";
import { ThunderboltOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { getPLMChangeOrders, triggerImpactAnalysis } from "../../api/plm";
import { useProductLineStore } from "../../store/productLineStore";
import type { PLMChangeOrder } from "../../types/plm";
import { usePermission } from "../../hooks/usePermission";

const { Title } = Typography;

const statusColors: Record<string, string> = {
  open: "blue",
  in_review: "orange",
  approved: "green",
  implemented: "cyan",
  closed: "default",
  cancelled: "red",
};

function useChangeTypeLabels() {
  const { t } = useTranslation("plm");
  return useMemo(() => ({
    ECN: t("changeOrders.changeType.ECN"),
    ECR: t("changeOrders.changeType.ECR"),
    SCN: t("changeOrders.changeType.SCN"),
  }), [t]);
}

export default function PLMChangeOrdersPage() {
  const { t } = useTranslation("plm");
  const changeTypeLabels = useChangeTypeLabels();
  const { message } = App.useApp();
  const { canEdit } = usePermission();
  const canEditPlm = canEdit("plm");
  const productLine = useProductLineStore((s) => s.selected);
  const [data, setData] = useState<PLMChangeOrder[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [impactLoading, setImpactLoading] = useState<Record<string, boolean>>({});

  const fetchData = (p: number = page, plCode?: string | null) => {
    setLoading(true);
    getPLMChangeOrders({ page: p, page_size: 20, product_line_code: plCode || undefined })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error(t("changeOrders.messages.loadFailed")))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    setPage(1);
    fetchData(1, productLine);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine]);

  const handleImpactAnalysis = async (changeId: string) => {
    setImpactLoading((prev) => ({ ...prev, [changeId]: true }));
    try {
      await triggerImpactAnalysis(changeId);
      message.success(t("changeOrders.messages.impactAnalysisTriggered"));
    } catch {
      message.error(t("changeOrders.messages.impactAnalysisFailed"));
    } finally {
      setImpactLoading((prev) => ({ ...prev, [changeId]: false }));
    }
  };

  const columns = useMemo(
    () => {
      const baseColumns = [
        { title: t("changeOrders.columns.changeNumber"), dataIndex: "change_number", key: "change_number", width: 160 },
        { title: t("changeOrders.columns.title"), dataIndex: "title", key: "title", ellipsis: true },
        {
          title: t("changeOrders.columns.changeType"),
          dataIndex: "change_type",
          key: "change_type",
          width: 130,
          render: (type: string) => changeTypeLabels[type as keyof typeof changeTypeLabels] || type,
        },
        {
          title: t("changeOrders.columns.status"),
          dataIndex: "status",
          key: "status",
          width: 100,
          render: (s: string) => <Tag color={statusColors[s] || "default"}>{s}</Tag>,
        },
        { title: t("changeOrders.columns.priority"), dataIndex: "priority", key: "priority", width: 80 },
      ];

      if (!canEditPlm) return baseColumns;

      return [
        ...baseColumns,
        {
          title: t("changeOrders.columns.actions"),
          key: "actions",
          width: 160,
          render: (_: unknown, record: PLMChangeOrder) => (
            <Button
              type="link"
              size="small"
              icon={<ThunderboltOutlined />}
              loading={impactLoading[record.change_id]}
              onClick={() => handleImpactAnalysis(record.change_id)}
            >
              {t("changeOrders.impactAnalysis")}
            </Button>
          ),
        },
      ];
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [canEditPlm, impactLoading, t, changeTypeLabels],
  );

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>
        {t("changeOrders.title")}
      </Title>

      <Table
        columns={columns}
        dataSource={data}
        rowKey="change_id"
        loading={loading}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => {
            setPage(p);
            fetchData(p, productLine);
          },
        }}
      />
    </div>
  );
}

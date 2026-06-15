import { Table } from "antd";
import { useTranslation } from "react-i18next";
import { formatDateTime } from "../../utils/dateTime";
import type { ChangeImpactAnalysis } from "../../api/changeImpact";
import ImpactScoreTag from "./ImpactScoreTag";

interface ChangeHistoryTableProps {
  data: ChangeImpactAnalysis[];
  loading?: boolean;
  onSelect?: (record: ChangeImpactAnalysis) => void;
}

export default function ChangeHistoryTable({
  data,
  loading,
  onSelect,
}: ChangeHistoryTableProps) {
  const { t } = useTranslation("changeImpact");
  return (
    <Table
      rowKey="id"
      loading={loading}
      dataSource={data}
      onRow={(record) => ({
        onClick: () => onSelect?.(record),
        style: { cursor: onSelect ? "pointer" : "default" },
      })}
      columns={[
        {
          title: t("historyTable.time"),
          dataIndex: "created_at",
          key: "created_at",
          render: (value: string) => formatDateTime(value),
        },
        {
          title: t("historyTable.nodeName"),
          dataIndex: "node_name",
          key: "node_name",
        },
        {
          title: t("historyTable.changeType"),
          dataIndex: "change_type",
          key: "change_type",
          render: (value: string) =>
            value === "attribute" ? t("report.changeTypeAttribute") : t("report.changeTypeStructure"),
        },
        {
          title: t("historyTable.impactScore"),
          dataIndex: "impact_score",
          key: "impact_score",
          render: (value: number) => <ImpactScoreTag score={value} />,
        },
        {
          title: t("historyTable.affectedCount"),
          key: "affected_count",
          render: (_: unknown, record: ChangeImpactAnalysis) =>
            record.impact_result?.summary?.total_affected ?? 0,
        },
      ]}
    />
  );
}

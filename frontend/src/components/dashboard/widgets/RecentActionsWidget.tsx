import { Card, Table, Button, Tag } from "antd";
import { HistoryOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import type { WidgetProps } from "./types";
import { useRelativeTime } from "../../../utils/relativeTime";

interface RecentActionRow {
  record_id: string;
  table_name?: string;
  entity_no?: string;
  action?: string;
  operated_at?: string;
}

export default function RecentActionsWidget({ data, loading, error, onRetry }: WidgetProps) {
  const { t } = useTranslation("dashboard");
  const formatTime = useRelativeTime();
  const items = (data.recent_actions ?? []) as RecentActionRow[];

  const actionLabel = (raw?: string) =>
    raw ? t(`recentActions.actionLabels.${raw}`, { defaultValue: t("recentActions.actionLabels.other") }) : "";
  const moduleLabel = (table?: string) =>
    table
      ? t(`recentActions.moduleLabels.${table}`, { defaultValue: t("recentActions.moduleLabels.other") })
      : t("recentActions.moduleLabels.other");

  const columns = [
    {
      title: t("recentActions.columns.action"),
      dataIndex: "action",
      key: "action",
      width: 110,
      render: (action: string) => <Tag>{actionLabel(action)}</Tag>,
    },
    {
      title: t("recentActions.columns.object"),
      key: "object",
      ellipsis: true,
      render: (_: unknown, row: RecentActionRow) => {
        const module = moduleLabel(row.table_name);
        return row.entity_no ? `${module} · ${row.entity_no}` : module;
      },
    },
    {
      title: t("recentActions.columns.time"),
      dataIndex: "operated_at",
      key: "operated_at",
      width: 130,
      render: (ts: string) => (ts ? formatTime(ts) : ""),
    },
  ];

  return (
    <Card
      title={<><HistoryOutlined /> {t("widget.recentActions")}</>}
      size="small"
      loading={loading}
    >
      {error ? (
        <Button onClick={onRetry} size="small">{t("riskList.retry")}</Button>
      ) : (
        <Table
          size="small"
          columns={columns}
          dataSource={items}
          rowKey="record_id"
          pagination={false}
          scroll={{ y: 200 }}
        />
      )}
    </Card>
  );
}

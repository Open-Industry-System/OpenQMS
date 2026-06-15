import { Card, Table, Button } from "antd";
import { HistoryOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import type { WidgetProps } from "./types";

export default function RecentActionsWidget({ data, loading, error, onRetry }: WidgetProps) {
  const { t } = useTranslation("dashboard");
  const items = data.recent_actions ?? [];

  const columns = [
    { title: t("recentActions.columns.action"), dataIndex: "action", key: "action", width: 120 },
    { title: t("recentActions.columns.object"), dataIndex: "entity_no", key: "entity_no", ellipsis: true },
    { title: t("recentActions.columns.time"), dataIndex: "operated_at", key: "operated_at", width: 180 },
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

import { Card, Table, Button } from "antd";
import { HistoryOutlined } from "@ant-design/icons";
import type { WidgetProps } from "./types";

export default function RecentActionsWidget({ data, loading, error, onRetry }: WidgetProps) {
  const items = data.recent_actions ?? [];

  const columns = [
    { title: "操作", dataIndex: "action", key: "action", width: 120 },
    { title: "对象", dataIndex: "entity_no", key: "entity_no", ellipsis: true },
    { title: "时间", dataIndex: "operated_at", key: "operated_at", width: 180 },
  ];

  return (
    <Card
      title={<><HistoryOutlined /> 最近操作</>}
      size="small"
      loading={loading}
    >
      {error ? (
        <Button onClick={onRetry} size="small">重试</Button>
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

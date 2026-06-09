import { Card, List, Button, Tag } from "antd";
import { ClockCircleOutlined } from "@ant-design/icons";
import type { WidgetProps } from "./types";

export default function AlertOverdueCapaWidget({ data, loading, error, onRetry }: WidgetProps) {
  const items = data.alerts?.overdue_capas ?? [];

  return (
    <Card
      title={<><ClockCircleOutlined /> 超期 CAPA Top5</>}
      size="small"
      loading={loading}
    >
      {error ? (
        <Button onClick={onRetry} size="small">重试</Button>
      ) : items.length === 0 ? (
        <span style={{ color: "#999" }}>暂无超期 CAPA</span>
      ) : (
        <List
          size="small"
          dataSource={items}
          renderItem={(item) => (
            <List.Item>
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>
                {item.document_no}
              </span>
              <Tag color="orange">超期 {item.overdue_days} 天</Tag>
            </List.Item>
          )}
        />
      )}
    </Card>
  );
}

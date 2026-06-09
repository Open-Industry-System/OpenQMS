import { Card, List, Button, Tag } from "antd";
import { WarningOutlined } from "@ant-design/icons";
import type { WidgetProps } from "./types";

export default function AlertHighRpnWidget({ data, loading, error, onRetry }: WidgetProps) {
  const items = data.alerts?.high_rpn_fmeas ?? [];

  return (
    <Card
      title={<><WarningOutlined /> 高 RPN FMEA Top5</>}
      size="small"
      loading={loading}
    >
      {error ? (
        <Button onClick={onRetry} size="small">重试</Button>
      ) : items.length === 0 ? (
        <span style={{ color: "#999" }}>暂无高 RPN 项</span>
      ) : (
        <List
          size="small"
          dataSource={items}
          renderItem={(item) => (
            <List.Item>
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>
                {item.document_no} — {item.node_name}
              </span>
              <Tag color="red">RPN {item.rpn}</Tag>
            </List.Item>
          )}
        />
      )}
    </Card>
  );
}

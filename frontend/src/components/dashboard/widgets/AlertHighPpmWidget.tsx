import { Card, List, Button, Tag } from "antd";
import { AlertOutlined } from "@ant-design/icons";
import type { WidgetProps } from "./types";

export default function AlertHighPpmWidget({ data, loading, error, onRetry }: WidgetProps) {
  const items = data.alerts?.high_ppm_suppliers ?? [];

  return (
    <Card
      title={<><AlertOutlined /> PPM 超标供应商 Top5</>}
      size="small"
      loading={loading}
    >
      {error ? (
        <Button onClick={onRetry} size="small">重试</Button>
      ) : items.length === 0 ? (
        <span style={{ color: "#999" }}>暂无超标供应商</span>
      ) : (
        <List
          size="small"
          dataSource={items}
          renderItem={(item) => (
            <List.Item>
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>
                {item.supplier_name}
              </span>
              <Tag color="red">PPM {item.ppm}</Tag>
            </List.Item>
          )}
        />
      )}
    </Card>
  );
}

import { Card, List, Button, Tag } from "antd";
import { ShopOutlined } from "@ant-design/icons";
import type { WidgetProps } from "./types";

export default function SupplierPpmWidget({ data, loading, error, onRetry }: WidgetProps) {
  const items = data.supplier?.ppm_trend ?? [];

  return (
    <Card
      title={<><ShopOutlined /> 供应商 PPM 趋势 Top5</>}
      size="small"
      loading={loading}
    >
      {error ? (
        <Button onClick={onRetry} size="small">重试</Button>
      ) : items.length === 0 ? (
        <span style={{ color: "#999" }}>暂无数据</span>
      ) : (
        <List
          size="small"
          dataSource={items}
          renderItem={(item) => (
            <List.Item>
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>
                {item.supplier_name}
              </span>
              <Tag color={item.ppm > 500 ? "red" : "green"}>{item.ppm} PPM</Tag>
            </List.Item>
          )}
        />
      )}
    </Card>
  );
}

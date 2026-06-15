import { Card, List, Button, Tag } from "antd";
import { ShopOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import type { WidgetProps } from "./types";

export default function SupplierPpmWidget({ data, loading, error, onRetry }: WidgetProps) {
  const { t } = useTranslation("dashboard");
  const items = data.supplier?.ppm_trend ?? [];

  return (
    <Card
      title={<><ShopOutlined /> {t("widget.supplierPpmTrend")}</>}
      size="small"
      loading={loading}
    >
      {error ? (
        <Button onClick={onRetry} size="small">{t("riskList.retry")}</Button>
      ) : items.length === 0 ? (
        <span style={{ color: "#999" }}>{t("alert.empty.supplierPpm")}</span>
      ) : (
        <List
          size="small"
          dataSource={items}
          renderItem={(item) => (
            <List.Item>
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>
                {item.supplier_name}
              </span>
              <Tag color={item.ppm > 500 ? "red" : "green"}>{t("alert.ppmValue", { ppm: item.ppm })}</Tag>
            </List.Item>
          )}
        />
      )}
    </Card>
  );
}

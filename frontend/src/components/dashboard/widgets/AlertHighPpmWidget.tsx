import { Card, List, Button, Tag } from "antd";
import { AlertOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import type { WidgetProps } from "./types";

export default function AlertHighPpmWidget({ data, loading, error, onRetry }: WidgetProps) {
  const { t } = useTranslation("dashboard");
  const items = data.alerts?.high_ppm_suppliers ?? [];

  return (
    <Card
      title={<><AlertOutlined /> {t("widget.highPpmSuppliersTop5")}</>}
      size="small"
      loading={loading}
    >
      {error ? (
        <Button onClick={onRetry} size="small">{t("riskList.retry")}</Button>
      ) : items.length === 0 ? (
        <span style={{ color: "#999" }}>{t("alert.empty.highPpm")}</span>
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

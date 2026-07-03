import { Card, List, Button, Tag } from "antd";
import { ClockCircleOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { useAlertDrilldown } from "../useDashboardDrilldown";
import AlertRow from "./AlertRow";
import type { WidgetProps } from "./types";

export default function AlertOverdueCapaWidget({ data, loading, error, onRetry }: WidgetProps) {
  const { t } = useTranslation("dashboard");
  const items = data.alerts?.overdue_capas ?? [];
  const getRowProps = useAlertDrilldown("alert_overdue_capa");

  return (
    <Card
      title={<><ClockCircleOutlined /> {t("widget.overdueCapaTop5")}</>}
      size="small"
      loading={loading}
    >
      {error ? (
        <Button onClick={onRetry} size="small">{t("riskList.retry")}</Button>
      ) : items.length === 0 ? (
        <span style={{ color: "#999" }}>{t("alert.empty.overdueCapa")}</span>
      ) : (
        <List
          size="small"
          dataSource={items}
          renderItem={(item) => {
            const { onClick, clickable } = getRowProps(item);
            return (
              <AlertRow onClick={onClick} clickable={clickable}>
                <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>
                  {item.document_no}
                </span>
                <Tag color="orange">{t("alert.overdueDays", { days: item.overdue_days })}</Tag>
              </AlertRow>
            );
          }}
        />
      )}
    </Card>
  );
}

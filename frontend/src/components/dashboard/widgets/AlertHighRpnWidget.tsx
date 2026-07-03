import { Card, List, Button, Tag } from "antd";
import { WarningOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { useAlertDrilldown } from "../useDashboardDrilldown";
import AlertRow from "./AlertRow";
import type { WidgetProps } from "./types";

export default function AlertHighRpnWidget({ data, loading, error, onRetry }: WidgetProps) {
  const { t } = useTranslation("dashboard");
  const items = data.alerts?.high_rpn_fmeas ?? [];
  const getRowProps = useAlertDrilldown("alert_high_rpn_fmea");

  return (
    <Card
      title={<><WarningOutlined /> {t("widget.highRpnFmeaTop5")}</>}
      size="small"
      loading={loading}
    >
      {error ? (
        <Button onClick={onRetry} size="small">{t("riskList.retry")}</Button>
      ) : items.length === 0 ? (
        <span style={{ color: "#999" }}>{t("alert.empty.highRpn")}</span>
      ) : (
        <List
          size="small"
          dataSource={items}
          renderItem={(item) => {
            const { onClick, clickable } = getRowProps(item);
            return (
              <AlertRow onClick={onClick} clickable={clickable}>
                <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>
                  {item.document_no} — {item.node_name}
                </span>
                <Tag color="red">RPN {item.rpn}</Tag>
              </AlertRow>
            );
          }}
        />
      )}
    </Card>
  );
}

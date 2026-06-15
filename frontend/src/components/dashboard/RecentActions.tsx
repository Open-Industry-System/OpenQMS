import { useCallback } from "react";
import { List, Skeleton, Typography, Button, theme } from "antd";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { DashboardRecentAction } from "../../types";
import { useRelativeTime } from "../../utils/relativeTime";

const { Text } = Typography;

interface RecentActionsProps {
  data: DashboardRecentAction[];
  loading: boolean;
  error?: boolean;
  onRetry?: () => void;
}

export default function RecentActions({
  data,
  loading,
  error,
  onRetry,
}: RecentActionsProps) {
  const { t } = useTranslation("dashboard");
  const navigate = useNavigate();
  const { token } = theme.useToken();
  const relativeTime = useRelativeTime();

  const getTypeMap = (tableName: string): { label: string; path: string } | undefined => {
    switch (tableName) {
      case "fmea_documents":
        return { label: t("recentActions.types.fmeaDocuments"), path: "/fmea" };
      case "capa_eightd":
        return { label: t("recentActions.types.capaEightd"), path: "/capa" };
      default:
        return undefined;
    }
  };

  const handleNavigate = useCallback(
    (path: string) => {
      navigate(path);
    },
    [navigate]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent, path: string) => {
      if (e.key === "Enter") {
        e.preventDefault();
        handleNavigate(path);
      }
    },
    [handleNavigate]
  );

  if (loading) {
    return (
      <div style={{ padding: "12px 0" }}>
        {[0, 1, 2, 3, 4].map((i) => (
          <Skeleton key={i} active paragraph={{ rows: 1 }} title={false} />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: "12px 0", textAlign: "center" }}>
        <Text type="secondary">{t("riskList.loadFailed")}</Text>
        <div style={{ marginTop: 8 }}>
          <Button size="small" onClick={onRetry}>
            {t("riskList.retry")}
          </Button>
        </div>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div style={{ padding: "12px 0", textAlign: "center" }}>
        <Text type="secondary">{t("recentActions.empty")}</Text>
      </div>
    );
  }

  return (
    <List
      dataSource={data}
      renderItem={(item) => {
        const mapped = getTypeMap(item.table_name);
        const label = mapped?.label ?? item.table_name;
        const path = mapped?.path ?? "";
        const navigateTo = path ? `${path}/${item.record_id}` : "";

        return (
          <List.Item
            role="listitem"
            tabIndex={0}
            onClick={() => navigateTo && handleNavigate(navigateTo)}
            onKeyDown={(e) => navigateTo && handleKeyDown(e, navigateTo)}
            style={{
              padding: "12px 0",
              cursor: navigateTo ? "pointer" : "default",
            }}
          >
            <div style={{ width: "100%" }}>
              <div style={{ marginBottom: 4 }}>
                <Text style={{ fontSize: 14, fontWeight: 500 }}>
                  {label} - {item.entity_no}
                </Text>
              </div>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <Text
                  type="secondary"
                  style={{ fontSize: 12 }}
                >
                  {item.action}
                </Text>
                <Text
                  type="secondary"
                  style={{ fontSize: 12, color: token.colorTextSecondary }}
                >
                  {relativeTime(item.operated_at)}
                </Text>
              </div>
            </div>
          </List.Item>
        );
      }}
    />
  );
}

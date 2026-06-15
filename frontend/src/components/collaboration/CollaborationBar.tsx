import { Avatar, Badge, Tooltip } from "antd";
import { useTranslation } from "react-i18next";
import type { ActiveUser } from "../../types/collaboration";

interface CollaborationBarProps {
  activeUsers: ActiveUser[];
  isSyncing: boolean;
}

export default function CollaborationBar({ activeUsers, isSyncing }: CollaborationBarProps) {
  const { t } = useTranslation("collaboration");
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 16px", borderBottom: "1px solid #f0f0f0" }}>
      <Avatar.Group max={{ count: 5 }}>
        {activeUsers.map((u) => (
          <Tooltip
            key={u.user_id}
            title={`${u.user_name} (${u.action === "editing" ? t("bar.editing") : t("bar.viewing")})`}
          >
            <Avatar
              style={{
                backgroundColor: u.action === "editing" ? "#52c41a" : "#bfbfbf",
                border: u.action === "editing" ? "2px solid #237804" : undefined,
              }}
            >
              {u.user_name?.[0] || "?"}
            </Avatar>
          </Tooltip>
        ))}
      </Avatar.Group>
      <span style={{ fontSize: 13, color: "#595959" }}>
        {activeUsers.length === 0
          ? t("bar.onlyYou")
          : t("bar.onlineCount", { count: activeUsers.length })}
      </span>
      {!isSyncing && (
        <Badge
          status="warning"
          text={<span style={{ fontSize: 12 }}>{t("bar.syncFailed")}</span>}
        />
      )}
    </div>
  );
}

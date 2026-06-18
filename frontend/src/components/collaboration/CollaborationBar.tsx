import { Avatar, Badge, Tooltip } from "antd";
import { useTranslation } from "react-i18next";
import type { ActiveUser } from "../../types/collaboration";

interface CollaborationBarProps {
  activeUsers: ActiveUser[];
  isSyncing: boolean;
  compact?: boolean;
}

export default function CollaborationBar({ activeUsers, isSyncing, compact }: CollaborationBarProps) {
  const { t } = useTranslation("collaboration");
  if (compact) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--qf-text-tertiary)" }}>
        <Avatar.Group max={{ count: 3 }} size="small">
          {activeUsers.map((u) => (
            <Tooltip
              key={u.user_id}
              title={`${u.user_name} (${u.action === "editing" ? t("bar.editing") : t("bar.viewing")})`}
            >
              <Avatar
                size="small"
                style={{
                  backgroundColor: u.action === "editing" ? "var(--qf-green)" : "var(--qf-text-tertiary)",
                  border: u.action === "editing" ? "2px solid rgba(0, 214, 143, 0.5)" : undefined,
                }}
              >
                {u.user_name?.[0] || "?"}
              </Avatar>
            </Tooltip>
          ))}
        </Avatar.Group>
        <span>
          {activeUsers.length === 0
            ? t("bar.onlyYou")
            : t("bar.onlineCount", { count: activeUsers.length })}
        </span>
        {!isSyncing && (
          <Badge status="warning" text={<span style={{ fontSize: 12 }}>{t("bar.syncFailed")}</span>} />
        )}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 16px", borderBottom: "1px solid var(--qf-border)" }}>
      <Avatar.Group max={{ count: 5 }}>
        {activeUsers.map((u) => (
          <Tooltip
            key={u.user_id}
            title={`${u.user_name} (${u.action === "editing" ? t("bar.editing") : t("bar.viewing")})`}
          >
            <Avatar
              style={{
                backgroundColor: u.action === "editing" ? "var(--qf-green)" : "var(--qf-text-tertiary)",
                border: u.action === "editing" ? "2px solid rgba(0, 214, 143, 0.5)" : undefined,
              }}
            >
              {u.user_name?.[0] || "?"}
            </Avatar>
          </Tooltip>
        ))}
      </Avatar.Group>
      <span style={{ fontSize: 13, color: "var(--qf-text-secondary)" }}>
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

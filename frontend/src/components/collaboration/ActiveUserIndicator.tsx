import { Badge } from "antd";
import { useTranslation } from "react-i18next";
import type { ActiveUser, EditingArea } from "../../types/collaboration";

interface ActiveUserIndicatorProps {
  activeUsers: ActiveUser[];
  rowKey?: string;
  field?: string;
  nodeId?: string;
}

export default function ActiveUserIndicator({
  activeUsers,
  rowKey,
  field,
  nodeId,
}: ActiveUserIndicatorProps) {
  const { t } = useTranslation("collaboration");
  const editors = activeUsers.filter((u) => {
    if (u.action !== "editing" || !u.editing_area) return false;
    const area = u.editing_area as EditingArea;
    // Support both row_key (FMEA) and rowId mapped to row_key (Control Plan)
    const areaRowKey = area.row_key || (area as Record<string, string>).rowId;
    if (rowKey && areaRowKey === rowKey) {
      return !field || area.field === field;
    }
    if (nodeId && area.node_id === nodeId) {
      return !field || area.field === field;
    }
    return false;
  });

  if (editors.length === 0) return null;

  return (
    <span style={{ fontSize: 11, color: "#52c41a", marginLeft: 4, whiteSpace: "nowrap" }}>
      <Badge color="green" style={{ marginRight: 4 }} />
      {t("activeUser.editing", { users: editors.map((e) => e.user_name).join(", ") })}
    </span>
  );
}

interface StatusBadgeProps {
  status: string;
  children?: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * 工业风 LED 状态徽章。
 * 映射常见业务状态到视觉语义：草稿、进行中、成功/批准、警告/返工、错误/高风险、信息/普通。
 */
export default function StatusBadge({ status, children, className, style }: StatusBadgeProps) {
  const normalized = (status || "").toLowerCase();

  let variant = "draft";
  switch (normalized) {
    case "approved":
    case "closed":
    case "resolved":
    case "done":
    case "completed":
    case "ok":
    case "pass":
      variant = "success";
      break;
    case "in_review":
    case "rework":
    case "pending":
    case "processing":
    case "open":
      variant = "warning";
      break;
    case "high":
    case "fatal":
    case "critical":
    case "error":
    case "failed":
    case "reject":
    case "overdue":
      variant = "error";
      break;
    case "medium":
    case "normal":
    case "info":
      variant = "info";
      break;
  }

  return (
    <span className={`qf-status qf-status--${variant} ${className || ""}`} style={style}>
      {children || status}
    </span>
  );
}

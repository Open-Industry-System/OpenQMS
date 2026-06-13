import type { ReactNode } from "react";

interface DataCardProps {
  title: ReactNode;
  extra?: ReactNode;
  children: ReactNode;
  className?: string;
  noPadding?: boolean;
  elevated?: boolean;
}

/**
 * 统一的数据卡片容器。
 * 带左侧青边装饰条标题，可选悬浮层样式。
 */
export default function DataCard({
  title,
  extra,
  children,
  className,
  noPadding,
  elevated,
}: DataCardProps) {
  return (
    <div className={`qf-card ${elevated ? "qf-card-elevated" : ""} ${className || ""}`}>
      <div className="qf-card__header">
        <h3 className="qf-card__title">{title}</h3>
        {extra ? <div>{extra}</div> : null}
      </div>
      <div className={`qf-card__body ${noPadding ? "qf-card__body--flush" : ""}`}>
        {children}
      </div>
    </div>
  );
}

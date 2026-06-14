import type { ReactNode } from "react";

interface PageShellProps {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  fullHeight?: boolean;
}

/**
 * 统一页面外壳：标题区 + 操作区 + 可滚动内容区。
 * 所有新设计页面应优先使用此组件以获得一致的页头间距与分隔线。
 */
export default function PageShell({
  title,
  subtitle,
  actions,
  children,
  className,
  fullHeight,
}: PageShellProps) {
  return (
    <div className={`qf-page ${className || ""}`} style={fullHeight ? { height: "100%" } : undefined}>
      <div className="qf-page__header">
        <div>
          <h1 className="qf-page__title">{title}</h1>
          {subtitle ? <div className="qf-page__subtitle">{subtitle}</div> : null}
        </div>
        {actions ? <div style={{ display: "flex", gap: 8, alignItems: "center" }}>{actions}</div> : null}
      </div>
      <div className="qf-page__body">{children}</div>
    </div>
  );
}

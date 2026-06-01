import { useState, useEffect, useCallback, type ReactNode } from "react";
import { DownOutlined, UpOutlined } from "@ant-design/icons";

interface CollapsibleSectionProps {
  title: string;
  defaultCollapsed?: boolean;
  children: ReactNode;
  hidden?: boolean;
  collapseAt?: number;
  style?: React.CSSProperties;
}

export default function CollapsibleSection({
  title,
  defaultCollapsed = false,
  children,
  hidden,
  collapseAt = 0,
  style,
}: CollapsibleSectionProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  useEffect(() => {
    if (collapseAt <= 0) return;

    const mql = window.matchMedia(`(max-width: ${collapseAt}px)`);
    setCollapsed(mql.matches);

    const handler = (e: MediaQueryListEvent) => {
      setCollapsed(e.matches);
    };

    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, [collapseAt]);

  const toggle = useCallback(() => {
    setCollapsed((prev) => !prev);
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter") {
        e.preventDefault();
        toggle();
      }
    },
    [toggle]
  );

  if (hidden) {
    return null;
  }

  return (
    <div style={style}>
      <div
        role="button"
        aria-expanded={!collapsed}
        tabIndex={0}
        onClick={toggle}
        onKeyDown={handleKeyDown}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "12px 0",
          cursor: "pointer",
          userSelect: "none",
        }}
      >
        <span style={{ fontSize: 16, fontWeight: 500 }}>{title}</span>
        {collapsed ? <DownOutlined /> : <UpOutlined />}
      </div>
      {!collapsed && <div>{children}</div>}
    </div>
  );
}

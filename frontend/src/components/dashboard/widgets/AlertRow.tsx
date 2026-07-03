import { useState, type ReactNode } from "react";
import { List, theme } from "antd";

interface AlertRowProps {
  onClick?: () => void;
  clickable: boolean;
  children: ReactNode;
}

/**
 * 预警列表行：有下钻目标时可点击（hover 高亮、键盘可达）；
 * 无权限/无目标时灰显且不响应。
 */
export default function AlertRow({ onClick, clickable, children }: AlertRowProps) {
  const { token } = theme.useToken();
  const [hover, setHover] = useState(false);
  return (
    <List.Item
      role={clickable ? "button" : undefined}
      onClick={clickable ? onClick : undefined}
      tabIndex={clickable ? 0 : -1}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onKeyDown={
        clickable
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick?.();
              }
            }
          : undefined
      }
      style={{
        cursor: clickable ? "pointer" : "default",
        opacity: clickable ? 1 : 0.5,
        background: hover && clickable ? token.colorFillQuaternary : undefined,
        transition: "background 0.15s ease",
      }}
    >
      {children}
    </List.Item>
  );
}

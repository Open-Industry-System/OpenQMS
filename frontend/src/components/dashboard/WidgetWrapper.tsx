import { Button, theme } from "antd";

import { CloseOutlined, ReloadOutlined } from "@ant-design/icons";
import type { WidgetLayoutItem, DashboardWidgetsData } from "./widgets/types";
import { getWidgetMeta, getWidgetComponent } from "./widgets/registry";

interface WidgetWrapperProps {
  item: WidgetLayoutItem;
  data: DashboardWidgetsData;
  loading: boolean;
  isEditing: boolean;
  onRemove: (i: string) => void;
  onRetry: () => void;
}

export default function WidgetWrapper({
  item,
  data,
  loading,
  isEditing,
  onRemove,
  onRetry,
}: WidgetWrapperProps) {
  const { token } = theme.useToken();
  const meta = getWidgetMeta(item.type);
  const Component = getWidgetComponent(item.type);


  if (!Component || !meta) {
    return (
      <div style={{ padding: 16, color: token.colorTextSecondary }}>
        未知组件: {item.type}
      </div>
    );
  }

  const hasModuleError = !!data.errors?.[meta.module];

  return (
    <div
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        position: "relative",
      }}
    >
      {/* Edit-mode delete overlay */}
      {isEditing && (
        <div
          style={{
            position: "absolute",
            top: 4,
            right: 4,
            zIndex: 10,
          }}
        >
          <Button
            type="text"
            size="small"
            danger
            icon={<CloseOutlined />}
            onClick={() => onRemove(item.i)}
          />
        </div>
      )}
      {/* Module error retry overlay (only when not editing) */}
      {hasModuleError && !isEditing && (
        <div
          style={{
            position: "absolute",
            top: 4,
            right: 4,
            zIndex: 10,
          }}
        >
          <ReloadOutlined
            style={{ color: token.colorError, cursor: "pointer" }}
            onClick={onRetry}
          />
        </div>
      )}
      {/* Frameless widget component — widgets own their Card/KPICard title */}
      <div style={{ flex: 1, overflow: "auto", height: "100%" }}>
        <Component
          data={data}
          loading={loading}
          error={hasModuleError}
          onRetry={onRetry}
        />
      </div>
    </div>
  );
}

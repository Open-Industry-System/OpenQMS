import { useCallback, useMemo, useState } from "react";
import { List, Tag, Typography, Button, Skeleton, theme } from "antd";
import { useNavigate } from "react-router-dom";
import type { DashboardAlerts } from "../../types";

const { Text } = Typography;

interface RiskListProps {
  data: DashboardAlerts | null;
  category: "fmea" | "capa" | "supplier";
  loading: boolean;
  error?: boolean;
  onRetry?: () => void;
  disabled?: boolean; // viewer role
}

interface RiskItem {
  id: string;
  title: string;
  description: string;
  tagText: string;
  tagColor: string;
  navigateTo: string;
  verb: string;
}

export default function RiskList({
  data,
  category,
  loading,
  error,
  onRetry,
  disabled,
}: RiskListProps) {
  const navigate = useNavigate();
  const { token } = theme.useToken();
  const [focusedId, setFocusedId] = useState<string | null>(null);

  const items = useMemo<RiskItem[]>(() => {
    if (!data) return [];
    switch (category) {
      case "fmea":
        return data.high_rpn_fmeas.map((item) => ({
          id: item.fmea_id,
          title: item.document_no,
          description: item.node_name,
          tagText: `RPN=${item.rpn}`,
          tagColor: item.rpn >= 200 ? "error" : "warning",
          navigateTo: `/fmea/${item.fmea_id}`,
          verb: "前往审批",
        }));
      case "capa":
        return data.overdue_capas.map((item) => ({
          id: item.report_id,
          title: item.document_no,
          description: `超期 ${item.overdue_days} 天`,
          tagText: `${item.overdue_days}天`,
          tagColor: "error",
          navigateTo: `/capa/${item.report_id}`,
          verb: "前往跟进",
        }));
      case "supplier":
        return data.high_ppm_suppliers.map((item) => ({
          id: item.supplier_id,
          title: item.supplier_name,
          description: "供应商 PPM 超标",
          tagText: `PPM=${item.ppm}`,
          tagColor: item.ppm > 500 ? "error" : "warning",
          navigateTo: `/suppliers/${item.supplier_id}`,
          verb: "前往查看",
        }));
      default:
        return [];
    }
  }, [data, category]);

  const handleNavigate = useCallback(
    (path: string) => {
      if (disabled) return;
      navigate(path);
    },
    [disabled, navigate]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent, path: string) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        handleNavigate(path);
      }
    },
    [handleNavigate]
  );

  if (loading) {
    return (
      <div style={{ padding: "12px 0" }}>
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} active paragraph={{ rows: 1 }} title={false} />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: "12px 0", textAlign: "center" }}>
        <Text type="secondary">加载失败</Text>
        <div style={{ marginTop: 8 }}>
          <Button size="small" onClick={onRetry}>
            重试
          </Button>
        </div>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div style={{ padding: "12px 0", textAlign: "center" }}>
        <Text type="secondary">
          暂无待处置事项，当前无超期或高风险项
        </Text>
      </div>
    );
  }

  return (
    <List
      dataSource={items}
      renderItem={(item) => {
        const isFocused = focusedId === item.id;
        return (
          <List.Item
            role="listitem"
            aria-label={`${item.title} ${item.description}`}
            tabIndex={disabled ? -1 : 0}
            onClick={() => handleNavigate(item.navigateTo)}
            onKeyDown={(e) => handleKeyDown(e, item.navigateTo)}
            onFocus={() => setFocusedId(item.id)}
            onBlur={() => setFocusedId((prev) => (prev === item.id ? null : prev))}
            style={{
              padding: "12px 0",
              cursor: disabled ? "default" : "pointer",
              outline: isFocused ? `2px solid ${token.colorPrimary}` : "none",
              outlineOffset: 2,
              borderRadius: 4,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                width: "100%",
                gap: 12,
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ marginBottom: 4 }}>
                  <Text
                    style={{
                      fontFamily: "monospace",
                      fontSize: 14,
                      fontWeight: 500,
                    }}
                  >
                    {item.title}
                  </Text>
                </div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {item.description}
                </Text>
              </div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  flexShrink: 0,
                }}
              >
                <Tag color={item.tagColor} style={{ borderRadius: 999 }}>
                  {item.tagText}
                </Tag>
                {!disabled && (
                  <Text
                    style={{
                      fontSize: 12,
                      color: token.colorPrimary,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {item.verb} →
                  </Text>
                )}
              </div>
            </div>
          </List.Item>
        );
      }}
    />
  );
}

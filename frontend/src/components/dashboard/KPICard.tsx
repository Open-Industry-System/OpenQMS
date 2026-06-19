import { Card, Statistic, Skeleton, Typography, theme } from "antd";
import type { GlobalToken } from "antd/es/theme/interface";
import type { ReactNode } from "react";
import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

export type KPIStatus = "success" | "warning" | "danger";

interface KPICardProps {
  title: string;
  value: number | null;
  status: KPIStatus;
  subtitle?: string;
  icon: ReactNode;
  onClick?: () => void;
  loading?: boolean;
  error?: boolean;
  onRetry?: () => void;
  disabled?: boolean;
}

const statusColorKey: Record<KPIStatus, keyof GlobalToken> = {
  success: "colorSuccess",
  warning: "colorWarning",
  danger: "colorError",
};

function getStatusColor(status: KPIStatus, token: GlobalToken): string {
  return token[statusColorKey[status]] as string;
}

export default function KPICard({
  title,
  value,
  status,
  subtitle,
  icon,
  onClick,
  loading = false,
  error = false,
  onRetry,
  disabled = false,
}: KPICardProps) {
  const { t } = useTranslation("dashboard");
  const { token } = theme.useToken();
  const [focused, setFocused] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  const clickable = !loading && !disabled && !error && !!onClick;
  const retryable = error && !!onRetry;

  const statusLabel =
    status === "success" ? t("kpi.normal") : status === "warning" ? t("kpi.warning") : t("kpi.danger");

  const handleClick = useCallback(() => {
    if (clickable && onClick) {
      onClick();
    }
    if (retryable && onRetry) {
      onRetry();
    }
  }, [clickable, onClick, retryable, onRetry]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if ((e.key === "Enter" || e.key === " ") && (clickable || retryable)) {
        e.preventDefault();
        handleClick();
      }
    },
    [clickable, retryable, handleClick]
  );

  const borderColor = loading
    ? token.colorBorderSecondary
    : error
      ? token.colorError
      : getStatusColor(status, token);

  const focusOutlineColor = token.colorPrimary;

  const ariaLabel = loading
    ? `${title}，${t("kpi.loading")}`
    : error
      ? `${title}，${t("kpi.loadFailed")}`
      : `${title}，${t("kpi.currentValue", { value: value ?? 0 })}，${statusLabel}${subtitle ? `，${subtitle}` : ""}`;

  return (
    <div
      ref={cardRef}
      role="button"
      aria-label={ariaLabel}
      tabIndex={clickable || retryable ? 0 : -1}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      style={{
        height: "100%",
        cursor: clickable || retryable ? "pointer" : "default",
        outline: focused ? `2px solid ${focusOutlineColor}` : "none",
        outlineOffset: focused ? "2px" : "0px",
        borderRadius: token.borderRadiusLG,
      }}
    >
      <Card
        styles={{ body: { padding: "12px" } }}
        style={{
          borderTop: `3px solid ${borderColor}`,
          borderRadius: token.borderRadiusLG,
          transition: "box-shadow 0.2s ease",
          boxShadow: focused
            ? `0 0 0 2px ${focusOutlineColor}`
            : "none",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            {loading ? (
              <>
                <Skeleton.Input active size="small" style={{ width: 80, marginBottom: 4 }} />
                <Skeleton.Input active size="large" style={{ width: 50, marginBottom: 2 }} />
                <Skeleton.Input active size="small" style={{ width: 100 }} />
              </>
            ) : (
              <>
                <Typography.Text
                  style={{
                    fontSize: 12,
                    color: token.colorTextSecondary,
                    display: "block",
                    marginBottom: 2,
                  }}
                >
                  {title}
                </Typography.Text>

                <Statistic
                  value={error ? "—" : value ?? 0}
                  valueStyle={{
                    fontSize: 22,
                    fontWeight: 600,
                    color: error
                      ? token.colorTextDisabled
                      : token.colorText,
                    fontFamily:
                      "'SF Mono', 'Cascadia Code', 'Consolas', monospace",
                    lineHeight: 1.2,
                  }}
                  formatter={(val) => (
                    <span>{val}</span>
                  )}
                />

                <Typography.Text
                  style={{
                    fontSize: 10,
                    color: token.colorTextTertiary,
                    display: "block",
                    marginTop: 2,
                  }}
                >
                  {error ? (
                    <span
                      role="button"
                      tabIndex={retryable ? 0 : -1}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (retryable && onRetry) onRetry();
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.stopPropagation();
                          e.preventDefault();
                          if (retryable && onRetry) onRetry();
                        }
                      }}
                      style={{
                        color: token.colorPrimary,
                        cursor: retryable ? "pointer" : "default",
                        textDecoration: "underline",
                      }}
                    >
                      {t("kpi.loadFailed")}
                    </span>
                  ) : (
                    subtitle ?? t("kpi.noData")
                  )}
                </Typography.Text>
              </>
            )}
          </div>

          <div
            style={{
              marginLeft: 12,
              color: loading || error
                ? token.colorTextDisabled
                : getStatusColor(status, token) ?? token.colorTextSecondary,
              fontSize: 20,
              lineHeight: 1,
              flexShrink: 0,
            }}
          >
            {icon}
          </div>
        </div>
      </Card>
    </div>
  );
}

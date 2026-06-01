# Dark Industrial Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the default Ant Design light theme with a dark industrial theme optimized for quality managers to identify risks within 30 seconds.

**Architecture:** Configure Ant Design's `darkAlgorithm` via `ConfigProvider` in `main.tsx`, then refactor `DashboardPage` to use token-based colors, proper state matrices, and accessible markup. `AppLayout` gets minimal token-driven style adjustments. No new dependencies.

**Tech Stack:** React 18, Ant Design 5.x, TypeScript 5.6, `theme.useToken()`

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `frontend/src/main.tsx` | ConfigProvider dark theme token config |
| Create | `frontend/src/utils/darkTheme.ts` | Theme token constants (single source) |
| Modify | `frontend/src/components/layout/AppLayout.tsx` | Layout styles via useToken |
| Modify | `frontend/src/pages/dashboard/DashboardPage.tsx` | Full dashboard rewrite: KPI, risk list, recent actions, quick entry |
| Create | `frontend/src/components/dashboard/KPICard.tsx` | KPI card with state matrix |
| Create | `frontend/src/components/dashboard/RiskList.tsx` | "待处置事项" list with state matrix |
| Create | `frontend/src/components/dashboard/RecentActions.tsx` | Recent actions timeline |
| Create | `frontend/src/components/dashboard/CollapsibleSection.tsx` | Mobile collapsible wrapper |

---

### Task 1: Theme Token Foundation

**Files:**
- Create: `frontend/src/utils/darkTheme.ts`
- Modify: `frontend/src/main.tsx:10`

- [ ] **Step 1: Create theme token constants**

```typescript
// frontend/src/utils/darkTheme.ts
import { theme } from "antd";
import type { ThemeConfig } from "antd";

const prefersReduced =
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export const darkTheme: ThemeConfig = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: "#3b82f6",
    colorSuccess: "#10b981",
    colorWarning: "#f59e0b",
    colorError: "#ef4444",
    colorInfo: "#06b6d4",

    colorBgLayout: "#0a0e1a",
    colorBgContainer: "#111827",
    colorBgElevated: "#1f2937",

    colorText: "#f0f9ff",
    colorTextSecondary: "#94a3b8",
    colorTextTertiary: "#8696a8",

    colorBorder: "rgba(148, 163, 184, 0.2)",
    colorBorderSecondary: "rgba(148, 163, 184, 0.1)",

    borderRadius: 8,
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif",
    fontSize: 14,

    motionDurationMid: prefersReduced ? "0s" : "0.2s",
    motionDurationSlow: prefersReduced ? "0s" : "0.3s",
  },
  components: {
    Layout: {
      headerBg: "#111827",
      bodyBg: "#0a0e1a",
      siderBg: "#111827",
    },
    Card: {
      colorBgContainer: "#111827",
    },
    Menu: {
      colorBgContainer: "transparent",
      colorItemBgHover: "#374151",
      colorItemBgSelected: "#1f2937",
    },
    Table: {
      colorBgContainer: "#111827",
      headerBg: "#1f2937",
    },
  },
};
```

- [ ] **Step 2: Apply theme in main.tsx**

Replace `frontend/src/main.tsx` line 10:

```tsx
// Before:
<ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: "#1677FF" } }}>

// After:
import { darkTheme } from "./utils/darkTheme";
// ...
<ConfigProvider locale={zhCN} theme={darkTheme}>
```

- [ ] **Step 3: Verify theme loads**

Run: `cd frontend && npm run dev`
Open `http://localhost:5173` — background should be dark (#0a0e1a), cards dark (#111827), text white (#f0f9ff).

- [ ] **Step 4: Register ECharts dark theme**

Check if ECharts is used in the project. If so, create `frontend/src/utils/echartsTheme.ts`:

```typescript
// frontend/src/utils/echartsTheme.ts
import * as echarts from "echarts";

export function registerEChartsDarkTheme() {
  echarts.registerTheme("openqms-dark", {
    backgroundColor: "transparent",
    textStyle: { color: "#94a3b8", fontSize: 12 },
    title: { textStyle: { color: "#f0f9ff" } },
    legend: { textStyle: { color: "#94a3b8" } },
    tooltip: {
      backgroundColor: "#1f2937",
      borderColor: "rgba(148,163,184,0.2)",
      textStyle: { color: "#f0f9ff" },
    },
    xAxis: {
      axisLine: { lineStyle: { color: "rgba(148,163,184,0.2)" } },
      splitLine: { lineStyle: { color: "rgba(148,163,184,0.1)" } },
      axisLabel: { color: "#94a3b8" },
    },
    yAxis: {
      axisLine: { lineStyle: { color: "rgba(148,163,184,0.2)" } },
      splitLine: { lineStyle: { color: "rgba(148,163,184,0.1)" } },
      axisLabel: { color: "#94a3b8" },
    },
    color: ["#3b82f6", "#06b6d4", "#10b981", "#f59e0b", "#ef4444"],
  });
}
```

Call `registerEChartsDarkTheme()` once in `main.tsx` after the import:

```tsx
import { registerEChartsDarkTheme } from "./utils/echartsTheme";
registerEChartsDarkTheme();
```

Then in any chart component, use `echarts.init(dom, "openqms-dark")` instead of `echarts.init(dom)`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/darkTheme.ts frontend/src/utils/echartsTheme.ts frontend/src/main.tsx
git commit -m "feat: add dark industrial theme token foundation and ECharts theme"
```

---

### Task 2: AppLayout Dark Theme

**Files:**
- Modify: `frontend/src/components/layout/AppLayout.tsx`

- [ ] **Step 1: Import useToken and remove hardcoded colors**

In `AppLayout.tsx`, the component already uses `theme.useToken()`. No import changes needed. Remove the inline `style={{ background: themeToken.colorBgContainer }}` from the `Sider` — the ConfigProvider token now handles this automatically via `components.Layout.siderBg`.

- [ ] **Step 2: Remove Sider background override**

```tsx
// Before (line 173):
<Sider
  trigger={null}
  collapsible
  collapsed={collapsed}
  style={{ background: themeToken.colorBgContainer }}
>

// After:
<Sider
  trigger={null}
  collapsible
  collapsed={collapsed}
>
```

- [ ] **Step 3: Remove Header background override**

```tsx
// Before (line 205-210):
<Header
  style={{
    padding: "0 24px",
    background: themeToken.colorBgContainer,
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    borderBottom: `1px solid ${themeToken.colorBorderSecondary}`,
  }}
>

// After:
<Header
  style={{
    padding: "0 24px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  }}
>
```

- [ ] **Step 4: Verify layout renders correctly**

Run: `cd frontend && npm run dev`
Check: sidebar dark, header dark, content area dark, menu items highlight correctly.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/AppLayout.tsx
git commit -m "refactor: remove hardcoded colors from AppLayout, rely on ConfigProvider tokens"
```

---

### Task 3: KPI Card Component

**Files:**
- Create: `frontend/src/components/dashboard/KPICard.tsx`

- [ ] **Step 1: Create KPI Card with full state matrix**

```tsx
// frontend/src/components/dashboard/KPICard.tsx
import { Card, Statistic, Skeleton, Typography, theme } from "antd";
import type { ReactNode } from "react";

export type KPIStatus = "success" | "warning" | "danger";

interface KPICardProps {
  title: string;
  value: number | null;          // null = loading or error
  status: KPIStatus;
  subtitle?: string;             // "较昨日 +3" or "暂无"
  icon: ReactNode;
  onClick?: () => void;
  loading?: boolean;
  error?: boolean;
  onRetry?: () => void;
  disabled?: boolean;            // viewer role
}

const statusBorderColor: Record<KPIStatus, string> = {
  success: "#10b981",
  warning: "#f59e0b",
  danger: "#ef4444",
};

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
  const { token } = theme.useToken();

  if (loading) {
    return (
      <Card style={{ borderTop: `3px solid ${token.colorBorder}` }}>
        <Skeleton active paragraph={false} />
        <Skeleton.Input active size="small" style={{ width: 60, marginTop: 8 }} />
      </Card>
    );
  }

  if (error) {
    return (
      <Card style={{ borderTop: `3px solid ${token.colorBorder}` }}>
        <Typography.Text type="secondary">{title}</Typography.Text>
        <div style={{ fontSize: 32, fontWeight: 600, marginTop: 8, color: token.colorTextDisabled }}>
          —
        </div>
        <Typography.Link onClick={onRetry} style={{ fontSize: 12 }}>
          加载失败，点击重试
        </Typography.Link>
      </Card>
    );
  }

  const borderColor = value === 0 ? token.colorSuccess : statusBorderColor[status];
  const clickable = !disabled && onClick;

  return (
    <Card
      hoverable={!!clickable}
      onClick={clickable ? onClick : undefined}
      style={{
        borderTop: `3px solid ${borderColor}`,
        cursor: clickable ? "pointer" : "default",
      }}
      tabIndex={clickable ? 0 : -1}
      onKeyDown={clickable ? (e) => e.key === "Enter" && onClick() : undefined}
      role={clickable ? "link" : undefined}
      aria-label={`${title}：${value ?? "—"}${subtitle ? `，${subtitle}` : ""}`}
    >
      <Typography.Text type="secondary" style={{ fontSize: 14 }}>
        {title}
      </Typography.Text>
      <div
        style={{
          fontSize: 32,
          fontWeight: 600,
          marginTop: 8,
          color: token.colorText,
          fontFamily: "'SF Mono', 'Cascadia Code', 'Consolas', monospace",
        }}
      >
        {value ?? "—"}
      </div>
      {subtitle && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {subtitle}
        </Typography.Text>
      )}
    </Card>
  );
}
```

- [ ] **Step 2: Verify component compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/dashboard/KPICard.tsx
git commit -m "feat: add KPICard component with full state matrix"
```

---

### Task 4: Risk List Component

**Files:**
- Create: `frontend/src/components/dashboard/RiskList.tsx`

- [ ] **Step 1: Create RiskList with state matrix**

```tsx
// frontend/src/components/dashboard/RiskList.tsx
import { List, Tag, Typography, Button, Skeleton, theme } from "antd";
import { useNavigate } from "react-router-dom";
import type { DashboardAlerts } from "../../types";

interface RiskListProps {
  data: DashboardAlerts | null;
  loading: boolean;
  error?: boolean;
  onRetry?: () => void;
  disabled?: boolean; // viewer
}

export default function RiskList({
  data,
  loading,
  error = false,
  onRetry,
  disabled = false,
}: RiskListProps) {
  const { token } = theme.useToken();
  const navigate = useNavigate();

  if (loading) {
    return (
      <div>
        {[1, 2, 3].map((i) => (
          <div key={i} style={{ padding: "12px 0", borderBottom: `1px solid ${token.colorBorderSecondary}` }}>
            <Skeleton active paragraph={{ rows: 1 }} title={{ width: "40%" }} />
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ textAlign: "center", padding: 24 }}>
        <Typography.Text type="secondary">加载失败</Typography.Text>
        <br />
        <Button type="default" onClick={onRetry} style={{ marginTop: 8 }}>
          重试
        </Button>
      </div>
    );
  }

  const items = [
    ...(data?.high_rpn_fmeas ?? []).map((item) => ({
      key: `fmea-${item.fmea_id}`,
      title: item.document_no,
      description: item.node_name,
      tag: `RPN=${item.rpn}`,
      tagColor: item.rpn >= 200 ? "error" : "warning" as const,
      action: "前往审批",
      onClick: () => navigate(`/fmea/${item.fmea_id}`),
    })),
    ...(data?.overdue_capas ?? []).map((item) => ({
      key: `capa-${item.report_id}`,
      title: item.document_no,
      description: `超期 ${item.overdue_days} 天`,
      tag: `${item.overdue_days}天`,
      tagColor: "error" as const,
      action: "前往跟进",
      onClick: () => navigate(`/capa/${item.report_id}`),
    })),
    ...(data?.high_ppm_suppliers ?? []).map((item) => ({
      key: `supplier-${item.supplier_id}`,
      title: item.supplier_name,
      description: `PPM: ${item.ppm}`,
      tag: `PPM=${item.ppm}`,
      tagColor: item.ppm > 500 ? "error" : "warning" as const,
      action: "前往查看",
      onClick: () => navigate(`/suppliers/${item.supplier_id}`),
    })),
  ];

  if (items.length === 0) {
    return (
      <div style={{ textAlign: "center", padding: 24 }}>
        <Typography.Text type="secondary">
          暂无待处置事项，当前无超期或高风险项
        </Typography.Text>
      </div>
    );
  }

  return (
    <List
      dataSource={items}
      renderItem={(item) => (
        <List.Item
          style={{ cursor: disabled ? "default" : "pointer", padding: "12px 0" }}
          onClick={disabled ? undefined : item.onClick}
          tabIndex={disabled ? -1 : 0}
          onKeyDown={(e) => !disabled && e.key === "Enter" && item.onClick()}
          role="listitem"
          aria-label={`${item.title}，${item.description}`}
        >
          <List.Item.Meta
            title={
              <span style={{ fontFamily: "'SF Mono', 'Cascadia Code', 'Consolas', monospace" }}>
                {item.title}
              </span>
            }
            description={item.description}
          />
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Tag color={item.tagColor}>{item.tag}</Tag>
            {!disabled && (
              <Typography.Link style={{ fontSize: 12 }}>{item.action} →</Typography.Link>
            )}
          </div>
        </List.Item>
      )}
    />
  );
}
```

- [ ] **Step 2: Verify component compiles**

Run: `cd frontend && npx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/dashboard/RiskList.tsx
git commit -m "feat: add RiskList component with action verbs and state matrix"
```

---

### Task 5: Recent Actions & Collapsible Section

**Files:**
- Create: `frontend/src/components/dashboard/RecentActions.tsx`
- Create: `frontend/src/components/dashboard/CollapsibleSection.tsx`

- [ ] **Step 1: Create relative time utility**

```tsx
// frontend/src/utils/relativeTime.ts
export function relativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60000);
  const diffHour = Math.floor(diffMs / 3600000);
  const diffDay = Math.floor(diffMs / 86400000);

  if (diffMin < 5) return "刚刚";
  if (diffMin < 60) return `${diffMin}分钟前`;
  if (diffHour < 24) return `${diffHour}小时前`;
  if (diffDay < 2) return "昨天";
  const d = new Date(dateStr);
  return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}
```

- [ ] **Step 2: Create RecentActions component**

```tsx
// frontend/src/components/dashboard/RecentActions.tsx
import { List, Typography, Skeleton, theme } from "antd";
import { useNavigate } from "react-router-dom";
import type { DashboardRecentAction } from "../../types";
import { relativeTime } from "../../utils/relativeTime";

interface RecentActionsProps {
  data: DashboardRecentAction[];
  loading: boolean;
  error?: boolean;
  onRetry?: () => void;
}

export default function RecentActions({
  data,
  loading,
  error = false,
  onRetry,
}: RecentActionsProps) {
  const { token } = theme.useToken();
  const navigate = useNavigate();

  if (loading) {
    return (
      <div>
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} style={{ padding: "8px 0" }}>
            <Skeleton active paragraph={{ rows: 1 }} title={{ width: "30%" }} />
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ textAlign: "center", padding: 24 }}>
        <Typography.Text type="secondary">加载失败</Typography.Text>
        <br />
        <Typography.Link onClick={onRetry} style={{ marginTop: 8, display: "inline-block" }}>
          重试
        </Typography.Link>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div style={{ textAlign: "center", padding: 24 }}>
        <Typography.Text type="secondary">暂无操作记录</Typography.Text>
      </div>
    );
  }

  const typeMap: Record<string, { label: string; path: string }> = {
    fmea_documents: { label: "FMEA", path: "/fmea" },
    capa_eightd: { label: "CAPA", path: "/capa" },
  };

  return (
    <List
      dataSource={data}
      renderItem={(item) => {
        const info = typeMap[item.table_name] || { label: item.table_name, path: "/" };
        return (
          <List.Item
            style={{ cursor: "pointer", padding: "8px 0" }}
            onClick={() => navigate(`${info.path}/${item.record_id}`)}
            tabIndex={0}
            onKeyDown={(e) => e.key === "Enter" && navigate(`${info.path}/${item.record_id}`)}
            role="listitem"
          >
            <List.Item.Meta
              title={
                <span>
                  <span style={{ color: token.colorTextSecondary, marginRight: 8 }}>
                    {relativeTime(item.operated_at)}
                  </span>
                  {info.label} - {item.entity_no}
                </span>
              }
              description={item.action}
            />
          </List.Item>
        );
      }}
    />
  );
}
```

- [ ] **Step 3: Create CollapsibleSection component**

```tsx
// frontend/src/components/dashboard/CollapsibleSection.tsx
import { useState } from "react";
import { Typography, theme } from "antd";
import { DownOutlined, UpOutlined } from "@ant-design/icons";
import type { ReactNode } from "react";

interface CollapsibleSectionProps {
  title: string;
  defaultCollapsed?: boolean;
  children: ReactNode;
  /** Hide entirely (e.g. viewer + quick entry) */
  hidden?: boolean;
}

export default function CollapsibleSection({
  title,
  defaultCollapsed = false,
  children,
  hidden = false,
}: CollapsibleSectionProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const { token } = theme.useToken();

  if (hidden) return null;

  return (
    <div>
      <div
        onClick={() => setCollapsed(!collapsed)}
        onKeyDown={(e) => e.key === "Enter" && setCollapsed(!collapsed)}
        role="button"
        tabIndex={0}
        aria-expanded={!collapsed}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          cursor: "pointer",
          padding: "8px 0",
          userSelect: "none",
        }}
      >
        <Typography.Text strong style={{ fontSize: 15 }}>
          {title}
        </Typography.Text>
        {collapsed ? <DownOutlined /> : <UpOutlined />}
      </div>
      {!collapsed && children}
    </div>
  );
}
```

- [ ] **Step 4: Verify all new files compile**

Run: `cd frontend && npx tsc --noEmit`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/relativeTime.ts frontend/src/components/dashboard/RecentActions.tsx frontend/src/components/dashboard/CollapsibleSection.tsx
git commit -m "feat: add RecentActions, CollapsibleSection, and relativeTime utility"
```

---

### Task 6: Dashboard Page Rewrite

**Files:**
- Modify: `frontend/src/pages/dashboard/DashboardPage.tsx`

- [ ] **Step 1: Rewrite DashboardPage**

Replace the entire file content:

```tsx
// frontend/src/pages/dashboard/DashboardPage.tsx
import { useEffect, useState, useCallback } from "react";
import { Row, Col, Card, Button, Typography, Space, theme } from "antd";
import {
  ClockCircleOutlined,
  AlertOutlined,
  WarningOutlined,
  RiseOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import {
  getDashboardSummary,
  getDashboardAlerts,
  getDashboardRecentActions,
} from "../../api/dashboard";
import type { DashboardSummary, DashboardAlerts, DashboardRecentAction } from "../../types";
import { useProductLineStore } from "../../store/productLineStore";
import { useAuthStore } from "../../store/authStore";
import KPICard from "../../components/dashboard/KPICard";
import RiskList from "../../components/dashboard/RiskList";
import RecentActions from "../../components/dashboard/RecentActions";
import CollapsibleSection from "../../components/dashboard/CollapsibleSection";

const { Title } = Typography;

export default function DashboardPage() {
  const navigate = useNavigate();
  const { token } = theme.useToken();
  const productLine = useProductLineStore((s) => s.selected);
  const user = useAuthStore((s) => s.user);
  const isViewer = user?.role === "viewer";

  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [alerts, setAlerts] = useState<DashboardAlerts | null>(null);
  const [recentActions, setRecentActions] = useState<DashboardRecentAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [summaryError, setSummaryError] = useState(false);
  const [alertsError, setAlertsError] = useState(false);
  const [actionsError, setActionsError] = useState(false);

  const fetchData = useCallback(() => {
    setLoading(true);
    setSummaryError(false);
    setAlertsError(false);
    setActionsError(false);

    getDashboardSummary(productLine || undefined)
      .then(setSummary)
      .catch(() => setSummaryError(true));

    getDashboardAlerts(productLine || undefined)
      .then(setAlerts)
      .catch(() => setAlertsError(true));

    getDashboardRecentActions()
      .then(setRecentActions)
      .catch(() => setActionsError(true))
      .finally(() => setLoading(false));
  }, [productLine]);

  useEffect(fetchData, [fetchData]);

  // KPI status logic
  const pendingStatus = (summary?.pending_actions ?? 0) > 0 ? "warning" : "success";
  const overdueStatus = (summary?.overdue_tasks ?? 0) > 0 ? "danger" : "success";
  const riskStatus = (summary?.high_risk_items ?? 0) > 0 ? "danger" : "success";
  const trendValue = summary?.month_trend ?? 0;
  const trendStatus = trendValue > 0 ? "success" : trendValue < 0 ? "danger" : "success";

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>
        质量仪表盘
      </Title>

      {/* P0: KPI 指标卡 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <KPICard
            title="待办事项"
            value={loading ? null : summary?.pending_actions ?? 0}
            status={pendingStatus}
            subtitle={loading ? undefined : (summary?.pending_actions ?? 0) === 0 ? "暂无" : undefined}
            icon={<ClockCircleOutlined />}
            onClick={() => navigate("/capa?pending_action=true")}
            loading={loading}
            error={summaryError}
            onRetry={fetchData}
            disabled={isViewer}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KPICard
            title="超期任务"
            value={loading ? null : summary?.overdue_tasks ?? 0}
            status={overdueStatus}
            subtitle={loading ? undefined : (summary?.overdue_tasks ?? 0) === 0 ? "暂无" : undefined}
            icon={<AlertOutlined />}
            onClick={() => navigate("/capa?overdue=true")}
            loading={loading}
            error={summaryError}
            onRetry={fetchData}
            disabled={isViewer}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KPICard
            title="高风险项"
            value={loading ? null : summary?.high_risk_items ?? 0}
            status={riskStatus}
            subtitle={loading ? undefined : (summary?.high_risk_items ?? 0) === 0 ? "暂无" : undefined}
            icon={<WarningOutlined />}
            onClick={() => navigate("/fmea?risk=high")}
            loading={loading}
            error={summaryError}
            onRetry={fetchData}
            disabled={isViewer}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KPICard
            title="本月新增"
            value={loading ? null : trendValue}
            status={trendStatus}
            subtitle={
              loading
                ? undefined
                : trendValue > 0
                  ? `↑ ${trendValue}%`
                  : trendValue < 0
                    ? `↓ ${Math.abs(trendValue)}%`
                    : "—"
            }
            icon={<RiseOutlined />}
            loading={loading}
            error={summaryError}
            onRetry={fetchData}
            disabled
          />
        </Col>
      </Row>

      {/* P1: 待处置事项 */}
      <div style={{ marginTop: 24 }}>
        <Title level={5} style={{ marginBottom: 16 }}>
          待处置事项
        </Title>
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={8}>
            <Card size="small" title="高 RPN FMEA">
              <RiskList
                data={alerts}
                loading={loading}
                error={alertsError}
                onRetry={fetchData}
                disabled={isViewer}
              />
            </Card>
          </Col>
          <Col xs={24} lg={8}>
            <Card size="small" title="超期 CAPA">
              <RiskList
                data={alerts ? { ...alerts, high_rpn_fmeas: [], high_ppm_suppliers: [] } : null}
                loading={loading}
                error={alertsError}
                onRetry={fetchData}
                disabled={isViewer}
              />
            </Card>
          </Col>
          <Col xs={24} lg={8}>
            <Card size="small" title="PPM 超标供应商">
              <RiskList
                data={alerts ? { ...alerts, high_rpn_fmeas: [], overdue_capas: [] } : null}
                loading={loading}
                error={alertsError}
                onRetry={fetchData}
                disabled={isViewer}
              />
            </Card>
          </Col>
        </Row>
      </div>

      {/* P2/P3: 最近操作 + 快速入口 */}
      <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
        <Col xs={24} lg={16}>
          <CollapsibleSection title="最近操作" defaultCollapsed={false}>
            <Card size="small">
              <RecentActions
                data={recentActions}
                loading={loading}
                error={actionsError}
                onRetry={fetchData}
              />
            </Card>
          </CollapsibleSection>
        </Col>
        <Col xs={24} lg={8}>
          <CollapsibleSection title="快速入口" hidden={isViewer}>
            <Card size="small">
              <Space direction="vertical" style={{ width: "100%" }}>
                <Button
                  type="default"
                  icon={<PlusOutlined />}
                  block
                  onClick={() => navigate("/fmea")}
                >
                  新建 FMEA
                </Button>
                <Button
                  type="default"
                  icon={<PlusOutlined />}
                  block
                  onClick={() => navigate("/capa")}
                >
                  新建 CAPA
                </Button>
                <Button
                  type="default"
                  icon={<PlusOutlined />}
                  block
                  onClick={() => navigate("/customer-quality")}
                >
                  新建客诉
                </Button>
              </Space>
            </Card>
          </CollapsibleSection>
        </Col>
      </Row>
    </div>
  );
}
```

- [ ] **Step 2: Fix RiskList split pattern**

The current `RiskList` receives full `alerts` but we need to split by category. Update `RiskList.tsx` to accept a `category` prop:

```tsx
// In RiskList.tsx, update the interface:
interface RiskListProps {
  data: DashboardAlerts | null;
  category: "fmea" | "capa" | "supplier";
  loading: boolean;
  error?: boolean;
  onRetry?: () => void;
  disabled?: boolean;
}
```

Then in the component, filter items by category instead of mixing all. Update the `items` construction:

```tsx
  let items: Array<{
    key: string;
    title: string;
    description: string;
    tag: string;
    tagColor: "error" | "warning";
    action: string;
    onClick: () => void;
  }> = [];

  if (category === "fmea") {
    items = (data?.high_rpn_fmeas ?? []).map((item) => ({
      key: `fmea-${item.fmea_id}`,
      title: item.document_no,
      description: item.node_name,
      tag: `RPN=${item.rpn}`,
      tagColor: item.rpn >= 200 ? "error" as const : "warning" as const,
      action: "前往审批",
      onClick: () => navigate(`/fmea/${item.fmea_id}`),
    }));
  } else if (category === "capa") {
    items = (data?.overdue_capas ?? []).map((item) => ({
      key: `capa-${item.report_id}`,
      title: item.document_no,
      description: `超期 ${item.overdue_days} 天`,
      tag: `${item.overdue_days}天`,
      tagColor: "error" as const,
      action: "前往跟进",
      onClick: () => navigate(`/capa/${item.report_id}`),
    }));
  } else {
    items = (data?.high_ppm_suppliers ?? []).map((item) => ({
      key: `supplier-${item.supplier_id}`,
      title: item.supplier_name,
      description: `PPM: ${item.ppm}`,
      tag: `PPM=${item.ppm}`,
      tagColor: item.ppm > 500 ? "error" as const : "warning" as const,
      action: "前往查看",
      onClick: () => navigate(`/suppliers/${item.supplier_id}`),
    }));
  }
```

Update `DashboardPage.tsx` risk list calls:

```tsx
<RiskList data={alerts} category="fmea" loading={loading} error={alertsError} onRetry={fetchData} disabled={isViewer} />
<RiskList data={alerts} category="capa" loading={loading} error={alertsError} onRetry={fetchData} disabled={isViewer} />
<RiskList data={alerts} category="supplier" loading={loading} error={alertsError} onRetry={fetchData} disabled={isViewer} />
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run build`
Expected: no TypeScript errors, build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/dashboard/DashboardPage.tsx frontend/src/components/dashboard/RiskList.tsx
git commit -m "feat: rewrite dashboard with KPI cards, risk list, recent actions, and collapsible sections"
```

---

### Task 7: Responsive & Accessibility Polish

**Files:**
- Modify: `frontend/src/pages/dashboard/DashboardPage.tsx`
- Modify: `frontend/src/components/dashboard/CollapsibleSection.tsx`

- [ ] **Step 1: Add mobile collapse logic to CollapsibleSection**

Update `CollapsibleSection` to accept a `collapseAt` breakpoint and auto-collapse on small screens:

```tsx
// frontend/src/components/dashboard/CollapsibleSection.tsx
import { useState, useEffect } from "react";
import { Typography, theme } from "antd";
import { DownOutlined, UpOutlined } from "@ant-design/icons";
import type { ReactNode } from "react";

interface CollapsibleSectionProps {
  title: string;
  defaultCollapsed?: boolean;
  children: ReactNode;
  hidden?: boolean;
  /** Auto-collapse below this viewport width (px). 0 = never auto-collapse. */
  collapseAt?: number;
}

export default function CollapsibleSection({
  title,
  defaultCollapsed = false,
  children,
  hidden = false,
  collapseAt = 0,
}: CollapsibleSectionProps) {
  const { token } = theme.useToken();
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  useEffect(() => {
    if (collapseAt <= 0) return;
    const mql = window.matchMedia(`(max-width: ${collapseAt}px)`);
    const handler = (e: MediaQueryListEvent | MediaQueryList) => {
      if (e.matches) setCollapsed(true);
    };
    handler(mql);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, [collapseAt]);

  if (hidden) return null;

  return (
    <div>
      <div
        onClick={() => setCollapsed(!collapsed)}
        onKeyDown={(e) => e.key === "Enter" && setCollapsed(!collapsed)}
        role="button"
        tabIndex={0}
        aria-expanded={!collapsed}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          cursor: "pointer",
          padding: "8px 0",
          userSelect: "none",
        }}
      >
        <Typography.Text strong style={{ fontSize: 15 }}>
          {title}
        </Typography.Text>
        {collapsed ? <DownOutlined /> : <UpOutlined />}
      </div>
      {!collapsed && children}
    </div>
  );
}
```

- [ ] **Step 2: Apply collapseAt to DashboardPage**

In `DashboardPage.tsx`, update the CollapsibleSection usage:

```tsx
{/* P2: 最近操作 — auto-collapse on mobile */}
<CollapsibleSection title="最近操作" collapseAt={767}>
  {/* ... */}
</CollapsibleSection>

{/* P3: 快速入口 — auto-collapse on mobile, hidden for viewer */}
<CollapsibleSection title="快速入口" collapseAt={767} hidden={isViewer}>
  {/* ... */}
</CollapsibleSection>
```

- [ ] **Step 3: Add ARIA landmarks**

In `DashboardPage.tsx`, wrap sections with semantic elements:

```tsx
{/* P0: KPI 指标卡 */}
<section aria-label="质量指标概览">
  <Row gutter={[16, 16]}>...</Row>
</section>

{/* P1: 待处置事项 */}
<section aria-label="待处置事项" style={{ marginTop: 24 }}>
  <Title level={5}>待处置事项</Title>
  ...
</section>
```

- [ ] **Step 4: Verify responsive behavior**

Run: `cd frontend && npm run dev`
Test: Chrome DevTools → toggle device toolbar → 375px width. "最近操作" and "快速入口" should auto-collapse with expand arrows.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/dashboard/CollapsibleSection.tsx frontend/src/pages/dashboard/DashboardPage.tsx
git commit -m "feat: add responsive auto-collapse and ARIA landmarks to dashboard"
```

---

### Task 8: Build Verification & Cleanup

**Files:**
- None (verification only)

- [ ] **Step 1: Full TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 2: Production build**

Run: `cd frontend && npm run build`
Expected: build succeeds. Note the gzipped JS size from the output.

- [ ] **Step 3: Lint check**

Run: `cd frontend && npm run lint`
Fix any warnings.

- [ ] **Step 4: Manual visual verification**

Run: `cd frontend && npm run dev`
Open `http://localhost:5173/dashboard` and verify:
- Dark background (#0a0e1a), dark cards (#111827)
- KPI cards show colored top borders (green/yellow/red)
- "待处置事项" section has action verbs (前往审批/前往跟进/前往查看)
- "最近操作" shows relative times
- "快速入口" buttons are `type="default"` (not primary)
- Tab through KPI cards and risk list items — focus ring visible
- Resize to 375px — "最近操作" and "快速入口" auto-collapse

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: dark industrial dashboard — complete implementation"
```

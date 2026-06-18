import { useEffect, useState, useCallback } from "react";
import { Button, Space, App } from "antd";
import {
  EditOutlined,
  CheckOutlined,
  CloseOutlined,
  ReloadOutlined,
  RollbackOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import DashboardGrid from "../../components/dashboard/DashboardGrid";
import WidgetLibraryPanel from "../../components/dashboard/WidgetLibraryPanel";
import {
  getDashboardLayout,
  saveDashboardLayout,
  getDashboardWidgets,
} from "../../api/dashboard";
import { useProductLineStore } from "../../store/productLineStore";
import { usePermission } from "../../hooks/usePermission";
import { PageShell } from "../../components/design";
import type {
  WidgetLayoutItem,
  DashboardLayoutConfig,
  DashboardWidgetsData,
} from "../../components/dashboard/widgets/types";
import {
  createWidgetLayoutItem,
  filterLayoutByPermission,
} from "../../components/dashboard/dashboardLayoutUtils";

const DEFAULT_LAYOUT: DashboardLayoutConfig = {
  lg: [
    { i: "kpi-pending", type: "kpi_pending_actions", x: 0, y: 0, w: 3, h: 2 },
    { i: "kpi-overdue", type: "kpi_overdue_tasks", x: 3, y: 0, w: 3, h: 2 },
    { i: "kpi-risk", type: "kpi_high_risk_items", x: 6, y: 0, w: 3, h: 2 },
    { i: "kpi-trend", type: "kpi_month_trend", x: 9, y: 0, w: 3, h: 2 },
    { i: "alert-fmea", type: "alert_high_rpn_fmea", x: 0, y: 2, w: 4, h: 4 },
    { i: "alert-capa", type: "alert_overdue_capa", x: 4, y: 2, w: 4, h: 4 },
    { i: "alert-ppm", type: "alert_high_ppm_suppliers", x: 8, y: 2, w: 4, h: 4 },
    { i: "recent-actions", type: "recent_actions", x: 0, y: 6, w: 12, h: 3 },
  ],
};

/** Detect overlapping or out-of-bounds widgets in the lg layout. */
function isLayoutCorrupted(layout: WidgetLayoutItem[]): boolean {
  for (const item of layout) {
    if (item.x < 0 || item.y < 0 || item.w <= 0 || item.h <= 0) return true;
    if (item.x + item.w > 12) return true;
  }
  for (let i = 0; i < layout.length; i++) {
    for (let j = i + 1; j < layout.length; j++) {
      const a = layout[i];
      const b = layout[j];
      const overlapX = a.x < b.x + b.w && a.x + a.w > b.x;
      const overlapY = a.y < b.y + b.h && a.y + a.h > b.y;
      if (overlapX && overlapY) return true;
    }
  }
  return false;
}

function createEmptyData(): DashboardWidgetsData {
  return {
    kpi: {},
    alerts: {},
    recent_actions: [],
    spc: {},
    msa: {},
    iqc: {},
    mes: {},
    supplier: {},
    quality_trend: {},
    errors: {},
  };
}

export default function DashboardPage() {
  const { t } = useTranslation("dashboard");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const productLine = useProductLineStore((s) => s.selected);
  const { canEdit, canView } = usePermission();
  const canEditDashboard = canEdit("dashboard");

  const [layout, setLayout] = useState<WidgetLayoutItem[]>(() =>
    DEFAULT_LAYOUT.lg.map((item) => ({ ...item }))
  );
  const [editLayout, setEditLayout] = useState<WidgetLayoutItem[] | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [data, setData] = useState<DashboardWidgetsData>(createEmptyData);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const layoutResp = await getDashboardLayout();
      let loadedLayout = (layoutResp.layout_config?.lg ?? DEFAULT_LAYOUT.lg).filter(
        (item) => !!item.type
      );
      if (isLayoutCorrupted(loadedLayout)) {
        console.warn("Dashboard layout corrupted; resetting to default", loadedLayout);
        loadedLayout = DEFAULT_LAYOUT.lg.map((item) => ({ ...item }));
      }
      setLayout(loadedLayout);

      const widgetTypes = [...new Set(loadedLayout.map((w) => w.type))];
      const widgetsResp = await getDashboardWidgets(widgetTypes, productLine || undefined);
      return widgetsResp;
    } catch (e) {
      console.error("Dashboard fetch error:", e);
      message.error(t("messages.loadFailed", "仪表盘加载失败"));
      return null;
    } finally {
      setLoading(false);
    }
  }, [productLine, t, message]);

  useEffect(() => {
    let cancelled = false;
    fetchData().then((widgetsResp) => {
      // Drop the result if a later product-line switch superseded this fetch
      // (resolved out of order) — prevents overwriting `data` with stale rows.
      if (!cancelled && widgetsResp) setData(widgetsResp);
    });
    return () => { cancelled = true; };
  }, [fetchData]);

  const handleEdit = () => {
    setEditLayout([...layout]);
    setIsEditing(true);
  };

  const handleSave = async () => {
    if (!editLayout) return;
    try {
      await saveDashboardLayout({ lg: editLayout });
      setLayout(editLayout);
      setIsEditing(false);
      setEditLayout(null);
      message.success(t("messages.saveSuccess", "布局已保存"));
      const widgetTypes = [...new Set(editLayout.map((w) => w.type))];
      const widgetsResp = await getDashboardWidgets(widgetTypes, productLine || undefined);
      setData(widgetsResp);
    } catch {
      message.error(t("messages.saveFailed", "保存失败"));
    }
  };

  const handleCancel = () => {
    setEditLayout(null);
    setIsEditing(false);
  };

  const handleReset = async () => {
    try {
      const resetLayout = filterLayoutByPermission(DEFAULT_LAYOUT.lg, canView);
      await saveDashboardLayout({ lg: resetLayout });
      setLayout(resetLayout);
      setEditLayout(resetLayout);
      message.success(t("messages.resetSuccess", "已恢复默认布局"));
      const widgetTypes = [...new Set(resetLayout.map((w) => w.type))];
      const widgetsResp = await getDashboardWidgets(widgetTypes, productLine || undefined);
      setData(widgetsResp);
    } catch {
      message.error(t("messages.resetFailed", "恢复失败"));
    }
  };

  const handleAddWidget = (type: string) => {
    if (!editLayout) return;
    const id =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : Math.random().toString(36).substring(2, 11);
    const newItem = createWidgetLayoutItem(type, id);
    setEditLayout([...editLayout, newItem]);
  };

  const handleRemoveWidget = (i: string) => {
    if (!editLayout) return;
    setEditLayout(editLayout.filter((w) => w.i !== i));
  };

  const currentLayout = isEditing && editLayout ? editLayout : layout;

  const actions = isEditing ? (
    <Space>
      <Button icon={<CheckOutlined />} type="primary" onClick={handleSave}>
        {t("actions.done", "完成")}
      </Button>
      <Button icon={<CloseOutlined />} onClick={handleCancel}>
        {tc("actions.cancel", "取消")}
      </Button>
      <Button icon={<RollbackOutlined />} onClick={handleReset}>
        {t("actions.resetDefault", "恢复默认")}
      </Button>
    </Space>
  ) : (
    <Space>
      <Button icon={<ReloadOutlined />} onClick={fetchData} loading={loading}>
        {tc("actions.refresh", "刷新")}
      </Button>
      {canEditDashboard && (
        <Button icon={<EditOutlined />} onClick={handleEdit}>
          {t("actions.editLayout", "编辑布局")}
        </Button>
      )}
    </Space>
  );

  return (
    <PageShell
      title={t("page.title", "质量仪表盘")}
      subtitle={t("page.subtitle", "全局质量态势 · KPI · 预警 · 近期动态")}
      actions={actions}
      fullHeight
    >
      <div style={{ flex: 1, display: "flex", minWidth: 0 }}>
        {isEditing && <WidgetLibraryPanel onAddWidget={handleAddWidget} />}
        <div style={{ flex: 1, minWidth: isEditing ? 1200 : 0, paddingBottom: 24 }}>
          <DashboardGrid
            layout={currentLayout}
            data={data}
            loading={loading}
            isEditing={isEditing}
            onLayoutChange={(newLayout) => {
              if (isEditing) setEditLayout(newLayout);
            }}
            onRemoveWidget={handleRemoveWidget}
            onRetry={fetchData}
          />
        </div>
      </div>
    </PageShell>
  );
}
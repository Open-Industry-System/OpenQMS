import { useEffect, useState, useCallback } from "react";
import { Button, Typography, Space, message } from "antd";
import {
  EditOutlined,
  CheckOutlined,
  CloseOutlined,
  ReloadOutlined,
  RollbackOutlined,
} from "@ant-design/icons";
import DashboardGrid from "../../components/dashboard/DashboardGrid";
import WidgetLibraryPanel from "../../components/dashboard/WidgetLibraryPanel";
import {
  getDashboardLayout,
  saveDashboardLayout,
  getDashboardWidgets,
} from "../../api/dashboard";
import { useProductLineStore } from "../../store/productLineStore";
import { usePermission } from "../../hooks/usePermission";
import type {
  WidgetLayoutItem,
  DashboardLayoutConfig,
  DashboardWidgetsData,
} from "../../components/dashboard/widgets/types";

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
    errors: {},
  };
}

const { Title } = Typography;

export default function DashboardPage() {
  const productLine = useProductLineStore((s) => s.selected);
  const { canEdit } = usePermission();
  const canEditDashboard = canEdit("dashboard");

  const [layout, setLayout] = useState<WidgetLayoutItem[]>(() =>
    DEFAULT_LAYOUT.lg.map((item) => ({ ...item }))
  );
  const [editLayout, setEditLayout] = useState<WidgetLayoutItem[] | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [data, setData] = useState<DashboardWidgetsData>(createEmptyData);
  const [loading, setLoading] = useState(true);

  // Fetch layout first, then fetch widgets based on returned layout types
  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const layoutResp = await getDashboardLayout();
      const validWidgets = (layoutResp.layout_config?.lg ?? DEFAULT_LAYOUT.lg).filter(
        (item) => !!item.type
      );
      setLayout(validWidgets);

      const widgetTypes = [...new Set(validWidgets.map((w) => w.type))];
      const widgetsResp = await getDashboardWidgets(widgetTypes, productLine || undefined);
      setData(widgetsResp);
    } catch (e) {
      console.error("Dashboard fetch error:", e);
      message.error("仪表盘加载失败");
    } finally {
      setLoading(false);
    }
  }, [productLine]);

  useEffect(() => {
    fetchData();
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
      message.success("布局已保存");
      // Re-fetch only widget data for the new layout types, no loading flicker
      const widgetTypes = [...new Set(editLayout.map((w) => w.type))];
      const widgetsResp = await getDashboardWidgets(widgetTypes, productLine || undefined);
      setData(widgetsResp);
    } catch {
      message.error("保存失败");
    }
  };

  const handleCancel = () => {
    setEditLayout(null);
    setIsEditing(false);
  };

  const handleReset = async () => {
    try {
      await saveDashboardLayout(DEFAULT_LAYOUT);
      const resetLayout = DEFAULT_LAYOUT.lg.map((item) => ({ ...item }));
      setLayout(resetLayout);
      setEditLayout(resetLayout);
      message.success("已恢复默认布局");
      // Re-fetch only widget data for default layout types, no loading flicker
      const widgetTypes = [...new Set(resetLayout.map((w) => w.type))];
      const widgetsResp = await getDashboardWidgets(widgetTypes, productLine || undefined);
      setData(widgetsResp);
    } catch {
      message.error("恢复失败");
    }
  };

  const handleAddWidget = (type: string) => {
    if (!editLayout) return;
    const id =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : Math.random().toString(36).substring(2, 11);
    const newItem: WidgetLayoutItem = {
      i: `${type}-${id}`,
      type,
      x: 0,
      y: 100, // Will be compacted by react-grid-layout
      w: 3,
      h: 2,
    };
    setEditLayout([...editLayout, newItem]);
  };

  const handleRemoveWidget = (i: string) => {
    if (!editLayout) return;
    setEditLayout(editLayout.filter((w) => w.i !== i));
  };

  const currentLayout = isEditing && editLayout ? editLayout : layout;

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>质量仪表盘</Title>
        <Space>
          {isEditing ? (
            <>
              <Button icon={<CheckOutlined />} type="primary" onClick={handleSave}>
                完成
              </Button>
              <Button icon={<CloseOutlined />} onClick={handleCancel}>
                取消
              </Button>
              <Button icon={<RollbackOutlined />} onClick={handleReset}>
                恢复默认
              </Button>
            </>
          ) : (
            <>
              <Button icon={<ReloadOutlined />} onClick={fetchData} loading={loading}>
                刷新
              </Button>
              {canEditDashboard && (
                <Button icon={<EditOutlined />} onClick={handleEdit}>
                  编辑布局
                </Button>
              )}
            </>
          )}
        </Space>
      </div>

      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {isEditing && (
          <WidgetLibraryPanel onAddWidget={handleAddWidget} />
        )}
        <div style={{ flex: 1, overflow: "auto", padding: "0 8px" }}>
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
    </div>
  );
}

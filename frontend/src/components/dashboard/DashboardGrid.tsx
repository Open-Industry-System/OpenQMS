import { useState, useMemo } from "react";
import { Responsive, WidthProvider } from "react-grid-layout/legacy";
import type { LayoutItem, ResponsiveLayouts } from "react-grid-layout/legacy";
import type { WidgetLayoutItem, DashboardWidgetsData } from "./widgets/types";
import WidgetWrapper from "./WidgetWrapper";

const ResponsiveGridLayout = WidthProvider(Responsive);

const GRID_CONFIG = {
  defaultCols: 12,
  rowHeight: 40,
  margin: [16, 16] as [number, number],
  containerPadding: [0, 0] as [number, number],
  breakpoints: { lg: 1200, md: 996, sm: 768, xs: 480 },
  cols: { lg: 12, md: 10, sm: 6, xs: 4 },
};

interface DashboardGridProps {
  layout: WidgetLayoutItem[];
  data: DashboardWidgetsData;
  loading: boolean;
  isEditing: boolean;
  onLayoutChange: (layout: WidgetLayoutItem[]) => void;
  onRemoveWidget: (i: string) => void;
  onRetry: () => void;
}

/** Scale lg layout (12 cols) to md layout (10 cols) preserving item.type */
function computeMdLayout(lgLayout: WidgetLayoutItem[]): WidgetLayoutItem[] {
  return lgLayout.map((item) => {
    const w = Math.max(2, Math.round((item.w * 10) / 12));
    const x = Math.round((item.x * 10) / 12);
    return {
      ...item,
      x: Math.min(x, 10 - w),
      w,
    };
  });
}

/** Sort by y/x then stack vertically for sm/xs breakpoints */
function computeMobileLayout(lgLayout: WidgetLayoutItem[]): WidgetLayoutItem[] {
  const sorted = [...lgLayout].sort((a, b) =>
    a.y === b.y ? a.x - b.x : a.y - b.y,
  );
  let currentY = 0;
  return sorted.map((item) => {
    const y = currentY;
    currentY += item.h;
    return {
      ...item,
      x: 0,
      y,
      w: 6, // Will be overridden by cols for sm/xs
    };
  });
}

export default function DashboardGrid({
  layout,
  data,
  loading,
  isEditing,
  onLayoutChange,
  onRemoveWidget,
  onRetry,
}: DashboardGridProps) {
  const [currentBreakpoint, setCurrentBreakpoint] = useState<string>("lg");

  const layouts: ResponsiveLayouts = useMemo(() => {
    const mobile = computeMobileLayout(layout);
    return {
      lg: layout,
      md: computeMdLayout(layout),
      sm: mobile.map((i) => ({ ...i, w: 6 })),
      xs: mobile.map((i) => ({ ...i, w: 4 })),
    };
  }, [layout]);

  // Only allow editing on lg breakpoint to avoid md layout overwriting lg persisted state
  const canEdit = isEditing && currentBreakpoint === "lg";

  return (
    <ResponsiveGridLayout
      className="dashboard-grid"
      layouts={layouts}
      breakpoints={GRID_CONFIG.breakpoints}
      cols={GRID_CONFIG.cols}
      rowHeight={GRID_CONFIG.rowHeight}
      margin={GRID_CONFIG.margin}
      containerPadding={GRID_CONFIG.containerPadding}
      onBreakpointChange={(bp: string) => setCurrentBreakpoint(bp)}
      compactType="vertical"
      isDraggable={canEdit}
      isResizable={canEdit}
      onLayoutChange={(currentLayout: readonly LayoutItem[], allLayouts: ResponsiveLayouts) => {
        // react-grid-layout onLayoutChange only returns {i,x,y,w,h} — merge 'type' back.
        // Only persist lg breakpoint; edit mode is disabled on md/sm/xs.
        if (isEditing && allLayouts.lg) {
          const typeMap = new Map(layout.map((w) => [w.i, w.type]));
          const newLayout: WidgetLayoutItem[] = allLayouts.lg.map((l: LayoutItem) => ({
            i: l.i,
            type: typeMap.get(l.i) || "",
            x: l.x,
            y: l.y,
            w: l.w,
            h: l.h,
          }));
          onLayoutChange(newLayout);
        }
      }}
    >
      {layout.map((item) => (
        <div key={item.i}>
          <WidgetWrapper
            item={item}
            data={data}
            loading={loading}
            isEditing={isEditing}
            onRemove={onRemoveWidget}
            onRetry={onRetry}
          />
        </div>
      ))}
    </ResponsiveGridLayout>
  );
}

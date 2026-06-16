import { useState, useMemo } from "react";
import { Responsive, WidthProvider } from "react-grid-layout/legacy";
import type { LayoutItem, ResponsiveLayouts } from "react-grid-layout/legacy";
import type { WidgetLayoutItem, DashboardWidgetsData } from "./widgets/types";
import { getWidgetMeta } from "./widgets/registry";
import WidgetWrapper from "./WidgetWrapper";

const ResponsiveGridLayout = WidthProvider(Responsive);

const GRID_CONFIG = {
  defaultCols: 12,
  rowHeight: 40,
  margin: [16, 16] as [number, number],
  containerPadding: [0, 0] as [number, number],
  breakpoints: { lg: 1200, md: 996, sm: 768, xs: 480 },
  cols: { lg: 12, md: 12, sm: 6, xs: 4 },
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

/** md breakpoint uses the same 12-col layout as lg; only column width shrinks. */
function computeMdLayout(lgLayout: WidgetLayoutItem[]): WidgetLayoutItem[] {
  return lgLayout.map((item) => ({ ...item }));
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

/** Two-column layout for sm (6 cols): KPI cards side-by-side, others full-width. */
function computeSmLayout(lgLayout: WidgetLayoutItem[]): WidgetLayoutItem[] {
  const sorted = [...lgLayout].sort((a, b) =>
    a.y === b.y ? a.x - b.x : a.y - b.y,
  );
  const cols = GRID_CONFIG.cols.sm;
  let rowY = 0;
  let rowX = 0;
  let rowHeight = 0;
  const result: WidgetLayoutItem[] = [];

  for (const item of sorted) {
    const meta = getWidgetMeta(item.type);
    const isKpi = meta?.category === "kpi";
    const w = isKpi ? Math.min(item.w, 3) : cols;

    if (rowX + w > cols) {
      rowY += rowHeight;
      rowX = 0;
      rowHeight = 0;
    }

    result.push({ ...item, x: rowX, y: rowY, w });
    rowX += w;
    rowHeight = Math.max(rowHeight, item.h);

    if (rowX >= cols) {
      rowY += rowHeight;
      rowX = 0;
      rowHeight = 0;
    }
  }

  return result;
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
    return {
      lg: layout,
      md: computeMdLayout(layout),
      sm: computeSmLayout(layout),
      xs: computeMobileLayout(layout).map((i) => ({ ...i, w: 4 })),
    };
  }, [layout]);

  // In edit mode the grid wrapper has minWidth:1200, guaranteeing the lg breakpoint.
  // Use isEditing directly to avoid stale breakpoint state timing issues.
  const canEdit = isEditing;

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
        // Only persist lg layout; edit mode keeps grid at lg breakpoint via minWidth.
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

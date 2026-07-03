import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useKpiDrilldown, useAlertDrilldown } from "../useDashboardDrilldown";
import type { DashboardWidgetsData } from "./types";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  canView: vi.fn((_m: string) => true),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../../hooks/usePermission", () => ({
  usePermission: () => ({ canView: mocks.canView }),
}));

const data = {
  kpi: { pending_breakdown: { fmea: 3, capa: 5, complaint: 4 } },
  alerts: {}, recent_actions: [],
  spc: {}, msa: {}, iqc: {}, mes: {}, supplier: {}, quality_trend: {}, errors: {},
} as DashboardWidgetsData;

describe("useKpiDrilldown", () => {
  afterEach(() => {
    mocks.navigate.mockClear();
    mocks.canView.mockReset();
    mocks.canView.mockReturnValue(true);
  });

  it("链接型：onClick 导航到目标 URL", () => {
    const { result } = renderHook(() => useKpiDrilldown("kpi_high_risk_items", data));
    expect(result.current.disabled).toBe(false);
    act(() => result.current.onClick?.());
    expect(mocks.navigate).toHaveBeenCalledWith("/fmea?high_rpn=true");
  });

  it("链接型无权限：disabled 且无 onClick", () => {
    mocks.canView.mockImplementation((m) => m !== "fmea");
    const { result } = renderHook(() => useKpiDrilldown("kpi_high_risk_items", data));
    expect(result.current.disabled).toBe(true);
    expect(result.current.onClick).toBeUndefined();
  });

  it("月度趋势：无 onClick、无菜单", () => {
    const { result } = renderHook(() => useKpiDrilldown("kpi_month_trend", data));
    expect(result.current.onClick).toBeUndefined();
    expect(result.current.menuItems).toBeUndefined();
    expect(result.current.disabled).toBe(false);
  });

  it("菜单型：三项含计数，onMenuClick 按 URL 导航", () => {
    const { result } = renderHook(() => useKpiDrilldown("kpi_pending_actions", data));
    const items = result.current.menuItems as { label?: string; disabled?: boolean }[];
    expect(items).toHaveLength(3);
    expect(items[0].label).toBe("FMEA Pending (3)");
    expect(items[1].label).toBe("CAPA Pending (5)");
    expect(items[2].label).toBe("Complaints Pending (4)");
    act(() => result.current.onMenuClick?.("/fmea?pending=true"));
    expect(mocks.navigate).toHaveBeenCalledWith("/fmea?pending=true");
  });

  it("菜单型：某分类无权限 → 该项 disabled", () => {
    mocks.canView.mockImplementation((m) => m !== "capa");
    const { result } = renderHook(() => useKpiDrilldown("kpi_pending_actions", data));
    const items = result.current.menuItems as { label?: string; disabled?: boolean }[];
    expect(items[0].disabled).toBe(false);
    expect(items[1].disabled).toBe(true);
  });
});

describe("useAlertDrilldown", () => {
  afterEach(() => {
    mocks.navigate.mockClear();
    mocks.canView.mockReset();
    mocks.canView.mockReturnValue(true);
  });

  it("有权限：行可点击并导航到详情页", () => {
    const { result } = renderHook(() => useAlertDrilldown("alert_high_rpn_fmea"));
    const row = result.current({ fmea_id: "f-1" });
    expect(row.clickable).toBe(true);
    act(() => row.onClick?.());
    expect(mocks.navigate).toHaveBeenCalledWith("/fmea/f-1");
  });

  it("无权限：行不可点击", () => {
    mocks.canView.mockReturnValue(false);
    const { result } = renderHook(() => useAlertDrilldown("alert_overdue_capa"));
    const row = result.current({ report_id: "r-1" });
    expect(row.clickable).toBe(false);
    expect(row.onClick).toBeUndefined();
  });
});

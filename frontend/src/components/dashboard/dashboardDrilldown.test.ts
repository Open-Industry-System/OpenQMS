import { describe, it, expect } from "vitest";
import { getKpiDrilldown, getAlertRowDrilldown } from "./dashboardDrilldown";
import type { DashboardWidgetsData } from "./widgets/types";

const allView = () => true;
const noView = () => false;

const data: DashboardWidgetsData = {
  kpi: { pending_breakdown: { fmea: 3, capa: 5, complaint: 4 } },
  alerts: {},
  recent_actions: [],
  spc: {}, msa: {}, iqc: {}, mes: {}, supplier: {}, quality_trend: {}, errors: {},
} as DashboardWidgetsData;

describe("getKpiDrilldown", () => {
  it("超期事项 → /capa?overdue=true，有权限可点", () => {
    expect(getKpiDrilldown("kpi_overdue_tasks", data, allView)).toEqual({
      kind: "link",
      url: "/capa?overdue=true",
      disabled: false,
    });
  });

  it("无目标模块权限 → disabled=true", () => {
    expect(getKpiDrilldown("kpi_overdue_tasks", data, noView)).toEqual({
      kind: "link",
      url: "/capa?overdue=true",
      disabled: true,
    });
  });

  it("高风险项 → /fmea?high_rpn=true", () => {
    expect(getKpiDrilldown("kpi_high_risk_items", data, allView)?.kind).toBe("link");
    expect((getKpiDrilldown("kpi_high_risk_items", data, allView) as { url: string }).url).toBe(
      "/fmea?high_rpn=true"
    );
  });

  it("月度趋势 → null（不可点）", () => {
    expect(getKpiDrilldown("kpi_month_trend", data, allView)).toBeNull();
  });

  it("待办事项 → 菜单三项，计数来自 pending_breakdown", () => {
    const d = getKpiDrilldown("kpi_pending_actions", data, allView);
    expect(d?.kind).toBe("menu");
    if (d?.kind === "menu") {
      expect(d.items).toHaveLength(3);
      expect(d.items[0]).toMatchObject({ url: "/fmea?pending=true", count: 3, disabled: false });
      expect(d.items[1]).toMatchObject({ url: "/capa?pending_action=true", count: 5, disabled: false });
      expect(d.items[2]).toMatchObject({ url: "/customer-quality?status=open", count: 4, disabled: false });
    }
  });

  it("待办菜单：无某分类权限 → 该项 disabled", () => {
    const d = getKpiDrilldown("kpi_pending_actions", data, (m) => m !== "capa");
    if (d?.kind === "menu") {
      expect(d.items[0].disabled).toBe(false); // fmea
      expect(d.items[1].disabled).toBe(true); // capa 无权限
      expect(d.items[2].disabled).toBe(false); // customer_quality
    }
  });

  it("待办菜单：缺 pending_breakdown 时计数回退 0", () => {
    const d = getKpiDrilldown("kpi_pending_actions", { ...data, kpi: {} }, allView);
    if (d?.kind === "menu") {
      expect(d.items.every((it) => it.count === 0)).toBe(true);
    }
  });

  it("单模块计数卡各映射正确 URL", () => {
    const cases: Record<string, string> = {
      spc_abnormal_count: "/spc?abnormal=true",
      msa_gauge_expiry: "/msa/gauges?expiring=30d",
      iqc_pending_inspections: "/iqc/inspections?status=pending",
      mes_equipment_status: "/mes/dashboard",
    };
    for (const [type, url] of Object.entries(cases)) {
      const d = getKpiDrilldown(type, data, allView);
      expect(d?.kind).toBe("link");
      expect((d as { url: string }).url).toBe(url);
    }
  });
});

describe("getAlertRowDrilldown", () => {
  it("高 RPN FMEA 行 → /fmea/:id", () => {
    expect(getAlertRowDrilldown("alert_high_rpn_fmea", { fmea_id: "f-1" }, allView)).toEqual({
      url: "/fmea/f-1",
    });
  });

  it("超期 CAPA 行 → /capa/:id", () => {
    expect(getAlertRowDrilldown("alert_overdue_capa", { report_id: "r-1" }, allView)).toEqual({
      url: "/capa/r-1",
    });
  });

  it("高 PPM 供应商行 → /suppliers/quality/:id", () => {
    expect(getAlertRowDrilldown("alert_high_ppm_suppliers", { supplier_id: "s-1" }, allView)).toEqual({
      url: "/suppliers/quality/s-1",
    });
  });

  it("无权限 → null", () => {
    expect(getAlertRowDrilldown("alert_high_rpn_fmea", { fmea_id: "f-1" }, noView)).toBeNull();
  });

  it("缺实体 ID → null", () => {
    expect(getAlertRowDrilldown("alert_high_rpn_fmea", {}, allView)).toBeNull();
  });

  it("未知类型 → null", () => {
    expect(getAlertRowDrilldown("unknown", { fmea_id: "x" }, allView)).toBeNull();
  });
});

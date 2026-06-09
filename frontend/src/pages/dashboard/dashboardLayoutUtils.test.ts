import { describe, expect, it } from "vitest";

import {
  createWidgetLayoutItem,
  filterLayoutByPermission,
  getWidgetErrorKey,
} from "../../components/dashboard/dashboardLayoutUtils";
import type { WidgetLayoutItem } from "../../components/dashboard/widgets/types";

describe("dashboard layout utilities", () => {
  it("creates added widgets with registry default size", () => {
    const item = createWidgetLayoutItem("recent_actions", "stable-id");

    expect(item).toMatchObject({
      i: "recent_actions-stable-id",
      type: "recent_actions",
      x: 0,
      y: 100,
      w: 12,
      h: 3,
    });
  });

  it("filters reset layout by widget module permission", () => {
    const layout: WidgetLayoutItem[] = [
      { i: "kpi-pending", type: "kpi_pending_actions", x: 0, y: 0, w: 3, h: 2 },
      { i: "alert-fmea", type: "alert_high_rpn_fmea", x: 0, y: 2, w: 4, h: 4 },
      { i: "alert-ppm", type: "alert_high_ppm_suppliers", x: 4, y: 2, w: 4, h: 4 },
    ];

    const filtered = filterLayoutByPermission(layout, (module) =>
      module === "dashboard" || module === "supplier"
    );

    expect(filtered.map((item) => item.type)).toEqual([
      "kpi_pending_actions",
      "alert_high_ppm_suppliers",
    ]);
  });

  it("maps widget types to backend error groups", () => {
    expect(getWidgetErrorKey("kpi_pending_actions")).toBe("kpi");
    expect(getWidgetErrorKey("alert_high_rpn_fmea")).toBe("alerts");
    expect(getWidgetErrorKey("recent_actions")).toBe("recent_actions");
    expect(getWidgetErrorKey("mes_equipment_status")).toBe("mes");
  });
});

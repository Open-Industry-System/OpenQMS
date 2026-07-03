import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi, afterEach } from "vitest";
import type { DashboardWidgetsData } from "./types";
import RecentActionsWidget from "./RecentActionsWidget";

// Two audit-log rows that reference the SAME record (same record_id) — e.g. a
// user created then updated one FMEA. The table must key rows by the unique
// audit-log id, not by record_id, or React warns about duplicate keys.
const dupRecordId = "b69697ab-90a5-4318-ab98-ba7482e1760c";
const data: DashboardWidgetsData = {
  kpi: {},
  alerts: {},
  recent_actions: [
    { log_id: "log-1", record_id: dupRecordId, table_name: "fmea_documents", entity_no: "PFMEA-2026-001", action: "CREATE", operated_at: "2026-06-29T10:00:00+00:00" },
    { log_id: "log-2", record_id: dupRecordId, table_name: "fmea_documents", entity_no: "PFMEA-2026-001", action: "UPDATE", operated_at: "2026-06-29T11:00:00+00:00" },
  ],
  spc: {}, msa: {}, iqc: {}, mes: {}, supplier: {}, quality_trend: {}, errors: {},
} as DashboardWidgetsData;

describe("RecentActionsWidget", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders both rows sharing a record_id without a duplicate-key warning", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(<RecentActionsWidget data={data} loading={false} error={false} onRetry={() => {}} />);

    // Both actions render (Create + Update), proving both rows survived.
    expect(screen.getByText("Create")).toBeInTheDocument();
    expect(screen.getByText("Update")).toBeInTheDocument();

    const dupKeyCall = errorSpy.mock.calls.find(
      (c) => typeof c[0] === "string" && c[0].includes("Encountered two children with the same key"),
    );
    expect(dupKeyCall).toBeUndefined();
  });
});
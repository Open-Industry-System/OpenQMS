import { describe, it, expect, vi, beforeEach, afterAll } from "vitest";
import { render, screen, fireEvent, waitFor, configure } from "@testing-library/react";
configure({ testIdAttribute: "data-e2e" });
afterAll(() => configure({ testIdAttribute: "data-testid" }));
import { App, ConfigProvider } from "antd";
import D3ContainmentPanel from "../D3ContainmentPanel";
import type { CAPAReport } from "../../../types";

const mockCapa: CAPAReport = {
  report_id: "capa-1",
  document_no: "8D-2026-001",
  title: "Test CAPA",
  product_line_code: "DC-DC-100",
  status: "D3_INTERIM",
  severity: "严重",
  d1_team: [],
  d2_description: null,
  d3_interim: null,
  d4_root_cause: null,
  d5_correction: null,
  d6_verification: null,
  d7_prevention: null,
  d8_closure: null,
  fmea_ref_id: null,
  fmea_node_id: null,
  due_date: null,
  d4_retry_count: 0,
  created_by: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const mockApis = vi.hoisted(() => ({
  getD3Runs: vi.fn().mockResolvedValue([]),
  getD3Snapshots: vi.fn().mockResolvedValue([]),
  getD3Report: vi.fn().mockResolvedValue(null),
  getD3Advice: vi.fn().mockResolvedValue({ advice: [] }),
  getD3Adoptions: vi.fn().mockResolvedValue([]),
  getD3Executions: vi.fn().mockResolvedValue([]),
  importD3Containment: vi.fn().mockResolvedValue({ run_id: "run-1" }),
  generateD3Report: vi.fn().mockResolvedValue({}),
  generateD3Advice: vi.fn().mockResolvedValue({}),
  decideD3Advice: vi.fn().mockResolvedValue({}),
  recordD3Execution: vi.fn().mockResolvedValue({}),
}));

vi.mock("../../../api/capa", () => ({
  ...mockApis,
}));

const renderPanel = (props: { capa?: CAPAReport; canEdit?: boolean } = {}) =>
  render(
    <ConfigProvider>
      <App>
        <D3ContainmentPanel capa={props.capa ?? mockCapa} canEdit={props.canEdit ?? true} />
      </App>
    </ConfigProvider>
  );

beforeEach(() => {
  vi.clearAllMocks();
  mockApis.getD3Runs.mockResolvedValue([]);
  mockApis.getD3Snapshots.mockResolvedValue([]);
  mockApis.getD3Report.mockResolvedValue(null);
  mockApis.getD3Advice.mockResolvedValue({ advice: [] });
  mockApis.getD3Adoptions.mockResolvedValue([]);
  mockApis.getD3Executions.mockResolvedValue([]);
});

describe("D3ContainmentPanel", () => {
  it("shows import button when canEdit and status is D3_INTERIM", async () => {
    mockApis.getD3Runs.mockResolvedValue([
      { run_id: "run-1", capa_id: "capa-1", factory_id: "f1", status: "completed", is_current: true, imported_types: [], analysis_context: {}, started_at: "2026-01-01T00:00:00Z", completed_at: "2026-01-01T00:00:00Z", created_at: "2026-01-01T00:00:00Z" },
    ]);
    renderPanel();
    await waitFor(() => expect(screen.getByTestId("d3-import-button")).toBeInTheDocument());
  });

  it("hides import button for viewer (canEdit=false)", async () => {
    renderPanel({ canEdit: false });
    await waitFor(() => expect(screen.queryByTestId("d3-import-button")).not.toBeInTheDocument());
  });

  it("hides import button when CAPA status is not D3_INTERIM", async () => {
    renderPanel({ capa: { ...mockCapa, status: "D4_ROOT_CAUSE" } });
    await waitFor(() => expect(screen.queryByTestId("d3-import-button")).not.toBeInTheDocument());
  });

  it("hides write buttons when viewing a historical run (is_current=false)", async () => {
    mockApis.getD3Runs.mockResolvedValue([
      { run_id: "run-1", capa_id: "capa-1", factory_id: "f1", status: "completed", is_current: true, imported_types: [], analysis_context: {}, started_at: "2026-01-01T00:00:00Z", completed_at: "2026-01-01T00:00:00Z", created_at: "2026-01-01T00:00:00Z" },
      { run_id: "run-0", capa_id: "capa-1", factory_id: "f1", status: "completed", is_current: false, imported_types: [], analysis_context: {}, started_at: "2026-01-01T00:00:00Z", completed_at: "2026-01-01T00:00:00Z", created_at: "2026-01-01T00:00:00Z" },
    ]);
    renderPanel();
    await waitFor(() => expect(screen.getByTestId("d3-import-button")).toBeInTheDocument());

    // Switch to historical run
    fireEvent.mouseDown(screen.getByRole("combobox"));
    await waitFor(() => expect(screen.getByText(/代次 2026-01-01/)).toBeInTheDocument());
    fireEvent.click(screen.getByText(/代次 2026-01-01/));

    await waitFor(() => expect(screen.queryByTestId("d3-import-button")).not.toBeInTheDocument());
    expect(screen.queryByTestId("d3-execution-add")).not.toBeInTheDocument();
  });
});

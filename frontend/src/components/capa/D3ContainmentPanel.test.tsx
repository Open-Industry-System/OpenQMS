import { describe, it, expect, vi, beforeEach, afterAll } from "vitest";
import { render, screen, fireEvent, waitFor, configure } from "@testing-library/react";
configure({ testIdAttribute: "data-e2e" });
afterAll(() => configure({ testIdAttribute: "data-testid" }));
import { App, ConfigProvider } from "antd";
import D3ContainmentPanel from "./D3ContainmentPanel";
import type { CAPAReport, D3ImportRun, D3ImpactReport, D3AdviceResponse, D3Execution } from "../../types";

const currentRunId = "run-current";
const historicalRunId = "run-hist";

const mockRuns: D3ImportRun[] = [
  {
    run_id: currentRunId,
    capa_id: "capa-1",
    factory_id: "fac-1",
    status: "completed",
    is_current: true,
    imported_types: ["inventory", "shipment", "iqc", "spc"],
    analysis_context: { capa_severity: "serious", risk_mapping_version: "v1" },
    started_at: "2026-07-12T00:00:00Z",
    completed_at: "2026-07-12T00:00:00Z",
    created_at: "2026-07-12T00:00:00Z",
  },
  {
    run_id: historicalRunId,
    capa_id: "capa-1",
    factory_id: "fac-1",
    status: "completed",
    is_current: false,
    imported_types: ["inventory", "shipment", "iqc", "spc"],
    analysis_context: { capa_severity: "serious", risk_mapping_version: "v1" },
    started_at: "2026-07-11T00:00:00Z",
    completed_at: "2026-07-11T00:00:00Z",
    created_at: "2026-07-11T00:00:00Z",
  },
];

const mockDoneReport: D3ImpactReport = {
  report_id: "report-1",
  run_id: currentRunId,
  factory_id: "fac-1",
  is_current: true,
  status: "done",
  risk_level: "high",
  risk_floor: "high",
  risk_explanation: "High risk",
  batches: [],
  impact_qty: [],
  customer_impact: [],
  time_window: {},
  llm_available: true,
  model: "test",
  stage_runs: [],
  prompt_stats: {},
  error: null,
  started_at: "2026-07-12T00:00:00Z",
  completed_at: "2026-07-12T00:00:00Z",
  generated_by: "user-1",
  generated_at: "2026-07-12T00:00:00Z",
  created_at: "2026-07-12T00:00:00Z",
};

const mockFailedReport: D3ImpactReport = {
  ...mockDoneReport,
  status: "failed",
  error: "llm_failed",
  risk_level: null,
  risk_floor: null,
  risk_explanation: null,
};

const mockEmptyAdvice: D3AdviceResponse = { advice: [], status: "done" };
const mockFailedAdvice: D3AdviceResponse = { advice: [], status: "failed", error: "llm_failed" };

const mockExecutions: D3Execution[] = [];

vi.mock("../../api/capa", () => ({
  importD3Containment: vi.fn().mockResolvedValue({}),
  getD3Runs: vi.fn().mockResolvedValue([]),
  getD3Snapshots: vi.fn().mockResolvedValue([]),
  generateD3Report: vi.fn().mockResolvedValue({}),
  getD3Report: vi.fn().mockResolvedValue(null),
  generateD3Advice: vi.fn().mockResolvedValue({ generation_id: "gen-1", status: "done" }),
  getD3Advice: vi.fn().mockResolvedValue({ advice: [], status: "done" }),
  decideD3Advice: vi.fn().mockResolvedValue({ adoption_id: "adopt-1" }),
  getD3Adoptions: vi.fn().mockResolvedValue([]),
  recordD3Execution: vi.fn().mockResolvedValue({ execution_id: "ex-1" }),
  updateD3Execution: vi.fn().mockResolvedValue({ execution_id: "ex-1" }),
  getD3Executions: vi.fn().mockResolvedValue([]),
}));

import {
  getD3Runs,
  getD3Report,
  getD3Advice,
  getD3Adoptions,
  getD3Executions,
} from "../../api/capa";

const baseCapa: CAPAReport = {
  report_id: "capa-1",
  document_no: "8D-001",
  title: "Test CAPA",
  status: "D3_INTERIM",
  severity: "严重",
  product_line_code: "DC-DC-100",
  factory_id: "fac-1",
  customer_name: null,
  created_at: "2026-07-12T00:00:00Z",
  updated_at: "2026-07-12T00:00:00Z",
} as unknown as CAPAReport;

const renderPanel = (props = {}) =>
  render(
    <ConfigProvider>
      <App>
        <D3ContainmentPanel capa={baseCapa} canEdit={true} {...props} />
      </App>
    </ConfigProvider>
  );

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getD3Runs).mockResolvedValue(mockRuns);
  // Use failed report so the generate button is visible (done is terminal → button hidden)
  vi.mocked(getD3Report).mockResolvedValue(mockFailedReport);
  vi.mocked(getD3Advice).mockResolvedValue(mockEmptyAdvice);
  vi.mocked(getD3Adoptions).mockResolvedValue([]);
  vi.mocked(getD3Executions).mockResolvedValue(mockExecutions);
});

describe("D3ContainmentPanel", () => {
  it("hides write buttons on historical run and restores them on current run", async () => {
    renderPanel();

    await waitFor(() => expect(screen.queryByTestId("d3-generate-report")).toBeInTheDocument());
    expect(screen.getByTestId("d3-execution-add")).toBeInTheDocument();

    // Switch to historical run
    const selector = screen.getByRole("combobox");
    fireEvent.mouseDown(selector);
    const histOption = screen.getByText(/代次.*2026-07-11/);
    fireEvent.click(histOption);

    await waitFor(() => expect(screen.queryByTestId("d3-generate-report")).not.toBeInTheDocument());
    expect(screen.queryByTestId("d3-execution-add")).not.toBeInTheDocument();
    expect(screen.queryByTestId("d3-generate-advice")).not.toBeInTheDocument();
    expect(getD3Report).toHaveBeenLastCalledWith("capa-1", historicalRunId);
    expect(getD3Adoptions).toHaveBeenLastCalledWith("capa-1", historicalRunId);

    // Switch back to current run
    fireEvent.mouseDown(selector);
    const currentOption = screen.getByText("当前代次");
    fireEvent.click(currentOption);

    await waitFor(() => expect(screen.queryByTestId("d3-generate-report")).toBeInTheDocument());
    expect(screen.getByTestId("d3-execution-add")).toBeInTheDocument();
    expect(getD3Report).toHaveBeenLastCalledWith("capa-1", currentRunId);
    expect(getD3Adoptions).toHaveBeenLastCalledWith("capa-1", currentRunId);
  });

  it("shows advice card and generate button when no advice exists", async () => {
    renderPanel();

    await waitFor(() => expect(screen.getByTestId("d3-advice-card")).toBeInTheDocument());
    expect(screen.getByTestId("d3-generate-advice")).toBeInTheDocument();
    expect(screen.getByTestId("d3-generate-advice")).toHaveTextContent("生成建议");
  });

  it("shows error banner and retry button when advice generation failed", async () => {
    vi.mocked(getD3Advice).mockResolvedValue(mockFailedAdvice);
    renderPanel();

    await waitFor(() => expect(screen.getByTestId("d3-advice-failed-banner")).toBeInTheDocument());
    expect(screen.getByTestId("d3-generate-advice")).toBeInTheDocument();
    expect(screen.getByTestId("d3-generate-advice")).toHaveTextContent("重试生成建议");
  });

  it("shows regenerate button when report is done, retry when failed, and attempt banner on newer failed retry", async () => {
    // done report → regenerate button visible (done is NOT terminal; POST regenerates)
    const doneWithFailedAttempt: D3ImpactReport = {
      ...mockDoneReport,
      latest_attempt_status: "failed",
      latest_attempt_error: "llm_failed",
    };
    vi.mocked(getD3Report).mockResolvedValue(doneWithFailedAttempt);
    renderPanel();

    const btn = await waitFor(() => screen.getByTestId("d3-generate-report"));
    expect(btn).toHaveTextContent("重新生成");
    // newer failed retry alongside the still-valid done report → warning banner
    expect(screen.getByTestId("d3-report-attempt-banner")).toBeInTheDocument();

    // failed report (no current, first failure) → retry button visible
    vi.mocked(getD3Report).mockResolvedValue(mockFailedReport);
    const selector = screen.getByRole("combobox");
    fireEvent.mouseDown(selector);
    fireEvent.click(screen.getByText(/代次.*2026-07-11/));
    // historical is read-only → button hidden; switch back to current to reload
    fireEvent.mouseDown(selector);
    fireEvent.click(screen.getByText("当前代次"));

    await waitFor(() => expect(screen.getByTestId("d3-generate-report")).toBeInTheDocument());
    expect(screen.getByTestId("d3-generate-report")).toHaveTextContent("重试生成报告");
  });

  it("shows regenerate-advice button when advice exists (done is not terminal)", async () => {
    // advice list present (done generation) → regenerate button visible
    vi.mocked(getD3Advice).mockResolvedValue({
      advice: [
        {
          advice_id: "a1",
          advice_type: "isolate",
          advice_text: "隔离库存",
          source_provenance: [{ source_type: "inventory", snapshot_id: null, record_key: "INV-1", stage: "llm_advice" }],
          target_batch_refs: null,
        },
      ],
      status: "done",
    });
    renderPanel();

    await waitFor(() => expect(screen.getByTestId("d3-generate-advice")).toBeInTheDocument());
    expect(screen.getByTestId("d3-generate-advice")).toHaveTextContent("重新生成建议");
  });
});

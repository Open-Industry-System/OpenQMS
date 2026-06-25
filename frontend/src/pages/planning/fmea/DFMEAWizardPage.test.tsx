import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent, act, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { App } from "antd";
import DFMEAWizardPage from "./DFMEAWizardPage";
import type { FMEADocument, GraphNode, GraphEdge } from "../../../types";

const mocks = vi.hoisted(() => ({
  getFMEA: vi.fn(),
  updateFMEA: vi.fn(),
  deleteFMEA: vi.fn(),
  getRecommendations: vi.fn(),
}));

vi.mock("../../../api/fmea", () => ({
  getFMEA: mocks.getFMEA,
  updateFMEA: mocks.updateFMEA,
  deleteFMEA: mocks.deleteFMEA,
}));

vi.mock("../../../api/recommendation", () => ({
  getRecommendations: mocks.getRecommendations,
}));

vi.mock("../../../hooks/usePermission", () => ({
  usePermission: () => ({ canView: () => true, canEdit: () => true, canApprove: () => true }),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => {
      // Step 0 ScopeTagField presets — must return empty containers or .filter crashes
      if (key === "wizard.scope.toolPresets") return [];
      if (key === "wizard.scope.trendPresets") return [];
      if (key === "wizard.scope.toolStructureMap") return {};
      // useDfmeaRules() calls t("dfmea") with returnObjects:true for several keys
      // These must be arrays/records or .map/.filter crashes in renderStep3
      if (key === "rules.verbPatterns") return [];
      if (key === "rules.failureChains") return [];
      if (key === "rules.defaultEffects") return [];
      if (key === "rules.defaultCauses") return [];
      if (key === "rules.fallbackPatterns") return [];
      if (key === "rules.measureBases") return {};
      if (key === "rules.modeSpecific") return {};
      if (key === "rules.modeRegex") return {};
      return key;
    },
  }),
}));

const node = (id: string, type: string, name = id): GraphNode => ({
  id, type, name, severity: 0, occurrence: 0, detection: 0,
});

function makeDoc(): FMEADocument {
  return {
    fmea_id: "fmea-1",
    document_no: "DFMEA-1",
    title: "DFMEA doc",
    fmea_type: "DFMEA",
    product_line_code: "DC-DC-100",
    status: "draft",
    version: 1,
    graph_data: {
      nodes: [node("func1", "ProcessStepFunction", "采集电压")],
      edges: [],
      wizardScope: { wizard_completed: true },
    },
    lock_version: 1,
    created_by: "u1",
    created_at: "2026-06-18T00:00:00Z",
    updated_at: "2026-06-18T00:00:00Z",
    approved_by: null,
    approved_at: null,
  };
}

function renderWizard() {
  return render(
    <App>
      <MemoryRouter initialEntries={["/fmea/fmea-1"]}>
        <Routes>
          <Route path="/fmea/:id" element={<DFMEAWizardPage />} />
        </Routes>
      </MemoryRouter>
    </App>
  );
}

async function goToStep3() {
  await screen.findByText("wizard.page.nextStep");
  for (let i = 0; i < 3; i++) {
    fireEvent.click(screen.getByText("wizard.page.nextStep"));
  }
}

const AI_RESPONSE = {
  suggestions: [{ name: "采集精度不足", confidence: 0.8, source: "llm" as const, explanation: "x" }],
  source: "hybrid" as const,
  cached: false,
  llm_available: true,
  graph_match_count: 0,
  effective_scope: "current_product_line" as const,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ shouldAdvanceTime: true });
  mocks.getFMEA.mockResolvedValue(makeDoc());
  mocks.updateFMEA.mockResolvedValue({});
  mocks.getRecommendations.mockResolvedValue(AI_RESPONSE);
});

async function typeAndWait(input: HTMLElement, value: string) {
  fireEvent.change(input, { target: { value } });
  await act(async () => { vi.advanceTimersByTime(600); });
  await waitFor(() => expect(mocks.getRecommendations).toHaveBeenCalled());
}

describe("DFMEAWizardPage sidebar step navigation on reopened draft", () => {
  it("allows jumping forward to a later sidebar step after loading a saved draft", async () => {
    // Draft has a function node → step 2 (Function Analysis) reached.
    // currentStep resets to 0 on load. The user should be able to click the
    // sidebar's step 3 to jump forward (previously blocked because the
    // session-only completedSteps ref was empty on reopen).
    renderWizard();
    await screen.findByText("wizard.page.nextStep");

    fireEvent.click(screen.getByText("wizard.steps.3"));

    await waitFor(() =>
      expect(screen.getByText("wizard.failure.addFailureMode")).toBeInTheDocument()
    );
  });
});

describe("DFMEAWizardPage Step 3 失效分析 — AI recommend wiring", () => {
  it("wires FM / FE / FC fields to the failure_mode / failure_effect / failure_cause triggers", async () => {
    renderWizard();
    await goToStep3();

    await waitFor(() => expect(screen.getByText("wizard.failure.addFailureMode")).toBeInTheDocument());
    fireEvent.click(screen.getByText("wizard.failure.addFailureMode"));

    const inputs = await screen.findAllByRole("textbox");
    expect(inputs.length).toBeGreaterThanOrEqual(3);

    mocks.getRecommendations.mockClear();
    await typeAndWait(inputs[0], "采集失");
    {
      const call = mocks.getRecommendations.mock.calls[0][1];
      expect(call.trigger_type).toBe("failure_mode");
      expect(call.context.function_description).toBe("采集电压");
      expect(typeof call.context.process_step).toBe("string");
    }

    mocks.getRecommendations.mockClear();
    await typeAndWait(inputs[1], "控制偏差");
    {
      const call = mocks.getRecommendations.mock.calls[0][1];
      expect(call.trigger_type).toBe("failure_effect");
      expect(call.context.function_description).toBe("采集电压");
      expect(typeof call.context.process_step).toBe("string");
    }

    mocks.getRecommendations.mockClear();
    await typeAndWait(inputs[2], "传感器故障");
    {
      const call = mocks.getRecommendations.mock.calls[0][1];
      expect(call.trigger_type).toBe("failure_cause");
      expect(call.context.function_description).toBe("采集电压");
      expect(typeof call.context.process_step).toBe("string");
    }
  });
});

// --- Step 5 (优化, 第六步) — redesigned per Reference/DFMEA.md ---

/** Graph with one AP=H failure chain: S=9 (effect), O=4 (cause), D=7 (DC) → H. */
function makeHighRiskDoc(): FMEADocument {
  const nodes: GraphNode[] = [
    node("func1", "ProcessStepFunction", "采集电压"),
    { ...node("fm1", "FailureMode", "采集失效") },
    { ...node("fe1", "FailureEffect", "数据错误"), severity: 9 },
    { ...node("fc1", "FailureCause", "传感器故障"), occurrence: 4 },
    { ...node("pc1", "PreventionControl", "现行预防") },
    { ...node("dc1", "DetectionControl", "现行探测"), detection: 7 },
  ];
  const edges: GraphEdge[] = [
    { source: "func1", target: "fm1", type: "HAS_FAILURE_MODE" },
    { source: "fm1", target: "fe1", type: "EFFECT_OF" },
    { source: "fc1", target: "fm1", type: "CAUSE_OF" },
    { source: "fc1", target: "pc1", type: "PREVENTED_BY" },
    { source: "fc1", target: "dc1", type: "DETECTED_BY" },
  ];
  return {
    ...makeDoc(),
    graph_data: { nodes, edges, wizardScope: { wizard_completed: true } },
  };
}

/** Graph with one AP=L failure chain (S=2,O=1,D=1) — reachable at step 5 but no H row. */
function makeLowRiskDoc(): FMEADocument {
  const nodes: GraphNode[] = [
    node("func1", "ProcessStepFunction", "采集电压"),
    node("fm1", "FailureMode", "采集失效"),
    { ...node("fe1", "FailureEffect", "数据错误"), severity: 2 },
    { ...node("fc1", "FailureCause", "传感器故障"), occurrence: 1 },
    node("pc1", "PreventionControl", "现行预防"),
    { ...node("dc1", "DetectionControl", "现行探测"), detection: 1 },
  ];
  const edges: GraphEdge[] = [
    { source: "func1", target: "fm1", type: "HAS_FAILURE_MODE" },
    { source: "fm1", target: "fe1", type: "EFFECT_OF" },
    { source: "fc1", target: "fm1", type: "CAUSE_OF" },
    { source: "fc1", target: "pc1", type: "PREVENTED_BY" },
    { source: "fc1", target: "dc1", type: "DETECTED_BY" },
  ];
  return {
    ...makeDoc(),
    graph_data: { nodes, edges, wizardScope: { wizard_completed: true } },
  };
}

async function goToStep5() {
  await screen.findByText("wizard.page.nextStep");
  fireEvent.click(screen.getByText("wizard.steps.5"));
}

/** Returns the input/textarea rendered inside the Field labeled `labelText`. */
function fieldInput(labelText: string): HTMLElement {
  const label = screen.getByText(labelText);
  const fieldDiv = label.parentElement!;
  return fieldDiv.querySelector("input, textarea") as HTMLElement;
}

/** Returns the container element of the Field labeled `labelText`. */
function fieldContainer(labelText: string): HTMLElement {
  const label = screen.getByText(labelText);
  return label.parentElement!;
}

describe("DFMEAWizardPage Step 5 优化 — redesigned per reference", () => {
  it("renders a red AP=H badge and the optimization field set for each H row", async () => {
    mocks.getFMEA.mockResolvedValue(makeHighRiskDoc());
    renderWizard();
    await goToStep5();

    // AP badge + failure mode name visible (addresses "看不到哪个 AP=H")
    expect(screen.getByText("wizard.optimization.apBadge")).toBeInTheDocument();
    expect(screen.getByText("采集失效")).toBeInTheDocument();

    // Reference optimization columns all present as Field labels
    for (const key of [
      "wizard.optimization.measure",
      "wizard.optimization.responsible",
      "wizard.optimization.dueDate",
      "wizard.optimization.status",
      "wizard.optimization.actionTaken",
      "wizard.optimization.completionDate",
      "wizard.optimization.revisedRatings",
      "wizard.optimization.revisedAp",
    ]) {
      expect(screen.getByText(key)).toBeInTheDocument();
    }
  });

  it("shows the no-optimization result when no row is AP=H", async () => {
    // Low-risk chain (AP=L) — step 5 is reachable but no H rows
    mocks.getFMEA.mockResolvedValue(makeLowRiskDoc());
    renderWizard();
    await goToStep5();

    expect(screen.getByText("wizard.optimization.noOptimization")).toBeInTheDocument();
  });

  it("creates a RecommendedAction node + OPTIMIZED_BY edge when typing an optimization measure", async () => {
    mocks.getFMEA.mockResolvedValue(makeHighRiskDoc());
    renderWizard();
    await goToStep5();

    mocks.updateFMEA.mockClear();
    const measure = fieldInput("wizard.optimization.measure");
    fireEvent.change(measure, { target: { value: "增加冗余传感器" } });
    await act(async () => { vi.advanceTimersByTime(600); });

    await waitFor(() => expect(mocks.updateFMEA).toHaveBeenCalled());
    const payload = mocks.updateFMEA.mock.calls[mocks.updateFMEA.mock.calls.length - 1][1];
    const gd = payload.graph_data;
    expect(gd.nodes.some((n: GraphNode) => n.type === "RecommendedAction" && n.name === "增加冗余传感器")).toBe(true);
    expect(gd.edges.some((e: GraphEdge) => e.type === "OPTIMIZED_BY")).toBe(true);
  });

  it("writes responsible / action_taken onto the RecommendedAction node", async () => {
    mocks.getFMEA.mockResolvedValue(makeHighRiskDoc());
    renderWizard();
    await goToStep5();

    // Create the RA node first by typing a measure
    fireEvent.change(fieldInput("wizard.optimization.measure"), { target: { value: "增加冗余传感器" } });
    await act(async () => { vi.advanceTimersByTime(600); });

    mocks.updateFMEA.mockClear();
    fireEvent.change(fieldInput("wizard.optimization.responsible"), { target: { value: "张工" } });
    await act(async () => { vi.advanceTimersByTime(600); });

    await waitFor(() => expect(mocks.updateFMEA).toHaveBeenCalled());
    const gd = mocks.updateFMEA.mock.calls[mocks.updateFMEA.mock.calls.length - 1][1].graph_data;
    const ra = gd.nodes.find((n: GraphNode) => n.type === "RecommendedAction");
    expect(ra?.responsible).toBe("张工");
  });

  it("computes AP after action from revised S/O/D ratings", async () => {
    mocks.getFMEA.mockResolvedValue(makeHighRiskDoc());
    renderWizard();
    await goToStep5();

    // Create the RA node
    fireEvent.change(fieldInput("wizard.optimization.measure"), { target: { value: "增加冗余传感器" } });
    await act(async () => { vi.advanceTimersByTime(600); });

    // Initial AP after action falls back to original S/O/D → H
    const revisedField = fieldContainer("wizard.optimization.revisedRatings");
    expect(within(revisedField).getByText("H")).toBeInTheDocument();

    // Set revised S'=5, O'=1, D'=1 → calculateAP(5,1,1) = L
    const numbers = within(revisedField).getAllByRole("spinbutton");
    fireEvent.change(numbers[0], { target: { value: "5" } });
    fireEvent.change(numbers[1], { target: { value: "1" } });
    fireEvent.change(numbers[2], { target: { value: "1" } });
    await act(async () => { vi.advanceTimersByTime(600); });

    await waitFor(() => expect(within(revisedField).getByText("L")).toBeInTheDocument());
  });
});

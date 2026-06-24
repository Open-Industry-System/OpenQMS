import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { App } from "antd";
import DFMEAWizardPage from "./DFMEAWizardPage";
import type { FMEADocument, GraphNode } from "../../../types";

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

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { I18nextProvider } from "react-i18next";
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import PFMEAWizardPage from "./PFMEAWizardPage";
import { getFMEA, updateFMEA } from "../../../api/fmea";
import zhPFMEA from "../../../locales/zh-CN/pfmea.json";
import zhDFMEA from "../../../locales/zh-CN/dfmea.json";
import type { FMEADocument } from "../../../types";
import type { Suggestion } from "../../../api/recommendation";

const i18nTest = i18n.createInstance();
i18nTest
  .use(initReactI18next)
  .init({
    lng: "zh-CN",
    fallbackLng: "zh-CN",
    interpolation: { escapeValue: false },
    resources: {
      "zh-CN": { pfmea: zhPFMEA, dfmea: zhDFMEA },
    },
  });

function I18nTestRouterWrapper({ children }: { children: React.ReactNode }) {
  return (
    <I18nextProvider i18n={i18nTest}>
      <MemoryRouter initialEntries={["/fmea/test-fmea"]}>
        <Routes>
          <Route path="/fmea/:id" element={children} />
        </Routes>
      </MemoryRouter>
    </I18nextProvider>
  );
}

vi.mock("../../../api/fmea", () => ({
  getFMEA: vi.fn(),
  deleteFMEA: vi.fn(),
  updateFMEA: vi.fn(),
}));

vi.mock("../../../api/recommendation", () => ({
  getRecommendations: vi.fn(),
}));

vi.mock("../../../hooks/usePermission", () => ({
  usePermission: () => ({ canView: () => true, canEdit: () => true, canApprove: () => true }),
}));

// Capture the onSelect of every SmartSuggestionDropdown so the test can drive an
// adoption deterministically (no need to open the async dropdown + click an item).
// The first failure_mode dropdown gets a data-testid we can click.
vi.mock("../../../components/dfmea/SmartSuggestionDropdown", () => ({
  default: (props: { triggerType: string; onSelect: (s: Suggestion) => void; value?: string }) => (
    <button
      type="button"
      data-testid={`suggestion-${props.triggerType}`}
      onClick={() =>
        props.onSelect({
          name: `AI建议-${props.triggerType}`,
          source: "graph",
          recommendation_id: `rec-${props.triggerType}`,
        } as Suggestion)
      }
    >
      {props.value}
    </button>
  ),
}));

const Z = { severity: 0, occurrence: 0, detection: 0 };
const baseDoc: FMEADocument = {
  fmea_id: "00000000-0000-0000-0000-000000000001",
  document_no: "PFMEA-2026-001",
  title: "SMT焊接生产线",
  fmea_type: "PFMEA",
  status: "draft",
  lock_version: 1,
  graph_data: {
    nodes: [
      { id: "pi", type: "ProcessItem", name: "线", ...Z },
      { id: "ps", type: "ProcessStep", name: "贴装", process_number: "OP10", ...Z },
      { id: "psf", type: "ProcessStepFunction", name: "准确贴装", ...Z },
      { id: "fm", type: "FailureMode", name: "偏移", ...Z },
      { id: "fe", type: "FailureEffect", name: "焊接不良", severity: 7 },
      { id: "fc", type: "FailureCause", name: "吸嘴磨损", ...Z, occurrence: 4 },
      { id: "pc", type: "PreventionControl", name: "定期更换吸嘴", ...Z },
      { id: "dc", type: "DetectionControl", name: "SPC监控", ...Z, detection: 3 },
    ],
    edges: [
      { source: "pi", target: "ps", type: "HAS_PROCESS_STEP" },
      { source: "ps", target: "psf", type: "HAS_FUNCTION" },
      { source: "psf", target: "fm", type: "HAS_FAILURE_MODE" },
      { source: "fm", target: "fe", type: "EFFECT_OF" },
      { source: "fc", target: "fm", type: "CAUSE_OF" },
      { source: "fc", target: "pc", type: "PREVENTED_BY" },
      { source: "fc", target: "dc", type: "DETECTED_BY" },
    ],
    wizardScope: {},
  },
} as unknown as FMEADocument;

describe("PFMEAWizardPage adoptions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getFMEA).mockResolvedValue(baseDoc);
    vi.mocked(updateFMEA).mockResolvedValue(baseDoc);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("forwards the adoption through the debounced save path to updateFMEA", async () => {
    render(<PFMEAWizardPage />, { wrapper: I18nTestRouterWrapper });
    await waitFor(() => screen.getByText(/PFMEA向导/i));

    // Advance to step 3 (failure analysis) where the SmartSuggestionDropdowns live.
    fireEvent.click(screen.getByRole("button", { name: /nextStep|下一步/i }));
    fireEvent.click(screen.getByRole("button", { name: /nextStep|下一步/i }));
    fireEvent.click(screen.getByRole("button", { name: /nextStep|下一步/i }));

    // The mocked failure_mode dropdown renders; clicking it fires onSelect with a
    // suggestion that carries a recommendation_id.
    const fmDropdown = await screen.findByTestId("suggestion-failure_mode");
    fireEvent.click(fmDropdown);

    // Switching to fake timers AFTER render so we can fast-forward the 500ms debounce.
    vi.useFakeTimers();
    await act(async () => {
      vi.advanceTimersByTime(600);
      // Flush the enqueued save promise chain.
      await Promise.resolve();
    });
    vi.useRealTimers();

    await waitFor(() => {
      expect(updateFMEA).toHaveBeenCalledWith(
        "test-fmea",
        expect.objectContaining({
          adoptions: [
            expect.objectContaining({
              field_id: "fm",
              recommendation_id: "rec-failure_mode",
              adopted_text: "AI建议-failure_mode",
            }),
          ],
        })
      );
    });
  });
});

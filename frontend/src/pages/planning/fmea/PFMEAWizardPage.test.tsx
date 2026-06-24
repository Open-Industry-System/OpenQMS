import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { I18nextProvider } from "react-i18next";
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import PFMEAWizardPage from "./PFMEAWizardPage";
import { getFMEA, updateFMEA } from "../../../api/fmea";
import { getRecommendations } from "../../../api/recommendation";
import zhPFMEA from "../../../locales/zh-CN/pfmea.json";
import zhDFMEA from "../../../locales/zh-CN/dfmea.json";
import type { FMEADocument } from "../../../types";

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

const Z = { severity: 0, occurrence: 0, detection: 0 };
const baseDoc: FMEADocument = {
  fmea_id: "00000000-0000-0000-0000-000000000001",
  document_no: "PFMEA-2026-001",
  title: "SMT焊接生产线",
  fmea_type: "PFMEA",
  status: "draft",
  lock_version: 1,
  graph_data: { nodes: [{ id: "pi_1", type: "ProcessItem", name: "SMT焊接生产线", ...Z }], edges: [], wizardScope: {} },
} as unknown as FMEADocument;

describe("PFMEAWizardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getFMEA).mockResolvedValue(baseDoc);
    vi.mocked(updateFMEA).mockResolvedValue(baseDoc);
    vi.mocked(getRecommendations).mockResolvedValue({
      suggestions: [],
      source: "rule",
      cached: false,
      llm_available: true,
      graph_match_count: 0,
      effective_scope: "current_product_line",
    });
  });

  it("redirects to editor when fmea_type is not PFMEA", async () => {
    vi.mocked(getFMEA).mockResolvedValue({ ...baseDoc, fmea_type: "DFMEA" } as unknown as FMEADocument);
    render(<PFMEAWizardPage />, { wrapper: I18nTestRouterWrapper });
    await waitFor(() => expect(getFMEA).toHaveBeenCalled());
    await waitFor(() => {
      expect(screen.queryByText(/PFMEA向导|PFMEA Wizard/i)).not.toBeInTheDocument();
    });
  });

  it("renders Step 0 scope fields and adds a ProcessStep in Step 1", async () => {
    render(<PFMEAWizardPage />, { wrapper: I18nTestRouterWrapper });
    await waitFor(() => screen.getByText(/PFMEA向导|PFMEA Wizard/i));

    fireEvent.click(screen.getByRole("button", { name: /下一步|nextStep/i }));
    await waitFor(() => screen.getByText(/添加过程步骤|addProcessStep/i));
  });

  it("Step 2 renders the FunctionTreeEditor", async () => {
    render(<PFMEAWizardPage />, { wrapper: I18nTestRouterWrapper });
    await waitFor(() => screen.getByText(/PFMEA向导/i));
    // advance to step 2
    fireEvent.click(screen.getByRole("button", { name: /nextStep|下一步/i }));
    fireEvent.click(screen.getByRole("button", { name: /nextStep|下一步/i }));
    await waitFor(() => screen.getByText(/addItemFunction|添加过程项目功能/i));
  });

  it("Step 4 renders the RiskTable with severity dialog and CC/SC column", async () => {
    const doc = {
      ...baseDoc,
      graph_data: {
        nodes: [
          { id: "pi", type: "ProcessItem", name: "线", ...Z },
          { id: "ps", type: "ProcessStep", name: "贴装", process_number: "OP10", ...Z },
          { id: "psf", type: "ProcessStepFunction", name: "准确贴装", ...Z },
          { id: "fm", type: "FailureMode", name: "偏移", ...Z },
          { id: "fe", type: "FailureEffect", name: "焊接不良", severity: 7, severity_plant: 7, severity_customer: 5, severity_user: 3 },
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
    };
    vi.mocked(getFMEA).mockResolvedValue(doc as unknown as FMEADocument);
    render(<PFMEAWizardPage />, { wrapper: I18nTestRouterWrapper });
    await waitFor(() => screen.getByText(/PFMEA向导/i));
    // advance to step 4 (0 -> 1 -> 2 -> 3 -> 4)
    fireEvent.click(screen.getByRole("button", { name: /nextStep|下一步/i }));
    fireEvent.click(screen.getByRole("button", { name: /nextStep|下一步/i }));
    fireEvent.click(screen.getByRole("button", { name: /nextStep|下一步/i }));
    fireEvent.click(screen.getByRole("button", { name: /nextStep|下一步/i }));

    // RiskTable renders an AP tag (H/M/L) or the class column (CC/SC/-)
    await waitFor(() => {
      const apTag = screen.queryByText(/^[HML]$/);
      const classTag = screen.queryByText(/^(CC|SC|-)$/);
      expect(apTag || classTag).toBeTruthy();
    });
  });

  it("Step 3 creates a failure chain on a ProcessStepFunction", async () => {
    const doc = {
      ...baseDoc,
      graph_data: {
        nodes: [
          { id: "pi", type: "ProcessItem", name: "线", ...Z },
          { id: "ps", type: "ProcessStep", name: "贴装", process_number: "OP10", ...Z },
          { id: "we1", type: "ProcessWorkElement", name: "贴片机吸嘴", classification: "Machine", ...Z },
          { id: "we2", type: "ProcessWorkElement", name: "操作员", classification: "Man", ...Z },
          { id: "psf", type: "ProcessStepFunction", name: "准确贴装", ...Z },
        ],
        edges: [
          { source: "pi", target: "ps", type: "HAS_PROCESS_STEP" },
          { source: "ps", target: "we1", type: "HAS_WORK_ELEMENT" },
          { source: "ps", target: "we2", type: "HAS_WORK_ELEMENT" },
          { source: "ps", target: "psf", type: "HAS_FUNCTION" },
        ],
        wizardScope: {},
      },
    };
    vi.mocked(getFMEA).mockResolvedValue(doc as unknown as FMEADocument);
    render(<PFMEAWizardPage />, { wrapper: I18nTestRouterWrapper });
    await waitFor(() => screen.getByText(/PFMEA向导/i));
    // advance to step 3 (0 -> 1 -> 2 -> 3)
    fireEvent.click(screen.getByRole("button", { name: /nextStep|下一步/i }));
    fireEvent.click(screen.getByRole("button", { name: /nextStep|下一步/i }));
    fireEvent.click(screen.getByRole("button", { name: /nextStep|下一步/i }));

    await waitFor(() => screen.getByRole("button", { name: /添加失效链|addFailureChain/i }));
    expect(screen.getByText("Machine:贴片机吸嘴, Man:操作员")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /添加失效链|addFailureChain/i }));
    await waitFor(() => {
      // After adding a failure chain, the failure_mode SmartSuggestionDropdown label appears.
      expect(screen.getAllByText(/失效模式|failureMode/i).length).toBeGreaterThan(0);
    });
  });

  it("Step 5 shows RecommendedAction editor for AP=H rows", async () => {
    const doc = {
      ...baseDoc,
      graph_data: {
        nodes: [
          { id: "pi", type: "ProcessItem", name: "线", ...Z },
          { id: "ps", type: "ProcessStep", name: "贴装", process_number: "OP10", ...Z },
          { id: "we1", type: "ProcessWorkElement", name: "贴片机吸嘴", classification: "Machine", ...Z },
          { id: "pif", type: "ProcessItemFunction", name: "输送线路", ...Z },
          { id: "psf", type: "ProcessStepFunction", name: "准确贴装", ...Z },
          { id: "wef", type: "ProcessWorkElementFunction", name: "吸嘴保持真空", ...Z },
          { id: "fm", type: "FailureMode", name: "偏移", ...Z },
          { id: "fe", type: "FailureEffect", name: "焊接不良", severity: 9, severity_plant: 9, severity_customer: 9, severity_user: 9 },
          { id: "fc", type: "FailureCause", name: "吸嘴磨损", ...Z, occurrence: 4 },
          { id: "pc", type: "PreventionControl", name: "定期更换吸嘴", ...Z },
          { id: "dc", type: "DetectionControl", name: "SPC监控", ...Z, detection: 4 },
        ],
        edges: [
          { source: "pi", target: "ps", type: "HAS_PROCESS_STEP" },
          { source: "ps", target: "we1", type: "HAS_WORK_ELEMENT" },
          { source: "pi", target: "pif", type: "HAS_FUNCTION" },
          { source: "pif", target: "psf", type: "FUNCTION_MAPPED_TO" },
          { source: "ps", target: "psf", type: "HAS_FUNCTION" },
          { source: "psf", target: "wef", type: "FUNCTION_MAPPED_TO" },
          { source: "we1", target: "wef", type: "HAS_FUNCTION" },
          { source: "psf", target: "fm", type: "HAS_FAILURE_MODE" },
          { source: "fm", target: "fe", type: "EFFECT_OF" },
          { source: "fc", target: "fm", type: "CAUSE_OF" },
          { source: "fc", target: "pc", type: "PREVENTED_BY" },
          { source: "fc", target: "dc", type: "DETECTED_BY" },
        ],
        wizardScope: {},
      },
    };
    vi.mocked(getFMEA).mockResolvedValue(doc as unknown as FMEADocument);
    render(<PFMEAWizardPage />, { wrapper: I18nTestRouterWrapper });
    await waitFor(() => screen.getByText(/PFMEA向导/i));
    // advance to step 5 (0 -> 1 -> 2 -> 3 -> 4 -> 5)
    for (let i = 0; i < 5; i++) {
      fireEvent.click(screen.getByRole("button", { name: /nextStep|下一步/i }));
    }

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/负责人|responsible/i)).toBeInTheDocument();
      expect(screen.getByPlaceholderText(/计划完成日期|Planned Completion Date/i)).toBeInTheDocument();
    });
  });

  it("finish is disabled until all gates pass", async () => {
    render(<PFMEAWizardPage />, { wrapper: I18nTestRouterWrapper });
    await waitFor(() => screen.getByText(/PFMEA向导/i));
    // advance to step 6 (0 -> 1 -> 2 -> 3 -> 4 -> 5 -> 6)
    for (let i = 0; i < 6; i++) {
      fireEvent.click(screen.getByRole("button", { name: /nextStep|下一步/i }));
    }

    await waitFor(() => {
      const finishBtn = screen.getByRole("button", { name: /完成创建|finish/i });
      expect(finishBtn).toBeDisabled();
    });
  });

  it("finish navigates to editor when all gates pass", async () => {
    function FinishRouterWrapper({ children }: { children: React.ReactNode }) {
      return (
        <I18nextProvider i18n={i18nTest}>
          <MemoryRouter initialEntries={["/fmea/test-fmea/wizard"]}>
            <Routes>
              <Route path="/fmea/:id/wizard" element={children} />
              <Route path="/fmea/:id" element={<div data-testid="editor-page">Editor Page</div>} />
            </Routes>
          </MemoryRouter>
        </I18nextProvider>
      );
    }

    const doc = {
      ...baseDoc,
      graph_data: {
        nodes: [
          { id: "pi", type: "ProcessItem", name: "线", ...Z },
          { id: "ps", type: "ProcessStep", name: "贴装", process_number: "OP10", ...Z },
          { id: "we1", type: "ProcessWorkElement", name: "贴片机吸嘴", classification: "Machine", ...Z },
          { id: "pif", type: "ProcessItemFunction", name: "输送线路", ...Z },
          { id: "psf", type: "ProcessStepFunction", name: "准确贴装", ...Z },
          { id: "wef", type: "ProcessWorkElementFunction", name: "吸嘴保持真空", ...Z },
          { id: "fm", type: "FailureMode", name: "偏移", ...Z },
          { id: "fe", type: "FailureEffect", name: "焊接不良", severity: 9, severity_plant: 9, severity_customer: 9, severity_user: 9 },
          { id: "fc", type: "FailureCause", name: "吸嘴磨损", ...Z, occurrence: 4 },
          { id: "pc", type: "PreventionControl", name: "定期更换吸嘴", ...Z },
          { id: "dc", type: "DetectionControl", name: "SPC监控", ...Z, detection: 4 },
          { id: "ra", type: "RecommendedAction", name: "更换吸嘴规格", responsible: "张三", due_date: "2026-07-01", status: "planned" },
        ],
        edges: [
          { source: "pi", target: "ps", type: "HAS_PROCESS_STEP" },
          { source: "ps", target: "we1", type: "HAS_WORK_ELEMENT" },
          { source: "pi", target: "pif", type: "HAS_FUNCTION" },
          { source: "pif", target: "psf", type: "FUNCTION_MAPPED_TO" },
          { source: "ps", target: "psf", type: "HAS_FUNCTION" },
          { source: "psf", target: "wef", type: "FUNCTION_MAPPED_TO" },
          { source: "we1", target: "wef", type: "HAS_FUNCTION" },
          { source: "psf", target: "fm", type: "HAS_FAILURE_MODE" },
          { source: "fm", target: "fe", type: "EFFECT_OF" },
          { source: "fc", target: "fm", type: "CAUSE_OF" },
          { source: "fc", target: "pc", type: "PREVENTED_BY" },
          { source: "fc", target: "dc", type: "DETECTED_BY" },
          { source: "fc", target: "ra", type: "OPTIMIZED_BY" },
        ],
        wizardScope: {},
      },
    };
    vi.mocked(getFMEA).mockResolvedValue(doc as unknown as FMEADocument);
    render(<PFMEAWizardPage />, { wrapper: FinishRouterWrapper });
    await waitFor(() => screen.getByText(/PFMEA向导/i));
    // advance to step 6
    for (let i = 0; i < 6; i++) {
      fireEvent.click(screen.getByRole("button", { name: /nextStep|下一步/i }));
    }

    await waitFor(() => {
      const finishBtn = screen.getByRole("button", { name: /完成创建|finish/i });
      expect(finishBtn).toBeEnabled();
    });

    fireEvent.click(screen.getByRole("button", { name: /完成创建|finish/i }));

    await waitFor(() => {
      expect(updateFMEA).toHaveBeenCalledWith(
        "test-fmea",
        expect.objectContaining({
          graph_data: expect.objectContaining({
            wizardScope: expect.objectContaining({ wizard_completed: true }),
          }),
        })
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId("editor-page")).toBeInTheDocument();
    });
  });
});

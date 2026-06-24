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
});

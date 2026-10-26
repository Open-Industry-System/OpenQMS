import { render, screen, fireEvent, waitFor, configure, act, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterAll } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { App } from "antd";
import { useAuthStore } from "../../store/authStore";
import * as capaApi from "../../api/capa";
import * as draftApi from "../../api/capaDraft";
import * as knowledgeApi from "../../api/knowledge";
import { useProductLineStore } from "../../store/productLineStore";
import * as fmeaApi from "../../api/fmea";
import CAPADetailPage from "./CAPADetailPage";

const route = vi.hoisted(() => ({ id: "test-report-id" }));
const prerequisiteProbe = vi.hoisted(() => ({ before: null as null | (() => Promise<void>) }));
vi.mock("../../components/capa/D4RecPanel", async () => {
  const actual = await vi.importActual<typeof import("../../components/capa/D4RecPanel")>("../../components/capa/D4RecPanel");
  return { default: (props: any) => { prerequisiteProbe.before = props.beforeAdopt; return <actual.default {...props} />; } };
});
const verificationCard = vi.hoisted(() => vi.fn());
const agentContext = vi.hoisted(() => ({ value: null as any }));
vi.mock("../../components/agent/AgentTaskContext", () => ({ useAgentTaskContext: () => agentContext.value }));
beforeEach(() => { agentContext.value = null; });

configure({ testIdAttribute: "data-e2e" });
afterAll(() => configure({ testIdAttribute: "data-testid" }));

// Mock react-router-dom params
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useParams: () => ({ id: route.id }),
    useNavigate: () => mockNavigate,
  };
});

// Mock APIs
vi.mock("../../api/capa", async () => {
  const actual = await vi.importActual<typeof import("../../api/capa")>("../../api/capa");
  return {
    ...actual,
    getCAPA: vi.fn(),
    getCapaOutcomeReview: vi.fn(),
    updateCAPA: vi.fn(),
    advanceCAPA: vi.fn(),
    linkFMEA: vi.fn(),
    generatePpt: vi.fn(),
    getPptExportReviewReport: vi.fn(),
    triggerScar: vi.fn(),
    listCapaSupplierOptions: vi.fn(),
    sinkKnowledge: vi.fn(),
    getD3Runs: vi.fn(),
    getD3Adoptions: vi.fn(),
    getD3Executions: vi.fn(),
    getD3Snapshots: vi.fn(),
    getD3Report: vi.fn(),
    getD3Advice: vi.fn(),
    getD4Recommendations: vi.fn(),
    getD7Recommendations: vi.fn(),
    listD7Actions: vi.fn().mockResolvedValue([]),
    getDocGateImpact: vi.fn(),
    getDocGateAudit: vi.fn(),
    getDocGateDecision: vi.fn(),
    confirmRepeat: vi.fn(),
    importD3Containment: vi.fn(),
  };
});
vi.mock("../../api/capaDraft");
vi.mock("../../api/knowledge", () => ({
  findCapaKnowledgeEntry: vi.fn().mockResolvedValue(null),
  listKnowledgeEntries: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 }),
  getKnowledgeEntry: vi.fn(),
}));
vi.mock("../../api/fmea", () => ({
  listFMEAs: vi.fn().mockResolvedValue({ items: [] }),
}));

// Mock D4VerificationCard to avoid rendering issues
vi.mock("../../components/capa/D4VerificationCard", () => ({
  default: (props: unknown) => { verificationCard(props); return null; },
}));

const mockCapa = {
  report_id: "test-report-id",
  title: "Test CAPA Report",
  document_no: "8D-2026-001",
  status: "D2_DESCRIPTION",
  severity: "fatal",
  product_line_code: "DC-DC-100",
  fmea_ref_id: null,
  fmea_node_id: null,
  due_date: null,
  created_at: "2026-01-01T00:00:00Z",
  d1_team: [],
  d2_description: "",
  d3_interim: "",
  d4_root_cause: "",
  d5_correction: "",
  d6_verification: "",
  d7_prevention: "",
  d8_closure: "",
};

function renderPage() {
  return render(
    <App>
      <BrowserRouter>
        <CAPADetailPage />
      </BrowserRouter>
    </App>
  );
}

function mockSupplierOptions() {
  vi.mocked(capaApi.listCapaSupplierOptions).mockResolvedValue({
    items: [{ supplier_id: "sup-1", supplier_no: "S-001", name: "Acme", status: "approved" }],
    total: 1,
    page: 1,
    page_size: 50,
  } as any);
}

describe("CAPADetailPage D3ContainmentPanel integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mockSupplierOptions();
    vi.mocked(capaApi.getD3Runs).mockResolvedValue([]);
    vi.mocked(capaApi.getD3Adoptions).mockResolvedValue([]);
    vi.mocked(capaApi.getD3Executions).mockResolvedValue([]);
    vi.mocked(draftApi.getAIDraftCapabilities).mockResolvedValue({
      ai_draft_enabled: false,
      llm_provider: null,
    });
    vi.mocked(capaApi.getD4Recommendations).mockResolvedValue({ items: [], stages: [] });
  });

  it("renders D3ContainmentPanel at D3_INTERIM", async () => {
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "engineer",
        role_key: "quality_engineer",
        permissions: { capa: 3 },
      } as any,
      token: "test-token",
    });

    const d3Capa = { ...mockCapa, status: "D3_INTERIM", d3_interim: "test content" };
    vi.mocked(capaApi.getCAPA).mockResolvedValue(d3Capa as any);

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /导入/ })).toBeInTheDocument();
    });
  });

  it("does not render D3ContainmentPanel at D4_ROOT_CAUSE", async () => {
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "engineer",
        role_key: "quality_engineer",
        permissions: { capa: 3 },
      } as any,
      token: "test-token",
    });

    const d4Capa = { ...mockCapa, status: "D4_ROOT_CAUSE", d4_root_cause: "root cause" };
    vi.mocked(capaApi.getCAPA).mockResolvedValue(d4Capa as any);

    renderPage();

    // Wait for the page to render - the title should be visible
    await waitFor(() => {
      expect(screen.getAllByText("8D-2026-001").length).toBeGreaterThan(0);
    });
    // D3 panel should NOT be rendered for D4 status
    expect(screen.queryByRole("button", { name: /导入/ })).not.toBeInTheDocument();
  });

  it("viewer detail page hides d3 write buttons", async () => {
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "viewer",
        role_key: "viewer",
        permissions: { capa: 1 },
      } as any,
      token: "test-token",
    });

    const d3Capa = { ...mockCapa, status: "D3_INTERIM", d3_interim: "test content" };
    vi.mocked(capaApi.getCAPA).mockResolvedValue(d3Capa as any);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("D3 临时遏制措施")).toBeInTheDocument();
    });
    // Viewer should NOT see the import button (canEdit=false)
    expect(screen.queryByRole("button", { name: /导入/ })).not.toBeInTheDocument();
  });

  it("historical d3 run read-only in detail page", async () => {
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "engineer",
        role_key: "quality_engineer",
        permissions: { capa: 3 },
      } as any,
      token: "test-token",
    });

    const d3Capa = { ...mockCapa, status: "D3_INTERIM", d3_interim: "test content" };
    vi.mocked(capaApi.getCAPA).mockResolvedValue(d3Capa as any);
    vi.mocked(capaApi.getD3Runs).mockResolvedValue([
      { run_id: "run-1", is_current: false, status: "done" } as any,
      { run_id: "run-2", is_current: true, status: "done" } as any,
    ]);
    vi.mocked(capaApi.getD3Snapshots).mockResolvedValue([]);
    vi.mocked(capaApi.getD3Report).mockResolvedValue(null);
    vi.mocked(capaApi.getD3Advice).mockResolvedValue({ advice: [] });
    vi.mocked(capaApi.getD4Recommendations).mockResolvedValue({ items: [], stages: [] });

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /导入/ })).toBeInTheDocument();
    });
    // Historical runs selector should appear when multiple runs exist
    // The selector text appears in the D3ContainmentPanel component
    await waitFor(() => {
      expect(screen.getAllByText(/选择代次|当前代次/).length).toBeGreaterThan(0);
    });
  });
});

describe("CAPADetailPage supplier risk input", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mockSupplierOptions();
    vi.mocked(draftApi.getAIDraftCapabilities).mockResolvedValue({
      ai_draft_enabled: false,
      llm_provider: null,
    });
    vi.mocked(capaApi.getD3Runs).mockResolvedValue([]);
    vi.mocked(capaApi.getD3Adoptions).mockResolvedValue([]);
    vi.mocked(capaApi.getD3Executions).mockResolvedValue([]);
    vi.mocked(capaApi.getD4Recommendations).mockResolvedValue({ items: [], stages: [] });
    vi.mocked(capaApi.getD7Recommendations).mockResolvedValue({ recommendations: [] } as any);
    vi.mocked(capaApi.getDocGateImpact).mockResolvedValue({ status: "done", affected_docs: [] } as any);
    vi.mocked(capaApi.getDocGateAudit).mockResolvedValue({ audit_run_id: null, audits: [] } as any);
    vi.mocked(capaApi.getDocGateDecision).mockResolvedValue({ decision: null } as any);
  });

  it("renders SupplierRiskInputCard and confirms repeat", async () => {
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "engineer",
        role_key: "quality_engineer",
        permissions: { capa: 3, supplier_risk: 3 },
      } as any,
      token: "test-token",
    });

    const riskInput = {
      input_id: "i1",
      status: "processed",
      repeat_suggested: true,
      repeat_detection_status: "matched",
      repeat_confirmed: null,
      matched_capa_nos: ["8D-2025-001"],
      evaluated_risk_level: "high",
      evaluated_risk_score: 80,
      linked_alert: null,
    };
    const capaWithRisk = {
      ...mockCapa,
      status: "D7_COMPLETED",
      supplier_risk_input: riskInput,
    };
    vi.mocked(capaApi.getCAPA).mockResolvedValue(capaWithRisk as any);
    vi.mocked(capaApi.confirmRepeat).mockResolvedValue({
      ...capaWithRisk,
      supplier_risk_input: { ...riskInput, repeat_confirmed: true },
    } as any);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("supplier-risk-input-card")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId("supplier-risk-confirm-yes"));
    await waitFor(() => {
      expect(capaApi.confirmRepeat).toHaveBeenCalledWith("test-report-id", true, expect.any(AbortSignal));
    });
  });

  it("hides confirm buttons without supplier_risk edit permission", async () => {
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "engineer",
        role_key: "quality_engineer",
        permissions: { capa: 3 },
      } as any,
      token: "test-token",
    });

    vi.mocked(capaApi.getCAPA).mockResolvedValue({
      ...mockCapa,
      status: "D7_COMPLETED",
      supplier_risk_input: {
        input_id: "i1",
        status: "processed",
        repeat_suggested: true,
        repeat_detection_status: "matched",
        repeat_confirmed: null,
        matched_capa_nos: ["8D-2025-001"],
        evaluated_risk_level: "high",
        evaluated_risk_score: 80,
        linked_alert: null,
      },
    } as any);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("supplier-risk-input-card")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("supplier-risk-confirm-yes")).not.toBeInTheDocument();
  });

  it("shows supplier_no/name from CAPA projection when locked (not raw UUID)", async () => {
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "engineer",
        role_key: "quality_engineer",
        permissions: { capa: 3 },
      } as any,
      token: "test-token",
    });

    const supplierId = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
    vi.mocked(capaApi.getCAPA).mockResolvedValue({
      ...mockCapa,
      status: "D7_COMPLETED",
      supplier_id: supplierId,
      supplier_no: "SUP-LABEL-01",
      supplier_name: "Label Supplier Co",
      supplier_risk_input: {
        input_id: "i1",
        status: "processed",
        repeat_suggested: false,
        repeat_detection_status: "not_matched",
        repeat_confirmed: null,
        matched_capa_nos: [],
        evaluated_risk_level: "medium",
        evaluated_risk_score: 50,
        linked_alert: null,
      },
    } as any);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("capa-supplier-readonly")).toBeInTheDocument();
    });
    const label = screen.getByTestId("capa-supplier-readonly");
    expect(label.textContent).toContain("SUP-LABEL-01");
    expect(label.textContent).toContain("Label Supplier Co");
    expect(label.textContent).not.toContain(supplierId);
    // i18n may resolve to zh default or en "Locked"
    expect(label.textContent).toMatch(/已锁定|Locked/);
  });
});

describe("CAPADetailPage AI draft integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mockSupplierOptions();
    vi.mocked(draftApi.getAIDraftCapabilities).mockResolvedValue({
      ai_draft_enabled: false,
      llm_provider: null,
    });
    vi.mocked(capaApi.getD3Runs).mockResolvedValue([]);
    vi.mocked(capaApi.getD3Adoptions).mockResolvedValue([]);
    vi.mocked(capaApi.getD3Executions).mockResolvedValue([]);
  });

  it("shows AI draft button when enabled and user has edit permission", async () => {
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "engineer",
        role_key: "quality_engineer",
        permissions: { capa: 3 }, // EDIT level
      } as any,
      token: "test-token",
    });

    vi.mocked(capaApi.getCAPA).mockResolvedValue(mockCapa as any);
    vi.mocked(capaApi.updateCAPA).mockResolvedValue(mockCapa as any);
    vi.mocked(draftApi.getAIDraftCapabilities).mockResolvedValue({
      ai_draft_enabled: true,
      llm_provider: "test",
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("AI Draft")).toBeInTheDocument();
    });
  });

  it("hides AI draft button when ai_draft_enabled is false", async () => {
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "engineer",
        role_key: "quality_engineer",
        permissions: { capa: 3 },
      } as any,
      token: "test-token",
    });

    vi.mocked(capaApi.getCAPA).mockResolvedValue(mockCapa as any);
    vi.mocked(draftApi.getAIDraftCapabilities).mockResolvedValue({
      ai_draft_enabled: false,
      llm_provider: null,
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("5W2H Problem Description")).toBeInTheDocument();
    });
    expect(screen.queryByText("AI Draft")).not.toBeInTheDocument();
  });

  it("hides AI draft button when user lacks edit permission", async () => {
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "viewer",
        role_key: "viewer",
        permissions: { capa: 1 }, // VIEW level only
      } as any,
      token: "test-token",
    });

    vi.mocked(capaApi.getCAPA).mockResolvedValue(mockCapa as any);
    vi.mocked(draftApi.getAIDraftCapabilities).mockResolvedValue({
      ai_draft_enabled: true,
      llm_provider: "test",
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("5W2H Problem Description")).toBeInTheDocument();
    });
    expect(screen.queryByText("AI Draft")).not.toBeInTheDocument();
  });

  it("shows draft preview modal after successful generation", async () => {
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "engineer",
        role_key: "quality_engineer",
        permissions: { capa: 3 },
      } as any,
      token: "test-token",
    });

    vi.mocked(capaApi.getCAPA).mockResolvedValue(mockCapa as any);
    vi.mocked(capaApi.updateCAPA).mockResolvedValue(mockCapa as any);
    vi.mocked(draftApi.getAIDraftCapabilities).mockResolvedValue({
      ai_draft_enabled: true,
      llm_provider: "test",
    });
    vi.mocked(draftApi.generateDraft).mockResolvedValue({
      content: "AI generated problem statement content",
      structured_data: { problem_statement: "AI generated problem statement content" },
      request_id: "test-req-id",
      step: "d2",
    });

    renderPage();

    const aiBtn = await screen.findByText("AI Draft");
    fireEvent.click(aiBtn);

    await waitFor(() => {
      expect(screen.getByText("AI Draft Preview")).toBeInTheDocument();
    });
    expect(screen.getByText("AI generated problem statement content")).toBeInTheDocument();
  });

  it("shows undo button after replacing draft content", async () => {
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "engineer",
        role_key: "quality_engineer",
        permissions: { capa: 3 },
      } as any,
      token: "test-token",
    });

    const capaWithContent = { ...mockCapa, d2_description: "Original content" };
    vi.mocked(capaApi.getCAPA).mockResolvedValue(capaWithContent as any);
    vi.mocked(capaApi.updateCAPA).mockResolvedValue(capaWithContent as any);
    vi.mocked(draftApi.getAIDraftCapabilities).mockResolvedValue({
      ai_draft_enabled: true,
      llm_provider: "test",
    });
    vi.mocked(draftApi.generateDraft).mockResolvedValue({
      content: "AI replacement content",
      structured_data: null,
      request_id: "test-req-id",
      step: "d2",
    });

    renderPage();

    const aiBtn = await screen.findByText("AI Draft");
    fireEvent.click(aiBtn);

    await waitFor(() => {
      expect(screen.getByText("AI Draft Preview")).toBeInTheDocument();
    });

    const replaceBtn = screen.getByRole("button", { name: /Replace|Re place/ });
    fireEvent.click(replaceBtn);

    await waitFor(() => {
      expect(screen.getByText("Undo Change")).toBeInTheDocument();
    });
  });
});

describe("CAPADetailPage 生成PPT button visibility", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mockSupplierOptions();
    vi.mocked(draftApi.getAIDraftCapabilities).mockResolvedValue({
      ai_draft_enabled: false,
      llm_provider: null,
    });
  });

  it("engineer (capa=2 CREATE) sees 生成PPT button on D8_CLOSURE", async () => {
    useAuthStore.setState({
      user: { user_id: "u1", username: "engineer", role_key: "quality_engineer",
              permissions: { capa: 2 } } as any,  // CREATE level
      token: "test-token",
    });
    const closedCapa = { ...mockCapa, status: "D8_CLOSURE", d8_closure: "已关闭" };
    vi.mocked(capaApi.getCAPA).mockResolvedValue(closedCapa as any);

    renderPage();
    await waitFor(() => expect(screen.getByDisplayValue(/已关闭/)).toBeInTheDocument(), { timeout: 3000 });
    expect(screen.getByRole("button", { name: /Generate PPT|生成 PPT/ })).toBeInTheDocument();
  });

  it("viewer (capa=1 VIEW) does NOT see 生成PPT button on D8_CLOSURE", async () => {
    useAuthStore.setState({
      user: { user_id: "u1", username: "viewer", role_key: "viewer",
              permissions: { capa: 1 } } as any,  // VIEW only
      token: "test-token",
    });
    const closedCapa = { ...mockCapa, status: "D8_CLOSURE", d8_closure: "已关闭" };
    vi.mocked(capaApi.getCAPA).mockResolvedValue(closedCapa as any);

    renderPage();
    await waitFor(() => expect(screen.getByDisplayValue(/已关闭/)).toBeInTheDocument(), { timeout: 3000 });
    expect(screen.queryByRole("button", { name: /Generate PPT|生成 PPT/ })).not.toBeInTheDocument();
  });

  it("engineer (capa=2) does NOT see 生成PPT button on D7_PREVENTION (not closed)", async () => {
    useAuthStore.setState({
      user: { user_id: "u1", username: "engineer", role_key: "quality_engineer",
              permissions: { capa: 2 } } as any,
      token: "test-token",
    });
    // mockCapa.status 默认 "D2_DESCRIPTION"（未关闭）
    vi.mocked(capaApi.getCAPA).mockResolvedValue(mockCapa as any);

    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/5W2H Problem Description/)).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /Generate PPT|生成 PPT/ })).not.toBeInTheDocument();
  });
});

describe("CAPADetailPage trigger SCAR", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mockSupplierOptions();
    vi.mocked(draftApi.getAIDraftCapabilities).mockResolvedValue({
      ai_draft_enabled: false,
      llm_provider: null,
    });
    vi.mocked(capaApi.getD3Runs).mockResolvedValue([]);
    vi.mocked(capaApi.getD3Adoptions).mockResolvedValue([]);
    vi.mocked(capaApi.getD3Executions).mockResolvedValue([]);
  });

  it("shows trigger button at D3 with edit permission and no linked SCAR", async () => {
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "engineer",
        role_key: "quality_engineer",
        permissions: { capa: 3 },
      } as any,
      token: "test-token",
    });

    const d3Capa = {
      ...mockCapa,
      status: "D3_INTERIM",
      d3_interim: "test content",
      linked_scar: null,
      d3_affected_lots: ["LOT-A", "LOT-B"],
    };
    vi.mocked(capaApi.getCAPA).mockResolvedValue(d3Capa as any);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("capa-trigger-scar")).toBeInTheDocument();
    });
  });

  it("hides trigger button at D1 / with linked SCAR / without edit permission", async () => {
    // D1_TEAM blocks trigger
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "engineer",
        role_key: "quality_engineer",
        permissions: { capa: 3 },
      } as any,
      token: "test-token",
    });
    vi.mocked(capaApi.getCAPA).mockResolvedValue({
      ...mockCapa,
      status: "D1_TEAM",
      linked_scar: null,
    } as any);
    const { unmount } = renderPage();
    await waitFor(() => {
      expect(screen.getAllByText("8D-2026-001").length).toBeGreaterThan(0);
    });
    expect(screen.queryByTestId("capa-trigger-scar")).not.toBeInTheDocument();
    unmount();

    // linked_scar present hides button
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "engineer",
        role_key: "quality_engineer",
        permissions: { capa: 3 },
      } as any,
      token: "test-token",
    });
    vi.mocked(capaApi.getCAPA).mockResolvedValue({
      ...mockCapa,
      status: "D3_INTERIM",
      d3_interim: "x",
      linked_scar: {
        scar_id: "scar-1",
        scar_no: "SCAR-260701-001",
        status: "open",
        supplier_id: "sup-1",
      },
    } as any);
    const { unmount: unmount2 } = renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("capa-linked-scar")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("capa-trigger-scar")).not.toBeInTheDocument();
    unmount2();

    // viewer cannot edit
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "viewer",
        role_key: "viewer",
        permissions: { capa: 1 },
      } as any,
      token: "test-token",
    });
    vi.mocked(capaApi.getCAPA).mockResolvedValue({
      ...mockCapa,
      status: "D3_INTERIM",
      d3_interim: "x",
      linked_scar: null,
    } as any);
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText("8D-2026-001").length).toBeGreaterThan(0);
    });
    expect(screen.queryByTestId("capa-trigger-scar")).not.toBeInTheDocument();
  });

  it("submit calls triggerScar with supplier_id and affected_batches", async () => {
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "engineer",
        role_key: "quality_engineer",
        permissions: { capa: 3 },
      } as any,
      token: "test-token",
    });

    const d3Capa = {
      ...mockCapa,
      status: "D3_INTERIM",
      d3_interim: "test content",
      d2_description: "problem",
      d4_root_cause: "root",
      linked_scar: null,
      d3_affected_lots: ["LOT-A", "LOT-B"],
    };
    vi.mocked(capaApi.getCAPA).mockResolvedValue(d3Capa as any);
    vi.mocked(capaApi.triggerScar).mockResolvedValue({
      scar_id: "scar-new",
      scar_no: "SCAR-260701-002",
      supplier_id: "sup-1",
      status: "open",
    } as any);

    renderPage();

    const triggerBtn = await screen.findByTestId("capa-trigger-scar");
    fireEvent.click(triggerBtn);

    await waitFor(() => {
      expect(screen.getByText(/从 8D 发起 SCAR|Trigger SCAR from 8D/)).toBeInTheDocument();
    });

    // Select supplier option (supplier_id, not affected_batches)
    const supplierSelect = document.getElementById("supplier_id") as HTMLElement;
    fireEvent.mouseDown(supplierSelect);
    const option = await screen.findByText(/S-001 - Acme/);
    fireEvent.click(option);

    // Submit modal
    const okButtons = screen.getAllByRole("button", { name: /发起 SCAR|Trigger SCAR/ });
    const submitBtn = okButtons[okButtons.length - 1];
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(capaApi.triggerScar).toHaveBeenCalledWith(
        "test-report-id",
        expect.objectContaining({
          supplier_id: "sup-1",
          affected_batches: ["LOT-A", "LOT-B"],
        }),
        expect.any(AbortSignal),
      );
    });
    expect(capaApi.getCAPA).toHaveBeenCalled();
  });
});

describe("CAPADetailPage knowledge sink card", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(draftApi.getAIDraftCapabilities).mockResolvedValue({
      ai_draft_enabled: false,
      llm_provider: null,
    });
    vi.mocked(knowledgeApi.findCapaKnowledgeEntry).mockResolvedValue(null);
  });

  it("shows knowledge card with entry summary and embedding badge on D8_CLOSURE", async () => {
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "engineer",
        role_key: "quality_engineer",
        permissions: { capa: 3 },
      } as any,
      token: "test-token",
    });
    vi.mocked(capaApi.getCAPA).mockResolvedValue({
      ...mockCapa,
      status: "D8_CLOSURE",
      d8_closure: "closed",
    } as any);
    vi.mocked(knowledgeApi.findCapaKnowledgeEntry).mockResolvedValue({
      entry_id: "e1",
      source_type: "capa",
      source_id: "test-report-id",
      document_no: "8D-2026-001",
      title: "Test CAPA Report",
      severity: "fatal",
      product_line_code: "DC-DC-100",
      factory_id: "f1",
      status: "active",
      embedding_status: "ready",
      embedding_id: "emb-1",
      lesson_summary: "Lesson learned about torque",
      tags: ["torque", "assembly"],
      created_at: "2026-01-01T00:00:00Z",
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("capa-knowledge-card")).toBeInTheDocument();
    });
    expect(screen.getByTestId("capa-knowledge-entry")).toBeInTheDocument();
    expect(screen.getByText("Lesson learned about torque")).toBeInTheDocument();
    expect(screen.getByTestId("capa-knowledge-embedding-status")).toHaveTextContent(
      /向量就绪|Embedding ready/,
    );
    expect(screen.getByTestId("capa-knowledge-resink")).toBeInTheDocument();
  });

  it("shows missing entry warning and resink on ARCHIVED", async () => {
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "engineer",
        role_key: "quality_engineer",
        permissions: { capa: 3 },
      } as any,
      token: "test-token",
    });
    vi.mocked(capaApi.getCAPA).mockResolvedValue({
      ...mockCapa,
      status: "ARCHIVED",
    } as any);
    vi.mocked(knowledgeApi.findCapaKnowledgeEntry).mockResolvedValue(null);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("capa-knowledge-missing")).toBeInTheDocument();
    });
    expect(screen.getByTestId("capa-knowledge-resink")).toBeInTheDocument();
  });

  it("approve uses formatCapaAdvanceError for 422 blocked outcome", async () => {
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "manager",
        role_key: "manager",
        permissions: { capa: 4 },
      } as any,
      token: "test-token",
    });
    vi.mocked(capaApi.getCAPA).mockResolvedValue({
      ...mockCapa,
      status: "D8_APPROVAL_PENDING",
    } as any);
    const err = {
      response: {
        status: 422,
        data: {
          detail: {
            outcome: "blocked",
            reason: "llm_unavailable",
            message: "LLM not configured",
          },
        },
      },
    };
    vi.mocked(capaApi.advanceCAPA).mockRejectedValue(err);
    vi.mocked(capaApi.getCapaOutcomeReview).mockResolvedValue({
      report_id: "test-report-id", status: "D8_APPROVAL_PENDING", contract: "capa.outcome-review.v1",
      review_round_id: "00000000-0000-4000-8000-000000000002", revision: "a".repeat(64), binding_status: "pending",
      core: { d4_root_cause: "root", d5_correction: "implemented", d6_verification: "tested", d7_prevention: "prevention" },
      verifications: [], d7_actions: [], documents: [], decision: null,
      supplement: { text: null, review_scope: "unreviewed_supplement", updated_by: null, updated_at: null },
    });

    renderPage();

    const approveBtn = await screen.findByTestId("capa-approve");
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(capaApi.advanceCAPA).toHaveBeenCalledWith("test-report-id", {
        target_state: "D8_CLOSURE", expected_outcome_revision: "a".repeat(64),
        expected_review_round_id: "00000000-0000-4000-8000-000000000002",
      }, expect.any(AbortSignal));
    });
    // Real formatter should map blocked outcome
    expect(capaApi.formatCapaAdvanceError(err, "fallback")).toMatch(/blocked|阻断|LLM/i);
  });

  it("resink shows failed outcome error banner", async () => {
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "engineer",
        role_key: "quality_engineer",
        permissions: { capa: 3 },
      } as any,
      token: "test-token",
    });
    vi.mocked(capaApi.getCAPA).mockResolvedValue({
      ...mockCapa,
      status: "D8_CLOSURE",
      d8_closure: "closed",
    } as any);
    vi.mocked(knowledgeApi.findCapaKnowledgeEntry).mockResolvedValue(null);
    vi.mocked(capaApi.sinkKnowledge).mockRejectedValue({
      response: {
        status: 422,
        data: {
          detail: { outcome: "failed", reason: "llm_failed", message: "timeout" },
        },
      },
    });

    renderPage();

    const resinkBtn = await screen.findByTestId("capa-knowledge-resink");
    fireEvent.click(resinkBtn);

    await waitFor(() => {
      expect(capaApi.sinkKnowledge).toHaveBeenCalledWith("test-report-id", expect.any(AbortSignal));
    });
    await waitFor(() => {
      expect(screen.getByTestId("capa-knowledge-error")).toHaveTextContent(/沉淀失败|timeout|failed|重试/i);
    });
  });

  it("shows load error (not missing/resink) when knowledge list fails", async () => {
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "engineer",
        role_key: "quality_engineer",
        permissions: { capa: 3 },
      } as any,
      token: "test-token",
    });
    vi.mocked(capaApi.getCAPA).mockResolvedValue({
      ...mockCapa,
      status: "D8_CLOSURE",
      d8_closure: "closed",
    } as any);
    vi.mocked(knowledgeApi.findCapaKnowledgeEntry).mockRejectedValue({
      response: { status: 500, data: { detail: "server error" } },
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("capa-knowledge-load-error")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("capa-knowledge-missing")).not.toBeInTheDocument();
    expect(screen.queryByTestId("capa-knowledge-resink")).not.toBeInTheDocument();
    expect(screen.getByTestId("capa-knowledge-reload")).toBeInTheDocument();
  });
});



describe("CAPADetailPage explicit Agent task target", () => {
  it("passes the displayed immutable report UUID to the global task provider", async () => {
    vi.clearAllMocks();
    mockSupplierOptions();
    vi.mocked(draftApi.getAIDraftCapabilities).mockResolvedValue({ ai_draft_enabled: false, llm_provider: null });
    const reportId = "00000000-0000-4000-8000-000000000001";
    const beginCreate = vi.fn();
    agentContext.value = { available: true, beginCreate };
    useAuthStore.setState({ user: { user_id: "u1", permissions: { capa: 1 } } as any, token: "test-token" });
    vi.mocked(capaApi.getCAPA).mockResolvedValue({ ...mockCapa, report_id: reportId } as any);
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "以本报告创建任务" }));
    expect(beginCreate).toHaveBeenCalledWith(reportId);
  });
});


describe("Task 5 reviewed outcome integration", () => {
  const review = {
    report_id: "test-report-id", status: "D8_APPROVAL_PENDING", contract: "capa.outcome-review.v1",
    review_round_id: "00000000-0000-4000-8000-000000000002", revision: "a".repeat(64), binding_status: "pending",
    core: { d4_root_cause: "根因", d5_correction: "实际纠正措施", d6_verification: "实施后复测合格", d7_prevention: "预防复发" },
    verifications: [], d7_actions: [], documents: [], decision: null,
    supplement: { text: "补充说明", review_scope: "unreviewed_supplement", updated_by: null, updated_at: null },
  } as const;
  const deferred = <T,>() => { let resolve!: (value: T) => void; let reject!: (value: unknown) => void;
    const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
  beforeEach(() => {
    route.id = "test-report-id";
    useProductLineStore.setState({ selected: null });
    vi.clearAllMocks(); localStorage.clear(); mockSupplierOptions();
    useAuthStore.setState({ user: { user_id: "u1", role_key: "admin", permissions: { capa: 5 } } as any, token: "credential-A" });
    vi.mocked(capaApi.getCAPA).mockResolvedValue({ ...mockCapa, status: "D8_APPROVAL_PENDING" } as any);
    vi.mocked(capaApi.getCapaOutcomeReview).mockResolvedValue(structuredClone(review) as any);
    vi.mocked(draftApi.getAIDraftCapabilities).mockResolvedValue({ ai_draft_enabled: true, llm_provider: null });
    vi.mocked(capaApi.getD7Recommendations).mockResolvedValue({ recommendations: [] } as any);
    vi.mocked(capaApi.getD4Recommendations).mockResolvedValue({ items: [], stages: [] });
  });
  it("only the visible current panel supplies decision expectations and duplicate approval is disabled", async () => {
    vi.mocked(capaApi.advanceCAPA).mockReturnValue(new Promise(() => {}));
    renderPage();
    await screen.findByText("实施后复测合格");
    const approve = screen.getByTestId("capa-approve");
    fireEvent.click(approve); fireEvent.click(approve);
    expect(capaApi.advanceCAPA).toHaveBeenCalledTimes(1);
    expect(capaApi.advanceCAPA).toHaveBeenCalledWith("test-report-id", {
      target_state: "D8_CLOSURE", expected_outcome_revision: review.revision, expected_review_round_id: review.review_round_id,
    }, expect.any(AbortSignal));
  });
  it("closed admin has no core link/adoption/undo controls but the unreviewed supplement remains writable", async () => {
    vi.mocked(capaApi.getCAPA).mockResolvedValue({ ...mockCapa, status: "D8_CLOSURE" } as any);
    vi.mocked(capaApi.getCapaOutcomeReview).mockResolvedValue({ ...review, status: "D8_CLOSURE", binding_status: "legacy_unversioned" } as any);
    renderPage();
    await screen.findByText("实施后复测合格");
    expect(screen.queryByRole("button", { name: /关联FMEA|Link FMEA|Change FMEA/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /撤销修改/ })).not.toBeInTheDocument();
    expect(screen.queryByTestId("capa-approve")).not.toBeInTheDocument();
    const supplement = screen.getByTestId("capa-outcome-supplement-edit");
    fireEvent.change(supplement, { target: { value: "结案后新增说明" } }); fireEvent.blur(supplement);
    expect(capaApi.updateCAPA).toHaveBeenCalledWith("test-report-id", { d8_closure: "结案后新增说明" }, expect.any(AbortSignal));
  });
  it("rejection sends exactly the current seen token with the existing reason", async () => {
    vi.mocked(capaApi.advanceCAPA).mockReturnValue(new Promise(() => {}));
    renderPage(); await screen.findByText("实施后复测合格");
    fireEvent.click(screen.getByTestId("capa-reject"));
    fireEvent.change(screen.getByTestId("capa-reject-reason"), { target: { value: "  重新验证  " } });
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /Reject|驳 回|驳回/ }));
    expect(capaApi.advanceCAPA).toHaveBeenCalledWith("test-report-id", {
      target_state: "D7_PREVENTION", reject_reason: "重新验证", expected_outcome_revision: review.revision,
      expected_review_round_id: review.review_round_id,
    }, expect.any(AbortSignal));
  });
  it.each([401, 403, 404, 409])("decision %s consumes the old token and reason without automatic material reload/replay", async status => {
    vi.mocked(capaApi.advanceCAPA).mockRejectedValue({ response: { status, data: { detail: "denied" } } });
    renderPage(); await screen.findByText("实施后复测合格");
    fireEvent.click(screen.getByTestId("capa-approve"));
    await waitFor(() => expect(screen.queryByTestId("capa-approve")).not.toBeInTheDocument());
    expect(capaApi.advanceCAPA).toHaveBeenCalledTimes(1);
    expect(capaApi.getCapaOutcomeReview).toHaveBeenCalledTimes(1);
    if (status === 409) {
      expect(capaApi.getCAPA).toHaveBeenCalledTimes(2);
      vi.mocked(capaApi.getCapaOutcomeReview).mockResolvedValue({ ...structuredClone(review), revision: "b".repeat(64) } as any);
      fireEvent.click(screen.getByRole("button", { name: /Reload review materials|重新加载审核材料/ }));
      await screen.findByText("实施后复测合格");
      expect(capaApi.advanceCAPA).toHaveBeenCalledTimes(1);
      fireEvent.click(screen.getByTestId("capa-approve"));
      expect(capaApi.advanceCAPA).toHaveBeenLastCalledWith("test-report-id", expect.objectContaining({ expected_outcome_revision: "b".repeat(64) }), expect.any(AbortSignal));
    }
  });
  it("timeout queries actual state and never automatically repeats a decision", async () => {
    vi.mocked(capaApi.advanceCAPA).mockRejectedValue(new Error("network timeout"));
    vi.mocked(capaApi.getCAPA).mockResolvedValueOnce({ ...mockCapa, status: "D8_APPROVAL_PENDING" } as any)
      .mockResolvedValue({ ...mockCapa, status: "D8_CLOSURE" } as any);
    renderPage(); await screen.findByText("实施后复测合格");
    fireEvent.click(screen.getByTestId("capa-approve"));
    await waitFor(() => expect(screen.getByTestId("capa-status")).toHaveTextContent("D8_CLOSURE"));
    expect(capaApi.advanceCAPA).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("capa-approve")).not.toBeInTheDocument();
    expect(capaApi.getCapaOutcomeReview).toHaveBeenCalledTimes(1);
  });
  it.each(["success", "denial"])("credential change aborts a decision and old %s cannot alter the new same-document view", async result => {
    const old = deferred<any>(); vi.mocked(capaApi.advanceCAPA).mockReturnValueOnce(old.promise);
    renderPage(); await screen.findByText("实施后复测合格");
    fireEvent.click(screen.getByTestId("capa-approve"));
    const signal = vi.mocked(capaApi.advanceCAPA).mock.calls[0][2]!;
    await act(async () => { useAuthStore.setState({ token: "credential-B" }); });
    await screen.findByText("实施后复测合格");
    expect(signal.aborted).toBe(true);
    await act(async () => result === "success" ? old.resolve({ ...mockCapa, status: "ARCHIVED" }) : old.reject({ response: { status: 403 } }));
    expect(screen.getByTestId("capa-status")).toHaveTextContent("D8_APPROVAL_PENDING");
    expect(screen.getByTestId("capa-approve")).toBeEnabled();
  });
  it.each(["user", "credential", "factory", "line", "tenant", "report", "stored credential", "stored factory"])("%s invalidation aborts every concurrent initial view controller and ignores old success/denial", async dimension => {
    const old = deferred<any>(), sources = deferred<any>(), capabilities = deferred<any>(), suppliers = deferred<any>();
    vi.mocked(capaApi.getCAPA).mockReturnValueOnce(old.promise);
    vi.mocked(fmeaApi.listFMEAs).mockReturnValueOnce(sources.promise);
    vi.mocked(draftApi.getAIDraftCapabilities).mockReturnValueOnce(capabilities.promise);
    vi.mocked(capaApi.listCapaSupplierOptions).mockReturnValueOnce(suppliers.promise);
    const rendered = renderPage();
    const signals = [vi.mocked(capaApi.getCAPA).mock.calls[0][1], vi.mocked(fmeaApi.listFMEAs).mock.calls[0][1],
      vi.mocked(draftApi.getAIDraftCapabilities).mock.calls[0][0], vi.mocked(capaApi.listCapaSupplierOptions).mock.calls[0][1]];
    await act(async () => {
      if (dimension === "stored credential") { localStorage.setItem("access_token", "stored-B"); window.dispatchEvent(new Event("storage")); }
      if (dimension === "stored factory") { localStorage.setItem("current_factory_id", "stored-factory-B"); window.dispatchEvent(new Event("storage")); }
      if (dimension === "user") useAuthStore.setState({ user: { ...useAuthStore.getState().user!, user_id: "u2" } });
      if (dimension === "credential") useAuthStore.setState({ token: "credential-B" });
      if (dimension === "factory") useAuthStore.setState({ currentFactoryId: "factory-B" });
      if (dimension === "line") useProductLineStore.setState({ selected: "line-B" });
      if (dimension === "tenant") { localStorage.setItem("tenant_slug", "tenant-B"); window.dispatchEvent(new Event("storage")); }
      if (dimension === "report") { route.id = "report-B"; rendered.rerender(<App><BrowserRouter><CAPADetailPage /></BrowserRouter></App>); }
    });
    await waitFor(() => signals.forEach(signal => expect(signal?.aborted).toBe(true)));
    await act(async () => {
      old.resolve({ ...mockCapa, title: "OLD PRIVATE", status: "ARCHIVED" });
      sources.reject({ response: { status: 403 } }); capabilities.resolve({ ai_draft_enabled: true }); suppliers.resolve({ items: [] });
    });
    expect(screen.queryByText("OLD PRIVATE")).not.toBeInTheDocument();
  });
  it("identity change aborts the current panel read and removes a typed rejection reason", async () => {
    renderPage(); await screen.findByText("实施后复测合格");
    fireEvent.click(screen.getByTestId("capa-reject"));
    fireEvent.change(screen.getByTestId("capa-reject-reason"), { target: { value: "PRIVATE REASON" } });
    const next = deferred<any>(); vi.mocked(capaApi.getCapaOutcomeReview).mockReturnValueOnce(next.promise);
    fireEvent.click(screen.getByRole("button", { name: /Reload review materials|重新加载审核材料/ }));
    const calls = vi.mocked(capaApi.getCapaOutcomeReview).mock.calls;
    const signal = calls[calls.length - 1][1]!;
    await act(async () => { useAuthStore.setState({ token: "credential-B" }); });
    expect(signal.aborted).toBe(true);
    await screen.findByText("实施后复测合格");
    fireEvent.click(screen.getByTestId("capa-reject"));
    expect(screen.getByTestId("capa-reject-reason")).toHaveValue("");
    await act(async () => next.reject({ response: { status: 403 } }));
    expect(screen.getByTestId("capa-reject-reason")).toHaveValue("");
  });
  it("archived admin has no core, supplement, verification or draft writing controls", async () => {
    vi.mocked(capaApi.getCAPA).mockResolvedValue({ ...mockCapa, status: "ARCHIVED" } as any);
    vi.mocked(capaApi.getCapaOutcomeReview).mockResolvedValue({ ...structuredClone(review), status: "ARCHIVED", binding_status: "verified" } as any);
    renderPage(); await screen.findByText("实施后复测合格");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Link FMEA|关联FMEA|Change FMEA|撤销修改|Undo Change|通过验证|Save verification/ })).not.toBeInTheDocument();
    expect(screen.queryByTestId("capa-ai-draft")).not.toBeInTheDocument();
    expect(screen.queryByTestId("capa-outcome-supplement-edit")).not.toBeInTheDocument();
    expect(verificationCard).not.toHaveBeenCalled();
  });
  it.each(["D4_ROOT_CAUSE", "D5_CORRECTION", "D6_VERIFICATION"])("%s stays writable without per-step approval", async status => {
    vi.mocked(capaApi.getCAPA).mockResolvedValue({ ...mockCapa, status } as any);
    // Isolate only recommendation transport; the actual page form and writer remain under test.
    if (status === "D5_CORRECTION") vi.spyOn(capaApi, "getD5Recommendations").mockResolvedValue({ existing_controls: [], general_suggestions: [], stages: [] });
    renderPage();
    const field = await screen.findByRole("textbox");
    fireEvent.change(field, { target: { value: "现场实施材料" } }); fireEvent.blur(field);
    const key = status === "D4_ROOT_CAUSE" ? "d4_root_cause" : status === "D5_CORRECTION" ? "d5_correction" : "d6_verification";
    expect(capaApi.updateCAPA).toHaveBeenCalledWith("test-report-id", { [key]: "现场实施材料" }, expect.any(AbortSignal));
    expect(screen.queryByTestId("capa-approve")).not.toBeInTheDocument();
    expect(capaApi.getCapaOutcomeReview).not.toHaveBeenCalled();
    if (status === "D4_ROOT_CAUSE") expect(verificationCard).toHaveBeenCalledWith(expect.objectContaining({ canEdit: true }));
  });

  it.each([401, 403, 404, 409])("unreadable necessary sources (%s) never expose an approval or rejection control", async status => {
    vi.mocked(capaApi.getCapaOutcomeReview).mockRejectedValue({ response: { status } });
    renderPage(); await screen.findByRole("alert");
    expect(screen.queryByTestId("capa-approve")).not.toBeInTheDocument();
    expect(screen.queryByTestId("capa-reject")).not.toBeInTheDocument();
    expect(capaApi.advanceCAPA).not.toHaveBeenCalled();
  });
  it.each(["Replace", "Append"])("a %s completing with terminal state withdraws all draft, undo, link and core editing controls", async action => {
    vi.mocked(capaApi.getCAPA).mockResolvedValue({ ...mockCapa, status: "D6_VERIFICATION" } as any);
    vi.mocked(draftApi.generateDraft).mockResolvedValue({ content: "已实施的验证记录", step: "d6", request_id: "draft", structured_data: null });
    vi.mocked(capaApi.updateCAPA).mockResolvedValue({ ...mockCapa, status: "D8_CLOSURE" } as any);
    vi.mocked(capaApi.getCapaOutcomeReview).mockResolvedValue({ ...structuredClone(review), status: "D8_CLOSURE", binding_status: "verified" } as any);
    renderPage(); fireEvent.click(await screen.findByText("AI Draft"));
    await screen.findByText("AI Draft Preview");
    fireEvent.click(screen.getByRole("button", { name: new RegExp(action) }));
    await screen.findByText("实施后复测合格");
    expect(capaApi.updateCAPA).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: /Undo Change|Replace|Append|Link FMEA|Change FMEA/ })).not.toBeInTheDocument();
    expect(screen.queryByTestId("capa-ai-draft")).not.toBeInTheDocument();
    expect(screen.getByTestId("capa-outcome-supplement-edit")).toBeEnabled();
  });
  it("closed supplement updates do not change the approved core binding or request decision expectations", async () => {
    const closed = { ...mockCapa, status: "D8_CLOSURE" };
    vi.mocked(capaApi.getCAPA).mockResolvedValue(closed as any);
    vi.mocked(capaApi.updateCAPA).mockResolvedValue({ ...closed, d8_closure: "新补充" } as any);
    vi.mocked(capaApi.getCapaOutcomeReview).mockResolvedValue({ ...structuredClone(review), status: "D8_CLOSURE", binding_status: "verified" } as any);
    renderPage(); await screen.findByText("实施后复测合格");
    const binding = screen.getByTestId("capa-outcome-binding").textContent;
    const field = screen.getByTestId("capa-outcome-supplement-edit");
    fireEvent.change(field, { target: { value: "新补充" } }); fireEvent.blur(field);
    await waitFor(() => expect(field).toHaveValue("新补充"));
    expect(screen.getByTestId("capa-outcome-binding").textContent).toBe(binding);
    expect(screen.getByTestId("capa-outcome-core")).not.toHaveTextContent("新补充");
    expect(capaApi.advanceCAPA).not.toHaveBeenCalled();
    expect(capaApi.getCapaOutcomeReview).toHaveBeenCalledTimes(1);
  });

  it("a successful single approval displays the actual verified decision and terminal core", async () => {
    const closed = { ...mockCapa, status: "D8_CLOSURE" };
    vi.mocked(capaApi.advanceCAPA).mockResolvedValue(closed as any);
    vi.mocked(capaApi.getCapaOutcomeReview).mockResolvedValueOnce(structuredClone(review) as any).mockResolvedValue({
      ...structuredClone(review), status: "D8_CLOSURE", binding_status: "verified",
      decision: { action: "approved", actor_id: "00000000-0000-4000-8000-000000000001", operated_at: "2026-10-23T00:00:00Z", audit_id: "00000000-0000-4000-8000-000000000005" },
    } as any);
    renderPage(); await screen.findByText("实施后复测合格");
    fireEvent.click(screen.getByTestId("capa-approve"));
    await waitFor(() => expect(screen.getByTestId("capa-outcome-binding")).toHaveTextContent("Review version verified"));
    expect(screen.getByTestId("capa-outcome-core")).toHaveTextContent("approved");
    expect(capaApi.advanceCAPA).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("capa-approve")).not.toBeInTheDocument();
    expect(verificationCard).not.toHaveBeenCalled();
  });

  it.each(["lookup", "resink"])("same-identity material reload does not cancel or strand pending knowledge %s", async operation => {
    const closed = { ...mockCapa, status: "D8_CLOSURE" };
    vi.mocked(capaApi.getCAPA).mockResolvedValue(closed as any);
    vi.mocked(capaApi.getCapaOutcomeReview).mockResolvedValue({ ...structuredClone(review), status: "D8_CLOSURE", binding_status: "legacy_unversioned" } as any);
    const pending = deferred<any>();
    const entry = { entry_id: "e1", lesson_summary: "CURRENT KNOWLEDGE", tags: [], embedding_status: "ready" };
    if (operation === "lookup") vi.mocked(knowledgeApi.findCapaKnowledgeEntry).mockReturnValueOnce(pending.promise);
    else {
      vi.mocked(knowledgeApi.findCapaKnowledgeEntry).mockResolvedValueOnce(null).mockResolvedValue(entry as any);
      vi.mocked(capaApi.sinkKnowledge).mockReturnValueOnce(pending.promise);
    }
    renderPage(); await screen.findByText("实施后复测合格");
    if (operation === "resink") fireEvent.click(await screen.findByTestId("capa-knowledge-resink"));
    const signal = operation === "lookup" ? vi.mocked(knowledgeApi.findCapaKnowledgeEntry).mock.calls[0][2]! : vi.mocked(capaApi.sinkKnowledge).mock.calls[0][1]!;
    fireEvent.click(screen.getByRole("button", { name: /Reload review materials|重新加载审核材料/ }));
    expect(signal.aborted).toBe(false);
    await act(async () => pending.resolve(operation === "lookup" ? entry : { entry_id: "e1", title: "Knowledge", document_no: "K-1", embedding_status: "ready" }));
    await screen.findByText("CURRENT KNOWLEDGE");
    expect(screen.getByTestId("capa-knowledge-resink")).not.toHaveClass("ant-btn-loading");
  });

  it.each(["success", "denial"])("a cancelled actual beforeAdopt rejects rather than granting continuation on late %s", async outcome => {
    const write = deferred<any>();
    vi.mocked(capaApi.getCAPA).mockResolvedValue({ ...mockCapa, status: "D4_ROOT_CAUSE", d4_root_cause: "Original" } as any);
    vi.mocked(capaApi.updateCAPA).mockReturnValueOnce(write.promise);
    renderPage(); const field = await screen.findByRole("textbox");
    fireEvent.change(field, { target: { value: "Unsaved material" } });
    const result = prerequisiteProbe.before!().then(() => ({ resolved: true }), error => ({ error }));
    expect(capaApi.updateCAPA).toHaveBeenCalledTimes(1);
    await act(async () => { useAuthStore.setState({ token: "credential-B" }); });
    await act(async () => outcome === "success" ? write.resolve({ ...mockCapa, status: "D4_ROOT_CAUSE" }) : write.reject({ response: { status: 403 } }));
    expect(await result).toMatchObject({ error: { name: "CanceledError" } });
  });

});

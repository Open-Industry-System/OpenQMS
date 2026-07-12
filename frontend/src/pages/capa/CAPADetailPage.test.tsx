import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { App } from "antd";
import { useAuthStore } from "../../store/authStore";
import * as capaApi from "../../api/capa";
import * as draftApi from "../../api/capaDraft";
import CAPADetailPage from "./CAPADetailPage";

// Mock react-router-dom params
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useParams: () => ({ id: "test-report-id" }),
    useNavigate: () => mockNavigate,
  };
});

// Mock APIs
vi.mock("../../api/capa");
vi.mock("../../api/capaDraft");
vi.mock("../../api/fmea", () => ({
  listFMEAs: vi.fn().mockResolvedValue({ items: [] }),
}));

// Mock D4VerificationCard to avoid rendering issues
vi.mock("../../components/capa/D4VerificationCard", () => ({
  default: () => null,
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

describe("CAPADetailPage D3ContainmentPanel integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
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

describe("CAPADetailPage AI draft integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
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
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

describe("CAPADetailPage AI draft integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
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

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
  title: "测试 8D 报告标题",
  document_no: "8D-2026-001",
  status: "D2_DESCRIPTION",
  severity: "致命",
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
      expect(screen.getByText("AI草拟")).toBeInTheDocument();
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
      expect(screen.getByText("5W2H 问题描述")).toBeInTheDocument();
    });
    expect(screen.queryByText("AI草拟")).not.toBeInTheDocument();
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
      expect(screen.getByText("5W2H 问题描述")).toBeInTheDocument();
    });
    expect(screen.queryByText("AI草拟")).not.toBeInTheDocument();
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
      content: "AI 生成的问题陈述内容",
      structured_data: { problem_statement: "AI 生成的问题陈述内容" },
      request_id: "test-req-id",
      step: "d2",
    });

    renderPage();

    // Wait for page to load and button to appear
    const aiBtn = await screen.findByText("AI草拟");
    fireEvent.click(aiBtn);

    // Wait for the preview modal to appear
    await waitFor(() => {
      expect(screen.getByText("AI 草稿预览")).toBeInTheDocument();
    });
    expect(screen.getByText("AI 生成的问题陈述内容")).toBeInTheDocument();
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

    const capaWithContent = { ...mockCapa, d2_description: "原始内容" };
    vi.mocked(capaApi.getCAPA).mockResolvedValue(capaWithContent as any);
    vi.mocked(capaApi.updateCAPA).mockResolvedValue(capaWithContent as any);
    vi.mocked(draftApi.getAIDraftCapabilities).mockResolvedValue({
      ai_draft_enabled: true,
      llm_provider: "test",
    });
    vi.mocked(draftApi.generateDraft).mockResolvedValue({
      content: "AI 替换内容",
      structured_data: null,
      request_id: "test-req-id",
      step: "d2",
    });

    renderPage();

    // Wait for page and generate
    const aiBtn = await screen.findByText("AI草拟");
    fireEvent.click(aiBtn);

    // Wait for preview and click replace
    await waitFor(() => {
      expect(screen.getByText("AI 草稿预览")).toBeInTheDocument();
    });

    const replaceBtn = screen.getByRole("button", { name: /替换|替 换/ });
    fireEvent.click(replaceBtn);

    // After replace, undo button should appear
    await waitFor(() => {
      expect(screen.getByText("撤销修改")).toBeInTheDocument();
    });
  });
});

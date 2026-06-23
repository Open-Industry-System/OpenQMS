import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { App } from "antd";
import FMEAEditorPage from "./FMEAEditorPage";
import type { FMEADocument, GraphEdge, GraphNode } from "../../../types";

const mocks = vi.hoisted(() => ({
  getFMEA: vi.fn(),
  getFMEAVersion: vi.fn(),
  listFMEAVersions: vi.fn(),
  canEdit: vi.fn(),
  startEditing: vi.fn(),
}));

vi.mock("antd", async () => {
  const actual = await vi.importActual<typeof import("antd")>("antd");
  return {
    ...actual,
    App: Object.assign(
      ({ children }: { children: React.ReactNode }) => <>{children}</>,
      { useApp: () => ({ message: { warning: vi.fn(), success: vi.fn(), error: vi.fn(), info: vi.fn() }, modal: {}, notification: {} }) }
    ),
  };
});

vi.mock("../../../api/fmea", () => ({
  getFMEA: mocks.getFMEA,
  updateFMEA: vi.fn(),
  transitionFMEA: vi.fn(),
}));
vi.mock("../../../api/version", () => ({
  getFMEAVersion: mocks.getFMEAVersion,
  listFMEAVersions: mocks.listFMEAVersions,
}));
vi.mock("../../../api/specialCharacteristic", () => ({
  syncFromFMEA: vi.fn(),
  getSeverityWarnings: vi.fn().mockResolvedValue({ warnings: [] }),
}));
vi.mock("../../../api/lessonsLearned", () => ({ getFMEALessons: vi.fn() }));
vi.mock("../../../api/graph", () => ({
  getImpactChain: vi.fn(),
  getCauseChain: vi.fn(),
  normalizeGraphData: vi.fn((nodes: unknown, edges: unknown) => ({ nodes, edges })),
}));
vi.mock("../../../api/changeImpact", () => ({ analyzeChangeImpact: vi.fn() }));
vi.mock("../../../store/authStore", () => ({
  useAuthStore: (selector: (s: { user: unknown }) => unknown) => selector({ user: { user_id: "u1", role_key: "admin" } }),
}));
vi.mock("../../../hooks/usePermission", () => ({
  usePermission: () => ({ canEdit: mocks.canEdit, canApprove: () => true }),
}));
vi.mock("../../../hooks/useCollaboration", () => ({
  useCollaboration: () => ({
    activeUsers: [],
    startEditing: mocks.startEditing,
    stopEditing: vi.fn(),
    isSyncing: false,
  }),
}));
vi.mock("../../../components/dfmea/SmartSuggestionDropdown", () => ({
  default: ({ value, disabled }: { value: string; disabled?: boolean }) => <input aria-label="smart-suggestion" value={value} disabled={disabled} readOnly />,
}));
vi.mock("../../../components/dfmea/StructureTree", () => ({ default: () => <div data-testid="dfmea-structure-tree" /> }));
vi.mock("../../../components/dfmea/ParameterDiagram", () => ({ default: () => <div data-testid="parameter-diagram" /> }));
vi.mock("../../../components/lessons/LessonsLearnedModal", () => ({ default: () => null }));
// 不 mock VersionHistoryTab — 用真实组件触发 onViewSnapshot
vi.mock("../../../components/version/CreateVersionModal", () => ({ default: () => null }));
vi.mock("../../../components/version/RollbackConfirmModal", () => ({ default: () => null }));
vi.mock("../../../components/version/VersionCompareView", () => ({ default: () => <div data-testid="version-compare" /> }));
vi.mock("../../../components/cross-links/RelatedCAPAList", () => ({ default: () => <div data-testid="related-capa" /> }));
vi.mock("../../../components/graph", () => ({
  GraphCanvas: () => <div data-testid="graph-canvas" />,
  GraphToolbar: () => <div data-testid="graph-toolbar" />,
  NodeDetailDrawer: () => null,
  GraphLegend: () => <div data-testid="graph-legend" />,
}));
vi.mock("../../../components/change-impact", () => ({ ImpactReportPanel: () => <div data-testid="impact-report" /> }));
vi.mock("../../../components/collaboration", () => ({
  CollaborationBar: () => <div data-testid="collaboration-bar" />,
  ActiveUserIndicator: () => <div data-testid="active-user" />,
  ConflictResolutionModal: () => null,
}));
vi.mock("../../../components/design", () => ({
  PageShell: ({ children, title, extra }: { children: React.ReactNode; title?: React.ReactNode; extra?: React.ReactNode }) => (
    <div>
      <h1>{title}</h1>
      <div>{extra}</div>
      {children}
    </div>
  ),
  DataCard: ({ children, title, extra }: { children: React.ReactNode; title?: React.ReactNode; extra?: React.ReactNode }) => (
    <section>
      <h2>{title}</h2>
      <div>{extra}</div>
      {children}
    </section>
  ),
  StatusBadge: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const node = (id: string, type: string, name = id): GraphNode => ({ id, type, name, severity: 0, occurrence: 0, detection: 0 });

function makeDoc(nodes: GraphNode[], edges: GraphEdge[]): FMEADocument {
  return {
    fmea_id: "fmea-1", document_no: "PFMEA-1", title: "doc", fmea_type: "PFMEA",
    product_line_code: "DC-DC-100", status: "draft", version: 1,
    graph_data: { nodes, edges, wizardScope: { wizard_completed: true } },
    lock_version: 1, created_by: "u1", created_at: "2026-06-18T00:00:00Z",
    updated_at: "2026-06-18T00:00:00Z", approved_by: null, approved_at: null,
  };
}

function renderEditor() {
  return render(
    <App>
      <MemoryRouter initialEntries={["/fmea/fmea-1"]}>
        <Routes><Route path="/fmea/:id" element={<FMEAEditorPage />} /></Routes>
      </MemoryRouter>
    </App>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.canEdit.mockReturnValue(true);
  mocks.getFMEA.mockResolvedValue(makeDoc([node("f1", "ProcessItemFunction", "当前功能")], []));
  mocks.listFMEAVersions.mockResolvedValue({
    items: [{ version_id: "v1", fmea_id: "fmea-1", major_no: 1, minor_no: 0, change_type: "approve", change_summary: "v1", created_by: "u1", created_at: "2026-06-18T00:00:00Z" }],
    total: 1, page: 1, page_size: 100,
  });
  mocks.getFMEAVersion.mockResolvedValue({
    version_id: "v1", fmea_id: "fmea-1", major_no: 1, minor_no: 0, change_type: "approve",
    change_summary: "v1", created_by: "u1", created_at: "2026-06-18T00:00:00Z",
    snapshot: {
      nodes: [
        node("f1", "ProcessItemFunction", "快照功能"),
        node("fm1", "FailureMode", "失效模式"),
      ],
      edges: [{ source: "f1", target: "fm1", type: "HAS_FAILURE_MODE" }],
    },
    sha256_hash: "abc",
  });
});

describe("FMEAEditorPage version snapshot", () => {
  it("loads version snapshot into read-only mode with banner", async () => {
    renderEditor();
    await waitFor(() => expect(mocks.getFMEA).toHaveBeenCalled());

    fireEvent.click(screen.getByText("tabs.versionHistory"));
    await waitFor(() => expect(mocks.listFMEAVersions).toHaveBeenCalled());
    const viewBtn = await screen.findByRole("button", { name: /history\.view/ });
    fireEvent.click(viewBtn);

    await waitFor(() => expect(mocks.getFMEAVersion).toHaveBeenCalledWith("fmea-1", 1, 0));
    await waitFor(() => expect(screen.getByText(/messages.viewingVersion/)).toBeInTheDocument());
    // 返回编辑器页签查看快照数据渲染的 function 列
    fireEvent.click(screen.getByText("tabs.editor"));
    // 快照功能名在失效分析表的 function 列 <div> 中渲染（非 input），用 getByText
    await waitFor(() => expect(screen.getByText("快照功能")).toBeInTheDocument());
    // 只读态未产生协作事件（注：未主动 focus 控件，此断言验证「无副作用」而非 guard 被触发）
    expect(mocks.startEditing).not.toHaveBeenCalled();
  });

  it("returns to current version on exit", async () => {
    renderEditor();
    await waitFor(() => expect(mocks.getFMEA).toHaveBeenCalled());
    fireEvent.click(screen.getByText("tabs.versionHistory"));
    const viewBtn = await screen.findByRole("button", { name: /history\.view/ });
    fireEvent.click(viewBtn);
    await waitFor(() => expect(screen.getByText(/messages.viewingVersion/)).toBeInTheDocument());

    fireEvent.click(screen.getByText("actions.exitVersion"));
    await waitFor(() => expect(mocks.getFMEA.mock.calls.length).toBeGreaterThanOrEqual(2));
    await waitFor(() => expect(screen.queryByText(/messages.viewingVersion/)).not.toBeInTheDocument());
  });
});

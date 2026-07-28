import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { App } from "antd";
import FMEAEditorPage from "./FMEAEditorPage";
import type { FMEADocument, GraphEdge, GraphNode } from "../../../types";

// Focused test for P2.3: the editor accumulates SmartSuggestionDropdown adoptions
// and forwards them (deduped by recommendation_id) in the updateFMEA payload.
// Mirrors the mocking strategy of FMEAEditorPage.test.tsx, but the dropdown mock
// captures each onSelect so the test can drive an adoption directly.

const mocks = vi.hoisted(() => ({
  getFMEA: vi.fn(),
  updateFMEA: vi.fn(),
  transitionFMEA: vi.fn(),
  canEdit: vi.fn(),
  warning: vi.fn(),
}));

// Capture the onSelect handlers keyed by triggerType so the test can invoke them.
const dropdown = vi.hoisted(() => ({
  handlers: {} as Record<string, (s: unknown) => void>,
}));

const dnd = vi.hoisted(() => ({
  onDragStart: null as ((e: unknown) => void) | null,
  onDragOver: null as ((e: unknown) => void) | null,
  onDragEnd: null as ((e: unknown) => void) | null,
  onDragCancel: null as (() => void) | null,
  activeId: null as string | null,
}));

vi.mock("@dnd-kit/core", () => ({
  DndContext: ({ children, onDragStart, onDragOver, onDragEnd, onDragCancel }: any) => {
    dnd.onDragStart = onDragStart;
    dnd.onDragOver = onDragOver;
    dnd.onDragEnd = onDragEnd;
    dnd.onDragCancel = onDragCancel;
    return children;
  },
  DragOverlay: ({ children }: any) => children,
  useDraggable: ({ id }: { id: string }) => ({
    attributes: {},
    listeners: {},
    setNodeRef: () => {},
    setActivatorNodeRef: () => {},
    isDragging: dnd.activeId === id,
  }),
  useDroppable: () => ({ setNodeRef: () => {}, isOver: false, rect: { top: 0, height: 40 } }),
  PointerSensor: function PointerSensor() {},
  useSensor: () => null,
  useSensors: () => null,
  closestCenter: () => null,
}));

vi.mock("antd", async () => {
  const actual = await vi.importActual<typeof import("antd")>("antd");
  return {
    ...actual,
    App: Object.assign(
      ({ children }: { children: React.ReactNode }) => <>{children}</>,
      { useApp: () => ({ message: { warning: mocks.warning, success: vi.fn(), error: vi.fn() }, modal: {}, notification: {} }) }
    ),
  };
});

vi.mock("../../../api/fmea", () => ({
  getFMEA: mocks.getFMEA,
  updateFMEA: mocks.updateFMEA,
  transitionFMEA: mocks.transitionFMEA,
}));

vi.mock("../../../api/specialCharacteristic", () => ({
  syncFromFMEA: vi.fn(),
  getSeverityWarnings: vi.fn().mockResolvedValue({ warnings: [] }),
}));

vi.mock("../../../api/lessonsLearned", () => ({
  getFMEALessons: vi.fn(),
}));

vi.mock("../../../api/graph", () => ({
  getImpactChain: vi.fn(),
  getCauseChain: vi.fn(),
  normalizeGraphData: vi.fn((data) => data),
}));

vi.mock("../../../api/changeImpact", () => ({
  analyzeChangeImpact: vi.fn(),
}));

vi.mock("../../../store/authStore", () => ({
  useAuthStore: (selector: (s: { user: unknown }) => unknown) => selector({ user: { user_id: "u1", role_key: "admin" } }),
}));

vi.mock("../../../hooks/usePermission", () => ({
  usePermission: () => ({
    canEdit: mocks.canEdit,
    canApprove: () => true,
  }),
}));

vi.mock("../../../hooks/useCollaboration", () => ({
  useCollaboration: () => ({
    activeUsers: [],
    startEditing: vi.fn(),
    stopEditing: vi.fn(),
    isSyncing: false,
  }),
}));

// Dropdown mock: capture onSelect per triggerType and render a marker input.
vi.mock("../../../components/dfmea/SmartSuggestionDropdown", () => ({
  default: ({ value, disabled, onSelect, triggerType }: any) => {
    dropdown.handlers[triggerType] = onSelect;
    return <input aria-label={`smart-suggestion-${triggerType}`} value={value} disabled={disabled} readOnly />;
  },
}));

vi.mock("../../../components/dfmea/StructureTree", () => ({ default: () => <div data-testid="dfmea-structure-tree" /> }));
vi.mock("../../../components/dfmea/ParameterDiagram", () => ({ default: () => <div data-testid="parameter-diagram" /> }));
vi.mock("../../../components/lessons/LessonsLearnedModal", () => ({ default: () => null }));
vi.mock("../../../components/version/VersionHistoryTab", () => ({ default: () => <div data-testid="version-history" /> }));
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
vi.mock("../../../components/change-impact", () => ({
  ImpactReportPanel: () => <div data-testid="impact-report" />,
}));
vi.mock("../../../components/collaboration", () => ({
  CollaborationBar: () => <div data-testid="collaboration-bar" />,
  ActiveUserIndicator: () => <div data-testid="active-user" />,
  ConflictResolutionModal: () => null,
}));
vi.mock("../../../components/design", () => ({
  PageShell: ({ children, title, extra, actions }: { children: React.ReactNode; title?: React.ReactNode; extra?: React.ReactNode; actions?: React.ReactNode }) => (
    <div>
      <h1>{title}</h1>
      <div>{extra}</div>
      <div>{actions}</div>
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
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

const Z = { severity: 0, occurrence: 0, detection: 0 };

function makeDoc(): FMEADocument {
  const psf: GraphNode = { id: "psf", type: "ProcessStepFunction", name: "准确贴装", classification: "CC", ...Z } as GraphNode;
  const nodes: GraphNode[] = [
    { id: "ps", type: "ProcessStep", name: "贴装", process_number: "OP10", ...Z } as GraphNode,
    psf,
    { id: "fm", type: "FailureMode", name: "贴装偏移", classification: "", ...Z } as GraphNode,
    { id: "fe", type: "FailureEffect", name: "功能丧失", severity: 8 } as GraphNode,
    { id: "fc", type: "FailureCause", name: "吸嘴磨损", occurrence: 4 } as GraphNode,
    { id: "pc", type: "PreventionControl", name: "校准" } as GraphNode,
    { id: "dc", type: "DetectionControl", name: "AOI", detection: 3 } as GraphNode,
  ];
  const edges: GraphEdge[] = [
    { source: "ps", target: "psf", type: "HAS_FUNCTION" },
    { source: "psf", target: "fm", type: "HAS_FAILURE_MODE" },
    { source: "fm", target: "fe", type: "EFFECT_OF" },
    { source: "fc", target: "fm", type: "CAUSE_OF" },
    { source: "fc", target: "pc", type: "PREVENTED_BY" },
    { source: "fc", target: "dc", type: "DETECTED_BY" },
  ];
  return {
    fmea_id: "fmea-1",
    document_no: "PFMEA-1",
    title: "PFMEA doc",
    fmea_type: "PFMEA",
    product_line_code: "DC-DC-100",
    status: "approved",
    lock_version: 1,
    graph_data: { nodes, edges, wizardScope: { wizard_completed: true } },
  } as unknown as FMEADocument;
}

function renderEditor() {
  return render(
    <App>
      <MemoryRouter initialEntries={["/fmea/fmea-1"]}>
        <Routes>
          <Route path="/fmea/:id" element={<FMEAEditorPage />} />
        </Routes>
      </MemoryRouter>
    </App>,
  );
}

describe("FMEAEditorPage AI suggestion adoption capture (P2.3)", () => {
  beforeEach(() => {
    mocks.canEdit.mockReturnValue(true);
    mocks.getFMEA.mockReset();
    mocks.updateFMEA.mockReset();
    dropdown.handlers = {};
  });

  async function renderReady(doc: FMEADocument) {
    mocks.getFMEA.mockResolvedValue(doc);
    mocks.updateFMEA.mockResolvedValue(doc);
    renderEditor();
    await waitFor(() => expect(mocks.getFMEA).toHaveBeenCalled());
    // Wait for the editor table to render (CC tag present) → dropdowns mounted.
    await waitFor(() => expect(screen.getAllByText("CC").length).toBeGreaterThan(0));
  }

  it("save payload includes adoptions entry with field_id/recommendation_id/adopted_text", async () => {
    const doc = makeDoc();
    await renderReady(doc);

    // Adopt a failure-mode suggestion (node id "fm").
    dropdown.handlers["failure_mode"]({
      name: "贴装偏移过大",
      source: "llm",
      recommendation_id: "rec-fm-1",
    });

    fireEvent.click(screen.getByRole("button", { name: /actions\.save/i }));
    await waitFor(() => expect(mocks.updateFMEA).toHaveBeenCalled());

    const [, payload] = mocks.updateFMEA.mock.calls[0];
    expect(payload.adoptions).toBeDefined();
    expect(payload.adoptions).toHaveLength(1);
    expect(payload.adoptions[0]).toEqual({
      field_id: "fm",
      recommendation_id: "rec-fm-1",
      source: "llm",
      stage_index: 0,
      adopted_text: "贴装偏移过大",
    });
  });

  it("dedupes adoptions by recommendation_id (last-write-wins)", async () => {
    const doc = makeDoc();
    await renderReady(doc);

    dropdown.handlers["failure_mode"]({ name: "first", source: "llm", recommendation_id: "rec-dup" });
    dropdown.handlers["failure_cause"]({ name: "second", source: "graph", recommendation_id: "rec-dup" });

    fireEvent.click(screen.getByRole("button", { name: /actions\.save/i }));
    await waitFor(() => expect(mocks.updateFMEA).toHaveBeenCalled());

    const [, payload] = mocks.updateFMEA.mock.calls[0];
    expect(payload.adoptions).toHaveLength(1);
    expect(payload.adoptions[0].adopted_text).toBe("second");
    expect(payload.adoptions[0].field_id).toBe("fc");
  });

  it("skips adoption when recommendation_id is empty and omits adoptions key", async () => {
    const doc = makeDoc();
    await renderReady(doc);

    // No recommendation_id → no adoption recorded.
    dropdown.handlers["failure_mode"]({ name: "no-id", source: "llm" });

    fireEvent.click(screen.getByRole("button", { name: /actions\.save/i }));
    await waitFor(() => expect(mocks.updateFMEA).toHaveBeenCalled());

    const [, payload] = mocks.updateFMEA.mock.calls[0];
    expect(payload.adoptions).toBeUndefined();
  });

  it("clears the accumulator after a successful save", async () => {
    const doc = makeDoc();
    await renderReady(doc);

    dropdown.handlers["failure_mode"]({ name: "once", source: "llm", recommendation_id: "rec-once" });
    fireEvent.click(screen.getByRole("button", { name: /actions\.save/i }));
    await waitFor(() => expect(mocks.updateFMEA).toHaveBeenCalledTimes(1));

    // Second save without a new adoption → no adoptions key.
    fireEvent.click(screen.getByRole("button", { name: /actions\.save/i }));
    await waitFor(() => expect(mocks.updateFMEA).toHaveBeenCalledTimes(2));
    const [, payload2] = mocks.updateFMEA.mock.calls[1];
    expect(payload2.adoptions).toBeUndefined();
  });
});

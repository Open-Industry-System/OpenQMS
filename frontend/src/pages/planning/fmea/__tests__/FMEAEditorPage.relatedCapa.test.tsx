import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { App } from "antd";
import FMEAEditorPage from "../FMEAEditorPage";
import type { FMEADocument, GraphEdge, GraphNode } from "../../../../types";

const mocks = vi.hoisted(() => ({
  getFMEA: vi.fn(),
  updateFMEA: vi.fn(),
  transitionFMEA: vi.fn(),
  canEdit: vi.fn(),
  warning: vi.fn(),
  relatedCapaProps: null as null | { fmeaId: string; fmeaNodeId?: string },
}));

const dnd = vi.hoisted(() => ({
  onDragStart: null as ((e: any) => void) | null,
  onDragOver: null as ((e: any) => void) | null,
  onDragEnd: null as ((e: any) => void) | null,
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

vi.mock("../../../../api/fmea", () => ({
  getFMEA: mocks.getFMEA,
  updateFMEA: mocks.updateFMEA,
  transitionFMEA: mocks.transitionFMEA,
}));
vi.mock("../../../../api/specialCharacteristic", () => ({
  syncFromFMEA: vi.fn(),
  getSeverityWarnings: vi.fn().mockResolvedValue({ warnings: [] }),
}));
vi.mock("../../../../api/lessonsLearned", () => ({ getFMEALessons: vi.fn() }));
vi.mock("../../../../api/graph", () => ({
  getImpactChain: vi.fn(),
  getCauseChain: vi.fn(),
  normalizeGraphData: vi.fn((data) => data),
}));
vi.mock("../../../../api/changeImpact", () => ({ analyzeChangeImpact: vi.fn() }));
vi.mock("../../../../store/authStore", () => ({
  useAuthStore: (selector: (s: { user: unknown }) => unknown) =>
    selector({ user: { user_id: "u1", role_key: "admin" } }),
}));
vi.mock("../../../../hooks/usePermission", () => ({
  usePermission: () => ({ canEdit: mocks.canEdit, canApprove: () => true }),
}));
vi.mock("../../../../hooks/useCollaboration", () => ({
  useCollaboration: () => ({
    activeUsers: [],
    startEditing: vi.fn(),
    stopEditing: vi.fn(),
    isSyncing: false,
  }),
}));
vi.mock("../../../../components/dfmea/SmartSuggestionDropdown", () => ({
  default: ({ value, disabled }: { value: string; disabled?: boolean }) => (
    <input aria-label="smart-suggestion" value={value} disabled={disabled} readOnly />
  ),
}));
vi.mock("../../../../components/dfmea/StructureTree", () => ({ default: () => <div data-testid="dfmea-structure-tree" /> }));
vi.mock("../../../../components/dfmea/ParameterDiagram", () => ({ default: () => <div data-testid="parameter-diagram" /> }));
vi.mock("../../../../components/lessons/LessonsLearnedModal", () => ({ default: () => null }));
vi.mock("../../../../components/version/VersionHistoryTab", () => ({ default: () => <div data-testid="version-history" /> }));
vi.mock("../../../../components/version/CreateVersionModal", () => ({ default: () => null }));
vi.mock("../../../../components/version/RollbackConfirmModal", () => ({ default: () => null }));
vi.mock("../../../../components/version/VersionCompareView", () => ({ default: () => <div data-testid="version-compare" /> }));
vi.mock("../../../../components/cross-links/RelatedCAPAList", () => ({
  default: (props: { fmeaId: string; fmeaNodeId?: string }) => {
    mocks.relatedCapaProps = props;
    return (
      <div data-testid="related-capa" data-fmea-node-id={props.fmeaNodeId ?? ""}>
        related-capa:{props.fmeaNodeId ?? "none"}
      </div>
    );
  },
}));
vi.mock("../../../../components/graph", () => ({
  GraphCanvas: ({ onNodeClick }: { onNodeClick?: (n: { id: string }) => void }) => (
    <div data-testid="graph-canvas">
      <button type="button" data-testid="graph-node-cause-1" onClick={() => onNodeClick?.({ id: "cause-1" })}>
        cause-1
      </button>
    </div>
  ),
  GraphToolbar: () => <div data-testid="graph-toolbar" />,
  NodeDetailDrawer: () => null,
  GraphLegend: () => <div data-testid="graph-legend" />,
}));
vi.mock("../../../../components/change-impact", () => ({
  ImpactReportPanel: () => <div data-testid="impact-report" />,
}));
vi.mock("../../../../components/collaboration", () => ({
  CollaborationBar: () => <div data-testid="collaboration-bar" />,
  ActiveUserIndicator: () => <div data-testid="active-user" />,
  ConflictResolutionModal: () => null,
}));
vi.mock("../../../../components/design", () => ({
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
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

const Z = { severity: 0, occurrence: 0, detection: 0 };

function makeDoc(): FMEADocument {
  const nodes: GraphNode[] = [
    { id: "ps", type: "ProcessStep", name: "贴装", process_number: "OP10", ...Z } as GraphNode,
    { id: "fn1", type: "ProcessStepFunction", name: "准确贴装", ...Z } as GraphNode,
    { id: "fm", type: "FailureMode", name: "贴装偏移", ...Z } as GraphNode,
    { id: "cause-1", type: "FailureCause", name: "Cause", ...Z } as GraphNode,
  ];
  const edges: GraphEdge[] = [
    { source: "ps", target: "fn1", type: "HAS_FUNCTION" },
    { source: "fn1", target: "fm", type: "HAS_FAILURE_MODE" },
    { source: "cause-1", target: "fm", type: "CAUSE_OF" },
  ];
  return {
    fmea_id: "f1",
    document_no: "PFMEA-1",
    title: "PFMEA doc",
    fmea_type: "PFMEA",
    product_line_code: "DC-DC-100",
    status: "approved",
    lock_version: 1,
    graph_data: { nodes, edges, wizardScope: { wizard_completed: true } },
  } as unknown as FMEADocument;
}

function renderEditor(initialEntry: string) {
  return render(
    <App>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/fmea/:id" element={<FMEAEditorPage />} />
          <Route path="/fmea/wizard/:id" element={<div data-testid="dfmea-wizard-page">DFMEA Wizard</div>} />
          <Route path="/fmea/pfmea-wizard/:id" element={<div data-testid="pfmea-wizard-page">PFMEA Wizard</div>} />
        </Routes>
      </MemoryRouter>
    </App>
  );
}

describe("FMEAEditorPage activeRelatedNodeId", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.relatedCapaProps = null;
    mocks.canEdit.mockReturnValue(true);
    mocks.getFMEA.mockResolvedValue(makeDoc());
  });

  it("passes highlightNode from URL into RelatedCAPAList", async () => {
    renderEditor("/fmea/f1?highlightNode=cause-1");
    await waitFor(() => expect(mocks.getFMEA).toHaveBeenCalled());
    const tab = await screen.findByText("tabs.relatedCapa");
    fireEvent.click(tab);
    await waitFor(() => {
      expect(mocks.relatedCapaProps?.fmeaNodeId).toBe("cause-1");
    });
  });

  it("updates RelatedCAPAList when graph node is selected", async () => {
    renderEditor("/fmea/f1");
    await waitFor(() => expect(mocks.getFMEA).toHaveBeenCalled());

    // open graph tab then click node
    fireEvent.click(await screen.findByText("tabs.graph"));
    await waitFor(() => expect(screen.getByTestId("graph-node-cause-1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("graph-node-cause-1"));

    fireEvent.click(await screen.findByText("tabs.relatedCapa"));
    await waitFor(() => {
      expect(mocks.relatedCapaProps?.fmeaNodeId).toBe("cause-1");
    });
  });
});

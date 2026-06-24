import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { App } from "antd";
import FMEAEditorPage from "./FMEAEditorPage";
import type { FMEADocument, GraphEdge, GraphNode } from "../../../types";

// ============================================================================
// 浏览器手动测试清单（jsdom 无法覆盖原生 @dnd-kit pointer/collision 真实行为）：
//   1. 连续拖两次：第一次 swap 后，立刻再拖另一个节点，应能正常排序。
//   2. 取消拖拽后再拖：拖出树外或按 ESC 取消，状态复位，再拖正常。
//   3. 跨父级非法拖：拖到不同父级的节点，显示红色非法框 + 松手弹「仅支持同级节点排序」。
//   4. viewer 不可拖：无编辑权限时 grip 不渲染。
//   5. 同级合法拖：拖到同级节点的上/下四分之一，显示青色 before/after 线，松手提交排序。
//   6. 被拖节点自身子树折叠 + 源行降权：拖拽时被拖节点的子树折叠（无空白）、被拖源行变淡；
//      overlay 跟随指针不错位（拖第 2/3 个节点也应与指针对齐）。同级子树保持展开
//      （折叠同级会位移被拖节点 → overlay 错位）。
// 注：@dnd-kit 拖拽源用 transform/overlay 管，DOM 不按视觉效果实时改；如需调整 live
// preview 行为，用 @dnd-kit 的 sortable/transform，不要回到原生 HTML5 DnD。
// ============================================================================

const mocks = vi.hoisted(() => ({
  getFMEA: vi.fn(),
  updateFMEA: vi.fn(),
  transitionFMEA: vi.fn(),
  canEdit: vi.fn(),
  warning: vi.fn(),
}));

// @dnd-kit/core mock：捕获 DndContext 的 handler 供测试直接驱动（jsdom 无法真实激活
// PointerSensor + collision），stub useDraggable/useDroppable。这样测试验证的是「我们的
// 拖拽逻辑（reorder/marker/collapse/warning）」，@dnd-kit 真实连线靠浏览器手测清单。
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

vi.mock("../../../components/dfmea/SmartSuggestionDropdown", () => ({
  default: ({ value, disabled }: { value: string; disabled?: boolean }) => <input aria-label="smart-suggestion" value={value} disabled={disabled} readOnly />,
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

function makeDoc(fmeaType: "PFMEA" | "DFMEA", stepFuncClass: string, fmClass: string): FMEADocument {
  // PFMEA: ProcessStepFunction carries classification (CC/SC); FailureMode.classification empty.
  // DFMEA: FailureMode carries classification (Filter Code); ProcessStepFunction has none.
  const psf: GraphNode = {
    id: "psf", type: "ProcessStepFunction", name: "准确贴装",
    classification: fmeaType === "PFMEA" ? stepFuncClass : "", ...Z,
  } as GraphNode;
  const fm: GraphNode = {
    id: "fm", type: "FailureMode", name: "贴装偏移",
    classification: fmClass, ...Z,
  } as GraphNode;
  const nodes: GraphNode[] = [
    { id: "ps", type: "ProcessStep", name: "贴装", process_number: "OP10", ...Z } as GraphNode,
    psf,
    fm,
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
    document_no: `${fmeaType}-1`,
    title: `${fmeaType} doc`,
    fmea_type: fmeaType,
    product_line_code: "DC-DC-100",
    status: "approved",
    lock_version: 1,
    graph_data: { nodes, edges, wizardScope: { wizard_completed: true } },
  } as unknown as FMEADocument;
}

function renderEditor(initialEntry = "/fmea/fmea-1") {
  return render(
    <App>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/fmea/:id" element={<FMEAEditorPage />} />
          <Route path="/fmea/wizard/:id" element={<div data-testid="dfmea-wizard-page">DFMEA Wizard</div>} />
          <Route path="/fmea/pfmea-wizard/:id" element={<div data-testid="pfmea-wizard-page">PFMEA Wizard</div>} />
        </Routes>
      </MemoryRouter>
    </App>,
  );
}

describe("FMEAEditorPage Class column", () => {
  beforeEach(() => {
    // Default: admin can edit.
    // (mocks.canEdit is the hoisted vi.fn() from the copied harness.)
    mocks.canEdit.mockReturnValue(true);
    mocks.getFMEA.mockReset();
  });

  it("PFMEA: Class column is read-only and shows CC from ProcessStepFunction.classification", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc("PFMEA", "CC", ""));
    renderEditor();
    await waitFor(() => expect(mocks.getFMEA).toHaveBeenCalled());
    // The PFMEA Class cell renders a read-only Tag with the aggregated label 'CC'.
    // (FailureMode.classification is '' here, so the old code would have shown '-' — this asserts the new behavior.)
    await waitFor(() => {
      expect(screen.getAllByText("CC").length).toBeGreaterThan(0);
    });
  });

  it("PFMEA: legacy docs fallback to FailureMode.classification when ProcessStepFunction has none", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc("PFMEA", "", "CC"));
    renderEditor();
    await waitFor(() => expect(mocks.getFMEA).toHaveBeenCalled());
    await waitFor(() => {
      expect(screen.getAllByText("CC").length).toBeGreaterThan(0);
    });
  });

  it("PFMEA: shows '-' when no CC and no SC", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc("PFMEA", "", ""));
    renderEditor();
    await waitFor(() => expect(mocks.getFMEA).toHaveBeenCalled());
    // No CC/SC tag content; aggregateSpecialCharacteristic returns '-'. Assert a '-' cell is present
    // and no 'CC'/'SC' tag is rendered for the class column.
    await waitFor(() => {
      // the read-only branch renders a Tag with label '-'
      expect(screen.getAllByText("-").length).toBeGreaterThan(0);
    });
    expect(screen.queryByText("CC")).toBeNull();
    expect(screen.queryByText("SC")).toBeNull();
  });

  it("PFMEA: incomplete draft redirects to PFMEA wizard and does not render editor table", async () => {
    const pfmeaDraft: FMEADocument = {
      ...makeDoc("PFMEA", "", ""),
      status: "draft",
      graph_data: { nodes: [], edges: [], wizardScope: { wizard_completed: false } },
    } as unknown as FMEADocument;
    mocks.getFMEA.mockResolvedValue(pfmeaDraft);
    renderEditor("/fmea/fmea-1");
    await waitFor(() => expect(mocks.getFMEA).toHaveBeenCalled());
    await waitFor(() => {
      expect(screen.getByTestId("pfmea-wizard-page")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("dfmea-structure-tree")).toBeNull();
    expect(screen.queryByTestId("parameter-diagram")).toBeNull();
  });

  it("DFMEA: incomplete draft redirects to DFMEA wizard and does not render editor table", async () => {
    const dfmeaDraft: FMEADocument = {
      ...makeDoc("DFMEA", "", ""),
      status: "draft",
      graph_data: { nodes: [], edges: [], wizardScope: { wizard_completed: false } },
    } as unknown as FMEADocument;
    mocks.getFMEA.mockResolvedValue(dfmeaDraft);
    renderEditor("/fmea/fmea-1");
    await waitFor(() => expect(mocks.getFMEA).toHaveBeenCalled());
    await waitFor(() => {
      expect(screen.getByTestId("dfmea-wizard-page")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("dfmea-structure-tree")).toBeNull();
    expect(screen.queryByTestId("parameter-diagram")).toBeNull();
  });

  it("DFMEA: Filter Code column unchanged (editable Select bound to FailureMode.classification)", async () => {
    // DFMEA: classification lives on FailureMode; the Select must still be present and editable.
    mocks.getFMEA.mockResolvedValue(makeDoc("DFMEA", "", "CC"));
    renderEditor();
    await waitFor(() => expect(mocks.getFMEA).toHaveBeenCalled());
    // The DFMEA branch renders the Select (role=combobox) with the CC option.
    await waitFor(() => {
      expect(screen.getAllByRole("combobox").length).toBeGreaterThan(0);
    });
    // And the Select's CC option is selectable (Filter Code still editable on FailureMode).
    expect(screen.getAllByText("CC").length).toBeGreaterThan(0);
  });
});

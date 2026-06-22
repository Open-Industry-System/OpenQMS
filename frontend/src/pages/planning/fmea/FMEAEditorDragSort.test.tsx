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

const node = (id: string, type: string, name = id): GraphNode => ({ id, type, name, severity: 0, occurrence: 0, detection: 0 });

function makeDoc(fmeaType: "PFMEA" | "DFMEA", nodes: GraphNode[], edges: GraphEdge[]): FMEADocument {
  return {
    fmea_id: "fmea-1",
    document_no: `${fmeaType}-1`,
    title: `${fmeaType} doc`,
    fmea_type: fmeaType,
    product_line_code: "DC-DC-100",
    status: "draft",
    version: 1,
    graph_data: { nodes, edges, wizardScope: { wizard_completed: true } },
    lock_version: 1,
    created_by: "u1",
    created_at: "2026-06-18T00:00:00Z",
    updated_at: "2026-06-18T00:00:00Z",
    approved_by: null,
    approved_at: null,
  };
}

function renderEditor() {
  return render(
    <App>
      <MemoryRouter initialEntries={["/fmea/fmea-1"]}>
        <Routes>
          <Route path="/fmea/:id" element={<FMEAEditorPage />} />
        </Routes>
      </MemoryRouter>
    </App>
  );
}

// 落点 rect：oTop=0, oHeight=40（与原 rect mock 一致）；aTop 即原 clientY 语义：
//   aTop<10 → before, 10..30 → inside, >30 → after。
const O_TOP = 0, O_HEIGHT = 40;
function activeRect(aTop: number) { return { current: { translated: { top: aTop } } }; }
function overRect() { return { top: O_TOP, height: O_HEIGHT }; }

function driveDragOver(dragId: string, overId: string, aTop: number) {
  dnd.activeId = dragId;
  dnd.onDragStart?.({ active: { id: dragId } });
  dnd.onDragOver?.({ active: { id: dragId, rect: activeRect(aTop) }, over: { id: overId, rect: overRect() } });
}
function driveEnd(dragId: string, overId: string, aTop: number) {
  dnd.onDragEnd?.({ active: { id: dragId, rect: activeRect(aTop) }, over: { id: overId, rect: overRect() } });
  dnd.activeId = null;
}
function driveDrag(dragId: string, overId: string, aTop: number) {
  driveDragOver(dragId, overId, aTop);
  driveEnd(dragId, overId, aTop);
}
function driveCancel() {
  dnd.onDragCancel?.();
  dnd.activeId = null;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.canEdit.mockReturnValue(true);
  mocks.updateFMEA.mockResolvedValue({});
  mocks.transitionFMEA.mockResolvedValue({});
  dnd.activeId = null;
  dnd.onDragStart = null;
  dnd.onDragOver = null;
  dnd.onDragEnd = null;
  dnd.onDragCancel = null;
});

describe("FMEAEditorPage PFMEA structure drag sorting", () => {
  it("enables dragging for editable PFMEA structure nodes", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [node("pi", "ProcessItem"), node("ps1", "ProcessStep"), node("ps2", "ProcessStep")],
      [
        { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
        { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
      ],
    ));

    renderEditor();

    const handle = await screen.findByTestId("fmea-structure-drag-handle-ps1");
    expect(handle).toBeInTheDocument();
  });

  it("does not enable dragging when canEdit('fmea') is false", async () => {
    mocks.canEdit.mockReturnValue(false);
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [node("pi", "ProcessItem"), node("ps1", "ProcessStep")],
      [{ source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" }],
    ));

    renderEditor();

    const ps1 = await screen.findByTestId("fmea-structure-node-ps1");
    expect(ps1).toBeInTheDocument();
    expect(screen.queryByTestId("fmea-structure-drag-handle-ps1")).toBeNull();
  });

  it("enables dragging for DFMEA documents", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "DFMEA",
      [node("sys", "System"), node("sub", "Subsystem")],
      [{ source: "sys", target: "sub", type: "HAS_PROCESS_STEP" }],
    ));

    renderEditor();

    const handle = await screen.findByTestId("fmea-structure-drag-handle-sub");
    expect(handle).toBeInTheDocument();
  });

  it("reorders DFMEA System roots and keeps table rows in structure order", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "DFMEA",
      [
        node("sys1", "System", "系统1"),
        node("fm1", "FailureMode", "失效1"),
        node("sys2", "System", "系统2"),
        node("fm2", "FailureMode", "失效2"),
      ],
      [
        { source: "sys1", target: "fm1", type: "HAS_FAILURE_MODE" },
        { source: "sys2", target: "fm2", type: "HAS_FAILURE_MODE" },
      ],
    ));

    renderEditor();

    await screen.findByTestId("fmea-structure-node-sys1");

    driveDrag("sys2", "sys1", 1);

    await waitFor(() => {
      expect(screen.getAllByTestId(/^fmea-structure-node-/).map((el) => el.getAttribute("data-testid"))).toEqual([
        "fmea-structure-node-sys2",
        "fmea-structure-node-sys1",
      ]);
    });
    expect(Array.from(document.querySelectorAll("tr[data-row-key]")).map((row) => row.getAttribute("data-row-key"))).toEqual([
      "row_sys2_fm2",
      "row_sys1_fm1",
    ]);
  });

  it("reorders legal same-parent drops and keeps table rows in structure order", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [
        node("pi", "ProcessItem", "过程"),
        node("ps1", "ProcessStep", "OP10"),
        node("fm1", "FailureMode", "失效1"),
        node("ps2", "ProcessStep", "OP20"),
        node("fm2", "FailureMode", "失效2"),
      ],
      [
        { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
        { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
        { source: "ps1", target: "fm1", type: "HAS_FAILURE_MODE" },
        { source: "ps2", target: "fm2", type: "HAS_FAILURE_MODE" },
      ],
    ));

    renderEditor();

    await screen.findByTestId("fmea-structure-node-ps1");

    driveDrag("ps2", "ps1", 1);

    await waitFor(() => {
      expect(screen.getAllByTestId(/^fmea-structure-node-/).map((el) => el.getAttribute("data-testid"))).toEqual([
        "fmea-structure-node-pi",
        "fmea-structure-node-ps2",
        "fmea-structure-node-ps1",
      ]);
    });
    expect(Array.from(document.querySelectorAll("tr[data-row-key]")).map((row) => row.getAttribute("data-row-key"))).toEqual([
      "row_ps2_fm2",
      "row_ps1_fm1",
    ]);
  });

  it("rejects an inside drop without reordering and shows a warning", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [node("pi", "ProcessItem"), node("ps1", "ProcessStep"), node("ps2", "ProcessStep")],
      [
        { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
        { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
      ],
    ));

    renderEditor();

    await screen.findByTestId("fmea-structure-node-ps1");

    driveDrag("ps2", "ps1", 20);

    await waitFor(() => expect(mocks.warning).toHaveBeenCalledWith("messages.sameLevelSortOnly"));
    expect(screen.getAllByTestId(/^fmea-structure-node-/).map((el) => el.getAttribute("data-testid"))).toEqual([
      "fmea-structure-node-pi",
      "fmea-structure-node-ps1",
      "fmea-structure-node-ps2",
    ]);
  });

  it("shows a valid before marker on a legal same-parent drag-over", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [node("pi", "ProcessItem"), node("ps1", "ProcessStep"), node("ps2", "ProcessStep")],
      [
        { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
        { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
      ],
    ));

    renderEditor();

    const ps1 = await screen.findByTestId("fmea-structure-node-ps1");

    driveDragOver("ps2", "ps1", 1);

    await waitFor(() => expect(ps1.getAttribute("data-drag-state")).toBe("before"));
  });

  it("shows an invalid marker on a cross-parent drag-over and clears it on drop", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [
        node("pi1", "ProcessItem"),
        node("pi2", "ProcessItem"),
        node("ps1", "ProcessStep"),
        node("ps2", "ProcessStep"),
      ],
      [
        { source: "pi1", target: "ps1", type: "HAS_PROCESS_STEP" },
        { source: "pi2", target: "ps2", type: "HAS_PROCESS_STEP" },
      ],
    ));

    renderEditor();

    const ps1 = await screen.findByTestId("fmea-structure-node-ps1");

    driveDragOver("ps2", "ps1", 1);
    await waitFor(() => expect(ps1.getAttribute("data-drag-state")).toBe("invalid"));

    driveEnd("ps2", "ps1", 1);
    await waitFor(() => expect(mocks.warning).toHaveBeenCalledWith("messages.sameLevelSortOnly"));
    expect(ps1.getAttribute("data-drag-state")).toBeNull();
  });

  it("does not make the row itself draggable (editing a name must not start a drag)", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [node("pi", "ProcessItem"), node("ps1", "ProcessStep")],
      [{ source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" }],
    ));
    renderEditor();
    const ps1 = await screen.findByTestId("fmea-structure-node-ps1");
    expect(ps1).not.toHaveAttribute("draggable");
    const handle = await screen.findByTestId("fmea-structure-drag-handle-ps1");
    expect(handle).toBeInTheDocument();
  });

  it("renders a drag overlay for the dragged row", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [node("pi", "ProcessItem"), node("ps1", "ProcessStep"), node("ps2", "ProcessStep")],
      [
        { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
        { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
      ],
    ));
    renderEditor();
    await screen.findByTestId("fmea-structure-node-ps2");

    driveDragOver("ps2", "ps1", 1);
    const overlay = await screen.findByTestId("fmea-structure-drag-overlay-ps2");
    // overlay renders the dragged row's name (whole-row content, not just a placeholder)
    expect(overlay).toHaveTextContent("ps2");

    driveEnd("ps2", "ps1", 1);
    await waitFor(() => {
      expect(screen.queryByTestId("fmea-structure-drag-overlay-ps2")).toBeNull();
    });
  });

  it("shows a valid after marker on a legal same-parent drag-over", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [node("pi", "ProcessItem"), node("ps1", "ProcessStep"), node("ps2", "ProcessStep")],
      [
        { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
        { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
      ],
    ));
    renderEditor();
    const ps1 = await screen.findByTestId("fmea-structure-node-ps1");
    driveDragOver("ps2", "ps1", 35); // > 0.75*40 → after
    await waitFor(() => expect(ps1.getAttribute("data-drag-state")).toBe("after"));
  });

  it("resets drag state on cancel and allows a subsequent drag", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [node("pi", "ProcessItem"), node("ps1", "ProcessStep"), node("ps2", "ProcessStep")],
      [
        { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
        { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
      ],
    ));
    renderEditor();
    const order = () => screen.getAllByTestId(/^fmea-structure-node-/).map((el) => el.getAttribute("data-testid"));
    await screen.findByTestId("fmea-structure-node-ps1");

    // start a drag (preview marker + overlay + collapse), then cancel
    driveDragOver("ps2", "ps1", 1);
    await waitFor(() => expect(screen.getByTestId("fmea-structure-drag-overlay-ps2")).toBeInTheDocument());
    driveCancel();

    // state fully reset: no overlay, no marker, original order intact
    await waitFor(() => expect(screen.queryByTestId("fmea-structure-drag-overlay-ps2")).toBeNull());
    expect(order()).toEqual(["fmea-structure-node-pi", "fmea-structure-node-ps1", "fmea-structure-node-ps2"]);

    // a subsequent drag still works (regression: drag state must not stay stuck)
    driveDrag("ps2", "ps1", 1);
    await waitFor(() => expect(order()).toEqual(["fmea-structure-node-pi", "fmea-structure-node-ps2", "fmea-structure-node-ps1"]));
  });

  it("allows a second drag immediately after a first swap (regression for post-swap drag break)", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [node("pi", "ProcessItem"), node("ps1", "ProcessStep"), node("ps2", "ProcessStep"), node("ps3", "ProcessStep")],
      [
        { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
        { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
        { source: "pi", target: "ps3", type: "HAS_PROCESS_STEP" },
      ],
    ));
    renderEditor();
    const order = () => screen.getAllByTestId(/^fmea-structure-node-/).map((el) => el.getAttribute("data-testid"));
    await screen.findByTestId("fmea-structure-node-ps1");

    // first swap: ps2 before ps1
    driveDrag("ps2", "ps1", 1);
    await waitFor(() => expect(order()).toEqual([
      "fmea-structure-node-pi", "fmea-structure-node-ps2", "fmea-structure-node-ps1", "fmea-structure-node-ps3",
    ]));

    // second swap immediately after: ps3 before ps2
    driveDrag("ps3", "ps2", 1);
    await waitFor(() => expect(order()).toEqual([
      "fmea-structure-node-pi", "fmea-structure-node-ps3", "fmea-structure-node-ps2", "fmea-structure-node-ps1",
    ]));
  });

  it("dims the dragged source row during drag", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [node("pi", "ProcessItem"), node("ps1", "ProcessStep"), node("ps2", "ProcessStep")],
      [
        { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
        { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
      ],
    ));
    renderEditor();
    const ps2 = await screen.findByTestId("fmea-structure-node-ps2");
    expect(ps2.style.opacity).toBe("");
    driveDragOver("ps2", "ps1", 1);
    await waitFor(() => expect(ps2.style.opacity).toBe("0.3"));
    driveEnd("ps2", "ps1", 1);
    await waitFor(() => expect(ps2.style.opacity).toBe(""));
  });

  it("live-previews sibling shift during drag-over and commits on drop", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [node("pi", "ProcessItem"), node("ps1", "ProcessStep"), node("ps2", "ProcessStep")],
      [
        { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
        { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
      ],
    ));
    renderEditor();
    const order = () => screen.getAllByTestId(/^fmea-structure-node-/).map((el) => el.getAttribute("data-testid"));
    await screen.findByTestId("fmea-structure-node-ps1");
    expect(order()).toEqual(["fmea-structure-node-pi", "fmea-structure-node-ps1", "fmea-structure-node-ps2"]);

    // during drag-over (before drop): siblings shift to preview the reorder
    driveDragOver("ps2", "ps1", 1);
    await waitFor(() => expect(order()).toEqual(["fmea-structure-node-pi", "fmea-structure-node-ps2", "fmea-structure-node-ps1"]));

    // drop commits the previewed order
    driveEnd("ps2", "ps1", 1);
    await waitFor(() => expect(order()).toEqual(["fmea-structure-node-pi", "fmea-structure-node-ps2", "fmea-structure-node-ps1"]));
  });

  it("reverts the live preview when the drag is cancelled", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [node("pi", "ProcessItem"), node("ps1", "ProcessStep"), node("ps2", "ProcessStep")],
      [
        { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
        { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
      ],
    ));
    renderEditor();
    const order = () => screen.getAllByTestId(/^fmea-structure-node-/).map((el) => el.getAttribute("data-testid"));
    await screen.findByTestId("fmea-structure-node-ps1");

    driveDragOver("ps2", "ps1", 1);
    await waitFor(() => expect(order()).toEqual(["fmea-structure-node-pi", "fmea-structure-node-ps2", "fmea-structure-node-ps1"]));

    driveCancel();
    await waitFor(() => expect(order()).toEqual(["fmea-structure-node-pi", "fmea-structure-node-ps1", "fmea-structure-node-ps2"]));
  });

  it("clears the live preview over an invalid (cross-parent) target", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [
        node("pi1", "ProcessItem"), node("pi2", "ProcessItem"),
        node("ps1", "ProcessStep"), node("ps2", "ProcessStep"),
      ],
      [
        { source: "pi1", target: "ps1", type: "HAS_PROCESS_STEP" },
        { source: "pi2", target: "ps2", type: "HAS_PROCESS_STEP" },
      ],
    ));
    renderEditor();
    const order = () => screen.getAllByTestId(/^fmea-structure-node-/).map((el) => el.getAttribute("data-testid"));
    const ps1 = await screen.findByTestId("fmea-structure-node-ps1");
    const ps2 = await screen.findByTestId("fmea-structure-node-ps2");
    // first preview a valid same-parent shift
    driveDragOver("ps1", "ps1", 35); // self after → valid no-op (changed:false) → preview null, order unchanged
    expect(order()).toEqual([
      "fmea-structure-node-pi1", "fmea-structure-node-ps1",
      "fmea-structure-node-pi2", "fmea-structure-node-ps2",
    ]);
    // cross-parent over ps2 (under pi2) → invalid, no preview shift, invalid marker on ps2
    driveDragOver("ps1", "ps2", 1);
    await waitFor(() => expect(ps2.getAttribute("data-drag-state")).toBe("invalid"));
    expect(ps1.getAttribute("data-drag-state")).toBeNull();
    expect(order()).toEqual([
      "fmea-structure-node-pi1", "fmea-structure-node-ps1",
      "fmea-structure-node-pi2", "fmea-structure-node-ps2",
    ]);
  });

  it("hides the dragged node's descendants during drag", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [node("pi", "ProcessItem"), node("ps1", "ProcessStep"), node("ps2", "ProcessStep")],
      [
        { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
        { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
      ],
    ));
    renderEditor();
    await screen.findByTestId("fmea-structure-drag-handle-pi");
    expect(screen.getByTestId("fmea-structure-node-ps1")).toBeInTheDocument();
    driveDragOver("pi", "ps1", 1);
    await waitFor(() => {
      expect(screen.queryByTestId("fmea-structure-node-ps1")).toBeNull();
      expect(screen.queryByTestId("fmea-structure-node-ps2")).toBeNull();
    });
  });

  it("collapses only the dragged node's own subtree (siblings stay expanded)", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [
        node("pi1", "ProcessItem"), node("pi2", "ProcessItem"),
        node("ps1", "ProcessStep"), node("ps2", "ProcessStep"), node("ps3", "ProcessStep"),
        node("we1", "ProcessWorkElement"), node("we2", "ProcessWorkElement"),
        node("ps4", "ProcessStep"),
      ],
      [
        { source: "pi1", target: "ps1", type: "HAS_PROCESS_STEP" },
        { source: "pi1", target: "ps2", type: "HAS_PROCESS_STEP" },
        { source: "pi1", target: "ps3", type: "HAS_PROCESS_STEP" },
        { source: "ps1", target: "we1", type: "HAS_WORK_ELEMENT" },
        { source: "ps2", target: "we2", type: "HAS_WORK_ELEMENT" },
        { source: "pi2", target: "ps4", type: "HAS_PROCESS_STEP" },
      ],
    ));
    renderEditor();
    await screen.findByTestId("fmea-structure-drag-handle-ps2");
    // sanity: both work elements visible before drag
    expect(screen.getByTestId("fmea-structure-node-we1")).toBeInTheDocument();
    expect(screen.getByTestId("fmea-structure-node-we2")).toBeInTheDocument();

    driveDragOver("ps2", "ps1", 1);
    await waitFor(() => {
      // only the dragged node's own subtree (we2, ps2's child) collapses
      expect(screen.queryByTestId("fmea-structure-node-we2")).toBeNull();
      // siblings' subtrees stay expanded (we1, ps1's child) — collapsing them would
      // shift the dragged node and misalign the DragOverlay
      expect(screen.getByTestId("fmea-structure-node-we1")).toBeInTheDocument();
      // sibling level + unrelated branch stay visible/expanded
      expect(screen.getByTestId("fmea-structure-node-ps1")).toBeInTheDocument();
      expect(screen.getByTestId("fmea-structure-node-ps3")).toBeInTheDocument();
      expect(screen.getByTestId("fmea-structure-node-ps4")).toBeInTheDocument();
    });
  });
});

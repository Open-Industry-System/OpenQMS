import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { App } from "antd";
import FMEAEditorPage from "./FMEAEditorPage";
import type { FMEADocument, GraphEdge, GraphNode } from "../../../types";

class DragDataTransferPolyfill implements DataTransfer {
  data = new Map<string, string>();
  dropEffect: "none" | "link" | "copy" | "move" = "none";
  effectAllowed: "none" | "copy" | "copyLink" | "copyMove" | "link" | "linkMove" | "move" | "all" | "uninitialized" = "uninitialized";
  files = [] as unknown as FileList;
  items = [] as unknown as DataTransferItemList;
  types: ReadonlyArray<string> = [];
  setData(format: string, value: string): boolean { this.data.set(format, value); return true; }
  getData(format: string): string { return this.data.get(format) || ""; }
  clearData(format?: string): boolean { if (format) { this.data.delete(format); } else { this.data.clear(); } return true; }
  setDragImage(): void {}
}

class DragEventPolyfill extends MouseEvent {
  dataTransfer: DataTransfer;
  constructor(type: string, init: MouseEventInit & { dataTransfer?: DataTransfer } = {}) {
    super(type, init);
    this.dataTransfer = init.dataTransfer || new DragDataTransferPolyfill();
  }
}

beforeAll(() => {
  globalThis.DataTransfer = DragDataTransferPolyfill as unknown as typeof DataTransfer;
  globalThis.DragEvent = DragEventPolyfill as unknown as typeof DragEvent;
});

const mocks = vi.hoisted(() => ({
  getFMEA: vi.fn(),
  updateFMEA: vi.fn(),
  transitionFMEA: vi.fn(),
  canEdit: vi.fn(),
  warning: vi.fn(),
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

function makeDataTransfer(): DataTransfer {
  const data = new Map<string, string>();
  return {
    effectAllowed: "",
    dropEffect: "",
    setData: vi.fn((format: string, value: string) => data.set(format, value)),
    getData: vi.fn((format: string) => data.get(format) || ""),
    clearData: vi.fn((format?: string) => { if (format) { data.delete(format); } else { data.clear(); } }),
    setDragImage: vi.fn(),
    files: [] as unknown as FileList,
    items: [] as unknown as DataTransferItemList,
    types: [],
  } as unknown as DataTransfer;
}

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

beforeEach(() => {
  vi.clearAllMocks();
  mocks.canEdit.mockReturnValue(true);
  mocks.updateFMEA.mockResolvedValue({});
  mocks.transitionFMEA.mockResolvedValue({});
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
    expect(handle).toHaveAttribute("draggable", "true");
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
    expect(ps1).not.toHaveAttribute("draggable");
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
    expect(handle).toHaveAttribute("draggable", "true");
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

    const sys1 = await screen.findByTestId("fmea-structure-node-sys1");
    const sys2Handle = await screen.findByTestId("fmea-structure-drag-handle-sys2");
    vi.spyOn(sys1, "getBoundingClientRect").mockReturnValue({
      x: 0, y: 0, top: 0, left: 0, bottom: 40, right: 200, width: 200, height: 40, toJSON: () => ({}),
    } as DOMRect);

    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(sys2Handle, { dataTransfer });
    fireEvent.dragOver(sys1, { clientY: 1, dataTransfer });
    fireEvent.drop(sys1, { clientY: 1, dataTransfer });

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

    const ps1 = await screen.findByTestId("fmea-structure-node-ps1");
    const ps2Handle = await screen.findByTestId("fmea-structure-drag-handle-ps2");
    vi.spyOn(ps1, "getBoundingClientRect").mockReturnValue({
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      bottom: 40,
      right: 200,
      width: 200,
      height: 40,
      toJSON: () => ({}),
    } as DOMRect);

    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(ps2Handle, { dataTransfer });
    fireEvent.dragOver(ps1, { clientY: 1, dataTransfer });
    fireEvent.drop(ps1, { clientY: 1, dataTransfer });

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

    const ps1 = await screen.findByTestId("fmea-structure-node-ps1");
    const ps2Handle = await screen.findByTestId("fmea-structure-drag-handle-ps2");
    vi.spyOn(ps1, "getBoundingClientRect").mockReturnValue({
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      bottom: 40,
      right: 200,
      width: 200,
      height: 40,
      toJSON: () => ({}),
    } as DOMRect);

    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(ps2Handle, { dataTransfer });
    fireEvent.dragOver(ps1, { clientY: 20, dataTransfer });
    fireEvent.drop(ps1, { clientY: 20, dataTransfer });

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
    const ps2Handle = await screen.findByTestId("fmea-structure-drag-handle-ps2");
    vi.spyOn(ps1, "getBoundingClientRect").mockReturnValue({
      x: 0, y: 0, top: 0, left: 0, bottom: 40, right: 200, width: 200, height: 40, toJSON: () => ({}),
    } as DOMRect);

    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(ps2Handle, { dataTransfer });
    fireEvent.dragOver(ps1, { clientY: 1, dataTransfer });

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
    const ps2Handle = await screen.findByTestId("fmea-structure-drag-handle-ps2");
    vi.spyOn(ps1, "getBoundingClientRect").mockReturnValue({
      x: 0, y: 0, top: 0, left: 0, bottom: 40, right: 200, width: 200, height: 40, toJSON: () => ({}),
    } as DOMRect);

    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(ps2Handle, { dataTransfer });
    fireEvent.dragOver(ps1, { clientY: 1, dataTransfer });

    await waitFor(() => expect(ps1.getAttribute("data-drag-state")).toBe("invalid"));

    fireEvent.drop(ps1, { clientY: 1, dataTransfer });
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
    expect(handle).toHaveAttribute("draggable", "true");
  });

  it("uses the whole row as the drag image", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [node("pi", "ProcessItem"), node("ps1", "ProcessStep"), node("ps2", "ProcessStep")],
      [
        { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
        { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
      ],
    ));
    renderEditor();
    const ps2Row = await screen.findByTestId("fmea-structure-node-ps2");
    const ps2Handle = await screen.findByTestId("fmea-structure-drag-handle-ps2");
    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(ps2Handle, { dataTransfer });
    expect(dataTransfer.setDragImage).toHaveBeenCalledWith(ps2Row, 0, 0);
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
    const piHandle = await screen.findByTestId("fmea-structure-drag-handle-pi");
    expect(screen.getByTestId("fmea-structure-node-ps1")).toBeInTheDocument();
    fireEvent.dragStart(piHandle, { dataTransfer: makeDataTransfer() });
    await waitFor(() => {
      expect(screen.queryByTestId("fmea-structure-node-ps1")).toBeNull();
      expect(screen.queryByTestId("fmea-structure-node-ps2")).toBeNull();
    });
  });

  it("previews the sibling reorder during drag-over before drop", async () => {
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
    const ps2Handle = await screen.findByTestId("fmea-structure-drag-handle-ps2");
    vi.spyOn(ps1, "getBoundingClientRect").mockReturnValue({
      x: 0, y: 0, top: 0, left: 0, bottom: 40, right: 200, width: 200, height: 40, toJSON: () => ({}),
    } as DOMRect);
    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(ps2Handle, { dataTransfer });
    fireEvent.dragOver(ps1, { clientY: 1, dataTransfer });
    await waitFor(() => {
      expect(screen.getAllByTestId(/^fmea-structure-node-/).map((el) => el.getAttribute("data-testid"))).toEqual([
        "fmea-structure-node-pi", "fmea-structure-node-ps2", "fmea-structure-node-ps1",
      ]);
    });
  });

  it("reverts the preview when the drag ends without a drop", async () => {
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
    const ps2Handle = await screen.findByTestId("fmea-structure-drag-handle-ps2");
    vi.spyOn(ps1, "getBoundingClientRect").mockReturnValue({
      x: 0, y: 0, top: 0, left: 0, bottom: 40, right: 200, width: 200, height: 40, toJSON: () => ({}),
    } as DOMRect);
    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(ps2Handle, { dataTransfer });
    fireEvent.dragOver(ps1, { clientY: 1, dataTransfer });
    await waitFor(() => expect(screen.getAllByTestId(/^fmea-structure-node-/).map((el) => el.getAttribute("data-testid"))).toEqual([
      "fmea-structure-node-pi", "fmea-structure-node-ps2", "fmea-structure-node-ps1",
    ]));
    fireEvent.dragEnd(ps2Handle);
    await waitFor(() => expect(screen.getAllByTestId(/^fmea-structure-node-/).map((el) => el.getAttribute("data-testid"))).toEqual([
      "fmea-structure-node-pi", "fmea-structure-node-ps1", "fmea-structure-node-ps2",
    ]));
  });
});

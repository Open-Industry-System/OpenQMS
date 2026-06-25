import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { App } from "antd";
import ControlPlanEditorPage from "./ControlPlanEditorPage";
import type { ControlPlan } from "../../../types";

const mocks = vi.hoisted(() => ({
  getControlPlan: vi.fn(),
  getCPVersion: vi.fn(),
  listCPVersions: vi.fn(),
  getCPSyncStatus: vi.fn(),
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

vi.mock("../../../api/controlPlan", () => ({
  getControlPlan: mocks.getControlPlan,
  createControlPlan: vi.fn(),
  updateControlPlan: vi.fn(),
  checkStaleItems: vi.fn().mockResolvedValue({ stale_items: [] }),
  approveControlPlan: vi.fn(),
  syncCSRToControlPlan: vi.fn(),
}));
vi.mock("../../../api/version", () => ({
  getCPVersion: mocks.getCPVersion,
  listCPVersions: mocks.listCPVersions,
}));
vi.mock("../../../api/customerQuality", () => ({ listCustomers: vi.fn().mockResolvedValue([]) }));
vi.mock("../../../api/specialCharacteristic", () => ({
  getCPSyncStatus: mocks.getCPSyncStatus,
  syncToCP: vi.fn(),
}));
vi.mock("../../../store/authStore", () => ({
  useAuthStore: (selector: (s: { user: unknown }) => unknown) => selector({ user: { user_id: "u1", role_key: "admin" } }),
}));
vi.mock("../../../hooks/usePermission", () => ({
  usePermission: () => ({ canEdit: () => true, canApprove: () => true }),
}));
vi.mock("../../../hooks/useCollaboration", () => ({
  useCollaboration: () => ({
    activeUsers: [],
    startEditing: mocks.startEditing,
    stopEditing: vi.fn(),
    isSyncing: false,
  }),
}));
vi.mock("../../../components/collaboration", () => ({
  CollaborationBar: () => <div data-testid="collab" />,
  ActiveUserIndicator: () => <div data-testid="au" />,
  ConflictResolutionModal: () => null,
}));
vi.mock("../../../components/control-plan/ImportFromFMEAModal", () => ({ default: () => null }));
vi.mock("../../../components/control-plan/ValidationPanel", () => ({ default: () => <div data-testid="validation-panel" /> }));
vi.mock("../../../components/version/CreateVersionModal", () => ({ default: () => null }));
vi.mock("../../../components/version/RollbackConfirmModal", () => ({ default: () => null }));
vi.mock("../../../components/version/VersionCompareView", () => ({ default: () => <div data-testid="vc" /> }));
vi.mock("../../../components/design/PageShell", () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, tc: (key: string) => key }),
}));

function makeCP(): ControlPlan {
  return {
    cp_id: "cp-1", document_no: "CP-1", title: "当前CP", status: "draft",
    phase: "sample", part_no: "P1", part_name: "件名", product_line_code: "DC-DC-100",
    fmea_ref_id: null, contact_info: "", core_group: "", org_factory: "", drawing_rev: "",
    sync_pending: false, items: [], version: 1, lock_version: 1,
    created_by: "u1", created_at: "2026-06-18T00:00:00Z", updated_at: "2026-06-18T00:00:00Z",
  } as unknown as ControlPlan;
}

function renderEditor() {
  return render(
    <App>
      <MemoryRouter initialEntries={["/control-plans/cp-1"]}>
        <Routes><Route path="/control-plans/:id" element={<ControlPlanEditorPage />} /></Routes>
      </MemoryRouter>
    </App>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getControlPlan.mockResolvedValue(makeCP());
  mocks.getCPSyncStatus.mockResolvedValue({ items: [] });
  mocks.listCPVersions.mockResolvedValue({
    items: [{ version_id: "v1", cp_id: "cp-1", major_no: 1, minor_no: 0, source_fmea_version_id: null, change_type: "approve", change_summary: "v1", created_by: "u1", created_at: "2026-06-18T00:00:00Z" }],
    total: 1, page: 1, page_size: 100,
  });
  mocks.getCPVersion.mockResolvedValue({
    version_id: "v1", cp_id: "cp-1", major_no: 1, minor_no: 0, source_fmea_version_id: null,
    change_type: "approve", change_summary: "v1", created_by: "u1", created_at: "2026-06-18T00:00:00Z",
    header_snapshot: {
      document_no: "CP-1", title: "快照CP", fmea_ref_id: null, product_line_code: "DC-DC-100",
      status: "approved", phase: "sample", part_no: "P1", part_name: "快照件名",
      contact_info: "", drawing_rev: "", org_factory: "", core_group: "",
    },
    items_snapshot: [],
    sha256_hash: "abc",
  });
});

describe("ControlPlanEditorPage version snapshot", () => {
  it("loads version snapshot into read-only mode with banner", async () => {
    renderEditor();
    await waitFor(() => expect(mocks.getControlPlan).toHaveBeenCalled());

    fireEvent.click(screen.getByText("pageTitle.versionHistory"));
    await waitFor(() => expect(mocks.listCPVersions).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText("v1.0")).toBeInTheDocument());
    const viewBtn = screen.getByRole("button", { name: /history\.view/ });
    fireEvent.click(viewBtn);

    await waitFor(() => expect(mocks.getCPVersion).toHaveBeenCalledWith("cp-1", 1, 0));
    await waitFor(() => expect(screen.getByText(/message.viewingVersion/)).toBeInTheDocument());
    // 快照标题是 title <Input value={title}>（:773），且测试的 PageShell mock 不渲染 title prop → 用 getByDisplayValue
    await waitFor(() => expect(screen.getByDisplayValue("快照CP")).toBeInTheDocument());
    // 快照态隐藏 ValidationPanel
    await waitFor(() => expect(screen.queryByTestId("validation-panel")).not.toBeInTheDocument());
    // 只读态未产生协作事件（注：未主动 focus 控件，此断言验证「无副作用」而非 guard 被触发）
    expect(mocks.startEditing).not.toHaveBeenCalled();
  });

  it("returns to current version on exit", async () => {
    renderEditor();
    await waitFor(() => expect(mocks.getControlPlan).toHaveBeenCalled());
    fireEvent.click(screen.getByText("pageTitle.versionHistory"));
    await waitFor(() => expect(mocks.listCPVersions).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText("v1.0")).toBeInTheDocument());
    const viewBtn = screen.getByRole("button", { name: /history\.view/ });
    fireEvent.click(viewBtn);
    await waitFor(() => expect(screen.getByText(/message.viewingVersion/)).toBeInTheDocument());

    fireEvent.click(screen.getByText("button.exitVersion"));
    await waitFor(() => expect(mocks.getControlPlan.mock.calls.length).toBeGreaterThanOrEqual(2));
    await waitFor(() => expect(screen.queryByText(/message.viewingVersion/)).not.toBeInTheDocument());
  });
});

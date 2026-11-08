import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { App } from "antd";
import i18n from "../../../i18n";
import ControlPlanEditorPage from "./ControlPlanEditorPage";
import { updateControlPlan } from "../../../api/controlPlan";
import { diffControlPlanItems } from "../../../utils/controlPlanDiff";
import type { ControlPlan, ControlPlanItem } from "../../../types";

const mocks = vi.hoisted(() => ({ getControlPlan: vi.fn(), getCPSyncStatus: vi.fn(), clientPut: vi.fn() }));
vi.mock("../../../api/client", () => ({ default: { put: mocks.clientPut } }));
vi.mock("../../../api/controlPlan", async () => {
  const actual = await vi.importActual<typeof import("../../../api/controlPlan")>("../../../api/controlPlan");
  return { ...actual, getControlPlan: mocks.getControlPlan, createControlPlan: vi.fn(), checkStaleItems: vi.fn(), approveControlPlan: vi.fn(), syncCSRToControlPlan: vi.fn() };
});
vi.mock("../../../api/customerQuality", () => ({ listCustomers: vi.fn().mockResolvedValue([]) }));
vi.mock("../../../api/specialCharacteristic", () => ({ getCPSyncStatus: mocks.getCPSyncStatus, syncToCP: vi.fn() }));
vi.mock("../../../api/version", () => ({ getCPVersion: vi.fn(), listCPVersions: vi.fn() }));
vi.mock("../../../store/authStore", () => ({ useAuthStore: (selector: (s: { user: unknown }) => unknown) => selector({ user: { user_id: "u1", role_key: "admin" } }) }));
vi.mock("../../../hooks/usePermission", () => ({ usePermission: () => ({ canEdit: () => true, canApprove: () => true }) }));
vi.mock("../../../hooks/useCollaboration", () => ({ useCollaboration: () => ({ activeUsers: [], startEditing: vi.fn(), stopEditing: vi.fn(), isSyncing: false }) }));
vi.mock("../../../components/collaboration", () => ({ CollaborationBar: () => null, ActiveUserIndicator: () => null, ConflictResolutionModal: () => null }));
vi.mock("../../../components/control-plan/ImportFromFMEAModal", () => ({ default: () => null }));
vi.mock("../../../components/control-plan/ValidationPanel", () => ({ default: () => null }));
vi.mock("../../../components/version/SyncPreviewDrawer", () => ({ default: () => null }));
vi.mock("../../../components/version/CreateVersionModal", () => ({ default: () => null }));
vi.mock("../../../components/version/RollbackConfirmModal", () => ({ default: () => null }));
vi.mock("../../../components/version/VersionCompareView", () => ({ default: () => null }));
vi.mock("../../../components/design/PageShell", () => ({ default: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock("../../../components/design/DataCard", () => ({ default: ({ children }: { children: React.ReactNode }) => <section>{children}</section> }));

const item = {
  item_id: "item-1", step_no: "10", process_name: "装配", equipment: "", characteristic_no: "C1",
  product_characteristic: "尺寸", process_characteristic: "温度", special_class: "", specification_tolerance: "",
  evaluation_method: "", sample_size: "", sample_frequency: "", control_method: "", reaction_plan: "",
  source_fmea_node_id: "node-1", source_characteristic_ref: { mapping_version: 2, fmea_id: "fmea-1", step_id: "step-1", function_id: "function-1", work_element_id: null, characteristic_id: "char-1" }, sort_order: 0,
} as ControlPlanItem;

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getControlPlan.mockResolvedValue({ cp_id: "cp-1", document_no: "CP-1", title: "CP", status: "draft", phase: "sample", part_no: "", part_name: "", product_line_code: "DC-DC-100", fmea_ref_id: "fmea-1", contact_info: "", core_group: "", org_factory: "", drawing_rev: "", sync_pending: false, items: [item], version: 1, lock_version: 4 } as ControlPlan);
  mocks.getCPSyncStatus.mockResolvedValue({ items: [] });
  mocks.clientPut.mockResolvedValue({ data: {} });
});
afterEach(async () => { await i18n.changeLanguage("en-US"); });

describe("Control Plan standard template and write boundary", () => {
  it("keeps the Task 1 labels and groups without exposing source metadata", async () => {
    await i18n.changeLanguage("zh-CN");
    render(<App><MemoryRouter initialEntries={["/control-plans/cp-1"]}><Routes><Route path="/control-plans/:id" element={<ControlPlanEditorPage />} /></Routes></MemoryRouter></App>);
    await waitFor(() => expect(mocks.getControlPlan).toHaveBeenCalled());
    expect(screen.getAllByRole("columnheader", { name: "产品特性" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("columnheader", { name: "过程特性" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("columnheader", { name: "反应计划" }).length).toBeGreaterThan(0);
    expect(screen.queryByText("内部来源元数据")).not.toBeInTheDocument();
  });

  it("compares read-only source metadata by content rather than object identity", () => {
    const copiedItem = {
      ...item,
      source_characteristic_ref: { ...item.source_characteristic_ref! },
    };
    expect(diffControlPlanItems([item], [copiedItem], [item]).itemChanges).toEqual([]);
  });

  it("preserves existing item identity but omits server-managed provenance from writes", async () => {
    await updateControlPlan("cp-1", { items: [item] });
    expect(mocks.clientPut).toHaveBeenCalledWith("/control-plans/cp-1", {
      items: [expect.objectContaining({ item_id: "item-1", source_fmea_node_id: "node-1", product_characteristic: "尺寸" })],
    });
    expect(mocks.clientPut.mock.calls[0][1].items[0]).not.toHaveProperty("source_characteristic_ref");
  });
});

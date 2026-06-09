import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { App } from "antd";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as plmApi from "../../api/plm";
import { useAuthStore } from "../../store/authStore";
import { useProductLineStore } from "../../store/productLineStore";
import PLMChangeOrdersPage from "./PLMChangeOrdersPage";
import PLMConnectionsPage from "./PLMConnectionsPage";
import PLMPartsPage from "./PLMPartsPage";

vi.mock("../../api/plm");

const connection = {
  connection_id: "conn-1",
  name: "Mock PLM",
  connector_type: "mock",
  config: {},
  is_active: true,
  product_line_code: "DC-DC-100",
  created_by: "u1",
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
};

const changeOrder = {
  change_id: "co-1",
  connection_id: "conn-1",
  external_id: "co-ext-1",
  change_number: "ECN-001",
  title: "替换关键物料",
  description: null,
  change_type: "ECN",
  status: "open",
  priority: "high",
  affected_part_numbers: ["P-100"],
  proposed_changes: null,
  requested_by: null,
  approved_by: null,
  planned_implementation_date: null,
  actual_implementation_date: null,
  source_updated_at: null,
  product_line_code: "DC-DC-100",
  plm_raw_data: null,
};

function setPermissions(permissions: Record<string, number>) {
  useAuthStore.setState({
    user: {
      user_id: "u1",
      username: "tester",
      role_key: permissions.plm >= 5 ? "admin" : "quality_engineer",
      permissions,
    } as any,
    token: "test-token",
  });
}

function setPLMPermission(level: number) {
  setPermissions({ plm: level });
}

function createPart(overrides: Partial<any> = {}) {
  return {
    part_id: "part-1",
    connection_id: "conn-1",
    external_id: "ext-1",
    part_number: "P-1",
    name: "Part 1",
    revision: "A",
    material: null,
    specification: null,
    status: "active",
    is_safety_related: true,
    is_key_characteristic: false,
    source_updated_at: null,
    product_line_code: "DC-DC-100",
    plm_raw_data: null,
    sc_links: [
      { link_id: "link-1", characteristic_type: "safety", status: "pending", sc_id: null, confirmed_at: null },
    ],
    ...overrides,
  };
}

function seedPartMocks(parts: any[]) {
  vi.mocked(plmApi.getPLMParts).mockResolvedValue({
    items: parts,
    total: parts.length,
    page: 1,
    page_size: 20,
  });
}

function renderWithApp(ui: React.ReactElement) {
  return render(<App>{ui}</App>);
}

describe("PLM page permissions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    useProductLineStore.setState({ selected: null });
    vi.mocked(plmApi.getPLMConnections).mockResolvedValue({
      items: [connection],
      total: 1,
      page: 1,
      page_size: 20,
    });
    vi.mocked(plmApi.getPLMChangeOrders).mockResolvedValue({
      items: [changeOrder],
      total: 1,
      page: 1,
      page_size: 20,
    });
    vi.mocked(plmApi.getPLMParts).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
    vi.mocked(plmApi.getPLMBOMTree).mockResolvedValue({
      root: "P-1",
      revision: "A",
      bom_revision: "A",
      items: [],
      total: 0,
    });
    vi.mocked(plmApi.importBOMToFMEA).mockResolvedValue({
      imported_nodes: 1,
      imported_edges: 0,
      root: "P-1",
      revision: "A",
      bom_revision: "A",
      fmea_id: "fmea-1",
    });
    vi.mocked(plmApi.confirmPLMPartSC).mockResolvedValue({
      status: "confirmed",
      sc_id: "sc-1",
      link_id: "link-1",
    });
  });

  it("hides connection mutation actions from PLM viewers", async () => {
    setPLMPermission(1);

    renderWithApp(<PLMConnectionsPage />);

    await screen.findByText("Mock PLM");
    expect(screen.queryByText("编辑")).not.toBeInTheDocument();
    expect(screen.queryByText("测试")).not.toBeInTheDocument();
    expect(screen.queryByText("同步")).not.toBeInTheDocument();
    expect(screen.queryByText("删除")).not.toBeInTheDocument();
  });

  it("lets PLM editors edit, test, and sync connections but not delete them", async () => {
    setPLMPermission(3);

    renderWithApp(<PLMConnectionsPage />);

    await screen.findByText("Mock PLM");
    expect(screen.getByText("编辑")).toBeInTheDocument();
    expect(screen.getByText("测试")).toBeInTheDocument();
    expect(screen.getByText("同步")).toBeInTheDocument();
    expect(screen.queryByText("删除")).not.toBeInTheDocument();
  });

  it("shows connection delete action only to PLM admins", async () => {
    setPLMPermission(5);

    renderWithApp(<PLMConnectionsPage />);

    await screen.findByText("Mock PLM");
    expect(screen.getByText("删除")).toBeInTheDocument();
  });

  it("hides impact analysis from PLM viewers", async () => {
    setPLMPermission(1);

    renderWithApp(<PLMChangeOrdersPage />);

    await screen.findByText("ECN-001");
    await waitFor(() => {
      expect(screen.queryByText("影响分析")).not.toBeInTheDocument();
    });
  });

  it("shows impact analysis to PLM editors", async () => {
    setPLMPermission(3);

    renderWithApp(<PLMChangeOrdersPage />);

    await screen.findByText("ECN-001");
    expect(screen.getByText("影响分析")).toBeInTheDocument();
  });

  it("allows PLM viewers to view BOM but hides import and SC confirmation", async () => {
    setPermissions({ plm: 1, special_characteristic: 2 });
    seedPartMocks([createPart()]);

    renderWithApp(<PLMPartsPage />);

    await screen.findByText("Part 1");
    expect(screen.getByText("BOM")).toBeInTheDocument();
    expect(screen.queryByText("导入 FMEA")).not.toBeInTheDocument();
    expect(screen.queryByText("确认SC")).not.toBeInTheDocument();
  });

  it("shows BOM/import/SC actions to users with PLM edit and SC create when pending link exists", async () => {
    setPermissions({ plm: 3, special_characteristic: 2 });
    seedPartMocks([createPart()]);

    renderWithApp(<PLMPartsPage />);

    await screen.findByText("Part 1");
    expect(screen.getByText("BOM")).toBeInTheDocument();
    expect(screen.getByText("导入 FMEA")).toBeInTheDocument();
    expect(screen.getByText("确认SC")).toBeInTheDocument();
  });

  it("hides SC action from PLM editors without SC create permission", async () => {
    setPermissions({ plm: 3, special_characteristic: 1 });
    seedPartMocks([createPart()]);

    renderWithApp(<PLMPartsPage />);

    await screen.findByText("Part 1");
    expect(screen.getByText("BOM")).toBeInTheDocument();
    expect(screen.getByText("导入 FMEA")).toBeInTheDocument();
    expect(screen.queryByText("确认SC")).not.toBeInTheDocument();
  });

  it("hides SC action once link is confirmed even if part flag remains true", async () => {
    setPermissions({ plm: 3, special_characteristic: 2 });
    seedPartMocks([createPart({
      sc_links: [
        { link_id: "link-1", characteristic_type: "safety", status: "confirmed", sc_id: "sc-1", confirmed_at: "2026-06-09T00:00:00Z" },
      ],
    })]);

    renderWithApp(<PLMPartsPage />);

    await screen.findByText("Part 1");
    expect(screen.getByText("BOM")).toBeInTheDocument();
    expect(screen.getByText("导入 FMEA")).toBeInTheDocument();
    expect(screen.queryByText("确认SC")).not.toBeInTheDocument();
  });

  it("resets parts pagination to page 1 when product line changes", async () => {
    setPermissions({ plm: 3, special_characteristic: 2 });
    vi.mocked(plmApi.getPLMParts).mockResolvedValue({
      items: [createPart()],
      total: 25,
      page: 1,
      page_size: 20,
    });

    renderWithApp(<PLMPartsPage />);

    await screen.findByText("Part 1");
    fireEvent.click(screen.getByTitle("2"));
    await waitFor(() => {
      expect(plmApi.getPLMParts).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }));
    });

    act(() => {
      useProductLineStore.setState({ selected: "LINE-2" });
    });

    await waitFor(() => {
      expect(plmApi.getPLMParts).toHaveBeenLastCalledWith(expect.objectContaining({
        page: 1,
        product_line_code: "LINE-2",
      }));
    });
    expect(screen.getByTitle("1")).toHaveClass("ant-pagination-item-active");
  });

  it("imports BOM with query revisions and separate import fields", async () => {
    setPermissions({ plm: 3, special_characteristic: 2 });
    seedPartMocks([createPart({ revision: "B" })]);

    renderWithApp(<PLMPartsPage />);

    await screen.findByText("Part 1");
    fireEvent.click(screen.getByText("导入 FMEA"));

    const modal = await screen.findByRole("dialog", { name: "BOM：P-1" });
    const revisionInput = within(modal).getByLabelText("零件版本");
    const bomRevisionInput = within(modal).getByLabelText("BOM 版本");
    const fmeaInput = within(modal).getByLabelText("FMEA ID");

    expect(revisionInput).toHaveValue("B");
    expect(bomRevisionInput).toHaveValue("B");
    fireEvent.change(revisionInput, { target: { value: "C" } });
    fireEvent.change(bomRevisionInput, { target: { value: "BOM-C" } });
    fireEvent.change(fmeaInput, { target: { value: "fmea-2" } });
    fireEvent.click(within(modal).getByRole("button", { name: "导入 FMEA" }));

    await waitFor(() => {
      expect(plmApi.importBOMToFMEA).toHaveBeenCalledWith(
        "conn-1",
        "P-1",
        { fmea_id: "fmea-2", overwrite: false },
        { revision: "C", bom_revision: "BOM-C" },
      );
    });
  });
});

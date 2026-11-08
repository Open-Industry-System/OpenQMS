import { readFileSync } from "node:fs";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { App } from "antd";
import ImportFromFMEAModal from "./ImportFromFMEAModal";

const mocks = vi.hoisted(() => ({
  listFMEAs: vi.fn(),
  listFMEAVersions: vi.fn(),
  getFMEAVersion: vi.fn(),
  previewImportFromFMEA: vi.fn(),
  applyImportFromFMEA: vi.fn(),
}));

vi.mock("../../api/fmea", () => ({ listFMEAs: mocks.listFMEAs }));
vi.mock("../../api/version", () => ({
  listFMEAVersions: mocks.listFMEAVersions,
  getFMEAVersion: mocks.getFMEAVersion,
}));
vi.mock("../../api/controlPlan", () => ({
  previewImportFromFMEA: mocks.previewImportFromFMEA,
  applyImportFromFMEA: mocks.applyImportFromFMEA,
}));

const sourceVersion = {
  version_id: "version-approved", fmea_id: "fmea-1", major_no: 1, minor_no: 0,
  change_type: "approve", change_summary: "批准", created_by: "u1", created_at: "2026-11-01T00:00:00Z",
};
const preview = {
  source_fmea_version_id: "version-approved", expected_lock_version: 7,
  mapping_version: 2, preview_digest: "digest-1", issues: [{ code: "relationship_warning", node_id: "step-1", blocking: false, message: "关系需要复核" }],
  items: [
    { candidate_key: "add-1", action: "add", item_id: null, source_ref: { mapping_version: 2, fmea_id: "fmea-1", step_id: "step-1", function_id: "function-1", work_element_id: null, characteristic_id: "characteristic-1" }, fields: { step_no: "10", product_characteristic: "尺寸" } },
    { candidate_key: "existing-1", action: "existing", item_id: "item-1", source_ref: { mapping_version: 2, fmea_id: "fmea-1", step_id: "step-1", function_id: "function-1", work_element_id: null, characteristic_id: "characteristic-2" }, fields: { step_no: "10", process_characteristic: "温度" } },
  ],
};

function renderModal() {
  return render(
    <App>
      <ImportFromFMEAModal cpId="cp-1" expectedLockVersion={7} open onClose={vi.fn()} onSuccess={vi.fn()} />
    </App>
  );
}

async function choose(selectIndex: number, option: string) {
  fireEvent.mouseDown(screen.getAllByRole("combobox")[selectIndex]);
  fireEvent.click(await screen.findByText(option));
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listFMEAs.mockResolvedValue({ items: [{ fmea_id: "fmea-1", document_no: "PFMEA-01", title: "装配", fmea_type: "PFMEA" }] });
  mocks.listFMEAVersions.mockResolvedValue({ items: [sourceVersion, { ...sourceVersion, version_id: "manual", minor_no: 1, change_type: "manual" }] });
  mocks.getFMEAVersion.mockResolvedValue({ ...sourceVersion, snapshot: { nodes: [{ id: "step-1", type: "ProcessStep", name: "装配", process_number: "10" }], edges: [] }, sha256_hash: "hash" });
  mocks.previewImportFromFMEA.mockResolvedValue(preview);
  mocks.applyImportFromFMEA.mockResolvedValue({ imported_count: 2, items: [] });
});

describe("ImportFromFMEAModal preview-confirm flow", () => {
  it("uses an approved snapshot's step ids to preview before it writes", async () => {
    renderModal();
    await choose(0, "PFMEA-01 - 装配");
    await waitFor(() => expect(mocks.listFMEAVersions).toHaveBeenCalledWith("fmea-1", { page_size: 100 }));
    await choose(1, "v1.0");
    await waitFor(() => expect(mocks.getFMEAVersion).toHaveBeenCalledWith("fmea-1", 1, 0));
    await screen.findByText("装配");

    fireEvent.click(screen.getByRole("button", { name: "Preview changes" }));
    await waitFor(() => expect(mocks.previewImportFromFMEA).toHaveBeenCalledWith("cp-1", {
      fmea_id: "fmea-1", source_fmea_version_id: "version-approved", expected_lock_version: 7, step_ids: ["step-1"],
    }));
    expect(mocks.applyImportFromFMEA).not.toHaveBeenCalled();
    expect(await screen.findByText("关系需要复核")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Confirm import/ }));
    await waitFor(() => expect(mocks.applyImportFromFMEA).toHaveBeenCalledWith("cp-1", {
      fmea_id: "fmea-1", source_fmea_version_id: "version-approved", expected_lock_version: 7,
      step_ids: ["step-1"], preview_digest: "digest-1", selected_candidate_keys: ["add-1", "existing-1"],
    }));
  });

  it("keeps a rework PFMEA available when it has a historical approved snapshot", async () => {
    mocks.listFMEAs.mockResolvedValueOnce({ items: [{ fmea_id: "fmea-1", document_no: "PFMEA-01", title: "返工中的装配", fmea_type: "PFMEA", status: "rework" }] });
    renderModal();
    await waitFor(() => expect(mocks.listFMEAs).toHaveBeenCalledWith({ page_size: 100 }));
    await choose(0, "PFMEA-01 - 返工中的装配");
    await choose(1, "v1.0");
    await screen.findByText("装配");
  });

  it("blocks the entire import preview when any backend issue is blocking", async () => {
    mocks.previewImportFromFMEA.mockResolvedValueOnce({
      ...preview,
      issues: [{ code: "ambiguous_existing_rows", node_id: "unrelated-step", blocking: true, message: "映射存在歧义，不能确认此预览" }],
    });
    renderModal();
    await choose(0, "PFMEA-01 - 装配");
    await choose(1, "v1.0");
    await screen.findByText("装配");
    fireEvent.click(screen.getByRole("button", { name: "Preview changes" }));
    expect(await screen.findByText("映射存在歧义，不能确认此预览")).toBeInTheDocument();
    expect(screen.getByText("This preview is blocked and cannot be confirmed.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Confirm import/ })).toBeDisabled();
    expect(mocks.applyImportFromFMEA).not.toHaveBeenCalled();
  });

  it("freezes selection during import so a committed response still refreshes and closes", async () => {
    let resolveApply: (() => void) | undefined;
    mocks.applyImportFromFMEA.mockImplementationOnce(() => new Promise<void>((resolve) => { resolveApply = resolve; }));
    const onClose = vi.fn();
    const onSuccess = vi.fn();
    render(<App><ImportFromFMEAModal cpId="cp-1" expectedLockVersion={7} open onClose={onClose} onSuccess={onSuccess} /></App>);
    await choose(0, "PFMEA-01 - 装配");
    await choose(1, "v1.0");
    await screen.findByText("装配");
    fireEvent.click(screen.getByRole("button", { name: "Preview changes" }));
    await screen.findByText("关系需要复核");
    fireEvent.click(screen.getByRole("button", { name: /Confirm import/ }));
    await waitFor(() => expect(mocks.applyImportFromFMEA).toHaveBeenCalledTimes(1));
    expect(screen.getAllByRole("checkbox").every((checkbox) => (checkbox as HTMLInputElement).disabled)).toBe(true);
    resolveApply?.();
    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("invalidates the preview after 409 and requires a new explicit preview", async () => {
    mocks.applyImportFromFMEA.mockRejectedValueOnce({ response: { status: 409 } });
    renderModal();
    await choose(0, "PFMEA-01 - 装配");
    await choose(1, "v1.0");
    await screen.findByText("装配");
    fireEvent.click(screen.getByRole("button", { name: "Preview changes" }));
    await screen.findByText("关系需要复核");

    fireEvent.click(screen.getByRole("button", { name: /Confirm import/ }));
    await waitFor(() => expect(mocks.applyImportFromFMEA).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("Preview expired. Generate a new preview before confirming.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Confirm import/ })).not.toBeInTheDocument();
    expect(mocks.applyImportFromFMEA).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: /Preview changes/ })).toBeEnabled();
  });
});


describe("unrun characteristic acceptance script contract (static only)", () => {
  const script = () => readFileSync("e2e/specs/m1-core/characteristic-correction.spec.ts", "utf8");
  it("scopes partial selection to candidate table and explicitly closes the remaining notice", () => {
    const source = script();
    expect(source).toContain("const importRows = candidateTable.locator(\"tbody tr\");");
    expect(source).toContain("page.getByRole(\"columnheader\", { name: \"产品特性\", exact: true })");
    expect(source).toContain("await expect(importDialog.getByText(\"已部分导入，仍有 4 项待同步。\")).toBeVisible();");
    expect(source).toContain("await importDialog.getByRole(\"button\", { name: /取\\s*消/ }).click();");
  });
  it("waits for reloaded deletion rows to render before capturing successful UI evidence", () => {
    const source = script();
    const readiness = source.indexOf('for (const row of afterDeletion.items)');
    expect(readiness).toBeGreaterThan(source.indexOf('evidence.applicableDeletion = afterDeletion;'));
    expect(readiness).toBeLessThan(source.indexOf('await shot(page, "applicable-deletion-reloaded")'));
    expect(source).toContain('row.product_characteristic || row.process_characteristic');
  });
  it("namespaces the second PFMEA fixture without changing its document type", () => {
    const source = script();
    expect(source).toContain('async function draft(type: string, label = type)');
    expect(source).toContain('document_no: `${prefix}-${label}`, fmea_type: type');
    expect(source).toContain('await draft("PFMEA", "PFMEA-TREE")');
  });
  it("uses wizard editing and legally completes the draft before the main tree deletion", () => {
    const source = script();
    expect(source).toContain("await completeDraftWizard(page, doc.fmea_id);");
    expect(source).not.toContain("await page.getByTestId(\"fmea-structure-node-wf\").click();");
    const deletion = source.slice(source.indexOf("test(\"editor function deletion"));
    expect(deletion.indexOf("await completeDraftWizard(page, doc.fmea_id);")).toBeLessThan(deletion.indexOf("const row ="));
    expect(deletion).toContain("await page.goto(`/fmea/pfmea-wizard/${doc.fmea_id}`);");
    expect(source).toContain("await page.getByRole(\"button\", { name: /完成/ }).click();");
  });
});


it("candidate-table-only partial selection retains its notice until explicit dismissal (mock API)", async () => {
  const onClose = vi.fn();
  render(<App><ImportFromFMEAModal cpId="cp-1" expectedLockVersion={7} open onClose={onClose} onSuccess={vi.fn()} /></App>);
  await choose(0, "PFMEA-01 - 装配");
  await choose(1, "v1.0");
  await screen.findByText("装配");
  fireEvent.click(screen.getByRole("button", { name: "Preview changes" }));
  await screen.findByText("尺寸");
  const tables = screen.getAllByRole("table");
  expect(tables).toHaveLength(2);
  const candidates = tables.find((table) => within(table).queryByText("尺寸"))!;
  expect(candidates.querySelectorAll("tbody tr")).toHaveLength(2);
  fireEvent.click(within(candidates.querySelectorAll("tbody tr")[1] as HTMLElement).getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: /Confirm import/ }));
  expect(await screen.findByText("Partially imported; 1 item(s) remain pending.")).toBeInTheDocument();
  expect(onClose).not.toHaveBeenCalled();
  expect(mocks.applyImportFromFMEA).toHaveBeenCalledWith("cp-1", expect.objectContaining({ selected_candidate_keys: ["add-1"] }));
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(onClose).toHaveBeenCalledTimes(1);
});

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { App } from "antd";
import SyncPreviewDrawer from "./SyncPreviewDrawer";

const mocks = vi.hoisted(() => ({ getSyncPreview: vi.fn(), applySyncFromFMEA: vi.fn() }));
vi.mock("../../api/version", () => ({ getSyncPreview: mocks.getSyncPreview, applySyncFromFMEA: mocks.applySyncFromFMEA }));

const preview = {
  source_fmea_version_id: "version-approved", fmea_version_id: "version-approved", fmea_version: "v1.0",
  expected_lock_version: 9, mapping_version: 3, preview_digest: "digest-9", issues: [{ code: "relationship_warning", message: "关系需要复核" }],
  summary: { add_count: 1, update_count: 2, delete_count: 1 },
  items: [
    { candidate_key: "add", item_id: null, action: "add", applicable: true, source_ref: {}, source_fmea_node_id: "n1", step_no: "10", base_value: null, current_value: null, fmea_new_value: { product_characteristic: "尺寸" }, merged_value: { product_characteristic: "尺寸" }, diff_fields: [], issues: [], conflicts: [] },
    { candidate_key: "sync", item_id: "item-2", action: "sync", applicable: true, source_ref: {}, source_fmea_node_id: "n2", step_no: "20", base_value: {}, current_value: { process_characteristic: "温度" }, fmea_new_value: { process_characteristic: "温度" }, merged_value: {}, diff_fields: ["process_characteristic"], issues: [], conflicts: [] },
    { candidate_key: "delete", item_id: "item-3", action: "delete", applicable: true, source_ref: {}, source_fmea_node_id: "n3", step_no: "30", base_value: {}, current_value: {}, fmea_new_value: null, merged_value: null, diff_fields: [], issues: [], conflicts: [] },
    { candidate_key: "protected", item_id: "item-4", action: "sync", applicable: true, source_ref: {}, source_fmea_node_id: "n4", step_no: "40", base_value: {}, current_value: {}, fmea_new_value: {}, merged_value: {}, diff_fields: [], issues: [{ code: "protected", message: "受保护，不能同步" }], conflicts: [{ code: "protected", message: "受保护，不能同步" }] },
    { candidate_key: "not-applicable", item_id: "item-5", action: "sync", applicable: false, source_ref: {}, source_fmea_node_id: "n5", step_no: "50", base_value: {}, current_value: {}, fmea_new_value: {}, merged_value: {}, diff_fields: [], issues: [{ code: "not_applicable", message: "不适用" }], conflicts: [] },
  ],
};

function renderDrawer() {
  return render(<App><SyncPreviewDrawer open cpId="cp-1" sourceFmeaVersionId="version-approved" onClose={vi.fn()} onSuccess={vi.fn()} /></App>);
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getSyncPreview.mockResolvedValue(preview);
  mocks.applySyncFromFMEA.mockResolvedValue({ version_id: "cp-version-2" });
});

describe("SyncPreviewDrawer preview-confirm flow", () => {
  it("uses candidate keys, excludes delete defaults, and disables protected candidates", async () => {
    renderDrawer();
    await waitFor(() => expect(mocks.getSyncPreview).toHaveBeenCalledWith("cp-1", "version-approved"));
    expect(await screen.findByText("关系需要复核")).toBeInTheDocument();

    expect(within(screen.getByText("30").closest("tr")!).getByRole("checkbox")).not.toBeChecked();
    expect(within(screen.getByText("40").closest("tr")!).getByRole("checkbox")).toBeDisabled();
    expect(within(screen.getByText("50").closest("tr")!).getByRole("checkbox")).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Confirm sync" }));
    await waitFor(() => expect(mocks.applySyncFromFMEA).toHaveBeenCalledWith("cp-1", {
      source_fmea_version_id: "version-approved", expected_lock_version: 9,
      preview_digest: "digest-9", selected_candidate_keys: ["add", "sync"],
    }));
  });

  it("does not retry a stale sync and requires an explicit fresh preview", async () => {
    mocks.applySyncFromFMEA.mockRejectedValueOnce({ response: { status: 409 } });
    renderDrawer();
    await screen.findByText("关系需要复核");
    fireEvent.click(screen.getByRole("button", { name: "Confirm sync" }));
    await waitFor(() => expect(mocks.applySyncFromFMEA).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("Preview expired. Generate a new preview before confirming.")).toBeInTheDocument();
    expect(mocks.getSyncPreview).toHaveBeenCalledTimes(1);
  });

  it("ignores a preview response after its CP or selected source context changes", async () => {
    let resolveFirst: ((value: typeof preview) => void) | undefined;
    mocks.getSyncPreview
      .mockImplementationOnce(() => new Promise<typeof preview>((resolve) => { resolveFirst = resolve; }))
      .mockResolvedValueOnce({ ...preview, fmea_version: "v2.0", source_fmea_version_id: "version-2", fmea_version_id: "version-2" });
    const onSuccess = vi.fn();
    const { rerender } = render(<App><SyncPreviewDrawer open cpId="cp-1" sourceFmeaVersionId="version-approved" onClose={vi.fn()} onSuccess={onSuccess} /></App>);
    rerender(<App><SyncPreviewDrawer open cpId="cp-2" sourceFmeaVersionId="version-2" onClose={vi.fn()} onSuccess={onSuccess} /></App>);
    await screen.findByText("FMEA Version: v2.0");
    resolveFirst?.(preview);
    await waitFor(() => expect(screen.queryByText("FMEA Version: v1.0")).not.toBeInTheDocument());
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("allows an explicit empty acknowledgement when only non-blocking warnings remain", async () => {
    mocks.getSyncPreview.mockResolvedValueOnce({
      ...preview,
      items: [],
      issues: [{ code: "review", message: "保留人工复核说明", blocking: false }],
      summary: { add_count: 0, update_count: 0, delete_count: 0 },
    });
    renderDrawer();
    expect(await screen.findByText("保留人工复核说明")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm no changes" })).toBeEnabled();
  });

  it("rejects an empty acknowledgement when the preview warning is blocking", async () => {
    mocks.getSyncPreview.mockResolvedValueOnce({
      ...preview,
      items: [],
      issues: [{ code: "blocked", message: "存在阻塞项", blocking: true }],
      summary: { add_count: 0, update_count: 0, delete_count: 0 },
    });
    renderDrawer();
    expect(await screen.findByText("存在阻塞项")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm no changes" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm sync" })).toBeDisabled();
  });

  it("keeps a partial sync open and reports the remaining protected work", async () => {
    const onClose = vi.fn();
    const onSuccess = vi.fn().mockResolvedValue(undefined);
    render(<App><SyncPreviewDrawer open cpId="cp-1" sourceFmeaVersionId="version-approved" onClose={onClose} onSuccess={onSuccess} /></App>);
    await screen.findByText("关系需要复核");
    fireEvent.click(within(screen.getByText("20").closest("tr")!).getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Confirm sync" }));
    await waitFor(() => expect(mocks.applySyncFromFMEA).toHaveBeenCalledWith("cp-1", expect.objectContaining({ selected_candidate_keys: ["add"] })));
    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("4 item(s) remain pending.")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /Preview again/ })).toBeInTheDocument();
  });

  it("reports a refresh failure after a committed sync separately from a rejected write", async () => {
    const onClose = vi.fn();
    const onSuccess = vi.fn().mockRejectedValue(new Error("refresh failed"));
    render(<App><SyncPreviewDrawer open cpId="cp-1" sourceFmeaVersionId="version-approved" onClose={onClose} onSuccess={onSuccess} /></App>);
    await screen.findByText("关系需要复核");
    fireEvent.click(within(screen.getByText("20").closest("tr")!).getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Confirm sync" }));
    await waitFor(() => expect(mocks.applySyncFromFMEA).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("Sync was applied, but the latest control plan could not be refreshed. Generate a new preview before another confirmation.")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /Preview again/ })).toBeInTheDocument();
  });

  it("freezes sync selection during apply so a committed full sync completes callbacks", async () => {
    let resolveApply: (() => void) | undefined;
    mocks.getSyncPreview.mockResolvedValueOnce({ ...preview, items: [preview.items[0]], issues: [], summary: { add_count: 1, update_count: 0, delete_count: 0 } });
    mocks.applySyncFromFMEA.mockImplementationOnce(() => new Promise<void>((resolve) => { resolveApply = resolve; }));
    const onClose = vi.fn();
    const onSuccess = vi.fn().mockResolvedValue(undefined);
    render(<App><SyncPreviewDrawer open cpId="cp-1" sourceFmeaVersionId="version-approved" onClose={onClose} onSuccess={onSuccess} /></App>);
    await screen.findByText("10");
    fireEvent.click(screen.getByRole("button", { name: "Confirm sync" }));
    await waitFor(() => expect(mocks.applySyncFromFMEA).toHaveBeenCalledTimes(1));
    expect(within(screen.getByText("10").closest("tr")!).getByRole("checkbox")).toBeDisabled();
    resolveApply?.();
    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("ignores an in-flight apply completion after external CP context changes", async () => {
    let resolveApply: (() => void) | undefined;
    mocks.getSyncPreview.mockResolvedValue({ ...preview, items: [preview.items[0]], issues: [], summary: { add_count: 1, update_count: 0, delete_count: 0 } });
    mocks.applySyncFromFMEA.mockImplementationOnce(() => new Promise<void>((resolve) => { resolveApply = resolve; }));
    const onClose = vi.fn();
    const onSuccess = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(<App><SyncPreviewDrawer open cpId="cp-1" sourceFmeaVersionId="version-approved" onClose={onClose} onSuccess={onSuccess} /></App>);
    await screen.findByText("10");
    fireEvent.click(screen.getByRole("button", { name: "Confirm sync" }));
    await waitFor(() => expect(mocks.applySyncFromFMEA).toHaveBeenCalledTimes(1));
    rerender(<App><SyncPreviewDrawer open cpId="cp-2" sourceFmeaVersionId="version-2" onClose={onClose} onSuccess={onSuccess} /></App>);
    resolveApply?.();
    await waitFor(() => expect(mocks.getSyncPreview).toHaveBeenCalledWith("cp-2", "version-2"));
    expect(onSuccess).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("explicitly acknowledges an empty no-op preview without inventing a selection", async () => {
    mocks.getSyncPreview.mockResolvedValueOnce({ ...preview, items: [], issues: [], summary: { add_count: 0, update_count: 0, delete_count: 0 } });
    renderDrawer();
    await waitFor(() => expect(screen.getByRole("button", { name: "Confirm no changes" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Confirm no changes" }));
    await waitFor(() => expect(mocks.applySyncFromFMEA).toHaveBeenCalledWith("cp-1", {
      source_fmea_version_id: "version-approved", expected_lock_version: 9, preview_digest: "digest-9", selected_candidate_keys: [],
    }));
  });
});


describe("final review regressions", () => {
  it("allows explicit selection and submission of an applicable deletion", async () => {
    renderDrawer();
    await screen.findByText("30");
    const deletion = within(screen.getByText("30").closest("tr")!).getByRole("checkbox");
    expect(deletion).not.toBeChecked();
    expect(deletion).toBeEnabled();
    fireEvent.click(deletion);
    fireEvent.click(screen.getByRole("button", { name: "Confirm sync" }));
    await waitFor(() => expect(mocks.applySyncFromFMEA).toHaveBeenCalledWith("cp-1", expect.objectContaining({ selected_candidate_keys: ["add", "sync", "delete"] })));
  });

  it("reopens with a fresh usable preview while an obsolete apply is unresolved", async () => {
    let resolveApply!: () => void;
    mocks.applySyncFromFMEA.mockImplementationOnce(() => new Promise<void>((resolve) => { resolveApply = resolve; }));
    const onSuccess = vi.fn();
    const props = { cpId: "cp-1", sourceFmeaVersionId: "version-approved", onClose: vi.fn(), onSuccess };
    const { rerender } = render(<App><SyncPreviewDrawer {...props} open /></App>);
    await screen.findByText("30");
    fireEvent.click(screen.getByRole("button", { name: /Confirm sync/ }));
    await waitFor(() => expect(mocks.applySyncFromFMEA).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    rerender(<App><SyncPreviewDrawer {...props} open={false} /></App>);
    await waitFor(() => expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument());
    rerender(<App><SyncPreviewDrawer {...props} open /></App>);
    await waitFor(() => expect(mocks.getSyncPreview).toHaveBeenCalledTimes(2));
    await screen.findByText("30");
    await waitFor(() => expect(screen.getByRole("button", { name: /Confirm sync/ })).toBeEnabled());
    resolveApply();
    await waitFor(() => expect(onSuccess).not.toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: /Confirm sync/ }));
    await waitFor(() => expect(mocks.applySyncFromFMEA).toHaveBeenCalledTimes(2));
  });
});

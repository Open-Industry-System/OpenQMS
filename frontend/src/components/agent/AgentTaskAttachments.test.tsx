import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AgentTaskAttachments from "./AgentTaskAttachments";
import * as api from "../../api/agentTaskAttachments";

vi.mock("../../api/agentTaskAttachments", () => ({
  getAttachmentAvailability: vi.fn(),
  listTaskAttachments: vi.fn(),
  uploadTaskAttachment: vi.fn(),
  deleteTaskAttachment: vi.fn(),
  downloadTaskAttachment: vi.fn()
}));

const taskId = "00000000-0000-4000-8000-000000000001";
const attachment = {
  attachment_id: "00000000-0000-4000-8000-000000000002",
  display_name: "clean.pdf",
  extension: "pdf",
  byte_size: 42,
  status: "available" as const,
  created_at: "2026-10-12T00:00:00Z",
  updated_at: "2026-10-12T00:00:01Z",
  expires_at: "2026-10-13T00:00:00Z"
};

describe("AgentTaskAttachments", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getAttachmentAvailability).mockResolvedValue({ enabled: true });
    vi.mocked(api.listTaskAttachments).mockResolvedValue({ items: [attachment] });
  });
  afterEach(() => vi.restoreAllMocks());

  it("does not send multipart until availability succeeds", async () => {
    let resolveAvailability!: (value: { enabled: true }) => void;
    vi.mocked(api.getAttachmentAvailability).mockReturnValue(new Promise(resolve => { resolveAvailability = resolve; }));
    render(<AgentTaskAttachments taskId={taskId} identity="u1" credential="jwt" open requestEpoch={1} />);

    expect(api.uploadTaskAttachment).not.toHaveBeenCalled();
    expect(api.listTaskAttachments).not.toHaveBeenCalled();
    resolveAvailability({ enabled: true });
    await screen.findByText("任务私有附件");
    expect(api.listTaskAttachments).toHaveBeenCalledWith(taskId, expect.any(AbortSignal));
  });

  it("clears selected file and rows on authorization loss", async () => {
    let rejectList!: (error: unknown) => void;
    vi.mocked(api.listTaskAttachments).mockReturnValue(new Promise((_, reject) => { rejectList = reject; }));
    render(<AgentTaskAttachments taskId={taskId} identity="u1" credential="jwt" open requestEpoch={1} />);

    await screen.findByText("任务私有附件");
    const picker = screen.getByLabelText("选择附件");
    fireEvent.change(picker, { target: { files: [new File(["safe"], "local.pdf", { type: "application/pdf" })] } });
    await waitFor(() => expect(screen.getByText("local.pdf")).toBeInTheDocument());
    rejectList({ response: { status: 403 } });
    await waitFor(() => expect(screen.queryByText("任务私有附件")).toBeNull());
    expect(screen.queryByText("local.pdf")).toBeNull();
  });

  it("aborts concurrent download and delete requests when the session changes", async () => {
    let resolveDownload!: (value: Blob) => void;
    let resolveDelete!: () => void;
    vi.mocked(api.downloadTaskAttachment).mockReturnValue(new Promise<Blob>(resolve => { resolveDownload = resolve; }));
    vi.mocked(api.deleteTaskAttachment).mockReturnValue(new Promise<void>(resolve => { resolveDelete = resolve; }));
    const view = render(<AgentTaskAttachments taskId={taskId} identity="u1" credential="jwt" open requestEpoch={1} />);

    await screen.findByRole("button", { name: "下载" });
    fireEvent.click(screen.getByRole("button", { name: "下载" }));
    fireEvent.click(screen.getByRole("button", { name: "删除" }));
    const downloadSignal = vi.mocked(api.downloadTaskAttachment).mock.calls[0][2];
    const deleteSignal = vi.mocked(api.deleteTaskAttachment).mock.calls[0][2];
    view.rerender(<AgentTaskAttachments taskId={taskId} identity="u2" credential="jwt" open requestEpoch={2} />);

    expect(downloadSignal?.aborted).toBe(true);
    expect(deleteSignal?.aborted).toBe(true);
    resolveDownload(new Blob());
    resolveDelete();
  });

  it("triggers one-time download and revokes its object URL", async () => {
    const blob = new Blob(["clean"]);
    vi.mocked(api.downloadTaskAttachment).mockResolvedValue(blob);
    const create = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:attachment");
    const revoke = vi.spyOn(URL, "revokeObjectURL");
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<AgentTaskAttachments taskId={taskId} identity="u1" credential="jwt" open requestEpoch={1} />);

    await screen.findByRole("button", { name: "下载" });
    fireEvent.click(screen.getByRole("button", { name: "下载" }));
    await waitFor(() => expect(create).toHaveBeenCalledWith(blob));
    expect(click).toHaveBeenCalledOnce();
    await waitFor(() => expect(revoke).toHaveBeenCalledWith("blob:attachment"));
  });
});

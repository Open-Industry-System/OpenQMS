import { beforeEach, describe, expect, it, vi } from "vitest";
import client from "./client";
import { getAttachmentAvailability, listTaskAttachments, uploadTaskAttachment } from "./agentTaskAttachments";

vi.mock("./client", () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }));

const taskId = "00000000-0000-4000-8000-000000000001";
const attachmentId = "00000000-0000-4000-8000-000000000002";
const attachment = {
  attachment_id: attachmentId,
  display_name: "clean.pdf",
  byte_size: 42,
  status: "available",
  scanned_at: "2026-10-12T00:00:00Z",
  expires_at: "2026-10-13T00:00:00Z"
};

describe("controlled task attachment API", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends only the file multipart field after availability is explicitly requested", async () => {
    vi.mocked(client.get).mockResolvedValue({ data: { enabled: true } });
    vi.mocked(client.post).mockResolvedValue({ data: attachment });
    const file = new File(["safe"], "clean.pdf", { type: "application/pdf" });
    const signal = new AbortController().signal;

    await getAttachmentAvailability(taskId, signal);
    await uploadTaskAttachment(taskId, file, signal);

    expect(client.get).toHaveBeenCalledWith(`/agent/tasks/${taskId}/attachments/availability`, { signal });
    expect(client.post).toHaveBeenCalledWith(`/agent/tasks/${taskId}/attachments`, expect.any(FormData), { signal });
    const body = vi.mocked(client.post).mock.calls[0][1] as FormData;
    expect([...body.keys()]).toEqual(["file"]);
    expect(body.get("file")).toBe(file);
  });

  it("rejects unknown or malformed attachment metadata before returning it", async () => {
    vi.mocked(client.get).mockResolvedValueOnce({ data: { items: [{ ...attachment, unsafe: "no" }] } })
      .mockResolvedValueOnce({ data: { items: [{ ...attachment, scanned_at: "not-a-date" }] } });

    await expect(listTaskAttachments(taskId)).rejects.toThrow("Invalid Agent attachment response");
    await expect(listTaskAttachments(taskId)).rejects.toThrow("Invalid Agent attachment response");
  });
});

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api/agentWorkspace";
import { useAuthStore } from "../../store/authStore";
import type { User } from "../../types";
import WorkspaceAssistant from "./WorkspaceAssistant";

vi.mock("../../api/agentWorkspace");

const reportId = "40404040-4040-4040-8040-404040404040";
const otherReportId = "50505050-5050-4050-8050-505050505050";
const conversationId = "ccc1";
const resumeId = "60606060-6060-4060-8060-606060606060";
const otherResumeId = "70707070-7070-4070-8070-707070707070";
const sourcePath = `/capa/${reportId}`;
const resumePath = `${sourcePath}?workspace_conversation=${resumeId}`;
const page = { kind: "capa", report_id: reportId } as const;
const list: api.WorkspaceResult = {
  kind: "pfmea_list",
  id: "list",
  items: [{ id: "existing-fmea", document_no: "PFMEA-A", title: "过程分析" }],
};
const preview: api.WorkspaceResult = {
  kind: "draft_preview",
  id: "draft-proposal",
  preview: {
    factory_name: "苏州工厂",
    product_line_name: "压铸线",
    title: "加严巡检草稿",
    document_no: "PFMEA-2026-D2",
    source_document_no: "8D-001",
    fmea_type: "PFMEA",
  },
};
const receipt: api.WorkspaceActionResult = {
  status: "applied",
  draft: { id: "created-fmea", document_no: preview.preview.document_no, title: preview.preview.title },
};

function Controls() {
  const navigate = useNavigate();
  return <>
    <button onClick={() => navigate(`/capa/${otherReportId}`)}>切换报告</button>
    <button onClick={() => navigate(`${sourcePath}?workspace_conversation=${otherResumeId}`)}>切换会话</button>
  </>;
}

function renderAssistant(path: string) {
  return render(<MemoryRouter initialEntries={[path]}>
    <WorkspaceAssistant />
    <Controls />
  </MemoryRouter>);
}

async function open() {
  renderAssistant(sourcePath);
  fireEvent.click(await screen.findByRole("button", { name: "工作区助手" }));
  return await screen.findByRole("textbox", { name: "向 Pi 提问" });
}

function input(text: string) {
  const textarea = screen.getByRole("textbox", { name: "向 Pi 提问" });
  fireEvent.change(textarea, { target: { value: text } });
  return textarea;
}

function send(text: string) {
  fireEvent.keyDown(input(text), { key: "Enter" });
}

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.setItem("access_token", "employee");
  localStorage.setItem("tenant_slug", "factory-tenant");
  localStorage.setItem("current_factory_id", "factory-1");
  useAuthStore.setState({
    token: "employee",
    user: {
      user_id: "operator",
      tenant_id: "tenant",
      is_active: true,
    } as User,
    currentFactoryId: "factory-1",
  });
  vi.mocked(api.getWorkspaceAvailability).mockResolvedValue({
    enabled: true,
    context: { document_no: "8D-001" },
  });
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  useAuthStore.setState({ token: null, user: null, currentFactoryId: null });
});

describe("工作区助手", () => {
  it("opens a linked conversation and waits for confirmation of its original draft preview", async () => {
    vi.mocked(api.getWorkspaceConversation).mockResolvedValue({
      conversation_id: resumeId,
      items: [{ kind: "user", id: "first-message", content: "准备一份巡检草稿" }, list, preview],
    });
    vi.mocked(api.resolveWorkspaceAction).mockResolvedValue(receipt);
    renderAssistant(resumePath);

    const drawer = await screen.findByRole("dialog", { name: "工作区助手" });
    expect(await within(drawer).findByText("准备一份巡检草稿")).toBeInTheDocument();
    expect(within(drawer).getByRole("link", { name: /PFMEA-A/ })).toBeInTheDocument();
    const card = within(drawer).getByRole("region", { name: "PFMEA 草稿预览" });
    expect(within(card).getByText("待确认")).toBeInTheDocument();
    expect(api.getWorkspaceConversation).toHaveBeenCalledWith(resumeId, page, expect.any(AbortSignal));
    expect(api.sendWorkspaceTurn).not.toHaveBeenCalled();
    expect(api.resolveWorkspaceAction).not.toHaveBeenCalled();

    fireEvent.click(within(card).getByRole("button", { name: "确认创建" }));
    expect(await within(drawer).findByRole("link", { name: /PFMEA-2026-D2/ })).toHaveAttribute("href", "/fmea/created-fmea");
    expect(api.resolveWorkspaceAction).toHaveBeenCalledOnce();
    expect(api.resolveWorkspaceAction).toHaveBeenCalledWith(
      preview.id, "confirm", { conversation_id: resumeId, page }, "factory-1", expect.any(AbortSignal),
    );
  });

  it.each([403, 404, 409])("starts a blank chat when the linked conversation is no longer available (%s)", async status => {
    vi.mocked(api.getWorkspaceConversation).mockRejectedValue({ response: { status } });
    vi.mocked(api.sendWorkspaceTurn).mockResolvedValue({ conversation_id: conversationId, items: [] });
    renderAssistant(resumePath);

    expect(await screen.findByText("无法恢复这段工作区会话。你可以开始新的对话。")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "PFMEA 草稿预览" })).not.toBeInTheDocument();
    send("开始新对话");
    expect(vi.mocked(api.sendWorkspaceTurn).mock.calls[0][0].conversation_id).toBeUndefined();
    await waitFor(() => expect(screen.queryByText("Pi 正在处理…")).not.toBeInTheDocument());
  });

  it("does not read a linked conversation if the report is unavailable", async () => {
    vi.mocked(api.getWorkspaceAvailability).mockRejectedValue({ response: { status: 403 } });
    renderAssistant(resumePath);

    expect(await screen.findByText("工作区助手暂不可用。")).toBeInTheDocument();
    expect(api.getWorkspaceConversation).not.toHaveBeenCalled();
    expect(screen.queryByRole("textbox", { name: "向 Pi 提问" })).not.toBeInTheDocument();
  });

  it("aborts an in-flight restore when the linked conversation changes on the same report", async () => {
    let finish!: (value: Awaited<ReturnType<typeof api.getWorkspaceConversation>>) => void;
    vi.mocked(api.getWorkspaceConversation)
      .mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }))
      .mockResolvedValueOnce({ conversation_id: otherResumeId, items: [] });
    renderAssistant(resumePath);

    await screen.findByText("正在恢复工作区会话…");
    send("尚未恢复时不发送");
    expect(api.sendWorkspaceTurn).not.toHaveBeenCalled();
    const signal = vi.mocked(api.getWorkspaceConversation).mock.calls[0][2];
    fireEvent.click(screen.getByRole("button", { name: "切换会话", hidden: true }));
    expect(signal.aborted).toBe(true);
    await waitFor(() => expect(api.getWorkspaceConversation).toHaveBeenLastCalledWith(otherResumeId, page, expect.any(AbortSignal)));
    await act(async () => finish({ conversation_id: resumeId, items: [preview] }));
    expect(screen.queryByRole("region", { name: "PFMEA 草稿预览" })).not.toBeInTheDocument();
  });

  it("withdraws all restored conversation data when action access is revoked", async () => {
    vi.mocked(api.getWorkspaceConversation).mockResolvedValue({
      conversation_id: resumeId,
      items: [{ kind: "user", id: "prior-message", content: "原有试用消息" }, list, preview],
    });
    vi.mocked(api.resolveWorkspaceAction).mockRejectedValue({ response: { status: 403 } });
    vi.mocked(api.sendWorkspaceTurn).mockResolvedValue({ conversation_id: conversationId, items: [] });
    renderAssistant(resumePath);

    fireEvent.click(await screen.findByRole("button", { name: "确认创建" }));
    expect(await screen.findByText("当前会话或报告已不可访问。请检查页面后重试。")).toBeInTheDocument();
    expect(screen.queryByText("原有试用消息")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "PFMEA 草稿预览" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /PFMEA-A/ })).not.toBeInTheDocument();
    send("开始新对话");
    expect(vi.mocked(api.sendWorkspaceTurn).mock.calls[0][0].conversation_id).toBeUndefined();
    await waitFor(() => expect(screen.queryByText("Pi 正在处理…")).not.toBeInTheDocument());
  });

  it("shows authorized PFMEA links and creates only the exact preview after confirmation", async () => {
    vi.mocked(api.sendWorkspaceTurn)
      .mockResolvedValueOnce({ conversation_id: conversationId, items: [list] })
      .mockResolvedValueOnce({ conversation_id: conversationId, items: [preview] });
    vi.mocked(api.resolveWorkspaceAction).mockResolvedValue(receipt);
    await open();
    expect(api.getWorkspaceConversation).not.toHaveBeenCalled();
    expect(screen.getByText("8D · 8D-001")).toBeInTheDocument();

    const textarea = input("同一条线有哪些 PFMEA？");
    fireEvent.compositionStart(textarea);
    fireEvent.keyDown(textarea, { key: "Enter" });
    fireEvent.compositionEnd(textarea);
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    expect(api.sendWorkspaceTurn).not.toHaveBeenCalled();
    fireEvent.keyDown(textarea, { key: "Enter" });

    expect(await screen.findByRole("link", { name: /PFMEA-A.*过程分析/ })).toHaveAttribute("href", "/fmea/existing-fmea");
    expect(api.sendWorkspaceTurn).toHaveBeenLastCalledWith(
      { page, request_id: expect.any(String), content: "同一条线有哪些 PFMEA？" },
      "factory-1",
      expect.any(AbortSignal),
    );

    send("创建一份加严巡检草稿，单号 PFMEA-2026-D2");
    const card = await screen.findByRole("region", { name: "PFMEA 草稿预览" });
    for (const value of Object.values(preview.preview)) {
      expect(within(card).getByText(value, { selector: "dd" })).toBeInTheDocument();
    }
    expect(api.resolveWorkspaceAction).not.toHaveBeenCalled();
    expect(api.sendWorkspaceTurn).toHaveBeenLastCalledWith(
      expect.objectContaining({ conversation_id: conversationId, page }),
      "factory-1",
      expect.any(AbortSignal),
    );

    const confirm = within(card).getByRole("button", { name: "确认创建" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect(await screen.findByRole("link", { name: /PFMEA-2026-D2 · 加严巡检草稿/ })).toHaveAttribute("href", "/fmea/created-fmea");
    expect(api.resolveWorkspaceAction).toHaveBeenCalledTimes(1);
    expect(api.resolveWorkspaceAction).toHaveBeenCalledWith(
      preview.id, "confirm", { conversation_id: conversationId, page }, "factory-1", expect.any(AbortSignal),
    );
  });

  it("retries the same message and action after uncertain results", async () => {
    vi.mocked(api.sendWorkspaceTurn)
      .mockRejectedValueOnce(new Error("connection lost"))
      .mockResolvedValueOnce({ conversation_id: conversationId, items: [list, preview] });
    vi.mocked(api.resolveWorkspaceAction)
      .mockRejectedValueOnce(new Error("connection lost"))
      .mockResolvedValueOnce(receipt);
    await open();
    send("创建草稿");
    fireEvent.click(await screen.findByRole("button", { name: "重试消息" }));
    fireEvent.click(await screen.findByRole("button", { name: "确认创建" }));

    const retry = await screen.findByRole("button", { name: "重试确认" });
    expect(screen.queryByRole("region", { name: "PFMEA 草稿预览" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /PFMEA-A/ })).not.toBeInTheDocument();
    expect(screen.getAllByText("创建草稿")).toHaveLength(1);

    fireEvent.click(retry);
    expect(await screen.findByText("已创建草稿", { exact: false, selector: "p" })).toBeInTheDocument();
    expect(vi.mocked(api.sendWorkspaceTurn).mock.calls[0][0]).toEqual(vi.mocked(api.sendWorkspaceTurn).mock.calls[1][0]);
    expect(vi.mocked(api.resolveWorkspaceAction).mock.calls[0].slice(0, 4))
      .toEqual(vi.mocked(api.resolveWorkspaceAction).mock.calls[1].slice(0, 4));
  });

  it("cancels an offered action and clears prior results on access denial", async () => {
    vi.mocked(api.sendWorkspaceTurn)
      .mockResolvedValueOnce({ conversation_id: conversationId, items: [list, preview] })
      .mockRejectedValueOnce({ response: { status: 403 } });
    vi.mocked(api.resolveWorkspaceAction).mockResolvedValue({ status: "cancelled" });
    await open();
    send("给我看一下并准备草稿");
    const card = await screen.findByRole("region", { name: "PFMEA 草稿预览" });
    fireEvent.click(within(card).getByRole("button", { name: "取消" }));
    expect(await within(card).findByText("已取消创建。")).toBeInTheDocument();
    expect(api.resolveWorkspaceAction).toHaveBeenCalledOnce();
    expect(api.resolveWorkspaceAction).toHaveBeenCalledWith(
      preview.id, "cancel", { conversation_id: conversationId, page }, "factory-1", expect.any(AbortSignal),
    );
    expect(within(card).queryByRole("button", { name: "确认创建" })).not.toBeInTheDocument();
    send("还有哪些？");
    expect(await screen.findByText("当前会话或报告已不可访问。请检查页面后重试。")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /PFMEA-A/ })).not.toBeInTheDocument();
    expect(screen.queryByText("加严巡检草稿")).not.toBeInTheDocument();
  });

  it("starts a fresh turn after the previous conversation becomes stale", async () => {
    vi.mocked(api.sendWorkspaceTurn)
      .mockResolvedValueOnce({ conversation_id: conversationId, items: [list, preview] })
      .mockRejectedValueOnce({ response: { status: 409 } })
      .mockResolvedValueOnce({ conversation_id: "new-conversation", items: [] });
    await open();
    send("查看同产品线 PFMEA 并准备草稿");
    await screen.findByRole("region", { name: "PFMEA 草稿预览" });
    send("换个标题");
    expect(await screen.findByText("本次对话已失效。请重新提问。")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "PFMEA 草稿预览" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /PFMEA-A/ })).not.toBeInTheDocument();
    send("重新查询 PFMEA");
    expect(vi.mocked(api.sendWorkspaceTurn).mock.calls[2][0].conversation_id).toBeUndefined();
    await waitFor(() => expect(screen.queryByText("Pi 正在处理…")).not.toBeInTheDocument());
  });

  it("keeps the transcript position while reading older messages", async () => {
    vi.mocked(api.sendWorkspaceTurn)
      .mockResolvedValueOnce({ conversation_id: conversationId, items: [list] })
      .mockResolvedValueOnce({ conversation_id: conversationId, items: [preview] });
    await open();
    send("列出 PFMEA");
    await screen.findByRole("link", { name: /PFMEA-A/ });
    const transcript = screen.getByRole("log", { name: "工作区对话" });
    Object.defineProperties(transcript, { scrollHeight: { value: 500 }, clientHeight: { value: 200 } });
    transcript.scrollTop = 20;
    fireEvent.scroll(transcript);

    send("准备一份草稿");
    await screen.findByRole("region", { name: "PFMEA 草稿预览" });
    expect(transcript.scrollTop).toBe(20);
    fireEvent.click(screen.getByRole("button", { name: "回到最新消息" }));
    expect(transcript.scrollTop).toBe(500);
  });

  it("withdraws old conversation data when switching pages and ignores a pending turn", async () => {
    let finish!: (value: { conversation_id: string; items: api.WorkspaceResult[] }) => void;
    vi.mocked(api.sendWorkspaceTurn)
      .mockResolvedValueOnce({ conversation_id: conversationId, items: [list] })
      .mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    vi.mocked(api.getWorkspaceAvailability)
      .mockResolvedValueOnce({ enabled: true, context: { document_no: "8D-001" } })
      .mockRejectedValueOnce({ response: { status: 403 } });
    await open();
    send("查询 PFMEA");
    await screen.findByRole("link", { name: /PFMEA-A/ });
    send("准备一份草稿");
    const signal = vi.mocked(api.sendWorkspaceTurn).mock.calls[1][2];

    fireEvent.click(screen.getByRole("button", { name: "切换报告", hidden: true }));
    await screen.findByText("工作区助手暂不可用。");
    expect(signal.aborted).toBe(true);
    await act(async () => finish({ conversation_id: conversationId, items: [preview] }));
    expect(screen.queryByText("8D · 8D-001")).not.toBeInTheDocument();
    expect(screen.queryByText("加严巡检草稿")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /PFMEA-A/ })).not.toBeInTheDocument();
  });

  it("drops pending confirmations when the selected factory changes", async () => {
    vi.mocked(api.sendWorkspaceTurn).mockResolvedValue({ conversation_id: conversationId, items: [preview] });
    let finish!: (value: api.WorkspaceActionResult) => void;
    vi.mocked(api.resolveWorkspaceAction).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    await open();
    send("创建草稿");
    fireEvent.click(await screen.findByRole("button", { name: "确认创建" }));
    const signal = vi.mocked(api.resolveWorkspaceAction).mock.calls[0][4];

    act(() => useAuthStore.getState().setCurrentFactoryId("factory-2"));
    expect(signal.aborted).toBe(true);
    await act(async () => finish(receipt));
    fireEvent.click(await screen.findByRole("button", { name: "工作区助手" }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "向 Pi 提问" })).toBeInTheDocument());
    expect(screen.queryByText("加严巡检草稿")).not.toBeInTheDocument();
    expect(screen.queryByText("已创建草稿", { exact: false })).not.toBeInTheDocument();
  });
});

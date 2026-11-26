import { useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { CommentOutlined, FileAddOutlined, SendOutlined } from "@ant-design/icons";
import { Button, Drawer, Input } from "antd";
import { Link, matchPath, useLocation } from "react-router-dom";
import { registerCapaRequest } from "../../api/capaRequestOwnership";
import {
  getWorkspaceAvailability,
  getWorkspaceConversation,
  resolveWorkspaceAction,
  sendWorkspaceTurn,
  type WorkspaceActionResult,
  type WorkspaceConversationItem,
  type WorkspacePage,
  type WorkspaceResult,
  type WorkspaceTurn,
} from "../../api/agentWorkspace";
import { useAuthStore } from "../../store/authStore";
import { readAgentCredential, readAgentIdentity, readAgentScope } from "./useAgentTaskActivity";
import "./workspaceAssistant.css";

function readWorkspaceAuthority() {
  const identity = readAgentIdentity();
  return identity
    ? JSON.stringify([identity, readAgentCredential(), useAuthStore.getState().user?.tenant_id, readAgentScope()])
    : "";
}

function subscribeWorkspaceAuthority(update: () => void) {
  const unsubscribe = useAuthStore.subscribe(update);
  window.addEventListener("storage", update);
  const timer = window.setInterval(update, 250);
  return () => {
    unsubscribe();
    window.removeEventListener("storage", update);
    window.clearInterval(timer);
  };
}

function ownedRequest(authority: string) {
  const controller = new AbortController();
  const current = () => !controller.signal.aborted && authority === readWorkspaceAuthority();
  registerCapaRequest(controller.signal, current);
  return { controller, current };
}

export default function WorkspaceAssistant() {
  const authority = useSyncExternalStore(subscribeWorkspaceAuthority, readWorkspaceAuthority, readWorkspaceAuthority);
  return authority ? <WorkspaceAssistantPanel key={authority} authority={authority} /> : null;
}

function WorkspaceAssistantPanel({ authority }: { authority: string }) {
  const { pathname, search } = useLocation();
  const reportId = matchPath("/capa/:id", pathname)?.params.id;
  const resumeConversationId = reportId
    ? new URLSearchParams(search).get("workspace_conversation") || undefined
    : undefined;
  const page = useMemo<WorkspacePage | null>(
    () => reportId ? { kind: "capa", report_id: reportId } : null,
    [reportId],
  );
  const visit = useMemo(() => ({ pathname }), [pathname]);
  const [availability, setAvailability] = useState<{
    visit: typeof visit;
    enabled: boolean;
    documentNo?: string;
  } | null>(null);
  const [open, setOpen] = useState(Boolean(resumeConversationId));
  const launcher = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (resumeConversationId) setOpen(true);
  }, [pathname, resumeConversationId]);

  useEffect(() => {
    const { controller, current } = ownedRequest(authority);
    void getWorkspaceAvailability(page, controller.signal)
      .then(({ enabled, context }) => {
        if (current()) setAvailability({ visit, enabled, documentNo: context?.document_no });
      })
      .catch(() => {
        if (current()) setAvailability({ visit, enabled: false });
      });
    return () => controller.abort();
  }, [authority, page, visit]);

  const currentAvailability = availability?.visit === visit ? availability : null;
  const enabled = currentAvailability?.enabled;
  const documentNo = currentAvailability?.documentNo;

  if (!enabled && !open) return null;
  return <>
    {enabled && <Button
      ref={launcher}
      type="primary"
      className="workspace-assistant-launcher"
      icon={<CommentOutlined aria-hidden="true" />}
      aria-haspopup="dialog"
      aria-expanded={open}
      onClick={() => setOpen(true)}
    >工作区助手</Button>}
    <Drawer
      title="工作区助手"
      extra={<span className="workspace-assistant-provider">Pi</span>}
      open={open}
      onClose={() => setOpen(false)}
      afterOpenChange={visible => { if (!visible) launcher.current?.focus(); }}
      width="min(100vw, 480px)"
      styles={{ body: { padding: 0, overflow: "hidden" } }}
      rootClassName="workspace-assistant-drawer"
    >
      {enabled && <div className="workspace-assistant-context">
        <span>当前参考页</span>
        <strong>{documentNo ? `8D · ${documentNo}` : "当前页面暂不支持读取"}</strong>
      </div>}
      {enabled && page && documentNo ? (
        <WorkspaceConversation
          key={JSON.stringify([pathname, resumeConversationId])}
          authority={authority}
          page={page}
          resumeConversationId={resumeConversationId}
        />
      ) : (
        <p className="workspace-assistant-empty" role="status">
          {!currentAvailability ? "正在检查助手状态…" : enabled ? "请在已接入助手的 8D 报告中提问。" : "工作区助手暂不可用。"}
        </p>
      )}
    </Drawer>
  </>;
}

type DraftPreview = Extract<WorkspaceResult, { kind: "draft_preview" }>;
type Entry =
  | Exclude<WorkspaceConversationItem, DraftPreview>
  | (DraftPreview & { resolution?: WorkspaceActionResult })
  | { kind: "action_result"; id: string; resolution: WorkspaceActionResult };

type Request =
  | { kind: "turn"; body: WorkspaceTurn }
  | { kind: "action"; id: string; operation: "confirm" | "cancel"; conversationId: string };

function upsertEntries(entries: Entry[], newEntries: Entry[]) {
  const entriesById = new Map(entries.map(entry => [entry.id, entry]));
  for (const entry of newEntries) entriesById.set(entry.id, entry);
  return Array.from(entriesById.values());
}

function WorkspaceConversation({ authority, page, resumeConversationId }: {
  authority: string;
  page: WorkspacePage;
  resumeConversationId?: string;
}) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [conversationId, setConversationId] = useState<string>();
  const [restoring, setRestoring] = useState(Boolean(resumeConversationId));
  const [content, setContent] = useState("");
  const [pending, setPending] = useState<Request | null>(null);
  const [retry, setRetry] = useState<Request | null>(null);
  const [notice, setNotice] = useState("");
  const [away, setAway] = useState(false);
  const request = useRef<AbortController | null>(null);
  const composing = useRef(false);
  const transcript = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);

  useLayoutEffect(() => () => request.current?.abort(), []);
  useLayoutEffect(() => {
    if (!resumeConversationId) return;
    const { controller, current } = ownedRequest(authority);
    void getWorkspaceConversation(resumeConversationId, page, controller.signal)
      .then(result => {
        if (!current()) return;
        setConversationId(result.conversation_id);
        setEntries(result.items);
      })
      .catch(() => {
        if (current()) setNotice("无法恢复这段工作区会话。你可以开始新的对话。");
      })
      .finally(() => {
        if (current()) setRestoring(false);
      });
    return () => controller.abort();
  }, [authority, page, resumeConversationId]);
  useLayoutEffect(() => {
    if (followLatest.current && transcript.current) transcript.current.scrollTop = transcript.current.scrollHeight;
  }, [entries, pending, notice]);

  async function execute(operation: Request) {
    if (restoring || request.current || authority !== readWorkspaceAuthority()) return;
    const { controller, current } = ownedRequest(authority);
    const factoryId = useAuthStore.getState().currentFactoryId;
    request.current = controller;
    setPending(operation);
    setNotice("");
    setRetry(null);
    try {
      if (operation.kind === "turn") {
        const result = await sendWorkspaceTurn(operation.body, factoryId, controller.signal);
        if (!current()) return;
        setConversationId(result.conversation_id);
        setEntries(previous => upsertEntries(
          previous.filter(entry => entry.kind !== "draft_preview" || entry.resolution),
          result.items,
        ));
      } else {
        const resolution = await resolveWorkspaceAction(
          operation.id,
          operation.operation,
          { conversation_id: operation.conversationId, page },
          factoryId,
          controller.signal,
        );
        if (!current()) return;
        setEntries(previous => {
          const original = previous.find(entry => entry.id === operation.id);
          return upsertEntries(previous, [original?.kind === "draft_preview"
            ? { ...original, resolution }
            : { kind: "action_result", id: operation.id, resolution }]);
        });
      }
    } catch (error) {
      if (!current()) return;
      const status = (error as { response?: { status?: number } })?.response?.status;
      switch (status) {
        case 401:
        case 403:
        case 404:
          setEntries(previous => resumeConversationId ? [] : previous.filter(entry => entry.kind === "user"));
          setConversationId(undefined);
          setNotice("当前会话或报告已不可访问。请检查页面后重试。");
          break;
        case 409:
          setEntries(previous => resumeConversationId ? [] : previous.filter(entry => entry.kind === "user"));
          setConversationId(undefined);
          setNotice(operation.kind === "action" ? "操作预览已失效。请重新提出创建请求。" : "本次对话已失效。请重新提问。");
          break;
        case 422:
          if (operation.kind === "action") {
            setEntries(previous => previous.filter(entry => entry.id !== operation.id));
            setNotice("操作预览已失效。请重新提出创建请求。");
          } else {
            setNotice("本次消息未被接受。请重新提问。");
          }
          break;
        default:
          setEntries(previous => resumeConversationId ? [] : previous.filter(entry => entry.kind === "user"));
          setRetry(operation);
          setNotice(operation.kind === "action" ? "执行结果待确认。请重试同一笔操作。" : "暂未收到答复。你可以重试这条消息。");
          break;
      }
    } finally {
      request.current = null;
      if (current()) setPending(null);
    }
  }

  function send() {
    const message = content.trim();
    if (!message || restoring || pending || retry || request.current || authority !== readWorkspaceAuthority()) return;
    const id = crypto.randomUUID();
    setEntries(previous => [...previous, { kind: "user", id, content: message }]);
    setContent("");
    void execute({ kind: "turn", body: { conversation_id: conversationId, request_id: id, page, content: message } });
  }

  const retryLabel = retry?.kind === "turn" ? "重试消息" : retry?.operation === "confirm" ? "重试确认" : "重试取消";
  return <>
    <div
      className="workspace-assistant-transcript"
      role="log"
      aria-label="工作区对话"
      ref={transcript}
      tabIndex={0}
      onScroll={event => {
        const viewport = event.currentTarget;
        followLatest.current = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight <= 32;
        setAway(!followLatest.current);
      }}
    >
      {restoring && <p className="workspace-assistant-notice" role="status">正在恢复工作区会话…</p>}
      {!restoring && !entries.length && <p className="workspace-assistant-empty">可以询问这份 8D 报告同一产品线有哪些 PFMEA，或请助手准备一份 PFMEA 草稿。</p>}
      {entries.map(entry => {
        switch (entry.kind) {
          case "user":
          case "assistant":
            return <div key={entry.id} className={`workspace-assistant-bubble workspace-assistant-bubble-${entry.kind}`}>
              <span className="workspace-assistant-speaker">{entry.kind === "user" ? "你" : "Pi"}</span>
              <p>{entry.content}</p>
            </div>;
          case "pfmea_list":
            return <section key={entry.id} className="workspace-assistant-card" aria-label="同产品线 PFMEA">
              <h3>同产品线 PFMEA</h3>
              {entry.items.length ? <ul className="workspace-assistant-results">
                {entry.items.map(item => <li key={item.id}><Link to={`/fmea/${encodeURIComponent(item.id)}`}>
                  <strong>{item.document_no}</strong><span>{item.title}</span>
                </Link></li>)}
              </ul> : <p>该产品线暂无可查看的 PFMEA。</p>}
            </section>;
          case "action_result":
            return <div key={entry.id} className="workspace-assistant-card"><ActionReceipt result={entry.resolution} /></div>;
          case "draft_preview":
            return <section key={entry.id} className="workspace-assistant-card" aria-label="PFMEA 草稿预览">
              <h3><FileAddOutlined aria-hidden="true" /> PFMEA 草稿预览</h3>
              <dl className="workspace-assistant-fields">
                <dt>工厂</dt><dd>{entry.preview.factory_name}</dd>
                <dt>产品线</dt><dd>{entry.preview.product_line_name}</dd>
                <dt>类型</dt><dd>{entry.preview.fmea_type}</dd>
                <dt>标题</dt><dd>{entry.preview.title}</dd>
                <dt>单号</dt><dd>{entry.preview.document_no}</dd>
                <dt>来源 8D</dt><dd>{entry.preview.source_document_no}</dd>
              </dl>
              {entry.resolution ? <ActionReceipt result={entry.resolution} /> : (
                <div className="workspace-assistant-actions">
                  <span>待确认</span>
                  <Button
                    autoInsertSpace={false}
                    disabled={!!pending || !!retry || !conversationId}
                    onClick={() => conversationId && void execute({ kind: "action", id: entry.id, operation: "cancel", conversationId })}
                  >取消</Button>
                  <Button
                    type="primary"
                    disabled={!!pending || !!retry || !conversationId}
                    onClick={() => conversationId && void execute({ kind: "action", id: entry.id, operation: "confirm", conversationId })}
                  >确认创建</Button>
                </div>
              )}
            </section>;
        }
      })}
      {pending && <p className="workspace-assistant-notice" role="status">{pending.kind === "turn" ? "Pi 正在处理…" : "正在提交操作…"}</p>}
      {notice && <div className="workspace-assistant-notice">
        <p role="status">{notice}</p>
        {retry && <div className="workspace-assistant-actions">
          <Button onClick={() => void execute(retry)}>{retryLabel}</Button>
          {retry.kind === "turn" && <Button onClick={() => { setRetry(null); setNotice(""); }}>继续提问</Button>}
        </div>}
      </div>}
    </div>
    {away && <Button type="text" size="small" className="workspace-assistant-latest" onClick={() => {
      followLatest.current = true;
      setAway(false);
      if (transcript.current) transcript.current.scrollTop = transcript.current.scrollHeight;
    }}>回到最新消息</Button>}
    <form className="workspace-assistant-compose" aria-label="发送消息" onSubmit={event => { event.preventDefault(); send(); }}>
      <Input.TextArea
        aria-label="向 Pi 提问"
        autoSize={{ minRows: 2, maxRows: 5 }}
        placeholder="向 Pi 提问"
        maxLength={4000}
        value={content}
        onChange={event => setContent(event.target.value)}
        onCompositionStart={() => { composing.current = true; }}
        onCompositionEnd={() => { composing.current = false; }}
        onKeyDown={event => {
          if (event.key !== "Enter" || event.shiftKey || composing.current || event.nativeEvent.isComposing || event.keyCode === 229) return;
          event.preventDefault();
          send();
        }}
      />
      <Button
        type="primary"
        htmlType="submit"
        autoInsertSpace={false}
        icon={<SendOutlined aria-hidden="true" />}
        disabled={!content.trim() || restoring || !!pending || !!retry}
      >发送</Button>
    </form>
  </>;
}

function ActionReceipt({ result }: { result: WorkspaceActionResult }) {
  return result.status === "cancelled"
    ? <p role="status">已取消创建。</p>
    : <p role="status">已创建草稿 <Link to={`/fmea/${encodeURIComponent(result.draft.id)}`}>{result.draft.document_no} · {result.draft.title}</Link></p>;
}

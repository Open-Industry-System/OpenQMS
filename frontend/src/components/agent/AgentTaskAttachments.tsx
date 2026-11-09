import { Button, Spin } from "antd";
import { useEffect, useRef, useState } from "react";
import {
  deleteTaskAttachment,
  downloadTaskAttachment,
  getAttachmentAvailability,
  listTaskAttachments,
  uploadTaskAttachment,
} from "../../api/agentTaskAttachments";
import type { AgentTaskAttachment } from "../../types/agentAttachment";

interface Props {
  taskId: string;
  identity: string;
  credential?: string;
  open?: boolean;
  requestEpoch?: number;
}

const denied = (error: unknown) => [401, 403, 404].includes((error as { response?: { status?: number } })?.response?.status ?? 0);

export default function AgentTaskAttachments({ taskId, identity, credential = "", open = true, requestEpoch = 0 }: Props) {
  const [rows, setRows] = useState<AgentTaskAttachment[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const [withdrawn, setWithdrawn] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const controllers = useRef(new Set<AbortController>());
  const sessionRef = useRef("");
  const session = JSON.stringify([taskId, identity, credential, open, requestEpoch]);
  sessionRef.current = session;

  const newController = () => {
    const controller = new AbortController();
    controllers.current.add(controller);
    return controller;
  };
  const abortAll = () => {
    controllers.current.forEach(controller => controller.abort());
    controllers.current.clear();
  };

  const clear = () => {
    setRows([]);
    setFile(null);
    setEnabled(false);
    setPending(false);
    setWithdrawn(false);
    if (inputRef.current) inputRef.current.value = "";
  };

  useEffect(() => {
    abortAll();
    const controller = newController();
    clear();
    if (!open || !taskId || !identity) return abortAll;
    const live = () => !controller.signal.aborted;
    void getAttachmentAvailability(taskId, controller.signal).then(async () => {
      if (!live()) return;
      setEnabled(true);
      const value = await listTaskAttachments(taskId, controller.signal);
      if (live()) setRows(value.items);
    }).catch(error => {
      if (!live()) return;
      clear();
      if (denied(error)) setWithdrawn(true);
      else setMessage("附件暂不可用。");
    }).finally(() => controllers.current.delete(controller));
    return abortAll;
  // Every identity, task, credential, open-state, and epoch transition invalidates retained state.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  async function upload() {
    if (!file || !enabled || pending) return;
    const controller = newController();
    const captured = session;
    setPending(true);
    setMessage("");
    try {
      const item = await uploadTaskAttachment(taskId, file, controller.signal);
      if (controller.signal.aborted || captured !== sessionRef.current) return;
      setRows(current => [item, ...current]);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
    } catch (error) {
      if (controller.signal.aborted || captured !== sessionRef.current) return;
      if (denied(error)) { clear(); setWithdrawn(true); }
      else setMessage("上传失败，请稍后重试。");
    } finally {
      controllers.current.delete(controller);
      if (!controller.signal.aborted && captured === sessionRef.current) setPending(false);
    }
  }

  async function remove(attachmentId: string) {
    const controller = newController();
    const captured = session;
    try {
      await deleteTaskAttachment(taskId, attachmentId, controller.signal);
      if (controller.signal.aborted || captured !== sessionRef.current) return;
      setRows(current => current.filter(item => item.attachment_id !== attachmentId));
    } catch (error) {
      if (controller.signal.aborted || captured !== sessionRef.current) return;
      if (denied(error)) { clear(); setWithdrawn(true); }
      else setMessage("删除失败，请稍后重试。");
    } finally {
      controllers.current.delete(controller);
    }
  }

  async function download(item: AgentTaskAttachment) {
    const controller = newController();
    const captured = session;
    try {
      const blob = await downloadTaskAttachment(taskId, item.attachment_id, controller.signal);
      if (controller.signal.aborted || captured !== sessionRef.current) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = item.display_name ?? "attachment";
      link.style.display = "none";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (error) {
      if (controller.signal.aborted || captured !== sessionRef.current) return;
      if (denied(error)) { clear(); setWithdrawn(true); }
      else setMessage("下载失败，请稍后重试。");
    } finally {
      controllers.current.delete(controller);
    }
  }

  if (!open || !taskId || withdrawn) return null;
  return <section aria-label="任务私有附件">
    <h3>任务私有附件</h3>
    <p>附件仅用于当前任务；完成病毒扫描前不可用，且不会发送给插件或模型。</p>
    {!enabled && !message && <Spin size="small" />}
    <label>选择附件<input type="file" ref={inputRef} disabled={!enabled || pending} onChange={event => setFile(event.target.files?.[0] ?? null)} /></label>
    <Button disabled={!enabled || !file || pending} onClick={() => void upload()}>上传附件</Button>
    {file && <p>{file.name}</p>}
    <ul>{rows.map(item => <li key={item.attachment_id}>
      <span>{item.display_name ?? "未命名附件"} · {item.status}</span>
      <Button aria-label="下载" disabled={item.status !== "available"} onClick={() => void download(item)}>下载</Button>
      <Button aria-label="删除" disabled={pending} onClick={() => void remove(item.attachment_id)}>删除</Button>
    </li>)}</ul>
    <p role="status" aria-live="polite">{message}</p>
  </section>;
}

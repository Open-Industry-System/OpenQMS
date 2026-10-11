import { useEffect, useRef, useState } from "react";
import { Button, Drawer } from "antd";
import { appendTaskMessage, controlTask, createTask, listTaskInstallations, listTasks } from "../../api/agentTasks";
import type { AgentTask, InstallationChoice, TaskAction, TaskControl, TaskCreate, TaskMessageCreate } from "../../types/agentTask";
import AgentActivity from "./AgentActivity";
import AgentTaskAttachments from "./AgentTaskAttachments";
import { useAgentTaskContext } from "./AgentTaskContext";
import { readAgentIdentity, useAgentTaskActivity } from "./useAgentTaskActivity";
type Operation = {
  kind: "message";
  taskId: string;
  body: TaskMessageCreate;
} | {
  kind: "control";
  taskId: string;
  body: TaskControl;
} | {
  kind: "create";
  body: TaskCreate;
};
export default function AgentSidebar() {
  const ctx = useAgentTaskContext();
  const activity = useAgentTaskActivity({
    taskId: ctx?.selectedTask?.task_id ?? null,
    identity: ctx?.identity ?? "",
    credential: ctx?.credential ?? "",
    open: ctx?.open ?? false,
    requestEpoch: ctx?.requestEpoch ?? 0
  });
  const [directoryPage, setDirectoryPage] = useState(1);
  const [directoryTotal, setDirectoryTotal] = useState(0);
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [installations, setInstallations] = useState<InstallationChoice[] | null>(null);
  const [installationId, setInstallation] = useState("");
  const [initialText, setInitialText] = useState("");
  const [text, setText] = useState("");
  const [pending, setPending] = useState(false);
  const [retry, setRetry] = useState<Operation | null>(null);
  const [notice, setNotice] = useState("");
  const busy = useRef(false);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const operationController = useRef<AbortController | null>(null);
  const sessionKey = JSON.stringify([ctx?.identity, ctx?.selectedTask?.task_id, ctx?.creationReportId]);
  const currentSession = useRef(sessionKey);
  currentSession.current = sessionKey;
  useEffect(() => {
    busy.current = false;
    operationController.current?.abort();
    setPending(false);
    setRetry(null);
    setNotice("");
    setText("");
    setInitialText("");
    return () => operationController.current?.abort();
  }, [sessionKey]);
  useEffect(() => {
    const controller = new AbortController();
    setTasks([]);
    if (ctx?.available && ctx.open)
      void listTasks({ page: directoryPage, page_size: 20 }, controller.signal).then(value => {
        if (!controller.signal.aborted && ctx.identity === readAgentIdentity()) {
          setTasks(value.items);
          setDirectoryTotal(value.total);
        }
      }).catch(error => {
        if (!controller.signal.aborted && ctx.identity === readAgentIdentity()) {
          setTasks([]);
          setDirectoryTotal(0);
          if ([401, 403, 404].includes(error?.response?.status)
            && (ctx.selectedTask || ctx.creationReportId)) {
            ctx.clearTask();
          }
        }
      });
    return () => controller.abort();
  }, [ctx?.available, ctx?.identity, ctx?.credential, ctx?.open, ctx?.requestEpoch, ctx?.creationReportId, directoryPage]);
  useEffect(() => {
    const controller = new AbortController();
    setInstallations(null);
    setInstallation("");
    if (ctx?.available && ctx.creationReportId)
      void listTaskInstallations(ctx.creationReportId, controller.signal).then(value => {
        if (!controller.signal.aborted && ctx.identity === readAgentIdentity()) {
          setInstallations(value.items);
          setInstallation(value.items[0]?.installation_id ?? "");
        }
      }).catch(error => {
        if (!controller.signal.aborted) {
          setInstallations([]);
          setNotice("无法读取插件目录。");
          if ([401, 403, 404].includes(error?.response?.status))
            ctx.clearTask();
        }
      });
    return () => controller.abort();
  }, [ctx?.available, ctx?.identity, ctx?.credential, ctx?.creationReportId]);
  async function execute(op: Operation) {
    if (!ctx || busy.current || ctx.identity !== readAgentIdentity())
      return;
    const captured = sessionKey;
    const controller = new AbortController();
    operationController.current = controller;
    busy.current = true;
    setPending(true);
    setNotice("提交中");
    const live = () => !controller.signal.aborted && captured === currentSession.current && ctx.identity === readAgentIdentity();
    try {
      if (op.kind === "message") {
        await appendTaskMessage(op.taskId, op.body, controller.signal);
        if (live()) {
          setRetry(null);
          setText("");
          setNotice("指令已入队；插件确认接收后才显示已确认接收。");
          ctx.refresh();
        }
      } else if (op.kind === "control") {
        await controlTask(op.taskId, op.body, controller.signal);
        if (live()) {
          setRetry(null);
          setNotice("控制操作已确认");
          ctx.refresh();
        }
      } else {
        const task = await createTask(op.body, controller.signal);
        if (live()) {
          setRetry(null);
          ctx.selectTask(task);
        }
      }
    } catch (error) {
      if (!live())
        return;
      const status = (error as {
        response?: {
          status?: number;
        };
      })?.response?.status;
      if (status === 409) {
        setRetry(null);
        setNotice("状态已变化，已刷新；请确认后重新操作。");
        ctx.refresh();
      } else if (status === 401 || status === 403 || status === 404) {
        setRetry(null);
        setNotice("任务访问已失效");
        ctx.clearTask();
      } else {
        setRetry(op);
        setNotice("连接中断，操作尚未确认；重试会发送原请求。");
      }
    } finally {
      if (live()) {
        busy.current = false;
        setPending(false);
      }
    }
  }
  function command(action: TaskAction, checkpointId?: string) {
    if (!ctx?.selectedTask || !activity.page || retry)
      return;
    const page = activity.page;
    const body: TaskControl = {
      action,
      run_id: page.run_id,
      expected_epoch: page.lease_epoch,
      idempotency_key: crypto.randomUUID()
    };
    if (checkpointId)
      body.checkpoint_id = checkpointId;
    void execute({ kind: "control", taskId: ctx.selectedTask.task_id, body });
  }
  if (!ctx?.available || ctx.identity !== readAgentIdentity())
    return null;
  const page = activity.page;
  return <>
    <Button ref={trigger} onClick={() => ctx.setOpen(true)}>Agent 任务</Button>
    <Drawer
      title="Agent 任务"
      open={ctx.open}
      width={560}
      onClose={() => ctx.setOpen(false)}
      afterOpenChange={open => {
        if (!open)
          trigger.current?.focus();
      }}
      destroyOnClose>
      <Button onClick={() => ctx.setOpen(false)}>关闭任务侧栏</Button>
      <label>选择任务<select
        aria-label="选择任务"
        value={ctx.selectedTask?.task_id ?? ""}
        onChange={event => {
          const task = tasks.find(item => item.task_id === event.target.value);
          if (task)
            ctx.selectTask(task);
        }}>
        <option value="">请选择任务</option>{ctx.selectedTask && !tasks.some(task => task.task_id === ctx.selectedTask?.task_id) && <option value={ctx.selectedTask.task_id}>当前任务 {ctx.selectedTask.target_capa_id}</option>}{tasks.map(task => <option key={task.task_id} value={task.task_id}>{task.target_capa_id} · {task.status}</option>)}</select>
      </label>
      <p>任务目录第 {directoryPage} 页</p>
      <Button disabled={directoryPage <= 1} onClick={() => setDirectoryPage(n => n - 1)}>上一页任务</Button>
      <Button disabled={directoryPage * 20 >= directoryTotal} onClick={() => setDirectoryPage(n => n + 1)}>下一页任务</Button>
      {ctx.creationReportId && <section aria-label="创建任务">
        <p>创建目标报告 {ctx.creationReportId}</p>
        <label>插件安装<select
          aria-label="插件安装"
          value={installationId}
          disabled={pending || retry !== null || !installations?.length}
          onChange={e => setInstallation(e.target.value)}>{installations?.map(choice => <option key={choice.installation_id} value={choice.installation_id}>{choice.plugin_key} · {choice.plugin_version}</option>)}</select>
        </label>
        {installations?.length === 0 && <p>暂无适用于本报告的插件安装，无法创建任务。</p>}
        <label>初始指令<textarea
          aria-label="初始指令"
          maxLength={10000}
          value={initialText}
          disabled={pending || retry !== null || !installations?.length}
          onChange={e => setInitialText(e.target.value)} />
        </label>
        <Button disabled={pending || retry !== null || !installationId || !initialText.trim()} onClick={() => void execute({
          kind: "create", body: {
            report_id: ctx.creationReportId!,
            installation_id: installationId,
            request_key: crypto.randomUUID(),
            initial_text: initialText
          }
        })}>创建任务</Button>
      </section>}
      {ctx.selectedTask && <>
        {activity.status === "interrupted" && <p>连接中断，重试中</p>}
        {activity.status === "denied" && <p>任务访问已失效</p>}
        {activity.status === "loading" && <p>正在读取任务活动</p>}
        {page && <>
          <AgentActivity task={ctx.selectedTask} page={page} onControl={command} pending={pending || retry !== null} />
          <AgentTaskAttachments
            taskId={ctx.selectedTask.task_id}
            identity={ctx.identity}
            credential={ctx.credential}
            open={ctx.open}
            requestEpoch={ctx.requestEpoch}
          />
          <label>追加指令<textarea
            aria-label="追加指令"
            maxLength={10000}
            value={text}
            disabled={pending || retry !== null || ["completed", "failed", "cancelled"].includes(page.task_status)}
            onChange={e => setText(e.target.value)} />
          </label>
          <Button disabled={pending || retry !== null || !text.trim() || ["completed", "failed", "cancelled"].includes(page.task_status)} onClick={() => void execute({ kind: "message", taskId: ctx.selectedTask!.task_id, body: { content: text, idempotency_key: crypto.randomUUID() } })}>发送指令</Button>
        </>}
      </>}
      {retry && <Button disabled={pending} onClick={() => void execute(retry)}>{retry.kind === "message" ? "重试发送原指令" : retry.kind === "control" ? "重试原控制操作" : "重试创建原任务"}</Button>}
      <p role="status" aria-live="polite">{notice}</p>
    </Drawer>
  </>;
}

import { useEffect, useRef, useState } from "react";
import { Button, Drawer } from "antd";
import { Link } from "react-router-dom";
import { appendTaskMessage, controlTask, createTask, listTaskInstallations, listTasks, listModelDeployments, launchTask, getTaskWorkflow, listTaskD5Checkpoints } from "../../api/agentTasks";
import type { D5CheckpointReference } from "../../api/agentTasks";
import type { AgentTask, ModelChoice, TaskWorkflow, InstallationChoice, TaskAction, TaskControl, TaskCreate, TaskMessageCreate } from "../../types/agentTask";
import { listTaskD5Proposals, listTaskD5Results, type D5Proposal } from "../../api/d5Proposals";
import D5ProposalPanel from "../capa/D5ProposalPanel";
import AgentActivity, { taskMessageState } from "./AgentActivity";
import AgentConversation from "./AgentConversation";
import AgentTaskAttachments from "./AgentTaskAttachments";
import { useAgentTaskContext } from "./AgentTaskContext";
import { readAgentCredential, readAgentIdentity, readAgentScope, useAgentTaskActivity } from "./useAgentTaskActivity";
import "./agentSidebar.css";

const D4_START = "deliver_d4_root_cause_candidate_v1";
const TASK_STATUS = {
  blocked_capability: "缺少所需授权", ready: "就绪", paused: "已暂停",
  completed: "已完成", failed: "失败", cancelled: "已取消",
};
const isDenied = (error: unknown) => [401, 403, 404].includes(
  (error as { response?: { status?: number } })?.response?.status ?? 0,
);
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
    scope: ctx?.scope,
    selectionEpoch: ctx?.selectionEpoch,
    requestEpoch: ctx?.requestEpoch ?? 0
  });
  const [checkpointPage,setCheckpointPage]=useState(1);
  const [checkpointTotal,setCheckpointTotal]=useState(0);
  const [checkpoints,setCheckpoints]=useState<D5CheckpointReference[]>([]);
  const [selectedCheckpoint,setSelectedCheckpoint]=useState<D5CheckpointReference|null>(null);
  const [correctionPage,setCorrectionPage]=useState(1);
  const [correctionTotal,setCorrectionTotal]=useState(0);
  const [corrections, setCorrections] = useState<D5Proposal[]>([]);
  const [correctionId, setCorrectionId] = useState("");
  const [models, setModels] = useState<ModelChoice[]>([]);
  const [modelId, setModelId] = useState("");
  const [workflow, setWorkflow] = useState<{ key: string; value: TaskWorkflow } | null>(null);
  const [workflowDenied, setWorkflowDenied] = useState<string | null>(null);
  const [proposalHistory, setProposalHistory] = useState<{ key: string; items: D5Proposal[] } | null>(null);
  const [taskView, setTaskView] = useState<"new" | "details" | "conversation">("new");
  const showDetails = taskView === "details";
  const composing = useRef(false);
  const [launchPending, setLaunchPending] = useState(false);
  const [launchNotice, setLaunchNotice] = useState("");
  const launchController = useRef<AbortController | null>(null);
  const launchBusy = useRef(false);
  const [directoryPage, setDirectoryPage] = useState(1);
  const [directory, setDirectory] = useState<{ key: string; tasks: AgentTask[]; total: number } | null>(null);
  const [installations, setInstallations] = useState<InstallationChoice[] | null>(null);
  const [installationId, setInstallation] = useState("");
  const [initialText, setInitialText] = useState("");
  const [text, setText] = useState("");
  const [pending, setPending] = useState(false);
  const [retry, setRetry] = useState<Operation | null>(null);
  const [notice, setNotice] = useState("");
  const busy = useRef(false);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const activeOperation = useRef<{ op: Operation; controller: AbortController } | null>(null);
  const taskId = ctx?.selectedTask?.task_id;
  const boundModel = ctx?.selectedTask?.model_deployment;
  const conversationKey = JSON.stringify([ctx?.identity, ctx?.credential, ctx?.scope, ctx?.open, taskId, ctx?.selectionEpoch]);
  const sessionKey = JSON.stringify([conversationKey, ctx?.creationReportId]);
  const currentSession = useRef(sessionKey);
  const currentConversation = useRef(conversationKey);
  currentSession.current = sessionKey;
  currentConversation.current = conversationKey;
  const hasCurrentScope = () => ctx?.identity === readAgentIdentity()
    && ctx?.credential === readAgentCredential() && ctx?.scope === readAgentScope();
  const directoryKey = JSON.stringify([ctx?.identity, ctx?.credential, ctx?.scope, ctx?.open, directoryPage]);
  const tasks = directory?.key === directoryKey ? directory.tasks : [];
  const directoryTotal = directory?.key === directoryKey ? directory.total : 0;
  const page = activity.page;
  const activityReady = activity.status === "ready";
  const activityDenied = activity.status === "denied";
  const modelWorkflow = activityReady && workflow?.key === conversationKey ? workflow.value : null;
  const modelDenied = workflowDenied === conversationKey;
  const canSend = Boolean(boundModel && modelWorkflow && !modelDenied
    && modelWorkflow.status !== "unavailable" && (page?.task_status === "ready" || page?.task_status === "paused"));

  useEffect(() => {
    busy.current = false;
    composing.current = false;
    setPending(false);
    setRetry(null);
    setNotice("");
    setText("");
    setInitialText("");
    return () => {
      activeOperation.current?.controller.abort();
      activeOperation.current = null;
    };
  }, [sessionKey]);
  useEffect(() => {
    if (!activityDenied && !modelDenied) return;
    const lostAuthority = (op: Operation) => op.kind === "message" || (activityDenied && op.kind === "control");
    const active = activeOperation.current;
    if (active && lostAuthority(active.op)) {
      active.controller.abort();
      activeOperation.current = null;
      busy.current = false;
      setPending(false);
      setNotice("");
    }
    setRetry(op => op && lostAuthority(op) ? null : op);
    launchController.current?.abort();
    launchBusy.current = false;
    setLaunchPending(false);
    setLaunchNotice("");
    setText("");
  }, [activityDenied, modelDenied]);
  useEffect(() => {
    setTaskView("new");
    setWorkflow(null);
    setWorkflowDenied(null);
    setProposalHistory(null);
  }, [conversationKey]);
  useEffect(() => {
    const controller = new AbortController();
    if (ctx?.available && ctx.open)
      void listTasks({ page: directoryPage, page_size: 20 }, controller.signal).then(value => {
        if (!controller.signal.aborted && hasCurrentScope()) {
          setDirectory({ key: directoryKey, tasks: value.items, total: value.total });
        }
      }).catch(error => {
        if (!controller.signal.aborted && hasCurrentScope()) {
          setDirectory(null);
          if ([401, 403, 404].includes(error?.response?.status)
            && (ctx.selectedTask || ctx.creationReportId)) {
            ctx.clearTask();
          }
        }
      });
    return () => controller.abort();
  }, [ctx?.available, directoryKey, ctx?.requestEpoch, ctx?.creationReportId]);
  useEffect(() => {
    const controller = new AbortController();
    setInstallations(null);
    setInstallation("");
    if (ctx?.available && ctx.open && ctx.creationReportId)
      void listTaskInstallations(ctx.creationReportId, controller.signal).then(value => {
        if (!controller.signal.aborted && hasCurrentScope()) {
          setInstallations(value.items);
          setInstallation(value.items[0]?.installation_id ?? "");
        }
      }).catch(error => {
        if (!controller.signal.aborted && hasCurrentScope()) {
          setInstallations([]);
          setNotice("无法读取插件目录。");
          if ([401, 403, 404].includes(error?.response?.status))
            ctx.clearTask();
        }
      });
    return () => controller.abort();
  }, [ctx?.available, ctx?.identity, ctx?.credential, ctx?.scope, ctx?.creationReportId, ctx?.open]);
  useEffect(() => {
    const controller = new AbortController();
    setModels([]);
    if (ctx?.available && ctx.open && ctx.creationReportId)
      void listModelDeployments(controller.signal).then(value => {
        if (!controller.signal.aborted && hasCurrentScope()) setModels(value.items);
      }).catch(() => { if (!controller.signal.aborted) setModels([]); });
    return () => controller.abort();
  }, [ctx?.identity, ctx?.credential, ctx?.scope, ctx?.creationReportId, ctx?.open, ctx?.requestEpoch]);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const live = () => !controller.signal.aborted && currentConversation.current === conversationKey && hasCurrentScope();
    if (!ctx?.open || !taskId || !boundModel || !activityReady || modelDenied) {
      setWorkflow(null);
      return;
    }
    async function poll() {
      if (!taskId) return;
      try {
        const result = await getTaskWorkflow(taskId, controller.signal);
        if (live()) {
          setWorkflow({ key: conversationKey, value: result });
          setWorkflowDenied(null);
        }
      } catch (error) {
        if (live()) {
          setWorkflow(null);
          if (isDenied(error)) {
            setWorkflowDenied(conversationKey);
            return;
          }
        }
      }
      if (live()) timer = setTimeout(poll, 1000);
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [conversationKey, activityReady, modelDenied, boundModel?.deployment_id]);
  useEffect(() => {
    const controller = new AbortController();
    if (!page) {
      setProposalHistory(null);
    } else if (ctx?.selectedTask && boundModel) {
      void listTaskD5Results(ctx.selectedTask.target_capa_id, ctx.selectedTask.task_id, controller.signal).then(items => {
        if (!controller.signal.aborted && currentConversation.current === conversationKey && hasCurrentScope()) {
          setProposalHistory({ key: conversationKey, items });
        }
      }).catch(() => {
        if (!controller.signal.aborted) setProposalHistory(null);
      });
    }
    return () => controller.abort();
  }, [conversationKey, page, boundModel?.deployment_id]);
  async function launch() {
    if (!ctx?.selectedTask?.model_deployment || launchBusy.current || modelDenied || !hasCurrentScope()) return;
    const captured = conversationKey;
    const controller = new AbortController();
    launchController.current = controller;
    launchBusy.current = true; setLaunchPending(true); setLaunchNotice("模型任务运行中");
    const live = () => !controller.signal.aborted && captured === currentConversation.current && hasCurrentScope();
    try {
      await launchTask(ctx.selectedTask.task_id, controller.signal);
      if (live()) { setLaunchNotice("模型任务已返回"); ctx.refresh(); }
    } catch {
      if (live()) { setLaunchNotice("启动尚未确认；请刷新当前任务，不能自动改选模型或重发。"); ctx.refresh(); }
    } finally { if (live()) { launchBusy.current = false; setLaunchPending(false); } }
  }
  function send(content: string) {
    if (!ctx?.selectedTask || !canSend || !content.trim() || retry || pending) return;
    void execute({kind:"message",taskId:ctx.selectedTask.task_id,body:{content,idempotency_key:crypto.randomUUID()}});
  }
  useEffect(() => {
    launchBusy.current = false; setLaunchPending(false); setLaunchNotice("");
    return () => launchController.current?.abort();
  }, [conversationKey]);
  useEffect(() => {
    const controller = new AbortController();
    setCorrections([]); setCorrectionId(""); setCorrectionTotal(0);
    if(activityReady && ctx?.open && ctx.selectedTask?.model_deployment)
      void listTaskD5Proposals(ctx.selectedTask.target_capa_id,ctx.selectedTask.task_id,correctionPage,controller.signal).then(data=>{
        if(!controller.signal.aborted && hasCurrentScope()){setCorrections(data.items);setCorrectionTotal(data.total);}
      }).catch(()=>{if(!controller.signal.aborted) setCorrections([]);});
    return ()=>controller.abort();
  },[activityReady,ctx?.identity,ctx?.credential,ctx?.scope,ctx?.selectedTask?.task_id,ctx?.selectedTask?.model_deployment,ctx?.open,ctx?.requestEpoch,correctionPage]);
  useEffect(()=>{setSelectedCheckpoint(null);setCheckpointPage(1);setCorrectionPage(1);},[ctx?.identity,ctx?.credential,ctx?.scope,ctx?.selectedTask?.task_id,ctx?.open]);
  useEffect(()=>{
    const controller=new AbortController();
    setCheckpoints([]);setCheckpointTotal(0);
    if (!activityReady) setSelectedCheckpoint(null);
    if(activityReady && ctx?.open && ctx.selectedTask?.model_deployment)
      void listTaskD5Checkpoints(ctx.selectedTask.task_id,checkpointPage,controller.signal).then(data=>{
        if(!controller.signal.aborted && hasCurrentScope()){setCheckpoints(data.items);setCheckpointTotal(data.total);}
      }).catch(()=>{if(!controller.signal.aborted){setCheckpoints([]);setSelectedCheckpoint(null);}});
    return ()=>controller.abort();
  },[activityReady,ctx?.identity,ctx?.credential,ctx?.scope,ctx?.selectedTask?.task_id,ctx?.open,ctx?.requestEpoch,checkpointPage,modelWorkflow?.checkpoint_id]);
  useEffect(() => setModelId(""), [ctx?.identity, ctx?.scope, ctx?.creationReportId, ctx?.open]);
  async function execute(op: Operation) {
    if (!ctx?.open || busy.current || !hasCurrentScope() || (op.kind === "message" && !canSend)
      || (op.kind === "control" && !activityReady))
      return;
    const captured = sessionKey;
    const controller = new AbortController();
    activeOperation.current = { op, controller };
    busy.current = true;
    setPending(true);
    setNotice("提交中");
    const live = () => !controller.signal.aborted && captured === currentSession.current && hasCurrentScope();
    try {
      if (op.kind === "message") {
        const message = await appendTaskMessage(op.taskId, op.body, controller.signal);
        if (live()) {
          setRetry(null);
          setText("");
          setNotice(`消息${taskMessageState(message.state === "accepted" ? "received" : message.state)}。`);
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
      } else if (status === 400 || status === 422) {
        setRetry(null);
        setNotice("服务端未接受该操作，请检查输入或任务状态。");
        ctx.refresh();
      } else {
        setRetry(op);
        setNotice("连接中断，操作尚未确认；重试会发送原请求。");
      }
    } finally {
      if (live()) {
        activeOperation.current = null;
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
  if (!ctx?.available || !hasCurrentScope())
    return null;
  const selectedInstallation = installations?.find(item => item.installation_id === installationId);
  const needsModel = selectedInstallation?.plugin_key === "openqms.controlled-d5-model";
  const questionRunMatches = modelWorkflow?.run_id === undefined ||
    (modelWorkflow.run_id === page?.run_id && modelWorkflow.lease_epoch === page?.lease_epoch
      && page?.run_status === "active");
  const questions = questionRunMatches
    ? modelWorkflow?.questions ?? (modelWorkflow?.question ? [{
      question_id: "current", text: modelWorkflow.question, created_at: ctx.selectedTask!.updated_at,
    }] : []) : [];
  const results = modelDenied || proposalHistory?.key !== conversationKey ? [] : proposalHistory.items;
  const waitingQuestionId = questionRunMatches && modelWorkflow?.question
    ? questions[questions.length - 1]?.question_id : undefined;
  const statusLabel = page?.run_status === "active" && questionRunMatches
    ? (waitingQuestionId ? "等待补充" : "运行中") : page && TASK_STATUS[page.task_status];
  const reportLabel = page?.context?.document_no ?? ctx.selectedTask?.target_capa_id;
  const pluginLabel = page?.context ? `${page.context.plugin_key} · ${page.context.plugin_version}` : "只读 Agent 插件";
  const sendLabel = `补充给 ${boundModel?.name ?? "Agent"}`;
  const selectedModel = models.find(model=>model.deployment_id===modelId);
  const newTaskRecipient = selectedModel ? `${selectedModel.name} · ${selectedModel.version}` : "所选模型";
  return <>
    <Button ref={trigger} onClick={() => ctx.setOpen(true)}>Agent 任务</Button>
    <Drawer
      title="Agent 任务"
      open={ctx.open}
      width="min(100vw, 560px)"
      className="agent-chat-drawer"
      onClose={() => ctx.setOpen(false)}
      afterOpenChange={open => {
        if (!open)
          trigger.current?.focus();
      }}
      destroyOnClose>
      {ctx.open && <>
      <div className="agent-chat-toolbar">
      <Button size="small" onClick={() => ctx.setOpen(false)}>关闭任务侧栏</Button>
      <label className="agent-chat-task-picker"><span>选择任务</span><select
        aria-label="选择任务"
        value={ctx.selectedTask?.task_id ?? ""}
        onChange={event => {
          const task = tasks.find(item => item.task_id === event.target.value);
          if (task)
            ctx.selectTask(task);
        }}>
        <option value="">请选择任务</option>{ctx.selectedTask && !tasks.some(task => task.task_id === ctx.selectedTask?.task_id) && <option value={ctx.selectedTask.task_id}>当前任务 {reportLabel}</option>}{tasks.map(task => <option key={task.task_id} value={task.task_id}>{task.target_capa_id.slice(0, 8)} · {task.model_deployment?.name ?? "只读"} · {TASK_STATUS[task.status]} · {task.task_id.slice(0, 8)}</option>)}</select>
      </label>
      <div className="agent-chat-paging">
      <span>任务目录第 {directoryPage} 页</span>
      <Button size="small" disabled={directoryPage <= 1} onClick={() => setDirectoryPage(n => n - 1)}>上一页任务</Button>
      <Button size="small" disabled={directoryPage * 20 >= directoryTotal} onClick={() => setDirectoryPage(n => n + 1)}>下一页任务</Button>
      </div>
      </div>
      {ctx.creationReportId && <section className="agent-chat-create" aria-label="创建任务">
        <p>创建目标报告 {ctx.creationReportId}</p>
        <label>插件安装<select
          aria-label="插件安装"
          value={installationId}
          disabled={pending || retry !== null || !installations?.length}
          onChange={e => setInstallation(e.target.value)}>{installations?.map(choice => <option key={choice.installation_id} value={choice.installation_id}>{choice.plugin_key} · {choice.plugin_version}</option>)}</select>
        </label>
        {installations?.length === 0 && <p>暂无适用于本报告的插件安装，无法创建任务。</p>}
        {needsModel && <label>新任务模型<select aria-label="新任务模型" value={modelId} disabled={pending || retry !== null} onChange={e => setModelId(e.target.value)}>
          <option value="">请选择批准的模型版本</option>{models.map(model => <option key={model.deployment_id} value={model.deployment_id}>{model.name} · {model.version} · {model.kind}</option>)}
        </select><p>新任务独立创建，不转交当前任务的聊天或资料。</p></label>}
        {needsModel && models.length === 0 && <p>暂无可用的批准模型部署。</p>}
        {needsModel && <>
          <Button disabled={pending || retry !== null || !installationId || !selectedModel} onClick={()=>void execute({kind:"create",body:{report_id:ctx.creationReportId!,installation_id:installationId,model_deployment_id:modelId,request_key:crypto.randomUUID(),initial_text:D4_START}})}>{`用 ${newTaskRecipient} 开始新任务（仅根据当前根因）`}</Button>
          <p>附加资料可用于对话；保存共享建议需要可核对的完整来源。</p>
        </>}
        {needsModel && <label>初始指令<textarea
          aria-label="初始指令"
          maxLength={10000}
          value={initialText}
          disabled={pending || retry !== null || !installations?.length}
          onChange={e => setInitialText(e.target.value)} />
        </label>}
        <Button disabled={pending || retry !== null || !installationId || (needsModel && (!initialText.trim() || !selectedModel))} onClick={() => void execute({
          kind: "create", body: {
            report_id: ctx.creationReportId!,
            installation_id: installationId,
            request_key: crypto.randomUUID(),
            initial_text: needsModel ? initialText
              : selectedInstallation?.plugin_key === "openqms.local-d4-root-cause-text" ? D4_START
                : "读取当前报告的 D4 元数据",
            ...(needsModel ? {model_deployment_id:modelId} : {})
          }
        })}>{needsModel ? `用 ${newTaskRecipient} 开始新任务（自由对话）` : "创建任务"}</Button>
      </section>}
      {activity.status === "interrupted" && <p role="status">连接中断，重试中</p>}
      {activity.status === "offline" && <div>
        <p role="status">暂时无法连接任务服务</p>
        <Button onClick={() => { if (hasCurrentScope()) ctx.refresh(); }}>重新连接</Button>
      </div>}
      {activity.status === "denied" && <p role="status">任务访问已失效</p>}
      {ctx.selectedTask && activity.status === "loading" && <p role="status">正在读取任务活动</p>}
      {ctx.selectedTask && page && <section className="agent-chat-task" aria-label="任务活动">
        <header className="agent-chat-context">
          <Link to={`/capa/${ctx.selectedTask.target_capa_id}`}>目标报告 {reportLabel}</Link>
          <div className="agent-chat-recipient">
            <strong>当前接收方：{boundModel ? `${boundModel.name} · ${boundModel.version}` : pluginLabel}</strong>
            <span>{statusLabel}</span>
          </div>
          <div className="agent-chat-actions">
            {boundModel && page.task_status === "ready" && <Button size="small" disabled={launchPending || modelDenied || !modelWorkflow || page.run_status === "active"} onClick={() => void launch()}>启动模型任务</Button>}
            <Button size="small" aria-pressed={showDetails} onClick={() => setTaskView(showDetails ? "conversation" : "details")}>
              {showDetails ? "返回对话" : "任务详情"}
            </Button>
          </div>
          {launchNotice && <p aria-live="polite">{launchNotice}</p>}
        </header>
        <AgentConversation key={conversationKey} task={ctx.selectedTask} page={page}
          questions={questions} waitingQuestionId={waitingQuestionId} proposals={results} hidden={showDetails} onOpenReport={() => ctx.setOpen(false)} />
        {taskView !== "new" && <div className="agent-chat-details" hidden={!showDetails}>
          <AgentActivity task={ctx.selectedTask} page={page} technicalOnly onControl={command} pending={pending || retry !== null} />
          <details><summary>任务附件</summary>
            <AgentTaskAttachments
              taskId={ctx.selectedTask.task_id}
              identity={ctx.identity}
              credential={ctx.credential}
              open={ctx.open}
              requestEpoch={ctx.requestEpoch}
            />
          </details>
          {boundModel && !modelDenied && <details><summary>建议与检查点</summary>
          <label>更正当前任务建议<select aria-label="更正当前任务建议" value={correctionId} disabled={pending || retry !== null} onChange={e=>setCorrectionId(e.target.value)}>
            <option value="">请选择当前任务待审建议</option>{corrections.map(item=><option key={item.proposal_id} value={item.proposal_id}>{item.proposal_id}</option>)}
          </select></label>
          <Button disabled={pending || retry !== null || correctionPage<=1} onClick={()=>setCorrectionPage(p=>p-1)}>上一页待更正建议</Button>
          <Button disabled={pending || retry !== null || correctionPage*20>=correctionTotal} onClick={()=>setCorrectionPage(p=>p+1)}>下一页待更正建议</Button>
          <Button disabled={pending || retry !== null || !corrections.some(item=>item.proposal_id===correctionId) || !canSend} onClick={()=>send(JSON.stringify({intent:'replace_d5',predecessor_id:correctionId}))}>明确更正选中建议</Button>
          <p>更正意图只指定前版；并列备选保留原建议。自由聊天含未界定资料时不能保存共享建议。</p>
          <label>选择处理范围检查点<select aria-label="选择处理范围检查点" value={selectedCheckpoint?.checkpoint_id??''} onChange={e=>setSelectedCheckpoint(checkpoints.find(cp=>cp.checkpoint_id===e.target.value)??null)}>
            <option value="">请选择实际任务检查点</option>
            {selectedCheckpoint && !checkpoints.some(cp=>cp.checkpoint_id===selectedCheckpoint.checkpoint_id) && <option value={selectedCheckpoint.checkpoint_id}>{selectedCheckpoint.created_at} · {selectedCheckpoint.checkpoint_id}</option>}
            {checkpoints.map(cp=><option key={cp.checkpoint_id} value={cp.checkpoint_id}>{cp.created_at} · {cp.checkpoint_id}</option>)}
          </select></label>
          <Button disabled={checkpointPage<=1} onClick={()=>setCheckpointPage(p=>p-1)}>上一页检查点</Button>
          <Button disabled={checkpointPage*20>=checkpointTotal} onClick={()=>setCheckpointPage(p=>p+1)}>下一页检查点</Button>
          {selectedCheckpoint && <D5ProposalPanel capaId={ctx.selectedTask.target_capa_id} checkpoint={{taskId:ctx.selectedTask.task_id,checkpointId:selectedCheckpoint.checkpoint_id}} />}
          <Button disabled={pending || retry !== null || !canSend} onClick={() => send(JSON.stringify({intent:'continue_d5',additional_context:'none'}))}>继续（无额外资料）</Button>
          </details>}
        </div>}
        {boundModel ? <div className="agent-chat-composer">
          <label>
            <span className="agent-chat-sr-only">追加指令</span>
            <textarea
              aria-label="追加指令"
              placeholder="输入要补充的内容"
              rows={2}
              maxLength={10000}
              value={text}
              disabled={!canSend || pending || retry !== null}
              onChange={e => setText(e.target.value)}
              onCompositionStart={() => { composing.current = true; }}
              onCompositionEnd={() => { composing.current = false; }}
              onKeyDown={e => {
                if (e.key !== "Enter" || e.shiftKey || composing.current
                  || e.nativeEvent.isComposing || e.keyCode === 229) return;
                e.preventDefault();
                send(text);
              }}
            />
          </label>
          <Button type="primary" disabled={!canSend || pending || retry !== null || !text.trim()} onClick={() => send(text)}>{sendLabel}</Button>
          {modelDenied && <p role="status">模型访问已失效</p>}
          {!modelDenied && !canSend && <p>{["ready", "paused"].includes(page.task_status)
            ? "模型暂不可用，恢复后可继续补充。" : "当前任务不接收新消息。"}</p>}
        </div> : <p className="agent-chat-readonly">该插件执行固定只读任务。</p>}
      </section>}
      {(retry || notice) && <div className="agent-chat-feedback">
        {retry && <Button disabled={pending || (retry.kind === "message" && !canSend) || (retry.kind === "control" && !activityReady)} onClick={() => void execute(retry)}>{retry.kind === "message" ? "重试发送原指令" : retry.kind === "control" ? "重试原控制操作" : "重试创建原任务"}</Button>}
        {notice && <p role="status">{notice}</p>}
      </div>}
      </>}
    </Drawer>
  </>;
}

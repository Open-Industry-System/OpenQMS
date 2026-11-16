import { useEffect, useRef, useState } from "react";
import { Button, Drawer } from "antd";
import { appendTaskMessage, controlTask, createTask, listTaskInstallations, listTasks, listModelDeployments, launchTask, getTaskWorkflow, listTaskD5Checkpoints } from "../../api/agentTasks";
import type { D5CheckpointReference } from "../../api/agentTasks";
import type { AgentTask, ModelChoice, TaskWorkflow, InstallationChoice, TaskAction, TaskControl, TaskCreate, TaskMessageCreate } from "../../types/agentTask";
import { listTaskD5Proposals, type D5Proposal } from "../../api/d5Proposals";
import D5ProposalPanel from "../capa/D5ProposalPanel";
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
  const [workflow, setWorkflow] = useState<TaskWorkflow | null>(null);
  const [launchPending, setLaunchPending] = useState(false);
  const [launchNotice, setLaunchNotice] = useState("");
  const launchController = useRef<AbortController | null>(null);
  const launchBusy = useRef(false);
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
  const sessionKey = JSON.stringify([ctx?.identity, ctx?.credential, ctx?.selectedTask?.task_id, ctx?.creationReportId, ctx?.requestEpoch]);
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
  useEffect(() => {
    const controller = new AbortController();
    setModels([]);
    if (ctx?.available && ctx.open && ctx.creationReportId)
      void listModelDeployments(controller.signal).then(value => {
        if (!controller.signal.aborted && ctx.identity === readAgentIdentity()) setModels(value.items);
      }).catch(() => { if (!controller.signal.aborted) setModels([]); });
    return () => controller.abort();
  }, [ctx?.identity, ctx?.credential, ctx?.creationReportId, ctx?.open, ctx?.requestEpoch]);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setWorkflow(null);
    const poll = async () => {
      if (!ctx?.open || !ctx.selectedTask?.model_deployment) return;
      try {
        const result = await getTaskWorkflow(ctx.selectedTask.task_id, controller.signal);
        if (!controller.signal.aborted && ctx.identity === readAgentIdentity()) setWorkflow(result);
      } catch {
        if (!controller.signal.aborted) { setWorkflow(null); setLaunchNotice("模型状态不可用；请检查当前权限与部署。"); }
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(poll, 1000);
      }
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [ctx?.identity, ctx?.credential, ctx?.selectedTask?.task_id, ctx?.selectedTask?.model_deployment, ctx?.open, ctx?.requestEpoch]);
  async function launch() {
    if (!ctx?.selectedTask?.model_deployment || launchBusy.current) return;
    const captured = sessionKey;
    const controller = new AbortController();
    launchController.current = controller;
    launchBusy.current = true; setLaunchPending(true); setLaunchNotice("模型任务运行中");
    const live = () => !controller.signal.aborted && captured === currentSession.current && ctx.identity === readAgentIdentity();
    try {
      await launchTask(ctx.selectedTask.task_id, controller.signal);
      if (live()) { setLaunchNotice("模型任务已返回"); ctx.refresh(); }
    } catch {
      if (live()) { setWorkflow(null); setLaunchNotice("启动尚未确认；请刷新当前任务，不能自动改选模型或重发。"); ctx.refresh(); }
    } finally { if (!controller.signal.aborted) { launchBusy.current = false; setLaunchPending(false); } }
  }
  function send(content: string) {
    if (!ctx?.selectedTask || !content.trim() || retry || pending) return;
    void execute({kind:"message",taskId:ctx.selectedTask.task_id,body:{content,idempotency_key:crypto.randomUUID()}});
  }
  useEffect(() => {
    launchBusy.current = false; setLaunchPending(false); setLaunchNotice("");
    return () => launchController.current?.abort();
  }, [ctx?.identity, ctx?.credential, ctx?.selectedTask?.task_id]);
  useEffect(() => {
    const controller = new AbortController();
    setCorrections([]); setCorrectionId(""); setCorrectionTotal(0);
    if(ctx?.open && ctx.selectedTask?.model_deployment)
      void listTaskD5Proposals(ctx.selectedTask.target_capa_id,ctx.selectedTask.task_id,correctionPage,controller.signal).then(data=>{
        if(!controller.signal.aborted && ctx.identity === readAgentIdentity()){setCorrections(data.items);setCorrectionTotal(data.total);}
      }).catch(()=>{if(!controller.signal.aborted) setCorrections([]);});
    return ()=>controller.abort();
  },[ctx?.identity,ctx?.credential,ctx?.selectedTask?.task_id,ctx?.selectedTask?.model_deployment,ctx?.open,ctx?.requestEpoch,correctionPage]);
  useEffect(()=>{setSelectedCheckpoint(null);setCheckpointPage(1);setCorrectionPage(1);},[ctx?.identity,ctx?.credential,ctx?.selectedTask?.task_id]);
  useEffect(()=>{
    const controller=new AbortController();
    setCheckpoints([]);setCheckpointTotal(0);
    if(ctx?.open && ctx.selectedTask?.model_deployment)
      void listTaskD5Checkpoints(ctx.selectedTask.task_id,checkpointPage,controller.signal).then(data=>{
        if(!controller.signal.aborted && ctx.identity===readAgentIdentity()){setCheckpoints(data.items);setCheckpointTotal(data.total);}
      }).catch(()=>{if(!controller.signal.aborted){setCheckpoints([]);setSelectedCheckpoint(null);}});
    return ()=>controller.abort();
  },[ctx?.identity,ctx?.credential,ctx?.selectedTask?.task_id,ctx?.open,ctx?.requestEpoch,checkpointPage,workflow?.checkpoint_id]);
  useEffect(() => setModelId(""), [ctx?.identity, ctx?.creationReportId]);
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
  const selectedInstallation = installations?.find(item => item.installation_id === installationId);
  const needsModel = selectedInstallation?.plugin_key === "openqms.controlled-d5-model";
  const boundModel = ctx.selectedTask?.model_deployment;
  const selectedModel = models.find(model=>model.deployment_id===modelId);
  const newTaskRecipient = selectedModel ? `${selectedModel.name} · ${selectedModel.version}` : "所选模型";
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
        {needsModel && <label>新任务模型<select aria-label="新任务模型" value={modelId} disabled={pending || retry !== null} onChange={e => setModelId(e.target.value)}>
          <option value="">请选择批准的模型版本</option>{models.map(model => <option key={model.deployment_id} value={model.deployment_id}>{model.name} · {model.version} · {model.kind}</option>)}
        </select><p>新任务独立创建，不转交当前任务的聊天或资料。</p></label>}
        {needsModel && models.length === 0 && <p>暂无可用的批准模型部署。</p>}
        {needsModel && <>
          <Button disabled={pending || retry !== null || !installationId || !models.some(model=>model.deployment_id===modelId)} onClick={()=>void execute({kind:"create",body:{report_id:ctx.creationReportId!,installation_id:installationId,model_deployment_id:modelId,request_key:crypto.randomUUID(),initial_text:"deliver_d4_root_cause_candidate_v1"}})}>{`用 ${newTaskRecipient} 开始新任务（仅根据当前根因）`}</Button>
          <p>附加资料可用于对话；保存共享建议需要可核对的完整来源。</p>
        </>}
        <label>初始指令<textarea
          aria-label="初始指令"
          maxLength={10000}
          value={initialText}
          disabled={pending || retry !== null || !installations?.length}
          onChange={e => setInitialText(e.target.value)} />
        </label>
        <Button disabled={pending || retry !== null || !installationId || !initialText.trim() || (needsModel && !models.some(model => model.deployment_id === modelId))} onClick={() => void execute({
          kind: "create", body: {
            report_id: ctx.creationReportId!,
            installation_id: installationId,
            request_key: crypto.randomUUID(),
            initial_text: initialText,
            ...(needsModel ? {model_deployment_id:modelId} : {})
          }
        })}>{needsModel ? `用 ${newTaskRecipient} 开始新任务（自由对话）` : "创建任务"}</Button>
      </section>}
      {ctx.selectedTask && <>
        {boundModel && <section aria-label="当前任务模型">
          <p>当前接收方：{boundModel.name} · {boundModel.version}</p>
          <p>部署版本 {boundModel.deployment_id}</p>
          <Button disabled={launchPending || page?.task_status !== 'ready' || page?.run_status === 'active'} onClick={() => void launch()}>启动模型任务</Button>
          <p>{launchNotice}</p>
          <label>更正当前任务建议<select aria-label="更正当前任务建议" value={correctionId} disabled={pending || retry !== null} onChange={e=>setCorrectionId(e.target.value)}>
            <option value="">请选择当前任务待审建议</option>{corrections.map(item=><option key={item.proposal_id} value={item.proposal_id}>{item.proposal_id}</option>)}
          </select></label>
          <Button disabled={pending || retry !== null || correctionPage<=1} onClick={()=>setCorrectionPage(p=>p-1)}>上一页待更正建议</Button>
          <Button disabled={pending || retry !== null || correctionPage*20>=correctionTotal} onClick={()=>setCorrectionPage(p=>p+1)}>下一页待更正建议</Button>
          <Button disabled={pending || retry !== null || !corrections.some(item=>item.proposal_id===correctionId) || ['completed','failed','cancelled'].includes(page?.task_status ?? '')} onClick={()=>send(JSON.stringify({intent:'replace_d5',predecessor_id:correctionId}))}>明确更正选中建议</Button>
          <p>更正意图只指定前版；并列备选保留原建议。自由聊天含未界定资料时不能保存共享建议。</p>
          {workflow?.question && <p>{workflow.question}</p>}
          {workflow?.status && <p>模型状态：{workflow.status}</p>}
          <label>选择处理范围检查点<select aria-label="选择处理范围检查点" value={selectedCheckpoint?.checkpoint_id??''} onChange={e=>setSelectedCheckpoint(checkpoints.find(cp=>cp.checkpoint_id===e.target.value)??null)}>
            <option value="">请选择实际任务检查点</option>
            {selectedCheckpoint && !checkpoints.some(cp=>cp.checkpoint_id===selectedCheckpoint.checkpoint_id) && <option value={selectedCheckpoint.checkpoint_id}>{selectedCheckpoint.created_at} · {selectedCheckpoint.checkpoint_id}</option>}
            {checkpoints.map(cp=><option key={cp.checkpoint_id} value={cp.checkpoint_id}>{cp.created_at} · {cp.checkpoint_id}</option>)}
          </select></label>
          <Button disabled={checkpointPage<=1} onClick={()=>setCheckpointPage(p=>p-1)}>上一页检查点</Button>
          <Button disabled={checkpointPage*20>=checkpointTotal} onClick={()=>setCheckpointPage(p=>p+1)}>下一页检查点</Button>
          {selectedCheckpoint && <D5ProposalPanel capaId={ctx.selectedTask.target_capa_id} checkpoint={{taskId:ctx.selectedTask.task_id,checkpointId:selectedCheckpoint.checkpoint_id}} />}
          <Button disabled={pending || retry !== null || ['completed','failed','cancelled'].includes(page?.task_status ?? '')} onClick={() => send(JSON.stringify({intent:'continue_d5',additional_context:'none'}))}>继续（无额外资料）</Button>
        </section>}

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
            onChange={e => setText(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && !["completed", "failed", "cancelled"].includes(page.task_status)) { e.preventDefault(); send(text); }
            }} />
          </label>
          <Button disabled={pending || retry !== null || !text.trim() || ["completed", "failed", "cancelled"].includes(page.task_status)} onClick={() => void execute({ kind: "message", taskId: ctx.selectedTask!.task_id, body: { content: text, idempotency_key: crypto.randomUUID() } })}>{boundModel ? `补充给 ${boundModel.name}` : "发送指令"}</Button>
        </>}
      </>}
      {retry && <Button disabled={pending} onClick={() => void execute(retry)}>{retry.kind === "message" ? "重试发送原指令" : retry.kind === "control" ? "重试原控制操作" : "重试创建原任务"}</Button>}
      <p role="status" aria-live="polite">{notice}</p>
    </Drawer>
  </>;
}

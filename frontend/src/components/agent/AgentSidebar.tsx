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
import { tr, useTr } from "../../i18n/tr";
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
  useTr();
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
          setNotice(tr("Plugin-Verzeichnis kann nicht gelesen werden.", "Unable to read plugin directory."));
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
        if (!controller.signal.aborted) { setWorkflow(null); setLaunchNotice(tr("Modellstatus nicht verfügbar; bitte Berechtigungen und Deployment prüfen.", "Model status unavailable; check your permissions and deployment.")); }
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
    launchBusy.current = true; setLaunchPending(true); setLaunchNotice(tr("Modellaufgabe läuft", "Model task running"));
    const live = () => !controller.signal.aborted && captured === currentSession.current && ctx.identity === readAgentIdentity();
    try {
      await launchTask(ctx.selectedTask.task_id, controller.signal);
      if (live()) { setLaunchNotice(tr("Modellaufgabe abgeschlossen", "Model task returned")); ctx.refresh(); }
    } catch {
      if (live()) { setWorkflow(null); setLaunchNotice(tr("Start noch nicht bestätigt; bitte Aufgabe neu laden – Modell wird nicht automatisch gewechselt oder erneut gesendet.", "Launch not yet confirmed; refresh the task – the model is not switched or resent automatically.")); ctx.refresh(); }
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
    setNotice(tr("Wird gesendet", "Submitting"));
    const live = () => !controller.signal.aborted && captured === currentSession.current && ctx.identity === readAgentIdentity();
    try {
      if (op.kind === "message") {
        await appendTaskMessage(op.taskId, op.body, controller.signal);
        if (live()) {
          setRetry(null);
          setText("");
          setNotice(tr("Anweisung eingereiht; „Empfang bestätigt“ erscheint erst nach Bestätigung durch das Plugin.", "Instruction queued; it shows as confirmed only after the plugin acknowledges it."));
          ctx.refresh();
        }
      } else if (op.kind === "control") {
        await controlTask(op.taskId, op.body, controller.signal);
        if (live()) {
          setRetry(null);
          setNotice(tr("Steueraktion bestätigt", "Control action confirmed"));
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
        setNotice(tr("Status hat sich geändert und wurde neu geladen; bitte prüfen und erneut ausführen.", "State changed and was refreshed; please review and retry."));
        ctx.refresh();
      } else if (status === 401 || status === 403 || status === 404) {
        setRetry(null);
        setNotice(tr("Zugriff auf die Aufgabe ist nicht mehr gültig", "Task access expired"));
        ctx.clearTask();
      } else {
        setRetry(op);
        setNotice(tr("Verbindung unterbrochen, Vorgang nicht bestätigt; Wiederholen sendet die ursprüngliche Anfrage.", "Connection lost, operation not confirmed; retry sends the original request."));
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
  const newTaskRecipient = selectedModel ? `${selectedModel.name} · ${selectedModel.version}` : tr("ausgewähltes Modell", "selected model");
  return <>
    <Button ref={trigger} onClick={() => ctx.setOpen(true)}>{tr("Agent-Aufgaben", "Agent tasks")}</Button>
    <Drawer
      title={tr("Agent-Aufgaben", "Agent tasks")}
      open={ctx.open}
      width={560}
      onClose={() => ctx.setOpen(false)}
      afterOpenChange={open => {
        if (!open)
          trigger.current?.focus();
      }}
      destroyOnClose>
      <Button onClick={() => ctx.setOpen(false)}>{tr("Aufgaben-Seitenleiste schließen", "Close task sidebar")}</Button>
      <label>{tr("Aufgabe wählen", "Select task")}<select
        aria-label={tr("Aufgabe wählen", "Select task")}
        value={ctx.selectedTask?.task_id ?? ""}
        onChange={event => {
          const task = tasks.find(item => item.task_id === event.target.value);
          if (task)
            ctx.selectTask(task);
        }}>
        <option value="">{tr("Bitte Aufgabe wählen", "Please select a task")}</option>{ctx.selectedTask && !tasks.some(task => task.task_id === ctx.selectedTask?.task_id) && <option value={ctx.selectedTask.task_id}>{tr("Aktuelle Aufgabe", "Current task")} {ctx.selectedTask.target_capa_id}</option>}{tasks.map(task => <option key={task.task_id} value={task.task_id}>{task.target_capa_id} · {task.status}</option>)}</select>
      </label>
      <p>{tr(`Aufgabenverzeichnis Seite ${directoryPage}`, `Task directory page ${directoryPage}`)}</p>
      <Button disabled={directoryPage <= 1} onClick={() => setDirectoryPage(n => n - 1)}>{tr("Vorherige Aufgabenseite", "Previous task page")}</Button>
      <Button disabled={directoryPage * 20 >= directoryTotal} onClick={() => setDirectoryPage(n => n + 1)}>{tr("Nächste Aufgabenseite", "Next task page")}</Button>
      {ctx.creationReportId && <section aria-label={tr("Aufgabe anlegen", "Create task")}>
        <p>{tr("Zielbericht für neue Aufgabe", "Target report for new task")} {ctx.creationReportId}</p>
        <label>{tr("Plugin-Installation", "Plugin installation")}<select
          aria-label={tr("Plugin-Installation", "Plugin installation")}
          value={installationId}
          disabled={pending || retry !== null || !installations?.length}
          onChange={e => setInstallation(e.target.value)}>{installations?.map(choice => <option key={choice.installation_id} value={choice.installation_id}>{choice.plugin_key} · {choice.plugin_version}</option>)}</select>
        </label>
        {installations?.length === 0 && <p>{tr("Keine passende Plugin-Installation für diesen Bericht – Aufgabe kann nicht angelegt werden.", "No plugin installation available for this report; cannot create a task.")}</p>}
        {needsModel && <label>{tr("Modell der neuen Aufgabe", "New task model")}<select aria-label={tr("Modell der neuen Aufgabe", "New task model")} value={modelId} disabled={pending || retry !== null} onChange={e => setModelId(e.target.value)}>
          <option value="">{tr("Bitte freigegebene Modellversion wählen", "Please select an approved model version")}</option>{models.map(model => <option key={model.deployment_id} value={model.deployment_id}>{model.name} · {model.version} · {model.kind}</option>)}
        </select><p>{tr("Die neue Aufgabe wird eigenständig angelegt; Chat und Unterlagen der aktuellen Aufgabe werden nicht übernommen.", "The new task is created independently; chat and materials of the current task are not carried over.")}</p></label>}
        {needsModel && models.length === 0 && <p>{tr("Keine freigegebenen Modell-Deployments verfügbar.", "No approved model deployments available.")}</p>}
        {needsModel && <>
          <Button disabled={pending || retry !== null || !installationId || !models.some(model=>model.deployment_id===modelId)} onClick={()=>void execute({kind:"create",body:{report_id:ctx.creationReportId!,installation_id:installationId,model_deployment_id:modelId,request_key:crypto.randomUUID(),initial_text:"deliver_d4_root_cause_candidate_v1"}})}>{tr(`Neue Aufgabe mit ${newTaskRecipient} starten (nur aus aktueller Grundursache)`, `Start new task with ${newTaskRecipient} (current root cause only)`)}</Button>
          <p>{tr("Zusätzliche Unterlagen können im Dialog genutzt werden; zum Speichern geteilter Vorschläge sind vollständige, prüfbare Quellen nötig.", "Extra materials can be used in chat; saving shared proposals requires complete, verifiable sources.")}</p>
        </>}
        <label>{tr("Erste Anweisung", "Initial instruction")}<textarea
          aria-label={tr("Erste Anweisung", "Initial instruction")}
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
        })}>{needsModel ? tr(`Neue Aufgabe mit ${newTaskRecipient} starten (freier Dialog)`, `Start new task with ${newTaskRecipient} (free chat)`) : tr("Aufgabe anlegen", "Create task")}</Button>
      </section>}
      {ctx.selectedTask && <>
        {boundModel && <section aria-label={tr("Modell der aktuellen Aufgabe", "Current task model")}>
          <p>{tr("Aktueller Empfänger: ", "Current recipient: ")}{boundModel.name} · {boundModel.version}</p>
          <p>{tr("Deployment-Version", "Deployment version")} {boundModel.deployment_id}</p>
          <Button disabled={launchPending || page?.task_status !== 'ready' || page?.run_status === 'active'} onClick={() => void launch()}>{tr("Modellaufgabe starten", "Launch model task")}</Button>
          <p>{launchNotice}</p>
          <label>{tr("Vorschlag der aktuellen Aufgabe korrigieren", "Correct current task proposal")}<select aria-label={tr("Vorschlag der aktuellen Aufgabe korrigieren", "Correct current task proposal")} value={correctionId} disabled={pending || retry !== null} onChange={e=>setCorrectionId(e.target.value)}>
            <option value="">{tr("Bitte offenen Vorschlag der aktuellen Aufgabe wählen", "Please select a pending proposal of the current task")}</option>{corrections.map(item=><option key={item.proposal_id} value={item.proposal_id}>{item.proposal_id}</option>)}
          </select></label>
          <Button disabled={pending || retry !== null || correctionPage<=1} onClick={()=>setCorrectionPage(p=>p-1)}>{tr("Vorherige Korrekturseite", "Previous correction page")}</Button>
          <Button disabled={pending || retry !== null || correctionPage*20>=correctionTotal} onClick={()=>setCorrectionPage(p=>p+1)}>{tr("Nächste Korrekturseite", "Next correction page")}</Button>
          <Button disabled={pending || retry !== null || !corrections.some(item=>item.proposal_id===correctionId) || ['completed','failed','cancelled'].includes(page?.task_status ?? '')} onClick={()=>send(JSON.stringify({intent:'replace_d5',predecessor_id:correctionId}))}>{tr("Ausgewählten Vorschlag ausdrücklich korrigieren", "Explicitly correct selected proposal")}</Button>
          <p>{tr("Eine Korrektur bezieht sich nur auf die Vorversion; Alternativen behalten den ursprünglichen Vorschlag. Enthält der freie Chat nicht abgegrenzte Unterlagen, können keine geteilten Vorschläge gespeichert werden.", "A correction only targets the previous version; alternatives keep the original proposal. Free chat with unscoped materials cannot save shared proposals.")}</p>
          {workflow?.question && <p>{workflow.question}</p>}
          {workflow?.status && <p>{tr("Modellstatus: ", "Model status: ")}{workflow.status}</p>}
          <label>{tr("Checkpoint für Bearbeitungsumfang wählen", "Select scope checkpoint")}<select aria-label={tr("Checkpoint für Bearbeitungsumfang wählen", "Select scope checkpoint")} value={selectedCheckpoint?.checkpoint_id??''} onChange={e=>setSelectedCheckpoint(checkpoints.find(cp=>cp.checkpoint_id===e.target.value)??null)}>
            <option value="">{tr("Bitte tatsächlichen Aufgaben-Checkpoint wählen", "Please select an actual task checkpoint")}</option>
            {selectedCheckpoint && !checkpoints.some(cp=>cp.checkpoint_id===selectedCheckpoint.checkpoint_id) && <option value={selectedCheckpoint.checkpoint_id}>{selectedCheckpoint.created_at} · {selectedCheckpoint.checkpoint_id}</option>}
            {checkpoints.map(cp=><option key={cp.checkpoint_id} value={cp.checkpoint_id}>{cp.created_at} · {cp.checkpoint_id}</option>)}
          </select></label>
          <Button disabled={checkpointPage<=1} onClick={()=>setCheckpointPage(p=>p-1)}>{tr("Vorherige Checkpoint-Seite", "Previous checkpoint page")}</Button>
          <Button disabled={checkpointPage*20>=checkpointTotal} onClick={()=>setCheckpointPage(p=>p+1)}>{tr("Nächste Checkpoint-Seite", "Next checkpoint page")}</Button>
          {selectedCheckpoint && <D5ProposalPanel capaId={ctx.selectedTask.target_capa_id} checkpoint={{taskId:ctx.selectedTask.task_id,checkpointId:selectedCheckpoint.checkpoint_id}} />}
          <Button disabled={pending || retry !== null || ['completed','failed','cancelled'].includes(page?.task_status ?? '')} onClick={() => send(JSON.stringify({intent:'continue_d5',additional_context:'none'}))}>{tr("Fortfahren (ohne zusätzliche Unterlagen)", "Continue (no extra materials)")}</Button>
        </section>}

        {activity.status === "interrupted" && <p>{tr("Verbindung unterbrochen, neuer Versuch läuft", "Connection lost, retrying")}</p>}
        {activity.status === "denied" && <p>{tr("Zugriff auf die Aufgabe ist nicht mehr gültig", "Task access expired")}</p>}
        {activity.status === "loading" && <p>{tr("Aufgabenaktivität wird geladen", "Loading task activity")}</p>}
        {page && <>
          <AgentActivity task={ctx.selectedTask} page={page} onControl={command} pending={pending || retry !== null} />
          <AgentTaskAttachments
            taskId={ctx.selectedTask.task_id}
            identity={ctx.identity}
            credential={ctx.credential}
            open={ctx.open}
            requestEpoch={ctx.requestEpoch}
          />
          <label>{tr("Weitere Anweisung", "Additional instruction")}<textarea
            aria-label={tr("Weitere Anweisung", "Additional instruction")}
            maxLength={10000}
            value={text}
            disabled={pending || retry !== null || ["completed", "failed", "cancelled"].includes(page.task_status)}
            onChange={e => setText(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && !["completed", "failed", "cancelled"].includes(page.task_status)) { e.preventDefault(); send(text); }
            }} />
          </label>
          <Button disabled={pending || retry !== null || !text.trim() || ["completed", "failed", "cancelled"].includes(page.task_status)} onClick={() => void execute({ kind: "message", taskId: ctx.selectedTask!.task_id, body: { content: text, idempotency_key: crypto.randomUUID() } })}>{boundModel ? tr(`Ergänzung an ${boundModel.name}`, `Add to ${boundModel.name}`) : tr("Anweisung senden", "Send instruction")}</Button>
        </>}
      </>}
      {retry && <Button disabled={pending} onClick={() => void execute(retry)}>{retry.kind === "message" ? tr("Ursprüngliche Anweisung erneut senden", "Resend original instruction") : retry.kind === "control" ? tr("Ursprüngliche Steueraktion wiederholen", "Retry original control action") : tr("Ursprüngliche Aufgabe erneut anlegen", "Retry creating original task")}</Button>}
      <p role="status" aria-live="polite">{notice}</p>
    </Drawer>
  </>;
}

import { Button } from "antd";
import { Link } from "react-router-dom";
import type { ActivityItem, ActivityPage, AgentTask, RuntimeSource, TaskAction } from "../../types/agentTask";
import { tr, useTr } from "../../i18n/tr";
interface Props {
  task: AgentTask;
  page: ActivityPage;
  pending: boolean;
  onControl: (action: TaskAction, checkpointId?: string) => void;
}
function Sources({ sources }: {
  sources: RuntimeSource[];
}) {
  return <ul>{sources.map(source => <li key={source.receipt_id}>
    <div>{tr("Lesebeleg", "Read receipt")} {source.receipt_id}</div>
    <div>{tr("Quellbericht", "Source report")} {source.source_capa_id}</div>
    <div>{tr("Quellversion", "Source version")} {source.projection_id}</div>
    <div>{tr("Prüfsumme", "Digest")} {source.projection_digest}</div>
    <div>{tr("Datenklasse", "Data class")} {source.data_class}</div>
  </li>)}</ul>;
}
function Row({ item, task, page, pending, onControl }: Pick<Props, "task" | "page" | "pending" | "onControl"> & {
  item: ActivityItem;
}) {
  switch (item.kind) {
    case "message": {
      const terminal = page.task_status === "failed" || page.task_status === "cancelled";
      const state = item.data.state === "received" ? tr("Empfang bestätigt", "Receipt confirmed") : `${item.data.state === "queued" ? tr("In Warteschlange", "Queued") : tr("Abgeholt", "Claimed")}${terminal ? tr(": Bei Abbruch nicht bestätigt (bedeutet nicht verarbeitet)", ": Not confirmed at termination (does not mean processed)") : ""}`;
      return <>
        <p>{task.model_deployment && item.data.content === "deliver_d4_root_cause_candidate_v1" ? tr("Nur Vorschlagsaufgabe aus aktueller Grundursache erstellen", "Create proposal task from current root cause only") : item.data.content}</p>
        <span>{state}</span>
      </>;
    }
    case "ack": return <p>{tr("Plugin hat Empfang bestätigt für Batch", "Plugin confirmed receipt of batch")} {item.data.batch_id}</p>;
    case "run_created":
    case "claim":
    case "finish": return <>
      <div>{tr("Plugin-Installation", "Plugin installation")} {item.data.installation_id}</div>
      <div>{tr("Plugin-Version", "Plugin version")} {item.data.plugin_version}</div>
      <div>{tr("Früherer Lauf", "Previous run")} {item.data.run_id} · {item.data.run_status} · {tr("Runde", "Epoch")} {item.data.lease_epoch}</div>
    </>;
    case "control": return <p>{tr("Steueraktion", "Control action")} {({
      pause: tr("Pausieren", "Pause"),
      resume: tr("Fortsetzen", "Resume"),
      cancel: tr("Abbrechen", "Cancel"),
      restart: tr("Neustart", "Restart")
    })[item.data.action]} · {item.data.control_id}</p>;
    case "event": return "presentation_code" in item.data ? <p>{tr("Plugin meldet: läuft", "Plugin reports running")}</p> : <>
      <p>{item.data.payload.stage}</p>
      <p>{item.data.payload.message}</p>{item.data.payload.completed !== null && <p>{tr("Fortschritt", "Progress")} {item.data.payload.completed} / {item.data.payload.total ?? tr("unbekannt", "unknown")}</p>}<Sources sources={item.data.sources} />
    </>;
    case "result": return <>
      <h4>{tr("Schreibgeschütztes Analyseergebnis", "Read-only analysis result")}</h4>{Object.entries(item.data.payload).map(([key, values]) => <div key={key}>
        <strong>{({
          explanations: tr("Erklärungen", "Explanations"),
          support: tr("Belege dafür", "Supporting evidence"),
          opposition: tr("Belege dagegen", "Opposing evidence"),
          missing_information: tr("Fehlende Informationen", "Missing information"),
          conditional_recommendations: tr("Bedingte Empfehlungen", "Conditional recommendations")
        } as Record<string, string>)[key]}</strong>
        <ul>{values.map((text: string, i: number) => <li key={i}>{text}</li>)}</ul>
      </div>)}<Sources sources={item.data.sources} />
    </>;
    case "checkpoint": {
      const cp = item.data;
      if ('checkpoint_type' in cp) return <>
        <h4>{tr("Aufgaben-Checkpoint", "Task checkpoint")} {cp.checkpoint_id}</h4>
        <p>{tr("Checkpoint-Lauf", "Checkpoint run")} {cp.run_id} · {cp.created_at}</p>
        <p>{tr("Checkpoints begrenzen den Bearbeitungsumfang späterer Vorschläge und stellen kein internes Modellgedächtnis wieder her.", "Checkpoints scope later proposals; they do not restore the model's internal memory.")}</p>
      </>;
      const sameRun = page.task_status === "paused" && page.run_status === "paused" && cp.run_id === page.run_id;
      const eligible = sameRun && cp.is_latest && cp.prefix_eligible;
      return <>
        <h4>{tr("Schreibgeschützter Checkpoint", "Read-only checkpoint")} {cp.checkpoint_id}</h4>
        <div>{tr("Checkpoint-Lauf", "Checkpoint run")} {cp.run_id} · {tr("Runde", "Epoch")} {cp.lease_epoch}</div>
        <div>{tr("Bestätigte Anweisungsnummer", "Accepted message seq.")} {cp.accepted_message_seq} · {tr("Aktualisierungsnummer", "Update seq.")} {cp.update_sequence}</div>
        <Sources sources={cp.sources} />
        <Button disabled={!eligible || pending} onClick={() => onControl("restart", cp.checkpoint_id)}>{tr("Ab diesem Checkpoint neu starten", "Restart from this checkpoint")}</Button>{!sameRun && <p>{tr("Aufgabe und Lauf müssen pausiert sein und der Checkpoint muss zum aktuellen Lauf gehören.", "Task and run must be paused and the checkpoint must belong to the current run.")}</p>}{(!cp.is_latest || !cp.prefix_eligible) && <p>{tr("Nur der neueste Checkpoint mit gültigem Nachrichtenpräfix kann zum Neustart verwendet werden.", "Only the latest checkpoint with a valid message prefix can be used for restart.")}</p>}<p>{tr("Beim Neustart werden die aktuellen Daten neu gelesen; das interne Plugin-Gedächtnis wird nicht wiederhergestellt und Geschäftsdaten werden nicht zurückgesetzt.", "Restart re-reads current facts; it does not restore plugin memory or roll back business data.")}</p>
      </>;
    }
  }
}
export default function AgentActivity({ task, page, pending, onControl }: Props) {
  useTr();
  const terminal = ["completed", "failed", "cancelled"].includes(page.task_status);
  const currentRun = [...page.items].reverse().find(item => (item.kind === "run_created" || item.kind === "claim" || item.kind === "finish") && item.data.run_id === page.run_id);
  const runData = currentRun && (currentRun.kind === "run_created" || currentRun.kind === "claim" || currentRun.kind === "finish") ? currentRun.data : null;
  return <section aria-label={tr("Aufgabenaktivität", "Task activity")} style={{ overflowWrap: "anywhere" }}>
    <Link to={`/capa/${task.target_capa_id}`}>{tr("Zielbericht", "Target report")} {task.target_capa_id}</Link>
    <p>{tr("Aufgabe", "Task")} {task.task_id}</p>
    <p>{tr("Plugin-Installation", "Plugin installation")} {runData?.installation_id ?? task.preferred_installation_id}</p>
    <p>{tr("Plugin-Version", "Plugin version")} {runData?.plugin_version ?? tr("im aktuellen Fenster nicht angegeben", "not provided in current window")}</p>
    <p>{tr("Aufgabenstatus", "Task status")} {page.task_status}</p>
    <p>{tr("Aktueller Lauf", "Current run")} {page.run_id ?? tr("kein Lauf", "no run")} · {page.run_status ?? tr("kein Status", "no status")}</p>{page.lease_epoch !== null && <p>{tr("Laufrunde", "Run epoch")} {page.lease_epoch}</p>}
    <div>
      <Button
        aria-label={tr("Pausieren", "Pause")}
        disabled={pending || !(["pending", "active"] as Array<string | null>).includes(page.run_status) || page.task_status !== "ready"}
        onClick={() => onControl("pause")}>{tr("Pausieren", "Pause")}</Button>
      <Button
        aria-label={tr("Fortsetzen", "Resume")}
        disabled={pending || page.run_status !== "paused" || page.task_status !== "paused"}
        onClick={() => onControl("resume")}>{tr("Fortsetzen", "Resume")}</Button>
      <Button disabled={pending || terminal} onClick={() => onControl("cancel")}>{tr("Aufgabe abbrechen", "Cancel task")}</Button>
    </div>
    <ol data-testid="agent-activity-window">{page.items.map(item => <li key={item.sequence} data-sequence={item.sequence}>
      <time>{item.created_at}</time>
      <Row item={item} task={task} page={page} pending={pending} onControl={onControl} />
    </li>)}</ol>
  </section>;
}

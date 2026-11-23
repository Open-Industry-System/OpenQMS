import { Button } from "antd";
import { Link } from "react-router-dom";
import type { ActivityItem, ActivityPage, AgentTask, RuntimeSource, TaskAction } from "../../types/agentTask";
interface Props {
  task: AgentTask;
  page: ActivityPage;
  pending: boolean;
  technicalOnly?: boolean;
  onControl: (action: TaskAction, checkpointId?: string) => void;
}
export function Sources({ sources }: {
  sources: RuntimeSource[];
}) {
  return <ul>{sources.map(source => <li key={source.receipt_id}>
    <div>读取凭据 {source.receipt_id}</div>
    <div>来源报告 {source.source_capa_id}</div>
    <div>来源版本 {source.projection_id}</div>
    <div>摘要 {source.projection_digest}</div>
    <div>数据级别 {source.data_class}</div>
  </li>)}</ul>;
}
export function TaskMessageText({ content, model }: { content: string; model: boolean }) {
  let label = content;
  if (content === "deliver_d4_root_cause_candidate_v1") {
    label = model ? "仅根据当前根因创建建议任务" : "读取当前根因";
  }
  else if (content === '{"intent":"continue_d5","additional_context":"none"}') label = "继续（无额外资料）";
  else if (/^\{"intent":"replace_d5","predecessor_id":"[a-f0-9-]+"\}$/i.test(content)) label = "明确更正选中建议";
  return <p>{label}</p>;
}
export function taskMessageState(state: "queued" | "claimed" | "received", status?: string) {
  if (state === "received") return "已确认接收";
  const label = state === "queued" ? "排队中" : "已领取";
  return status === "failed" || status === "cancelled"
    ? `${label}：终止时未确认接收（不代表已处理）` : label;
}
export function TaskResult({ result }: { result: Extract<ActivityItem, { kind: "result" }>["data"] }) {
  const labels = {
    explanations: "解释",
    support: "支持证据",
    opposition: "反对证据",
    missing_information: "缺失信息",
    conditional_recommendations: "条件建议",
  } as const;
  return <>
    <h4>只读分析结果</h4>
    {(Object.keys(labels) as (keyof typeof labels)[]).map(key => result.payload[key].length > 0 && <div key={key}>
      <strong>{labels[key]}</strong>
      <ul>{result.payload[key].map((value, index) => <li key={index}>{value}</li>)}</ul>
    </div>)}
    <details><summary>查看结果证据</summary><Sources sources={result.sources} /></details>
  </>;
}
function Row({ item, task, page, pending, onControl }: Pick<Props, "task" | "page" | "pending" | "onControl"> & {
  item: ActivityItem;
}) {
  switch (item.kind) {
    case "message": return <>
      <TaskMessageText content={item.data.content} model={Boolean(task.model_deployment)} />
      <span>{taskMessageState(item.data.state, page.task_status)}</span>
    </>;
    case "ack": return <p>插件已确认接收批次 {item.data.batch_id}</p>;
    case "run_created":
    case "claim":
    case "finish": return <>
      <div>插件安装 {item.data.installation_id}</div>
      <div>插件版本 {item.data.plugin_version}</div>
      <div>历史运行 {item.data.run_id} · {item.data.run_status} · 轮次 {item.data.lease_epoch}</div>
    </>;
    case "control": return <p>控制操作 {({
      pause: "暂停",
      resume: "继续",
      cancel: "取消",
      restart: "重启"
    })[item.data.action]} · {item.data.control_id}</p>;
    case "event": return "presentation_code" in item.data ? <p>插件报告运行中</p> : <>
      <p>{item.data.payload.stage}</p>
      <p>{item.data.payload.message}</p>{item.data.payload.completed !== null && <p>进度 {item.data.payload.completed} / {item.data.payload.total ?? "未知"}</p>}<Sources sources={item.data.sources} />
    </>;
    case "result": return <TaskResult result={item.data} />;
    case "checkpoint": {
      const cp = item.data;
      if ('checkpoint_type' in cp) return <>
        <h4>任务检查点 {cp.checkpoint_id}</h4>
        <p>检查点运行 {cp.run_id} · {cp.created_at}</p>
        <p>检查点用于界定后续建议的处理范围，不恢复模型内部记忆。</p>
      </>;
      const sameRun = page.task_status === "paused" && page.run_status === "paused" && cp.run_id === page.run_id;
      const eligible = sameRun && cp.is_latest && cp.prefix_eligible;
      return <>
        <h4>只读检查点 {cp.checkpoint_id}</h4>
        <div>检查点运行 {cp.run_id} · 轮次 {cp.lease_epoch}</div>
        <div>已确认指令序号 {cp.accepted_message_seq} · 更新序号 {cp.update_sequence}</div>
        <Sources sources={cp.sources} />
        <Button disabled={!eligible || pending} onClick={() => onControl("restart", cp.checkpoint_id)}>从此检查点重启</Button>{!sameRun && <p>当前任务与运行须已暂停，且检查点须属于当前运行。</p>}{(!cp.is_latest || !cp.prefix_eligible) && <p>仅最新且消息前缀有效的检查点可用于重启。</p>}<p>重启将重新读取当前事实；不恢复插件内部记忆，也不回滚业务数据。</p>
      </>;
    }
  }
}
export default function AgentActivity({ task, page, pending, onControl, technicalOnly = false }: Props) {
  const terminal = ["completed", "failed", "cancelled"].includes(page.task_status);
  const currentRun = [...page.items].reverse().find(item => (item.kind === "run_created" || item.kind === "claim" || item.kind === "finish") && item.data.run_id === page.run_id);
  const runData = currentRun && (currentRun.kind === "run_created" || currentRun.kind === "claim" || currentRun.kind === "finish") ? currentRun.data : null;
  return <section aria-label={technicalOnly ? "运行与控制" : "任务活动"} style={{ overflowWrap: "anywhere" }}>
    {!technicalOnly && <Link to={`/capa/${task.target_capa_id}`}>目标报告 {task.target_capa_id}</Link>}
    <p>任务 {task.task_id}</p>
    <p>插件安装 {runData?.installation_id ?? task.preferred_installation_id}</p>
    <p>插件版本 {runData?.plugin_version ?? "当前窗口未提供"}</p>
    <p>任务状态 {page.task_status}</p>
    <p>当前运行 {page.run_id ?? "暂无运行"} · {page.run_status ?? "暂无状态"}</p>{page.lease_epoch !== null && <p>运行轮次 {page.lease_epoch}</p>}
    <div>
      <Button
        aria-label="暂停"
        disabled={pending || !(["pending", "active"] as Array<string | null>).includes(page.run_status) || page.task_status !== "ready"}
        onClick={() => onControl("pause")}>暂停</Button>
      <Button
        aria-label="继续"
        disabled={pending || page.run_status !== "paused" || page.task_status !== "paused"}
        onClick={() => onControl("resume")}>继续</Button>
      <Button disabled={pending || terminal} onClick={() => onControl("cancel")}>取消任务</Button>
    </div>
    <ol data-testid={technicalOnly ? "agent-technical-window" : "agent-activity-window"}>{page.items.filter(item => !technicalOnly || (item.kind !== "message" && item.kind !== "result")).map(item => <li key={item.sequence} data-sequence={item.sequence}>
      <time>{item.created_at}</time>
      <Row item={item} task={task} page={page} pending={pending} onControl={onControl} />
    </li>)}</ol>
  </section>;
}

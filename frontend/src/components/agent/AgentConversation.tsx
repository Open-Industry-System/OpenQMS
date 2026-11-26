import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "antd";
import { Link } from "react-router-dom";
import type { ActivityPage, AgentTask, TaskQuestion } from "../../types/agentTask";
import type { D5Proposal } from "../../api/d5Proposals";
import { TaskMessageText, TaskResult, taskMessageState } from "./AgentActivity";

interface Props {
  task: AgentTask;
  page: ActivityPage;
  questions: TaskQuestion[];
  waitingQuestionId?: string;
  proposals: D5Proposal[];
  hidden: boolean;
  onOpenReport: () => void;
}

const PROPOSAL_STATE = { pending: "待审阅", adopted: "已采纳", withdrawn: "已撤回", superseded: "已替代" };

export default function AgentConversation({ task, page, questions, waitingQuestionId, proposals, hidden, onOpenReport }: Props) {
  const viewport = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const [away, setAway] = useState(false);
  const entries: { id: string; time: string; sequence?: number; employee?: boolean; body: ReactNode }[] = [];

  for (const item of page.items) {
    if (item.kind === "message") entries.push({
      id: item.data.message_id, time: item.created_at, sequence: item.sequence, employee: true,
      body: <>
        <TaskMessageText content={item.data.content} model={Boolean(task.model_deployment)} />
        <span className="agent-chat-message-state">{taskMessageState(item.data.state, page.task_status)}</span>
      </>,
    });
    if (item.kind === "result") entries.push({
      id: item.data.result_id, time: item.created_at, sequence: item.sequence, body: <TaskResult result={item.data} />,
    });
  }
  for (const question of questions) entries.push({
    id: question.question_id, time: question.created_at,
    body: <>
      <strong>Agent 追问</strong>
      {question.question_id === waitingQuestionId && <span className="agent-chat-message-state"> · 等待补充</span>}
      <p>{question.text}</p>
    </>,
  });
  for (const proposal of proposals) entries.push({
    id: proposal.proposal_id, time: proposal.created_at,
    body: <>
      <strong>D5 建议 · {PROPOSAL_STATE[proposal.state]}</strong>
      <p>{proposal.original_text}</p>
      <Link to={`/capa/${task.target_capa_id}`} onClick={onOpenReport}>在 8D 报告中审阅建议</Link>
    </>,
  });
  entries.sort((a, b) => Date.parse(a.time) - Date.parse(b.time));

  useLayoutEffect(() => {
    const el = viewport.current;
    if (!hidden && follow.current && el) el.scrollTop = el.scrollHeight;
  });

  return <div className="agent-chat-conversation" hidden={hidden}>
    <div
      ref={viewport}
      className="agent-chat-scroll"
      role="region"
      aria-label="任务对话"
      tabIndex={0}
      onScroll={event => {
        const el = event.currentTarget;
        follow.current = el.scrollHeight - el.scrollTop - el.clientHeight <= 32;
        setAway(!follow.current);
      }}
    >
      {entries.length === 0 && <p className="agent-chat-empty">暂无对话记录</p>}
      <ol className="agent-chat-messages" aria-live="polite" aria-relevant="additions text" data-testid="agent-activity-window">
        {entries.map(entry => <li key={entry.id} data-sequence={entry.sequence} className={entry.employee ? "agent-chat-mine" : undefined}>
          <div className="agent-chat-byline">
            <strong>{entry.employee ? "我" : "Agent"}</strong>
            <time dateTime={entry.time}>{new Date(entry.time).toLocaleString("zh-CN")}</time>
          </div>
          <div className="agent-chat-message">{entry.body}</div>
        </li>)}
      </ol>
    </div>
    {away && <Button size="small" className="agent-chat-latest" onClick={() => {
      follow.current = true;
      setAway(false);
      if (viewport.current) viewport.current.scrollTop = viewport.current.scrollHeight;
    }}>回到最新消息</Button>}
  </div>;
}

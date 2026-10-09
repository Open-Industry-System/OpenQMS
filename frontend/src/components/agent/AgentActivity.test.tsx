import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { render as rtlRender, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, describe, it, expect, vi } from "vitest";
import AgentActivity from "./AgentActivity";
function render(ui: ReactElement) {
  return rtlRender(<MemoryRouter>{ui}</MemoryRouter>);
}
const id = "00000000-0000-4000-8000-000000000001", run = "00000000-0000-4000-8000-000000000002";
const task = {
  task_id: id,
  target_capa_id: id,
  factory_id: id,
  preferred_installation_id: id,
  status: "ready" as const,
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z"
};
const source = {
  receipt_id: id,
  source_capa_id: id,
  projection_id: "capa.d4.summary.masked.v1" as const,
  projection_digest: "a".repeat(64),
  data_class: "internal" as const
};
const base = {
  task_id: id,
  task_status: "paused" as const,
  run_id: run,
  run_status: "paused" as const,
  lease_epoch: 4,
  window_end_sequence: 10,
  next_before_sequence: null,
  items: []
};
const cp = (latest = true, runId = run) => ({
  sequence: 5,
  kind: "checkpoint" as const,
  created_at: task.created_at,
  data: {
    checkpoint_id: id,
    task_id: id,
    run_id: runId,
    lease_epoch: 3,
    tenant_generation: 1,
    accepted_message_seq: 1,
    update_sequence: 5,
    created_at: task.created_at,
    sources: [source],
    is_latest: latest,
    prefix_eligible: true
  }
});
afterEach(cleanup);
describe("escaped, provenance-aware activity", () => {
  it("can pause a pending current run using the current server state", () => {
    const control = vi.fn();
    render(<AgentActivity
      task={task}
      page={{ ...base, task_status: "ready", run_status: "pending" }}
      onControl={control}
      pending={false} />);
    expect(screen.getByRole("button", { name: "暂停" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "暂停" }));
    expect(control).toHaveBeenCalledWith("pause");
  });
  it("shows immutable target, escaped messages, received alias and actual queued/claimed terminal distinction", () => {
    render(<AgentActivity
      task={task}
      page={{
        ...base, task_status: "failed", items: ["queued", "claimed", "received"].map((state, i) => ({
          sequence: i + 1,
          kind: "message",
          created_at: task.created_at,
          data: {
            message_id: id,
            author_id: id,
            sequence: i + 1,
            content: "<img src=x onerror=alert(1)>",
            data_class: "restricted",
            state
          }
        })) as any
      }}
      onControl={vi.fn()}
      pending={false} />);
    expect(screen.getByRole("link", { name: `目标报告 ${id}` })).toHaveAttribute("href", `/capa/${id}`);
    expect(screen.getAllByText("<img src=x onerror=alert(1)>")).toHaveLength(3);
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByText("已确认接收")).toBeInTheDocument();
    expect(screen.getByText("排队中：终止时未确认接收（不代表已处理）")).toBeInTheDocument();
    expect(screen.getByText("已领取：终止时未确认接收（不代表已处理）")).toBeInTheDocument();
  });
  it("unsourced progress is only fixed plugin-running presentation", () => {
    render(<AgentActivity
      task={task}
      page={{
        ...base, items: [{
          sequence: 1,
          kind: "event",
          created_at: task.created_at,
          data: {
            event_id: id,
            task_id: id,
            run_id: run,
            event_type: "progress",
            presentation_code: "plugin_running",
            created_at: task.created_at,
            sources: []
          }
        }]
      }}
      onControl={vi.fn()}
      pending={false} />);
    expect(screen.getByText("插件报告运行中")).toBeInTheDocument();
  });
  it("shows full checkpoint source/digest and sends checkpoint only when current paused run eligible", () => {
    const control = vi.fn();
    render(<AgentActivity task={task} page={{ ...base, items: [cp()] }} onControl={control} pending={false} />);
    expect(screen.getByText(`摘要 ${source.projection_digest}`)).toBeInTheDocument();
    expect(screen.getByText(`来源版本 ${source.projection_id}`)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "从此检查点重启" }));
    expect(control).toHaveBeenCalledWith("restart", id);
    expect(screen.getByText(/重新读取当前事实/)).toBeInTheDocument();
  });
  it.each([{ task_status: "ready", run_status: "active", run_id: run }, { task_status: "paused", run_status: "active", run_id: run }, { task_status: "paused", run_status: "paused", run_id: id }])("disables CP against current server state %j", state => {
    render(<AgentActivity task={task} page={{ ...base, ...state, items: [cp()] } as any} onControl={vi.fn()} pending={false} />);
    expect(screen.getByRole("button", { name: "从此检查点重启" })).toBeDisabled();
    expect(screen.getByText(/当前任务与运行须已暂停/)).toBeInTheDocument();
  });
  it("historical/latest-ineligible CP is disabled with reason", () => {
    render(<AgentActivity task={task} page={{ ...base, items: [cp(false)] }} onControl={vi.fn()} pending={false} />);
    expect(screen.getByRole("button", { name: "从此检查点重启" })).toBeDisabled();
    expect(screen.getByText(/仅最新且消息前缀有效的检查点/)).toBeInTheDocument();
  });
});

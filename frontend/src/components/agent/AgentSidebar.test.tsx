import { render, screen, fireEvent, act, waitFor, cleanup, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import { AgentTaskProvider, useAgentTaskContext } from "./AgentTaskContext";
import AgentSidebar from "./AgentSidebar";
import type { ActivityPage } from "../../types/agentTask";
import * as api from "../../api/agentTasks";
import * as proposals from "../../api/d5Proposals";
vi.mock("../../api/d5Proposals",()=>({listD5Proposals:vi.fn(),listTaskD5Proposals:vi.fn(),listTaskD5Results:vi.fn(),listD5Measures:vi.fn(),checkpointProposals:vi.fn()}));
vi.mock("../../api/agentTasks", async () => ({
  ...await vi.importActual("../../api/agentTasks"),
  getTaskAvailability: vi.fn(),
  listTaskInstallations: vi.fn(),
  listTasks: vi.fn(),
  getTaskActivity: vi.fn(),
  createTask: vi.fn(),
  appendTaskMessage: vi.fn(),
  controlTask: vi.fn(),
  listModelDeployments: vi.fn(),
  getTaskWorkflow: vi.fn(),
  listTaskD5Checkpoints: vi.fn(),
  launchTask: vi.fn()
}));
vi.mock("./AgentTaskAttachments", () => ({
  default: ({ taskId }: { taskId: string }) => <div data-testid="task-attachments">附件任务 {taskId}</div>
}));
const a = "00000000-0000-4000-8000-000000000001", b = "00000000-0000-4000-8000-000000000002", run = "00000000-0000-4000-8000-000000000003";
const task = {
  task_id: a,
  target_capa_id: a,
  factory_id: a,
  preferred_installation_id: a,
  status: "ready" as const,
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z"
};
const bound = { ...task, model_deployment: { deployment_id: a, name: "模型甲", version: "1" } };
const page = {
  task_id: a,
  task_status: "ready" as const,
  run_id: run,
  run_status: "active" as const,
  lease_epoch: 3,
  window_end_sequence: 0,
  next_before_sequence: null,
  items: []
};
function TestPage({ report = a }: {
  report?: string;
}) {
  const ctx = useAgentTaskContext();
  const location = useLocation();
  return <>
    <button onClick={() => ctx?.beginCreate(report)}>创建 {report}</button>
    <button onClick={() => ctx?.selectTask(task)}>选择 A</button>
    <button onClick={() => ctx?.selectTask(bound)}>选择模型任务</button>
    <span>页面 {report}</span>
    <span>地址 {location.pathname}</span>
    <span>选中任务 {ctx?.selectedTask?.task_id ?? "无"}</span>
  </>;
}
function Harness({ report = a }: {
  report?: string;
}) {
  return <MemoryRouter>
    <AgentTaskProvider>
      <AgentSidebar />
      <TestPage report={report} />
    </AgentTaskProvider>
  </MemoryRouter>;
}
async function select() {
  await waitFor(() => expect(screen.getByRole("button", { name: "Agent 任务" })).toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: "选择 A" }));
  await screen.findByRole("region", { name: "任务对话" });
}
async function selectModel() {
  await screen.findByRole("button", { name: "Agent 任务" });
  fireEvent.click(screen.getByRole("button", { name: "选择模型任务" }));
  await waitFor(() => expect(screen.getByLabelText("追加指令")).toBeEnabled());
}
async function showDetails(model = false) {
  fireEvent.click(await screen.findByRole("button", { name: "任务详情" }));
  if (model) fireEvent.click(screen.getByText("建议与检查点", { selector: "summary" }));
}
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  localStorage.setItem("access_token", "jwt");
  useAuthStore.setState({ user: { user_id: "u1" } as any, token: "jwt", currentFactoryId: null, factoryScope: null });
  vi.mocked(api.getTaskAvailability).mockResolvedValue({ enabled: true });
  vi.mocked(api.listTasks).mockResolvedValue({
    items: [task],
    total: 1,
    page: 1,
    page_size: 20
  });
  vi.mocked(api.listTaskInstallations).mockResolvedValue({ items: [{ installation_id: a, plugin_key: "readonly", plugin_version: "1.0" }] });
  vi.mocked(proposals.listTaskD5Results).mockResolvedValue([]);
  vi.mocked(proposals.listTaskD5Proposals).mockResolvedValue({items:[{proposal_id:b,task_id:a,original_text:"旧建议",state:"pending",basis_current:true,can_adopt:true,can_withdraw:true,created_at:task.created_at}],total:1,page:1,page_size:20});
  vi.mocked(api.listTaskD5Checkpoints).mockResolvedValue({items:[],total:0,page:1,page_size:20});
  vi.mocked(proposals.listD5Measures).mockResolvedValue({legacy_text:null,items:[],total:0,page:1,page_size:20});
  vi.mocked(proposals.checkpointProposals).mockResolvedValue([]);
  vi.mocked(api.getTaskActivity).mockResolvedValue(page);
  vi.mocked(api.listModelDeployments).mockResolvedValue({items:[{deployment_id:a,name:"模型甲",version:"1",kind:"local"},{deployment_id:b,name:"模型乙",version:"2",kind:"cloud"}]});
  vi.mocked(api.getTaskWorkflow).mockResolvedValue({status:"waiting",question:"请补充",checkpoint_id:null});
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
describe("global user task sidebar", () => {
  it("stops task and workflow polling during an outage and reconnects on request", async () => {
    vi.useFakeTimers();
    let finishOldWorkflow!: (value: Awaited<ReturnType<typeof api.getTaskWorkflow>>) => void;
    const oldWorkflow = new Promise<Awaited<ReturnType<typeof api.getTaskWorkflow>>>(resolve => {
      finishOldWorkflow = resolve;
    });
    vi.mocked(api.getTaskActivity).mockReset().mockRejectedValue(new Error("connection interrupted"))
      .mockResolvedValueOnce(page);
    vi.mocked(api.getTaskWorkflow).mockReset().mockReturnValue(oldWorkflow)
      .mockResolvedValueOnce({ status: "waiting", question: "旧问题", checkpoint_id: null });
    render(<Harness />);
    await act(async () => {});
    fireEvent.click(screen.getByRole("button", { name: "选择模型任务" }));
    await act(async () => {});
    expect(screen.getByText("旧问题")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(api.getTaskWorkflow).toHaveBeenCalledTimes(2);
    const oldSignal = vi.mocked(api.getTaskWorkflow).mock.calls[1][1];

    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(screen.getByText("连接中断，重试中")).toBeInTheDocument();
    expect(screen.queryByText("旧问题")).toBeNull();
    await act(() => vi.advanceTimersByTimeAsync(10000));
    expect(screen.getByText("暂时无法连接任务服务")).toBeInTheDocument();
    expect(oldSignal?.aborted).toBe(true);
    await act(async () => {
      finishOldWorkflow({ status: "waiting", question: "迟到问题", checkpoint_id: null });
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(api.getTaskActivity).toHaveBeenCalledTimes(4);
    expect(api.getTaskWorkflow).toHaveBeenCalledTimes(2);

    vi.mocked(api.getTaskActivity).mockResolvedValue(page);
    vi.mocked(api.getTaskWorkflow).mockResolvedValue({ status: "waiting", question: "重新连接后的问题", checkpoint_id: null });
    fireEvent.click(screen.getByRole("button", { name: "重新连接" }));
    await act(async () => {});
    expect(api.getTaskActivity).toHaveBeenCalledTimes(5);
    expect(api.listTasks).toHaveBeenCalledTimes(2);
    expect(screen.getByText("重新连接后的问题")).toBeInTheDocument();
    expect(screen.queryByText("迟到问题")).toBeNull();
    expect(screen.queryByRole("button", { name: "重新连接" })).toBeNull();
  });
  it.each([401, 403, 404])("directory %s withdraws all activity immediately and ignores an outstanding old poll without a deny loop", async (status) => {
    vi.useFakeTimers();
    const restricted: ActivityPage = {
      ...page,
      window_end_sequence: 2,
      items: [
        {
          sequence: 1,
          kind: "message",
          created_at: task.created_at,
          data: {
            message_id: b,
            sequence: 1,
            author_id: a,
            content: "受限目录测试指令",
            data_class: "restricted",
            state: "received"
          },
        },
        {
          sequence: 2,
          kind: "result",
          created_at: task.created_at,
          data: {
            result_id: b,
            task_id: a,
            run_id: run,
            data_class: "restricted",
            payload: {
              explanations: ["受限目录测试结果"],
              support: [],
              opposition: [],
              missing_information: [],
              conditional_recommendations: []
            },
            sources: [{
              receipt_id: b,
              source_capa_id: a,
              projection_id: "capa.d4.summary.masked.v1",
              projection_digest: "a".repeat(64),
              data_class: "internal"
            }],
          },
        },
      ],
    };
    let resolveOld!: (value: ActivityPage) => void;
    const oldPoll = new Promise<ActivityPage>(resolve => {
      resolveOld = resolve;
    });
    let rejectDirectory!: (error: unknown) => void;
    const nextDirectory = new Promise<Awaited<ReturnType<typeof api.listTasks>>>((_, reject) => {
      rejectDirectory = reject;
    });
    vi.mocked(api.getTaskActivity).mockReset().mockResolvedValueOnce(restricted).mockReturnValueOnce(oldPoll);
    vi.mocked(api.listTasks).mockReset().mockRejectedValue({ response: { status } })
      .mockResolvedValueOnce({
        items: [task],
        total: 21,
        page: 1,
        page_size: 20
      }).mockReturnValueOnce(nextDirectory);
    render(<Harness />);
    await act(async () => {
      await Promise.resolve();
    });
    fireEvent.click(screen.getByRole("button", { name: "选择 A" }));
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText("受限目录测试指令")).toBeInTheDocument();
    expect(screen.getByText("受限目录测试结果")).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(api.getTaskActivity).toHaveBeenCalledTimes(2);
    const oldSignal = vi.mocked(api.getTaskActivity).mock.calls[1][2];
    fireEvent.click(screen.getByRole("button", { name: "下一页任务" }));
    await act(async () => {
      rejectDirectory({ response: { status } });
    });
    expect(screen.getByText("选中任务 无")).toBeInTheDocument();
    expect(screen.queryByText("受限目录测试指令")).toBeNull();
    expect(screen.queryByText("受限目录测试结果")).toBeNull();
    expect(screen.queryByRole("link", { name: `目标报告 ${a}` })).toBeNull();
    expect(screen.queryByRole("button", { name: "暂停" })).toBeNull();
    expect(screen.queryByRole("button", { name: "发送指令" })).toBeNull();
    expect(oldSignal?.aborted).toBe(true);
    await act(async () => {
      resolveOld(restricted);
      await Promise.resolve();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(screen.queryByText("受限目录测试指令")).toBeNull();
    expect(screen.queryByText("受限目录测试结果")).toBeNull();
    expect(api.getTaskActivity).toHaveBeenCalledTimes(2);
    expect(api.listTasks).toHaveBeenCalledTimes(3);
    expect(screen.getByRole("button", { name: "下一页任务" })).toBeDisabled();
  });
  it("mounts the selected task attachment panel after activity without changing runtime controls", async () => {
    render(<Harness />);
    await select();
    expect(screen.queryByTestId("task-attachments")).toBeNull();
    await showDetails();
    fireEvent.click(screen.getByText("任务附件", { selector: "summary" }));
    expect(screen.getByTestId("task-attachments")).toHaveTextContent(`附件任务 ${a}`);
    expect(screen.getByRole("button", { name: "暂停" })).toBeEnabled();
    expect(screen.queryByLabelText("追加指令")).toBeNull();
  });
  it("follows the fixed report link through SPA navigation and retains the selected task", async () => {
    render(<Harness />);
    await select();
    fireEvent.click(screen.getByRole("link", { name: `目标报告 ${a}` }));
    await waitFor(() => expect(screen.getByText(`地址 /capa/${a}`)).toBeInTheDocument());
    expect(screen.getByRole("link", { name: `目标报告 ${a}` })).toBeInTheDocument();
  });
  it("A target persists across B navigation and factory/PL selection; JWT refresh preserves selection", async () => {
    const view = render(<Harness />);
    await select();
    view.rerender(<Harness report={b} />);
    act(() => useAuthStore.setState({ currentFactoryId: b }));
    await screen.findByRole("link", { name: `目标报告 ${a}` });
    act(() => {
      localStorage.setItem("access_token", "jwt2");
      useAuthStore.setState({ token: "jwt2" });
    });
    await waitFor(() => expect(screen.getByRole("link", { name: `目标报告 ${a}` })).toBeInTheDocument());
    expect(api.getTaskAvailability).toHaveBeenCalledTimes(2);
  });
  it("paginates only the current user task directory while preserving selected task", async () => {
    vi.mocked(api.listTasks).mockResolvedValueOnce({
      items: [task],
      total: 21,
      page: 1,
      page_size: 20
    }).mockResolvedValueOnce({
      items: [{ ...task, task_id: b, target_capa_id: b }],
      total: 21,
      page: 2,
      page_size: 20
    });
    render(<Harness />);
    await select();
    await waitFor(() => expect(screen.getByRole("button", { name: "下一页任务" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "下一页任务" }));
    await waitFor(() => expect(screen.getByText("任务目录第 2 页")).toBeInTheDocument());
    expect(api.listTasks).toHaveBeenLastCalledWith({ page: 2, page_size: 20 }, expect.any(AbortSignal));
    expect(screen.getByRole("link", { name: `目标报告 ${a}` })).toBeInTheDocument();
  });
  it("same-user credential refresh reauthorizes a denied activity without losing the target", async () => {
    vi.mocked(api.getTaskActivity).mockRejectedValueOnce({ response: { status: 401 } }).mockResolvedValue(page);
    render(<Harness />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Agent 任务" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "选择 A" }));
    await waitFor(() => expect(screen.getByText("任务访问已失效")).toBeInTheDocument());
    expect(screen.queryByRole("link", { name: `目标报告 ${a}` })).toBeNull();
    act(() => {
      localStorage.setItem("access_token", "new-jwt");
      useAuthStore.setState({ token: "new-jwt" });
    });
    await waitFor(() => expect(screen.getByRole("link", { name: `目标报告 ${a}` })).toBeInTheDocument());
    expect(api.getTaskAvailability).toHaveBeenCalledTimes(1);
  });
  it("same-window tenant change is detected by bounded identity polling", async () => {
    render(<Harness />);
    await select();
    localStorage.setItem("tenant_slug", "other");
    await waitFor(() => expect(screen.queryByRole("link", { name: `目标报告 ${a}` })).toBeNull());
  });
  it("logout clears body and selection immediately", async () => {
    render(<Harness />);
    await select();
    act(() => useAuthStore.getState().logout());
    expect(screen.queryByRole("link", { name: `目标报告 ${a}` })).toBeNull();
    expect(screen.queryByRole("button", { name: "Agent 任务" })).toBeNull();
  });
  it("tenant storage change clears selected task before presenting old content", async () => {
    render(<Harness />);
    await select();
    act(() => {
      localStorage.setItem("tenant_slug", "other");
      window.dispatchEvent(new Event("storage"));
    });
    expect(screen.queryByRole("link", { name: `目标报告 ${a}` })).toBeNull();
  });
  it("404 availability hides task entry", async () => {
    vi.mocked(api.getTaskAvailability).mockRejectedValue({ response: { status: 404 } });
    render(<Harness />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.queryByRole("button", { name: "Agent 任务" })).toBeNull();
  });
  it("empty directory disables creation with explanation and no secret fields", async () => {
    vi.mocked(api.listTaskInstallations).mockResolvedValue({ items: [] });
    render(<Harness />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Agent 任务" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: `创建 ${a}` }));
    await waitFor(() => expect(screen.getByText("暂无适用于本报告的插件安装，无法创建任务。")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "创建任务" })).toBeDisabled();
    expect(screen.queryByLabelText(/secret|密钥/i)).toBeNull();
  });
  it("creates with exact immutable explicit report body", async () => {
    vi.mocked(api.createTask).mockResolvedValue(task);
    render(<Harness />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Agent 任务" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: `创建 ${a}` }));
    await waitFor(() => expect(screen.getByRole("button", { name: "创建任务" })).toBeEnabled());
    expect(screen.queryByLabelText("初始指令")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "创建任务" }));
    await waitFor(() => expect(api.createTask).toHaveBeenCalled());
    expect(api.createTask).toHaveBeenCalledWith({
      report_id: a,
      installation_id: a,
      request_key: expect.any(String),
      initial_text: "读取当前报告的 D4 元数据"
    }, expect.any(AbortSignal));
  });
  it("unconfirmed append retries same original body/key despite input changes; duplicate clicks prevented", async () => {
    let reject!: (e: unknown) => void;
    vi.mocked(api.appendTaskMessage).mockReturnValueOnce(new Promise((_, r) => {
      reject = r;
    })).mockResolvedValueOnce({ message_id: b, sequence: 1, state: "accepted" });
    render(<Harness />);
    await selectModel();
    fireEvent.change(screen.getByLabelText("追加指令"), { target: { value: "原始指令" } });
    fireEvent.click(screen.getByRole("button", { name: "补充给 模型甲" }));
    fireEvent.click(screen.getByRole("button", { name: "补充给 模型甲" }));
    expect(api.appendTaskMessage).toHaveBeenCalledTimes(1);
    await act(async () => reject(new Error("lost response")));
    fireEvent.click(screen.getByRole("button", { name: "重试发送原指令" }));
    await waitFor(() => expect(api.appendTaskMessage).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.appendTaskMessage).mock.calls[0][1]).toEqual(vi.mocked(api.appendTaskMessage).mock.calls[1][1]);
    expect(screen.getByRole("status")).toHaveTextContent("已确认接收");
  });
  it("control lost response retry preserves epoch/action/key; 409 refreshes current state and new command uses fresh epoch", async () => {
    vi.mocked(api.controlTask).mockRejectedValueOnce(new Error("lost")).mockRejectedValueOnce({ response: { status: 409 } }).mockResolvedValueOnce({
      control_id: b,
      task_id: a,
      task_status: "paused",
      run_id: run,
      run_status: "paused",
      lease_epoch: 5
    });
    render(<Harness />);
    await select();
    await showDetails();
    fireEvent.click(screen.getByRole("button", { name: "暂停" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "重试原控制操作" })).toBeInTheDocument());
    vi.mocked(api.getTaskActivity).mockResolvedValue({ ...page, lease_epoch: 4 });
    fireEvent.click(screen.getByRole("button", { name: "重试原控制操作" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("状态已变化，已刷新"));
    expect(vi.mocked(api.controlTask).mock.calls[0][1]).toEqual(vi.mocked(api.controlTask).mock.calls[1][1]);
    await waitFor(() => expect(screen.getByText("运行轮次 4")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "暂停" }));
    await waitFor(() => expect(api.controlTask).toHaveBeenCalledTimes(3));
    expect(vi.mocked(api.controlTask).mock.calls[2][1].expected_epoch).toBe(4);
    expect(vi.mocked(api.controlTask).mock.calls[2][1].idempotency_key).not.toBe(vi.mocked(api.controlTask).mock.calls[0][1].idempotency_key);
  });
});

it("keeps Enter addressed to bound A after selecting B; only explicit new task uses B", async () => {
  const bound = {...task, model_deployment:{deployment_id:a,name:"模型甲",version:"1"}};
  vi.mocked(api.listTasks).mockResolvedValue({items:[bound],total:1,page:1,page_size:20});
  vi.mocked(api.listTaskInstallations).mockResolvedValue({items:[{installation_id:a,plugin_key:"openqms.controlled-d5-model",plugin_version:"1"}]});
  vi.mocked(api.appendTaskMessage).mockResolvedValue({message_id:b,sequence:1,state:"accepted"});
  vi.mocked(api.createTask).mockResolvedValue({...bound,task_id:b,model_deployment:{deployment_id:b,name:"模型乙",version:"2"}});
  render(<Harness />);
  await select();
  fireEvent.change(screen.getByLabelText("选择任务"),{target:{value:a}});
  await waitFor(() => expect(screen.getByText("当前接收方：模型甲 · 1")).toBeInTheDocument());
  fireEvent.click(screen.getByRole("button",{name:`创建 ${a}`}));
  await waitFor(() => expect(screen.getByLabelText("新任务模型")).toBeEnabled());
  fireEvent.change(screen.getByLabelText("新任务模型"),{target:{value:b}});
  fireEvent.change(screen.getByLabelText("追加指令"),{target:{value:"继续甲"}});
  fireEvent.keyDown(screen.getByLabelText("追加指令"),{key:"Enter",code:"Enter"});
  await waitFor(() => expect(api.appendTaskMessage).toHaveBeenCalledWith(a,{content:"继续甲",idempotency_key:expect.any(String)},expect.any(AbortSignal)));
  fireEvent.change(screen.getByLabelText("初始指令"),{target:{value:"新任务乙"}});
  fireEvent.click(screen.getByRole("button",{name:"用 模型乙 · 2 开始新任务（自由对话）"}));
  await waitFor(() => expect(api.createTask).toHaveBeenCalledWith(expect.objectContaining({model_deployment_id:b,initial_text:"新任务乙"}),expect.any(AbortSignal)));
});
it("polls model questions and accepts supplement while launch is pending",async()=>{
  vi.mocked(api.getTaskActivity).mockResolvedValue({...page,run_status:"pending"});
  vi.mocked(api.listTasks).mockResolvedValue({items:[{...task,model_deployment:{deployment_id:a,name:"模型甲",version:"1"}}],total:1,page:1,page_size:20});
  vi.mocked(api.launchTask).mockReturnValue(new Promise(()=>{}));
  render(<Harness />); await select();
  fireEvent.change(screen.getByLabelText("选择任务"),{target:{value:a}});
  fireEvent.click(await screen.findByRole("button",{name:"启动模型任务"}));
  await waitFor(()=>expect(api.launchTask).toHaveBeenCalledTimes(1));
  expect(await screen.findByText("请补充")).toBeInTheDocument();
  expect(screen.getByLabelText("追加指令")).toBeEnabled();
});
it('sends correction only as explicit source-free intent for a current-task pending proposal',async()=>{
  vi.mocked(api.listTasks).mockResolvedValue({items:[{...task,model_deployment:{deployment_id:a,name:'模型甲',version:'1'}}],total:1,page:1,page_size:20});
  render(<Harness />); await select();
  fireEvent.change(screen.getByLabelText('选择任务'),{target:{value:a}});
  await showDetails(true);
  fireEvent.change(await screen.findByLabelText('更正当前任务建议'),{target:{value:b}});
  fireEvent.click(screen.getByRole('button',{name:'明确更正选中建议'}));
  await waitFor(()=>expect(api.appendTaskMessage).toHaveBeenCalledWith(a,{content:JSON.stringify({intent:'replace_d5',predecessor_id:b}),idempotency_key:expect.any(String)},expect.any(AbortSignal)));
});
it('discards late model options after changing the creation report',async()=>{
  let resolve!: (v:any)=>void;
  vi.mocked(api.listModelDeployments).mockReturnValueOnce(new Promise(r=>{resolve=r})).mockResolvedValue({items:[]});
  vi.mocked(api.listTaskInstallations).mockResolvedValue({items:[{installation_id:a,plugin_key:'openqms.controlled-d5-model',plugin_version:'1'}]});
  const view=render(<Harness />);
  await waitFor(()=>expect(screen.getByRole('button',{name:'Agent 任务'})).toBeInTheDocument());
  fireEvent.click(screen.getByRole('button',{name:`创建 ${a}`}));
  await waitFor(()=>expect(api.listModelDeployments).toHaveBeenCalledTimes(1));
  view.rerender(<Harness report={b}/>);
  fireEvent.click(screen.getByRole('button',{name:`创建 ${b}`}));
  await act(async()=>resolve({items:[{deployment_id:a,name:'迟到旧模型',version:'1',kind:'local'}]}));
  expect(screen.queryByText(/迟到旧模型/)).toBeNull();
  expect(screen.getByRole('button',{name:'用 所选模型 开始新任务（自由对话）'})).toBeDisabled();
});
it('clears an old model question on workflow denial without switching recipients',async()=>{
  vi.mocked(api.listTasks).mockResolvedValue({items:[{...task,model_deployment:{deployment_id:a,name:'模型甲',version:'1'}}],total:1,page:1,page_size:20});
  vi.mocked(api.getTaskWorkflow).mockResolvedValueOnce({status:'waiting',question:'受限旧问题',checkpoint_id:null}).mockRejectedValue({response:{status:403}});
  render(<Harness />);await select();
  fireEvent.change(screen.getByLabelText('选择任务'),{target:{value:a}});
  await screen.findByText('受限旧问题');
  await waitFor(()=>expect(screen.queryByText('受限旧问题')).toBeNull(),{timeout:2500});
  expect(screen.getByText('当前接收方：模型甲 · 1')).toBeInTheDocument();
  expect(screen.getByLabelText('追加指令')).toBeDisabled();
  expect(api.launchTask).not.toHaveBeenCalled();
});
it('explicit source-free start uses selected approved model without rewriting free initial text',async()=>{
  vi.mocked(api.listTaskInstallations).mockResolvedValue({items:[{installation_id:a,plugin_key:'openqms.controlled-d5-model',plugin_version:'1'}]});
  vi.mocked(api.createTask).mockReturnValue(new Promise(()=>{}));
  render(<Harness />);
  await waitFor(()=>expect(screen.getByRole('button',{name:'Agent 任务'})).toBeInTheDocument());
  fireEvent.click(screen.getByRole('button',{name:`创建 ${a}`}));
  fireEvent.change(await screen.findByLabelText('新任务模型'),{target:{value:b}});
  fireEvent.change(screen.getByLabelText('初始指令'),{target:{value:'保留自由输入'}});
  fireEvent.click(screen.getByRole('button',{name:'用 模型乙 · 2 开始新任务（仅根据当前根因）'}));
  await waitFor(()=>expect(api.createTask).toHaveBeenCalledWith({report_id:a,installation_id:a,model_deployment_id:b,request_key:expect.any(String),initial_text:'deliver_d4_root_cause_candidate_v1'},expect.any(AbortSignal)));
  expect(screen.getByLabelText('初始指令')).toHaveValue('保留自由输入');
});
it('does not offer another launch while the current server run is active',async()=>{
  vi.mocked(api.listTasks).mockResolvedValue({items:[{...task,model_deployment:{deployment_id:a,name:'模型甲',version:'1'}}],total:1,page:1,page_size:20});
  render(<Harness />);await select();
  fireEvent.change(screen.getByLabelText('选择任务'),{target:{value:a}});
  expect(await screen.findByRole('button',{name:'启动模型任务'})).toBeDisabled();
});

it('names the bound recipient on the normal send action',async()=>{
  vi.mocked(api.listTasks).mockResolvedValue({items:[{...task,model_deployment:{deployment_id:a,name:'模型甲',version:'1'}}],total:1,page:1,page_size:20});
  render(<Harness/>);await select();
  fireEvent.change(screen.getByLabelText('选择任务'),{target:{value:a}});
  expect(await screen.findByRole('button',{name:'补充给 模型甲'})).toBeInTheDocument();
});
it('allows explicitly choosing an earlier checkpoint instead of silently using latest workflow checkpoint',async()=>{
  vi.mocked(api.listTasks).mockResolvedValue({items:[{...task,model_deployment:{deployment_id:a,name:'模型甲',version:'1'}}],total:1,page:1,page_size:20});
  vi.mocked(api.listTaskD5Checkpoints).mockResolvedValue({items:[{checkpoint_id:b,run_id:run,created_at:task.created_at}],total:1,page:1,page_size:20});
  vi.mocked(api.getTaskWorkflow).mockResolvedValue({status:'waiting',question:'当前问题',checkpoint_id:run});
  render(<Harness/>);await select();
  fireEvent.change(screen.getByLabelText('选择任务'),{target:{value:a}});
  await showDetails(true);
  fireEvent.change(await screen.findByLabelText('选择处理范围检查点'),{target:{value:b}});
  await waitFor(()=>expect(proposals.checkpointProposals).toHaveBeenCalledWith(a,b,expect.any(AbortSignal)));
  expect(screen.getByLabelText('选择处理范围检查点')).toHaveValue(b);
});

it('pages current-task pending correction choices rather than being trapped by the first report page',async()=>{
  vi.mocked(api.listTasks).mockResolvedValue({items:[{...task,model_deployment:{deployment_id:a,name:'模型甲',version:'1'}}],total:1,page:1,page_size:20});
  const current=(id:string)=>({proposal_id:id,task_id:a,original_text:'current',state:'pending' as const,basis_current:true,can_adopt:true,can_withdraw:true,created_at:task.created_at});
  vi.mocked(proposals.listD5Proposals).mockResolvedValue({items:Array.from({length:20},(_,i)=>({...current(`old-${i}`),task_id:'other-task'})),total:41,page:1,page_size:20});
  vi.mocked(proposals.listTaskD5Proposals).mockImplementation(async(_report,_task,page)=>({items:page===2?[current(b)]:Array.from({length:20},(_,i)=>current(`current-${i}`)),total:21,page:page??1,page_size:20}));
  render(<Harness/>);await select();
  fireEvent.change(screen.getByLabelText('选择任务'),{target:{value:a}});
  await showDetails(true);
  fireEvent.click(await screen.findByRole('button',{name:'下一页待更正建议'}));
  await waitFor(()=>expect(proposals.listTaskD5Proposals).toHaveBeenLastCalledWith(a,a,2,expect.any(AbortSignal)));
  fireEvent.change(screen.getByLabelText('更正当前任务建议'),{target:{value:b}});
  fireEvent.click(screen.getByRole('button',{name:'明确更正选中建议'}));
  await waitFor(()=>expect(api.appendTaskMessage).toHaveBeenCalledWith(a,{content:JSON.stringify({intent:'replace_d5',predecessor_id:b}),idempotency_key:expect.any(String)},expect.any(AbortSignal)));
});

it("keeps IME confirmation and Shift+Enter in the draft, then sends a single multiline message", async () => {
  vi.mocked(api.appendTaskMessage).mockResolvedValue({ message_id: b, sequence: 1, state: "queued" });
  render(<Harness />);
  await selectModel();
  const input = screen.getByLabelText("追加指令");
  fireEvent.compositionStart(input);
  fireEvent.change(input, { target: { value: "压装异常" } });
  expect(fireEvent.keyDown(input, { key: "Enter", isComposing: false })).toBe(true);
  fireEvent.compositionEnd(input);
  expect(fireEvent.keyDown(input, { key: "Enter", keyCode: 229 })).toBe(true);
  expect(fireEvent.keyDown(input, { key: "Enter", shiftKey: true })).toBe(true);
  expect(api.appendTaskMessage).not.toHaveBeenCalled();

  fireEvent.change(input, { target: { value: "压装异常\n下午补充数据" } });
  expect(fireEvent.keyDown(input, { key: "Enter" })).toBe(false);
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("消息排队中"));
  expect(api.appendTaskMessage).toHaveBeenCalledExactlyOnceWith(
    a, { content: "压装异常\n下午补充数据", idempotency_key: expect.any(String) }, expect.any(AbortSignal),
  );
});

it("discards a late workflow and an unconfirmed append when switching tasks", async () => {
  const other = { ...bound, task_id: b, target_capa_id: b, model_deployment: { deployment_id: b, name: "模型乙", version: "2" } };
  vi.mocked(api.listTasks).mockResolvedValue({ items: [bound, other], total: 2, page: 1, page_size: 20 });
  vi.mocked(api.getTaskActivity).mockImplementation(async id => ({ ...page, task_id: id }));
  let finishAppend!: (value: Awaited<ReturnType<typeof api.appendTaskMessage>>) => void;
  let finishWorkflow!: (value: Awaited<ReturnType<typeof api.getTaskWorkflow>>) => void;
  vi.mocked(api.appendTaskMessage).mockReturnValue(new Promise(resolve => { finishAppend = resolve; }));
  vi.mocked(api.getTaskWorkflow).mockResolvedValueOnce({ status: "running", question: null, checkpoint_id: null })
    .mockImplementation(id => id === a
      ? new Promise(resolve => { finishWorkflow = resolve; })
      : Promise.resolve({ status: "waiting", question: "乙的问题", checkpoint_id: null }));
  render(<Harness />);
  await selectModel();
  const input = screen.getByLabelText("追加指令");
  fireEvent.change(input, { target: { value: "甲的草稿" } });
  fireEvent.keyDown(input, { key: "Enter" });
  await waitFor(() => expect(finishWorkflow).toBeDefined(), { timeout: 2000 });
  const oldSignal = vi.mocked(api.appendTaskMessage).mock.calls[0][2];
  const oldPoll = vi.mocked(api.getTaskWorkflow).mock.calls.slice().reverse().find(call => call[0] === a);
  fireEvent.change(screen.getByLabelText("选择任务"), { target: { value: b } });
  await screen.findByText("乙的问题");
  expect(oldSignal?.aborted).toBe(true);
  expect(oldPoll?.[1]?.aborted).toBe(true);
  await act(async () => {
    finishAppend({ message_id: a, sequence: 1, state: "accepted" });
    finishWorkflow({ status: "waiting", question: "甲的迟到问题", checkpoint_id: null });
  });
  expect(screen.queryByText("甲的迟到问题")).toBeNull();
  expect(screen.queryByText("消息已确认接收。")).toBeNull();
  expect(screen.getByLabelText("追加指令")).toHaveValue("");
});

it("keeps a reauthorized task selected after a factory change but clears its old draft", async () => {
  render(<Harness />);
  await selectModel();
  fireEvent.change(screen.getByLabelText("追加指令"), { target: { value: "上一工厂的草稿" } });
  const oldPoll = vi.mocked(api.getTaskWorkflow).mock.calls[0][1];
  act(() => useAuthStore.setState({ currentFactoryId: b }));
  await waitFor(() => expect(screen.getByLabelText("追加指令")).toBeEnabled());
  expect(oldPoll?.aborted).toBe(true);
  expect(screen.getByLabelText("追加指令")).toHaveValue("");
});

it.each(["completed", "cancelled", "failed"] as const)("renders %s model conversations read-only", async task_status => {
  vi.mocked(api.getTaskActivity).mockResolvedValue({ ...page, task_status });
  render(<Harness />);
  await screen.findByRole("button", { name: "Agent 任务" });
  fireEvent.click(screen.getByRole("button", { name: "选择模型任务" }));
  const input = await screen.findByLabelText("追加指令");
  expect(input).toBeDisabled();
  fireEvent.keyDown(input, { key: "Enter" });
  expect(screen.getByRole("button", { name: "补充给 模型甲" })).toBeDisabled();
  expect(api.appendTaskMessage).not.toHaveBeenCalled();
});

it("places server questions between employee turns and ignores runtime progress as a reply", async () => {
  const timeline: ActivityPage = {
    ...page, window_end_sequence: 3,
    items: [
      { kind: "message", sequence: 1, created_at: "2026-10-01T00:00:01Z",
        data: { message_id: a, sequence: 1, author_id: a, state: "received", content: "开始", data_class: "restricted" } },
      { kind: "event", sequence: 2, created_at: "2026-10-01T00:00:02Z",
        data: { event_id: b, task_id: a, run_id: run, event_type: "progress", presentation_code: "plugin_running",
          created_at: "2026-10-01T00:00:02Z", sources: [] } },
      { kind: "message", sequence: 3, created_at: "2026-10-01T00:00:04Z",
        data: { message_id: b, sequence: 2, author_id: a, state: "claimed", content: "继续", data_class: "restricted" } },
    ],
  };
  vi.mocked(api.getTaskActivity).mockResolvedValue(timeline);
  vi.mocked(api.getTaskWorkflow).mockResolvedValue({
    status: "running", question: null, checkpoint_id: null, run_id: run, lease_epoch: 3,
    questions: [{ question_id: run, text: "请核对班次", created_at: "2026-10-01T00:00:03Z" }],
  });
  render(<Harness />);
  await selectModel();
  const conversation = within(screen.getByRole("region", { name: "任务对话" }));
  const rows = conversation.getAllByRole("listitem");
  expect(rows).toHaveLength(3);
  expect(rows[0]).toHaveTextContent("我");
  expect(rows[0]).toHaveTextContent("已确认接收");
  expect(rows[1]).toHaveTextContent("请核对班次");
  expect(rows[2]).toHaveTextContent("已领取");
  expect(conversation.queryByText("插件报告运行中")).toBeNull();
});

it("keeps the creation request for another report when the current model is revoked", async () => {
  let revoke!: (reason: unknown) => void;
  let finishCreate!: (value: Awaited<ReturnType<typeof api.createTask>>) => void;
  vi.mocked(api.getTaskWorkflow)
    .mockResolvedValueOnce({ status: "running", question: null, checkpoint_id: null })
    .mockImplementation(() => new Promise((_, reject) => { revoke = reject; }));
  vi.mocked(api.createTask).mockReturnValue(new Promise(resolve => { finishCreate = resolve; }));
  vi.mocked(api.getTaskActivity).mockImplementation(async id => ({ ...page, task_id: id }));
  render(<Harness report={b} />);
  await selectModel();
  fireEvent.click(screen.getByRole("button", { name: `创建 ${b}` }));
  const create = await screen.findByRole("button", { name: "创建任务" });
  await waitFor(() => expect(create).toBeEnabled());
  fireEvent.click(create);
  const signal = vi.mocked(api.createTask).mock.calls[0][1];
  await waitFor(() => expect(revoke).toBeDefined(), { timeout: 2000 });
  await act(async () => revoke({ response: { status: 403 } }));
  expect(signal?.aborted).toBe(false);
  await act(async () => finishCreate({ ...task, task_id: b, target_capa_id: b }));
  expect(await screen.findByRole("link", { name: `目标报告 ${b}` })).toBeInTheDocument();
});

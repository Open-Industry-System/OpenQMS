import { render, screen, fireEvent, act, waitFor, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import { AgentTaskProvider, useAgentTaskContext } from "./AgentTaskContext";
import AgentSidebar from "./AgentSidebar";
import type { ActivityPage } from "../../types/agentTask";
import * as api from "../../api/agentTasks";
import * as proposals from "../../api/d5Proposals";
vi.mock('../../api/fmea',()=>({listFMEAs:vi.fn().mockImplementation(async()=>({items:[{fmea_id:a,title:'已授权FMEA',document_no:'F-1'}],total:1,page:1,page_size:20})),getFMEA:vi.fn().mockResolvedValue({graph_data:{nodes:[{id:'cause-A',type:'FailureCause',name:'磨损'}]}})}));
vi.mock("../../api/d5Proposals",()=>({listD5Proposals:vi.fn(),listTaskD5Proposals:vi.fn(),listD5Measures:vi.fn(),checkpointProposals:vi.fn()}));
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
  await waitFor(() => expect(screen.getByRole("button", { name: "暂停" })).toBeEnabled());
}
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  localStorage.setItem("access_token", "jwt");
  useAuthStore.setState({ user: { user_id: "u1" } as any, token: "jwt" });
  vi.mocked(api.getTaskAvailability).mockResolvedValue({ enabled: true });
  vi.mocked(api.listTasks).mockResolvedValue({
    items: [task],
    total: 1,
    page: 1,
    page_size: 20
  });
  vi.mocked(api.listTaskInstallations).mockResolvedValue({ items: [{ installation_id: a, plugin_key: "readonly", plugin_version: "1.0" }] });
  vi.mocked(proposals.listTaskD5Proposals).mockResolvedValue({items:[{proposal_id:b,task_id:a,original_text:"旧建议",state:"pending",basis_current:true,can_adopt:true,can_withdraw:true,created_at:task.created_at}],total:1,page:1,page_size:20});
  vi.mocked(api.listTaskD5Checkpoints).mockResolvedValue({items:[],total:0,page:1,page_size:20});
  vi.mocked(proposals.listD5Measures).mockResolvedValue({legacy_text:null,items:[],total:0,page:1,page_size:20});
  vi.mocked(proposals.checkpointProposals).mockResolvedValue([]);
  vi.mocked(api.getTaskActivity).mockResolvedValue(page);
  vi.mocked(api.listModelDeployments).mockResolvedValue({items:[{deployment_id:a,name:"模型甲",version:"1",kind:"local",profile:"model_d5_proposal_r6_v1"},{deployment_id:b,name:"模型乙",version:"2",kind:"cloud",profile:"model_d5_proposal_r6_v1"}]});
  vi.mocked(api.getTaskWorkflow).mockResolvedValue({status:"waiting",question:"请补充",checkpoint_id:null});
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
describe("global user task sidebar", () => {
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
    expect(screen.getByRole("button", { name: "暂停" })).toBeEnabled();
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
    expect(screen.getByTestId("task-attachments")).toHaveTextContent(`附件任务 ${a}`);
    expect(screen.getByRole("button", { name: "暂停" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "发送指令" })).toBeDisabled();
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
    await waitFor(()=>expect(screen.getByRole("link", { name: `目标报告 ${a}` })).toBeInTheDocument());
    act(() => {
      localStorage.setItem("access_token", "jwt2");
      useAuthStore.setState({ token: "jwt2" });
    });
    await waitFor(() => expect(screen.getByRole("link", { name: `目标报告 ${a}` })).toBeInTheDocument());
    expect(api.getTaskAvailability).toHaveBeenCalledTimes(1);
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
    await waitFor(() => expect(screen.getByLabelText("初始指令")).toBeEnabled());
    fireEvent.change(screen.getByLabelText("初始指令"), { target: { value: "读取事实" } });
    fireEvent.click(screen.getByRole("button", { name: "创建任务" }));
    await waitFor(() => expect(api.createTask).toHaveBeenCalled());
    expect(api.createTask).toHaveBeenCalledWith({
      report_id: a,
      installation_id: a,
      request_key: expect.any(String),
      initial_text: "读取事实"
    }, expect.any(AbortSignal));
  });
  it("unconfirmed append retries same original body/key despite input changes; duplicate clicks prevented", async () => {
    let reject!: (e: unknown) => void;
    vi.mocked(api.appendTaskMessage).mockReturnValueOnce(new Promise((_, r) => {
      reject = r;
    })).mockResolvedValueOnce({ message_id: b, sequence: 1, state: "accepted" });
    render(<Harness />);
    await select();
    fireEvent.change(screen.getByLabelText("追加指令"), { target: { value: "原始指令" } });
    fireEvent.click(screen.getByRole("button", { name: "发送指令" }));
    fireEvent.click(screen.getByRole("button", { name: "发送指令" }));
    expect(api.appendTaskMessage).toHaveBeenCalledTimes(1);
    await act(async () => reject(new Error("lost response")));
    fireEvent.click(screen.getByRole("button", { name: "重试发送原指令" }));
    await waitFor(() => expect(api.appendTaskMessage).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.appendTaskMessage).mock.calls[0][1]).toEqual(vi.mocked(api.appendTaskMessage).mock.calls[1][1]);
    expect(screen.getByRole("status")).toHaveTextContent("指令已入队");
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
  fireEvent.click(await screen.findByRole('button',{name:'下一页待更正建议'}));
  await waitFor(()=>expect(proposals.listTaskD5Proposals).toHaveBeenLastCalledWith(a,a,2,expect.any(AbortSignal)));
  fireEvent.change(screen.getByLabelText('更正当前任务建议'),{target:{value:b}});
  fireEvent.click(screen.getByRole('button',{name:'明确更正选中建议'}));
  await waitFor(()=>expect(api.appendTaskMessage).toHaveBeenCalledWith(a,{content:JSON.stringify({intent:'replace_d5',predecessor_id:b}),idempotency_key:expect.any(String)},expect.any(AbortSignal)));
});

it('separates D4 analysis creation using only server-approved D4 profile and fixed source-neutral intent',async()=>{
 vi.mocked(api.listTaskInstallations).mockResolvedValue({items:[{installation_id:a,plugin_key:'openqms.controlled-d5-model',plugin_version:'1'}]});
 vi.mocked(api.listModelDeployments).mockResolvedValue({items:[{deployment_id:b,name:'D4候选模型',version:'1',kind:'cloud',profile:'model_d4_candidate_v1'}]});
 vi.mocked(api.createTask).mockReturnValue(new Promise(()=>{}));
 render(<Harness/>);await screen.findByRole('button',{name:'Agent 任务'});fireEvent.click(screen.getByRole('button',{name:`创建 ${a}`}));
 fireEvent.change(await screen.findByLabelText('新任务类型'),{target:{value:'d4'}});
 fireEvent.change(screen.getByLabelText('新任务模型'),{target:{value:b}});
 fireEvent.change(await screen.findByLabelText('D4 输入 FMEA'),{target:{value:a}});
 fireEvent.change(await screen.findByLabelText('D4 输入原因节点'),{target:{value:'cause-A'}});
 fireEvent.click(screen.getByRole('button',{name:'开始 D4 根因分析候选任务'}));
 await waitFor(()=>expect(api.createTask).toHaveBeenCalledWith({report_id:a,installation_id:a,model_deployment_id:b,request_key:expect.any(String),initial_text:'deliver_d4_root_cause_candidate_v1',derived_source_scope:{target_report_id:a,fmea_id:a,cause_node_id:'cause-A'}},expect.any(AbortSignal)));
 expect(screen.getByText(/新增事实请先维护 D2\/D3\/FMEA/)).toBeInTheDocument();
});

it('offers only complete-source R6 D5 deployments for new D5 tasks',async()=>{
 vi.mocked(api.listTaskInstallations).mockResolvedValue({items:[{installation_id:a,plugin_key:'openqms.controlled-d5-model',plugin_version:'1'}]});
 vi.mocked(api.listModelDeployments).mockResolvedValue({items:[{deployment_id:a,name:'旧版部署',version:'1',kind:'cloud',profile:'model_d5_proposal_v1'},{deployment_id:b,name:'完整来源部署',version:'2',kind:'cloud',profile:'model_d5_proposal_r6_v1'}]});
 render(<Harness/>);await screen.findByRole('button',{name:'Agent 任务'});fireEvent.click(screen.getByRole('button',{name:`创建 ${a}`}));
 const picker=await screen.findByLabelText('新任务模型');
 await waitFor(()=>expect(picker).toHaveTextContent('完整来源部署'));
 expect(picker).not.toHaveTextContent('旧版部署');
});

it('never paints a late FMEA cause from a previous creation report',async()=>{
 const fmea=await import('../../api/fmea');let resolve!:(v:any)=>void;
 vi.mocked(fmea.getFMEA).mockReturnValueOnce(new Promise(r=>resolve=r));
 vi.mocked(api.listTaskInstallations).mockResolvedValue({items:[{installation_id:a,plugin_key:'openqms.controlled-d5-model',plugin_version:'1'}]});
 const view=render(<Harness/>);await screen.findByRole('button',{name:'Agent 任务'});fireEvent.click(screen.getByRole('button',{name:`创建 ${a}`}));
 fireEvent.change(await screen.findByLabelText('新任务类型'),{target:{value:'d4'}});
 fireEvent.change(await screen.findByLabelText('D4 输入 FMEA'),{target:{value:a}});
 await waitFor(()=>expect(fmea.getFMEA).toHaveBeenCalled());
 view.rerender(<Harness report={b}/>);fireEvent.click(screen.getByRole('button',{name:`创建 ${b}`}));
 await act(async()=>resolve({graph_data:{nodes:[{id:'old-cause',type:'FailureCause',name:'旧报告受限原因'}]}}));
 expect(screen.queryByText('旧报告受限原因')).toBeNull();
 expect(screen.getByLabelText('D4 输入原因节点')).toHaveValue('');
});

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { InvestigationFacts, InvestigationResult } from "../../api/iqcInvestigations";
import i18n from "../../i18n";
import { useAuthStore } from "../../store/authStore";
import IqcInvestigationDrawer, { IqcInvestigationPanel } from "./IqcInvestigationPanel";

const api = vi.hoisted(() => ({
  context: vi.fn(), list: vi.fn(), create: vi.fn(), launch: vi.fn(), result: vi.fn(),
}));

vi.mock("../../api/iqcInvestigations", () => ({ iqcInvestigations: api }));

const facts: InvestigationFacts = {
  inspection_id: "inspection-a", inspection_no: "IQC-500", inspection_revision: 2,
  product_line_code: "LINE-A", part_no: "AX-10", part_name: "定位轴", lot_no: "B45",
  lot_qty: 100, sample_qty: 10, defect_qty: 2, defect_description: "外径超上限",
  aql_level: "2.5", accept_number: 1, reject_number: 2,
  inspection_result: "rejected", status: "judged", inspection_date: "2026-11-18",
  judged_at: "2026-11-18T09:50:00Z", parent_inspection_id: null, family_complete: true, family: [],
};

const linkedId = "0cde87f4-c014-4be6-bc9a-72dfd9bfa41c";
const card: InvestigationResult = {
  result_id: "same-result", task_id: "task-a", created_at: "2026-11-18T09:50:00Z", stale: false,
  card: {
    action: "consider_new", facts, missing: ["supplier_information_unavailable"],
    next_steps: ["confirm_sample_extent"], d2: "AX-10 的批次 B45 抽检发现外径超上限。",
    evidence: [{ receipt_id: "e1", projection: "iqc.inspection.items.v1", version: "v1", data: {
      rows: [{ item_name: "直径", spec_upper: 15, measured_value: 15.3 }],
    } }],
  },
  current_hint: { action: "consider_new", checked_modules: ["capa"], investigations: [] },
};

const authBefore = useAuthStore.getState();
const completedTask = { task_id: card.task_id, status: "completed", result_id: card.result_id };
const preparedContext = {
  inspection_id: facts.inspection_id, expected_version: "revision-2", eligible: true, facts,
  deployments: [{ deployment_id: "model-a", name: "Approved", version: "r1" }],
};

async function openHistory() {
  fireEvent.click(await screen.findByRole("button", { name: "查看建议" }));
}

function renderPanel() {
  return render(<MemoryRouter>
    <IqcInvestigationPanel scopeKey="tenant/employee" credentialsCurrent={() => true} inspectionId={facts.inspection_id} />
  </MemoryRouter>);
}

describe("IQC investigation sidebar", () => {
  beforeEach(async () => {
    vi.resetAllMocks();
    useAuthStore.setState(authBefore);
    await i18n.changeLanguage("zh-CN");
    api.context.mockResolvedValue(preparedContext);
    api.list.mockResolvedValue({ items: [completedTask] });
    api.result.mockResolvedValue(card);
  });

  it("reuses the same fixed create request after an uncertain failure and launches the created task", async () => {
    api.list.mockResolvedValue({ items: [] });
    api.create.mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce({ task_id: "new-task", status: "ready" });
    api.launch.mockResolvedValue({ task_id: "new-task", status: "queued" });
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: "准备调查" }));
    await screen.findByText("操作暂未完成，请重试。");
    fireEvent.click(await screen.findByRole("button", { name: "准备调查" }));
    await waitFor(() => expect(api.launch).toHaveBeenCalledTimes(1));
    const first = api.create.mock.calls[0][1];
    expect(api.create.mock.calls[1][1]).toEqual(first);
    expect(first).toEqual({
      expected_version: "revision-2", model_deployment_id: "model-a", request_key: expect.any(String),
    });
    expect(api.launch).toHaveBeenCalledWith(facts.inspection_id, "new-task", expect.any(AbortSignal));
    expect(screen.getByRole("combobox", { name: "已批准模型部署" })).toBeInTheDocument();
  });

  it("reads the same result as each employee and replaces current guidance without changing original advice", async () => {
    api.context.mockResolvedValue({ ...preparedContext, eligible: false });
    api.result.mockResolvedValueOnce({
      ...card,
      current_hint: {
        action: "supplement_existing", checked_modules: ["capa", "scar"],
        investigations: [{
          kind: "capa", object_id: linkedId, number: "8D-884", status: "open", summary: "关联调查",
        }],
      },
    });
    render(<MemoryRouter><IqcInvestigationDrawer inspectionId={facts.inspection_id} /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "调查建议" }));
    await openHistory();
    expect(await screen.findByText("查看或补充已有调查。")).toBeInTheDocument();
    expect(screen.getByText(/生成时的调查建议：已核范围内可考虑新建调查/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /8D-884/ })).toHaveAttribute("href", `/capa/${linkedId}`);
    expect(screen.queryByRole("button", { name: "准备调查" })).toBeNull();

    act(() => useAuthStore.setState({ token: "another-employee-session" }));
    expect(screen.queryByText("关联调查")).toBeNull();
    fireEvent.click(await screen.findByRole("button", { name: "调查建议" }));
    await openHistory();
    expect(await screen.findByText("已核范围内可考虑新建调查。")).toBeInTheDocument();
    expect(screen.queryByText("关联调查")).toBeNull();
    expect(screen.getByText(/生成时的调查建议：已核范围内可考虑新建调查/)).toBeInTheDocument();
    expect(api.result.mock.calls.map(args => args.slice(0, 3))).toEqual([
      [facts.inspection_id, card.task_id, card.result_id], [facts.inspection_id, card.task_id, card.result_id],
    ]);
  });

  it("discards a late authorized response when the inspection changes", async () => {
    let resolve!: (value: InvestigationResult) => void;
    api.result.mockReturnValueOnce(new Promise(done => { resolve = done; }));
    const view = render(<MemoryRouter><IqcInvestigationDrawer inspectionId={facts.inspection_id} /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "调查建议" }));
    await openHistory();
    await waitFor(() => expect(api.result).toHaveBeenCalledOnce());
    api.context.mockResolvedValue({ ...preparedContext, inspection_id: "inspection-b" });
    api.list.mockResolvedValue({ items: [] });
    view.rerender(<MemoryRouter><IqcInvestigationDrawer inspectionId="inspection-b" /></MemoryRouter>);
    await act(async () => resolve(card));
    expect(api.result.mock.calls[0][3].aborted).toBe(true);
    expect(screen.queryByText(card.card.d2!)).toBeNull();
    expect(screen.queryByText("当前操作提示")).toBeNull();
  });

  it("reauthorizes clipboard access and withdraws the old card on denial", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    api.result.mockResolvedValueOnce(card).mockRejectedValueOnce({ response: { status: 403 } });
    renderPanel();
    await openHistory();
    const region = await screen.findByRole("region", { name: "调查建议卡" });
    fireEvent.click(within(region).getByRole("button", { name: "复制 D2 草稿" }));
    await screen.findByText("当前无法读取调查建议。");
    expect(writeText).not.toHaveBeenCalled();
    expect(screen.queryByText(card.card.d2!)).toBeNull();
    expect(screen.queryByText("当前操作提示")).toBeNull();
    expect(api.result).toHaveBeenCalledTimes(2);
  });
});

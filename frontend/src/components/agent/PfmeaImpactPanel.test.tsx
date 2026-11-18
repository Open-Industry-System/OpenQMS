import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import i18n from "../../i18n";
import PfmeaImpactPanel, { type ImpactRecommendation, type PfmeaImpactClients } from "./PfmeaImpactPanel";

const target = {
  fmeaId: "fmea-a", documentNo: "PF-020", title: "OP40 assembly",
  approvedVersionId: "approved-3", approvedVersionLabel: "v3.0", hasUnapprovedRevision: true,
};

const recommendation: ImpactRecommendation = {
  reportVersionLabel: "D4 rev 8", approvedVersionLabel: "v3.0", freshness: "stale",
  conclusion: "impact_found",
  measures: [{
    measureId: "M1", formalRevision: "M1-2", text: "紧固动作", conclusion: "impact_found",
    facts: ["正式快照已有紧固工序"], inference: "当前控制可能覆盖不足", reason: "节点路径与措施一致",
    adjustments: ["考虑加入防错"], gaps: ["缺少量具校验记录"], evidence: [{ id: "source1", label: "D4 验证记录" }],
  }, {
    measureId: "M2", formalRevision: null, text: "检具复核", conclusion: "insufficient_evidence",
    facts: [], reason: "缺少工位标识", adjustments: [], gaps: ["补充记录编号"], evidence: [],
  }],
};

function clients() {
  return {
    listTargets: vi.fn<PfmeaImpactClients["listTargets"]>()
      .mockResolvedValue({ items: [target], total: 1 }),
    start: vi.fn<PfmeaImpactClients["start"]>()
      .mockResolvedValue({ taskId: "task-a", status: "queued" }),
    readRecommendation: vi.fn<PfmeaImpactClients["readRecommendation"]>().mockResolvedValue(recommendation),
    readEvidence: vi.fn<NonNullable<PfmeaImpactClients["readEvidence"]>>()
      .mockResolvedValue({ label: "D4 验证记录", text: "受控来源正文" }),
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}

describe("PfmeaImpactPanel", () => {
  beforeEach(async () => { await i18n.changeLanguage("zh-CN"); });

  it("confirms the approved version and reuses one start key after an uncertain failure", async () => {
    const api = clients();
    api.start.mockRejectedValueOnce(new Error("Network offline"));
    const onStarted = vi.fn();
    render(<PfmeaImpactPanel reportId="report-a" scopeKey="tenant-a/user-a" client={api} onStarted={onStarted} />);

    const selection = await screen.findByRole("option", { name: /PF-020.*v3.0/ });
    expect(api.start).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("目标 PFMEA"), { target: { value: selection.getAttribute("value") } });
    expect(screen.getByText("批准基线：v3.0")).toBeInTheDocument();
    expect(screen.getByText("已有未批准修订，本次仍评估所选批准版本。")).toBeInTheDocument();
    const start = screen.getByRole("button", { name: "开始评估" });
    fireEvent.click(start);
    await screen.findByText("暂无法完成操作，请重试。");
    fireEvent.click(start);
    fireEvent.click(start);
    await screen.findByText("等待运行");
    const request = api.start.mock.calls[0][1];
    expect(api.start).toHaveBeenCalledTimes(2);
    expect(api.start.mock.calls[1][1]).toEqual(request);
    expect(request).toMatchObject({ fmeaId: "fmea-a", approvedVersionId: "approved-3" });
    expect(request.requestKey).toBeTruthy();
    expect(onStarted).toHaveBeenCalledTimes(1);
    expect(start).toBeDisabled();
  });

  it("renders the verified verdict, measure versions, evidence and gaps on every authorized open", async () => {
    const api = clients();
    const props = { reportId: "report-a", scopeKey: "a", client: api, recommendationId: "result-1" };
    const view = render(<PfmeaImpactPanel {...props} />);
    await screen.findByText("建议已过期");
    expect(screen.getByText("报告版本：D4 rev 8 · 批准基线：v3.0")).toBeInTheDocument();
    expect(screen.getByText("紧固动作")).toBeInTheDocument();
    expect(screen.getByText("检具复核")).toBeInTheDocument();
    expect(screen.getByText("正式修订：M1-2")).toBeInTheDocument();
    expect(screen.getByText("证据不足")).toBeInTheDocument();
    expect(screen.getByText("缺少量具校验记录")).toBeInTheDocument();
    expect(screen.getByText("考虑加入防错")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "D4 验证记录" }));
    await screen.findByText("受控来源正文");

    view.rerender(<PfmeaImpactPanel {...props} open={false} />);
    expect(screen.queryByText("紧固动作")).toBeNull();
    api.readRecommendation.mockResolvedValueOnce(null);
    view.rerender(<PfmeaImpactPanel {...props} open />);
    await screen.findByText("评估暂不可用。");
    expect(api.readRecommendation).toHaveBeenCalledTimes(2);
    expect(screen.queryByText("紧固动作")).toBeNull();
    expect(screen.queryByText("D4 验证记录")).toBeNull();
    expect(screen.queryByText("受控来源正文")).toBeNull();
  });

  it("drops a late recommendation across identities even when transport ignores abort", async () => {
    const api = clients();
    const previous = deferred<ImpactRecommendation>();
    api.readRecommendation.mockReturnValueOnce(previous.promise).mockResolvedValueOnce(null);
    const props = { reportId: "report-a", client: api, recommendationId: "result-1" };
    const view = render(<PfmeaImpactPanel {...props} scopeKey="tenant-a/user-a" />);
    await waitFor(() => expect(api.readRecommendation).toHaveBeenCalledTimes(1));
    const previousSignal = api.readRecommendation.mock.calls[0][2];
    view.rerender(<PfmeaImpactPanel {...props} scopeKey="tenant-b/user-b" />);
    await screen.findByText("评估暂不可用。");
    expect(previousSignal.aborted).toBe(true);
    await act(async () => previous.resolve(recommendation));
    expect(screen.queryByText("紧固动作")).toBeNull();
    expect(screen.queryByText("D4 验证记录")).toBeNull();
  });

  it("clears the whole recommendation when an evidence read is no longer authorized", async () => {
    const api = clients();
    api.readEvidence.mockRejectedValueOnce({ response: { status: 403 } });
    render(<PfmeaImpactPanel reportId="report-a" scopeKey="a" client={api} recommendationId="result-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "D4 验证记录" }));
    await screen.findByText("评估暂不可用。");
    expect(screen.queryByText("紧固动作")).toBeNull();
    expect(screen.queryByText("检具复核")).toBeNull();
    expect(screen.queryByText("建议已过期")).toBeNull();
  });

  it("does not announce a late task after the report changes", async () => {
    const api = clients();
    const prior = deferred<{ taskId: string; status: "queued" }>();
    api.start.mockReturnValueOnce(prior.promise);
    const onStarted = vi.fn();
    const props = { scopeKey: "a", client: api, onStarted };
    const view = render(<PfmeaImpactPanel reportId="report-a" {...props} />);
    const selection = await screen.findByRole("option", { name: /PF-020.*v3.0/ });
    fireEvent.change(screen.getByLabelText("目标 PFMEA"), { target: { value: selection.getAttribute("value") } });
    fireEvent.click(screen.getByRole("button", { name: "开始评估" }));
    const signal = api.start.mock.calls[0][2];
    view.rerender(<PfmeaImpactPanel reportId="report-b" {...props} />);
    await act(async () => prior.resolve({ taskId: "old-task", status: "queued" }));
    expect(signal.aborted).toBe(true);
    expect(onStarted).not.toHaveBeenCalled();
    expect(screen.queryByText("等待运行")).toBeNull();
  });

  it("requires explicit reconfirmation and a new key after an input conflict on the same approved version", async () => {
    const api = clients();
    api.start.mockRejectedValueOnce({ response: { status: 409 } });
    render(<PfmeaImpactPanel reportId="report-a" scopeKey="a" client={api} />);
    async function selectTarget() {
      const selection = await screen.findByRole("option", { name: /PF-020.*v3.0/ });
      fireEvent.change(screen.getByLabelText("目标 PFMEA"), { target: { value: selection.getAttribute("value") } });
    }
    await selectTarget();
    fireEvent.click(screen.getByRole("button", { name: "开始评估" }));
    await screen.findByText("评估输入已变化，请重新确认。");
    await screen.findByRole("option", { name: /PF-020.*v3.0/ });
    expect(api.start).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "开始评估" })).toBeDisabled();
    await selectTarget();
    fireEvent.click(screen.getByRole("button", { name: "开始评估" }));
    await screen.findByText("等待运行");
    expect(api.start.mock.calls[1][1].requestKey).not.toBe(api.start.mock.calls[0][1].requestKey);
  });

  it("keeps the unresolved request key when reopening the same scope", async () => {
    const api = clients();
    const prior = deferred<null>();
    api.start.mockReturnValueOnce(prior.promise);
    const props = { reportId: "report-a", scopeKey: "a", client: api };
    const view = render(<PfmeaImpactPanel {...props} />);
    async function start() {
      const selection = await screen.findByRole("option", { name: /PF-020.*v3.0/ });
      fireEvent.change(screen.getByLabelText("目标 PFMEA"), { target: { value: selection.getAttribute("value") } });
      fireEvent.click(screen.getByRole("button", { name: "开始评估" }));
    }
    await start();
    view.rerender(<PfmeaImpactPanel {...props} open={false} />);
    expect(api.start.mock.calls[0][2].aborted).toBe(true);
    view.rerender(<PfmeaImpactPanel {...props} open />);
    await start();
    await screen.findByText("等待运行");
    expect(api.start.mock.calls[1][1].requestKey).toBe(api.start.mock.calls[0][1].requestKey);
    await act(async () => prior.resolve(null));
    expect(screen.getByText("等待运行")).toBeInTheDocument();
  });
});

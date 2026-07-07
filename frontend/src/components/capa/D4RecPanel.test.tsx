import { describe, it, expect, vi, beforeEach, afterAll } from "vitest";
import { render, screen, fireEvent, waitFor, configure } from "@testing-library/react";
configure({ testIdAttribute: "data-e2e" }); // 生产组件用 data-e2e（计划 Global Constraint），切 Testing Library 的 testIdAttribute
afterAll(() => configure({ testIdAttribute: "data-testid" })); // 复位默认，防止 vitest 非默认隔离配置下泄漏到后续测试文件
import { App, ConfigProvider } from "antd";
import D4RecPanel from "./D4RecPanel";

const mockStages = vi.hoisted(() =>
  Array.from({ length: 12 }, (_, i) => ({
    index: i + 1,
    name: `Stage ${i + 1}`,
    source: "test",
    status: i === 11 ? "done" : "pending",
    hit_count: 0,
    summary: `summary ${i + 1}`,
  }))
);

vi.mock("../../api/capa", () => ({
  getD4Recommendations: vi.fn().mockResolvedValue({
    stages: mockStages,
    items: [
      {
        failure_cause_node_id: "c1",
        failure_cause_name: "根因A",
        failure_mode_name: "虚焊",
        fmea_document_no: "PFMEA-1",
        match_source: "fmea_graph",
        match_reason: "r",
        related_d2_keywords: [],
        confidence: 0.6,
        fmea_id: "f1",
        stage_index: 2,
      },
    ],
  }),
  adoptRecommendation: vi.fn().mockResolvedValue({ adoption_id: "a1", d_step: "d4", field_value: "根因A" }),
}));

import { adoptRecommendation } from "../../api/capa";

const renderPanel = (props = {}) => render(
  <ConfigProvider><App>
    <D4RecPanel capaId="c1" canAdopt={true} beforeAdopt={vi.fn()} onAdopted={vi.fn()} {...props} />
  </App></ConfigProvider>
);

beforeEach(() => vi.clearAllMocks());

describe("D4RecPanel adopt", () => {
  it("renders DAG and provenance tags", async () => {
    renderPanel();
    await waitFor(() => expect(screen.queryByTestId("rec-dag-stage-1")).toBeInTheDocument());
    expect(screen.getByTestId("rec-dag-stage-12")).toBeInTheDocument();
    expect(screen.getByTestId("rec-source-fmea_graph")).toBeInTheDocument();
    expect(screen.getByTestId("rec-item-stage-2")).toBeInTheDocument();
  });

  it("calls beforeAdopt then adoptRecommendation with source/item_ref and stage_index", async () => {
    const beforeAdopt = vi.fn().mockResolvedValue(undefined);
    const onAdopted = vi.fn();
    renderPanel({ beforeAdopt, onAdopted });
    await waitFor(() => expect(screen.queryByTestId("d4-adopt")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("d4-adopt"));
    await waitFor(() => expect(beforeAdopt).toHaveBeenCalled());
    await waitFor(() => expect(adoptRecommendation).toHaveBeenCalledWith("c1", expect.objectContaining({
      d_step: "d4",
      adopted_text: "根因A",
      source: "fmea_graph",
      stage_index: 2,
      item_ref: expect.objectContaining({ failure_cause_node_id: "c1", fmea_id: "f1" }),
    })));
    await waitFor(() => expect(onAdopted).toHaveBeenCalled());
  });

  it("does not call adoptRecommendation until beforeAdopt resolves (flush-then-adopt ordering)", async () => {
    let resolveBefore!: () => void;
    const beforeAdopt = vi.fn().mockReturnValue(new Promise<void>((r) => { resolveBefore = r; }));
    renderPanel({ beforeAdopt });
    await waitFor(() => expect(screen.queryByTestId("d4-adopt")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("d4-adopt"));
    await waitFor(() => expect(beforeAdopt).toHaveBeenCalled());
    // beforeAdopt 未 resolve：让微任务跑完一轮，采纳端点仍不应被调用
    await new Promise((r) => setTimeout(r, 0));
    expect(adoptRecommendation).not.toHaveBeenCalled();
    resolveBefore();
    await waitFor(() => expect(adoptRecommendation).toHaveBeenCalledWith("c1", expect.objectContaining({ d_step: "d4", stage_index: 2 })));
  });

  it("does not call adoptRecommendation when beforeAdopt rejects (save failed → block adopt)", async () => {
    const beforeAdopt = vi.fn().mockRejectedValue(new Error("save failed"));
    renderPanel({ beforeAdopt });
    await waitFor(() => expect(screen.queryByTestId("d4-adopt")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("d4-adopt"));
    await waitFor(() => expect(beforeAdopt).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 0));
    expect(adoptRecommendation).not.toHaveBeenCalled();
  });

  it("disables adopt when canAdopt=false", async () => {
    renderPanel({ canAdopt: false });
    await waitFor(() => expect(screen.queryByTestId("d4-adopt")).toBeInTheDocument());
    expect((screen.getByTestId("d4-adopt") as HTMLButtonElement).closest("button")!).toBeDisabled();
  });
});

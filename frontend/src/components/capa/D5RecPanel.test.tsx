import { describe, it, expect, vi, beforeEach, afterAll } from "vitest";
import { render, screen, fireEvent, waitFor, configure } from "@testing-library/react";
configure({ testIdAttribute: "data-e2e" }); // 生产组件用 data-e2e（计划 Global Constraint），切 Testing Library 的 testIdAttribute
afterAll(() => configure({ testIdAttribute: "data-testid" })); // 复位默认，防止 vitest 非默认隔离配置下泄漏到后续测试文件
import { App, ConfigProvider } from "antd";
import D5RecPanel from "./D5RecPanel";

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
  getD5Recommendations: vi.fn().mockResolvedValue({
    stages: mockStages,
    existing_controls: [{
      control_node_id: "ctrl1",
      control_name: "焊接监控",
      control_type: "prevention",
      match_source: "fmea_graph",
      match_reason: "r",
      fmea_id: "f1",
      failure_mode_node_id: "fm",
      failure_cause_node_id: "c1",
      stage_index: 3,
    }],
    general_suggestions: [{
      content: "通用措施",
      category: "预防措施",
      basis: "",
      confidence: 0.5,
      match_reason: "r",
      match_source: "rule",
      stage_index: 4,
    }],
  }),
  adoptRecommendation: vi.fn().mockResolvedValue({ adoption_id: "a1", d_step: "d5", field_value: "x" }),
}));

import { adoptRecommendation } from "../../api/capa";

const renderPanel = (props = {}) => render(
  <ConfigProvider><App>
    <D5RecPanel capaId="c1" canAdopt={true} beforeAdopt={vi.fn()} onAdopted={vi.fn()} {...props} />
  </App></ConfigProvider>
);

beforeEach(() => vi.clearAllMocks());

describe("D5RecPanel adopt", () => {
  it("renders DAG and provenance tags for control + suggestion", async () => {
    renderPanel();
    await waitFor(() => expect(screen.queryByTestId("rec-dag-stage-1")).toBeInTheDocument());
    expect(screen.getByTestId("rec-dag-stage-12")).toBeInTheDocument();
    expect(screen.getByTestId("rec-source-fmea_graph")).toBeInTheDocument();
    expect(screen.getByTestId("rec-item-stage-3")).toBeInTheDocument();
    expect(screen.getByTestId("rec-source-rule")).toBeInTheDocument();
    expect(screen.getByTestId("rec-item-stage-4")).toBeInTheDocument();
  });

  it("adopts existing control via d5-adopt-control with stage_index", async () => {
    renderPanel();
    await waitFor(() => expect(screen.queryByTestId("d5-adopt-control")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("d5-adopt-control"));
    await waitFor(() => expect(adoptRecommendation).toHaveBeenCalledWith("c1", expect.objectContaining({
      d_step: "d5",
      adopted_text: "焊接监控",
      source: "fmea_graph",
      stage_index: 3,
      item_ref: expect.objectContaining({ control_node_id: "ctrl1", failure_cause_node_id: "c1" }),
    })));
  });

  it("adopts general suggestion via d5-adopt-suggestion with stage_index", async () => {
    renderPanel();
    await waitFor(() => expect(screen.queryByTestId("d5-adopt-suggestion")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("d5-adopt-suggestion"));
    await waitFor(() => expect(adoptRecommendation).toHaveBeenCalledWith("c1", expect.objectContaining({
      d_step: "d5",
      adopted_text: "通用措施",
      source: "rule",
      stage_index: 4,
    })));
  });

  it("waits for beforeAdopt to resolve before adopting (flush-then-adopt ordering)", async () => {
    let resolveBefore!: () => void;
    const beforeAdopt = vi.fn().mockReturnValue(new Promise<void>((r) => { resolveBefore = r; }));
    renderPanel({ beforeAdopt });
    await waitFor(() => expect(screen.queryByTestId("d5-adopt-control")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("d5-adopt-control"));
    await waitFor(() => expect(beforeAdopt).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 0));
    expect(adoptRecommendation).not.toHaveBeenCalled();
    resolveBefore();
    await waitFor(() => expect(adoptRecommendation).toHaveBeenCalledWith("c1", expect.objectContaining({ d_step: "d5", stage_index: 3 })));
  });

  it("does not adopt when beforeAdopt rejects (save failed → block adopt)", async () => {
    const beforeAdopt = vi.fn().mockRejectedValue(new Error("save failed"));
    renderPanel({ beforeAdopt });
    await waitFor(() => expect(screen.queryByTestId("d5-adopt-control")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("d5-adopt-control"));
    await waitFor(() => expect(beforeAdopt).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 0));
    expect(adoptRecommendation).not.toHaveBeenCalled();
  });
});

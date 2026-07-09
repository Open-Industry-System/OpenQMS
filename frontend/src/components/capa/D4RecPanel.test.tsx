import { describe, it, expect, vi, beforeEach, afterAll } from "vitest";
import { render, screen, fireEvent, waitFor, configure } from "@testing-library/react";
configure({ testIdAttribute: "data-e2e" }); // 生产组件用 data-e2e（计划 Global Constraint），切 Testing Library 的 testIdAttribute
afterAll(() => configure({ testIdAttribute: "data-testid" })); // 复位默认，防止 vitest 非默认隔离配置下泄漏到后续测试文件
import { App, ConfigProvider } from "antd";
import D4RecPanel from "./D4RecPanel";
import type { StageRun } from "../../types";

const mockStages = vi.hoisted(() =>
  Array.from({ length: 12 }, (_, i) => ({
    index: i + 1,
    name: `Stage ${i + 1}`,
    source: "test",
    status: i === 11 ? "done" : "pending",
    hit_count: 0,
    summary: `summary ${i + 1}`,
  } as StageRun))
);

vi.mock("../../api/capa", () => ({
  RecommendationBlockedError: class RecommendationBlockedError extends Error {
    detail: { blocked: true; reason: string; stages: StageRun[] };
    constructor(detail: { blocked: true; reason: string; stages: StageRun[] }) {
      super(detail.reason);
      this.detail = detail;
    }
  },
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

import { getD4Recommendations, adoptRecommendation, RecommendationBlockedError } from "../../api/capa";

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

  it("renders DAG even when recommendations list is empty", async () => {
    vi.mocked(getD4Recommendations).mockResolvedValueOnce({ stages: mockStages, items: [] });
    renderPanel();
    await waitFor(() => expect(screen.queryByTestId("rec-dag-stage-1")).toBeInTheDocument());
    expect(screen.getByTestId("rec-dag-stage-12")).toBeInTheDocument();
  });

  it("renders BLOCKED banner on 422 detail.blocked", async () => {
    vi.mocked(getD4Recommendations).mockRejectedValueOnce(
      new RecommendationBlockedError({ blocked: true, reason: "LLM credentials not configured", stages: [] })
    );
    renderPanel();
    await waitFor(() => expect(screen.getByTestId("rec-blocked-banner")).toBeInTheDocument());
    expect(screen.getByTestId("rec-blocked-banner")).toHaveTextContent("LLM");
  });

  it("renders all 6 new D4 match_source groups", async () => {
    vi.mocked(getD4Recommendations).mockResolvedValueOnce({
      stages: mockStages,
      items: [
        {
          failure_cause_node_id: "c2",
          failure_cause_name: "同类型产品 KB 根因",
          failure_cause_desc: null,
          failure_mode_node_id: null,
          failure_mode_name: null,
          fmea_document_no: null,
          fmea_id: null,
          match_source: "same_type_product_kb",
          match_reason: "r",
          related_d2_keywords: [],
          confidence: 0.5,
          source_capa_id: null,
          source_capa_document_no: null,
          source_product_line_code: null,
          stage_index: 4,
        },
        {
          failure_cause_node_id: "c3",
          failure_cause_name: "经验教训根因",
          failure_cause_desc: null,
          failure_mode_node_id: null,
          failure_mode_name: null,
          fmea_document_no: null,
          fmea_id: null,
          match_source: "lessons_learned",
          match_reason: "r",
          related_d2_keywords: [],
          confidence: 0.5,
          source_capa_id: null,
          source_capa_document_no: null,
          source_product_line_code: null,
          stage_index: 5,
        },
        {
          failure_cause_node_id: "c4",
          failure_cause_name: "SPC 异常根因",
          failure_cause_desc: null,
          failure_mode_node_id: null,
          failure_mode_name: null,
          fmea_document_no: null,
          fmea_id: null,
          match_source: "spc_anomaly",
          match_reason: "r",
          related_d2_keywords: [],
          confidence: 0.5,
          source_capa_id: null,
          source_capa_document_no: null,
          source_product_line_code: null,
          stage_index: 6,
        },
        {
          failure_cause_node_id: "c5",
          failure_cause_name: "MES 根因",
          failure_cause_desc: null,
          failure_mode_node_id: null,
          failure_mode_name: null,
          fmea_document_no: null,
          fmea_id: null,
          match_source: "mes",
          match_reason: "r",
          related_d2_keywords: [],
          confidence: 0.5,
          source_capa_id: null,
          source_capa_document_no: null,
          source_product_line_code: null,
          stage_index: 7,
        },
        {
          failure_cause_node_id: "c6",
          failure_cause_name: "IQC 根因",
          failure_cause_desc: null,
          failure_mode_node_id: null,
          failure_mode_name: null,
          fmea_document_no: null,
          fmea_id: null,
          match_source: "iqc",
          match_reason: "r",
          related_d2_keywords: [],
          confidence: 0.5,
          source_capa_id: null,
          source_capa_document_no: null,
          source_product_line_code: null,
          stage_index: 8,
        },
        {
          failure_cause_node_id: "c7",
          failure_cause_name: "供货历史根因",
          failure_cause_desc: null,
          failure_mode_node_id: null,
          failure_mode_name: null,
          fmea_document_no: null,
          fmea_id: null,
          match_source: "supplier_history",
          match_reason: "r",
          related_d2_keywords: [],
          confidence: 0.5,
          source_capa_id: null,
          source_capa_document_no: null,
          source_product_line_code: null,
          stage_index: 9,
        },
      ],
    });
    renderPanel();
    await waitFor(() => expect(screen.queryByTestId("rec-source-same_type_product_kb")).toBeInTheDocument());
    expect(screen.getByTestId("rec-source-lessons_learned")).toBeInTheDocument();
    expect(screen.getByTestId("rec-source-spc_anomaly")).toBeInTheDocument();
    expect(screen.getByTestId("rec-source-mes")).toBeInTheDocument();
    expect(screen.getByTestId("rec-source-iqc")).toBeInTheDocument();
    expect(screen.getByTestId("rec-source-supplier_history")).toBeInTheDocument();
  });
});

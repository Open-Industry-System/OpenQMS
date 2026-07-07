import { describe, it, expect, afterAll } from "vitest";
import { render, screen, configure } from "@testing-library/react";
import { ConfigProvider } from "antd";
import RecommendationDAG from "./RecommendationDAG";
import type { StageRun } from "../../types";

configure({ testIdAttribute: "data-e2e" });
afterAll(() => configure({ testIdAttribute: "data-testid" }));

const makeStages = (): StageRun[] => [
  { index: 1, name: "Context", source: "internal", status: "done", hit_count: 1, summary: "ok" },
  { index: 2, name: "FMEA Search", source: "fmea_graph", status: "done", hit_count: 3, summary: "3 hits" },
  { index: 3, name: "Global KB RAG", source: "semantic_search", status: "running", hit_count: 0, summary: "searching" },
  { index: 4, name: "Same-Type Product KB", source: "same_type_product_kb", status: "skipped", hit_count: 0, summary: "no product type" },
  { index: 5, name: "Lessons Learned", source: "lessons_learned", status: "done", hit_count: 2, summary: "2 lessons" },
  { index: 6, name: "SPC Anomaly", source: "spc_anomaly", status: "error", hit_count: 0, summary: "service timeout" },
  { index: 7, name: "MES Equipment", source: "mes", status: "pending", hit_count: 0, summary: "queued" },
  { index: 8, name: "IQC Incoming", source: "iqc", status: "done", hit_count: 5, summary: "5 lots" },
  { index: 9, name: "Supplier History", source: "supplier_history", status: "skipped", hit_count: 0, summary: "no supplier" },
  { index: 10, name: "Rule Engine", source: "rule_engine", status: "done", hit_count: 1, summary: "1 rule" },
  { index: 11, name: "LLM Fusion", source: "llm", status: "running", hit_count: 0, summary: "calling llm" },
  { index: 12, name: "Output", source: "internal", status: "pending", hit_count: 0, summary: "waiting" },
];

const renderDAG = (stages?: StageRun[]) =>
  render(
    <ConfigProvider>
      <RecommendationDAG stages={stages} />
    </ConfigProvider>
  );

describe("RecommendationDAG", () => {
  it("renders 12 stage nodes with rec-dag-stage-{index} test ids", () => {
    renderDAG(makeStages());
    for (let i = 1; i <= 12; i++) {
      expect(screen.getByTestId(`rec-dag-stage-${i}`)).toBeInTheDocument();
    }
  });

  it("preserves each node's status in data-status", () => {
    const stages = makeStages();
    renderDAG(stages);
    stages.forEach((stage) => {
      const node = screen.getByTestId(`rec-dag-stage-${stage.index}`);
      expect(node).toHaveAttribute("data-status", stage.status);
    });
  });

  it("maps status to Ant Design colors: done green, skipped gray, error red", () => {
    renderDAG(makeStages());

    const finish = screen.getByTestId("rec-dag-stage-1");
    expect(finish.className).toMatch(/ant-steps-item-finish|finish/);

    const wait = screen.getByTestId("rec-dag-stage-4");
    expect(wait.className).toMatch(/ant-steps-item-wait|wait/);

    const error = screen.getByTestId("rec-dag-stage-6");
    expect(error.className).toMatch(/ant-steps-item-error|error/);
  });

  it("renders nothing when stages is empty", () => {
    const { container } = renderDAG([]);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when stages is undefined", () => {
    const { container } = renderDAG(undefined);
    expect(container.firstChild).toBeNull();
  });

  it("uses i18n stage names when keys exist", () => {
    renderDAG(makeStages());
    expect(screen.getByText("Context Collection")).toBeInTheDocument();
    expect(screen.getByText("This Product FMEA Search")).toBeInTheDocument();
  });

  it("renders source tag, hit count badge and summary text", () => {
    renderDAG(makeStages());
    expect(screen.getByText("fmea_graph")).toBeInTheDocument();
    expect(screen.getByText("3 hits")).toBeInTheDocument();
  });
});

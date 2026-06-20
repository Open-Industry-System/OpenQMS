import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import ScopeTagField from "./ScopeTagField";
import { getRecommendations } from "../../api/recommendation";

vi.mock("../../api/recommendation", () => ({
  getRecommendations: vi.fn(),
}));

const mockedGetRecommendations = vi.mocked(getRecommendations);

const AI_RESPONSE = {
  suggestions: [],
  source: "rule" as const,
  cached: false,
  llm_available: false,
  graph_match_count: 0,
  effective_scope: "current_product_line" as const,
};

function renderField(overrides: Partial<React.ComponentProps<typeof ScopeTagField>> = {}) {
  return render(
    <ScopeTagField
      value=""
      onChange={() => {}}
      presets={["边界图", "P图", "接口矩阵"]}
      triggerType="dfmea_tool"
      fmeaId="fmea-1"
      context={{ fmea_title: "DC-DC", product_line_code: "DC-DC-100", task: "分析" }}
      {...overrides}
    />,
  );
}

describe("ScopeTagField", () => {
  beforeEach(() => mockedGetRecommendations.mockReset());

  it("renders unselected preset quick-add chips", () => {
    renderField();
    expect(screen.getByText("+ 边界图")).toBeInTheDocument();
    expect(screen.getByText("+ P图")).toBeInTheDocument();
    expect(screen.getByText("+ 接口矩阵")).toBeInTheDocument();
  });

  it("hides a preset chip once selected and calls onChange to add", () => {
    const onChange = vi.fn();
    renderField({ onChange });
    fireEvent.click(screen.getByText("+ 边界图"));
    expect(onChange).toHaveBeenCalledWith("边界图");
  });

  it("does not show a chip for an already-selected preset", () => {
    renderField({ value: "边界图" });
    expect(screen.queryByText("+ 边界图")).not.toBeInTheDocument();
    expect(screen.getByText("+ P图")).toBeInTheDocument();
  });

  it("AI button fetches suggestions and renders purple AI chips", async () => {
    mockedGetRecommendations.mockResolvedValueOnce({
      ...AI_RESPONSE,
      suggestions: [{ name: "故障树分析(FTA)", confidence: 0.8, source: "llm", explanation: "" }],
      source: "hybrid",
      llm_available: true,
    });
    renderField();
    fireEvent.click(screen.getByTestId("scope-ai-btn"));
    await waitFor(() => expect(mockedGetRecommendations).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText("故障树分析(FTA)")).toBeInTheDocument());
  });

  it("clicking an AI chip adds it via onChange", async () => {
    mockedGetRecommendations.mockResolvedValueOnce({
      ...AI_RESPONSE,
      suggestions: [{ name: "设计评审", confidence: 0.7, source: "llm", explanation: "" }],
      source: "hybrid",
      llm_available: true,
    });
    const onChange = vi.fn();
    renderField({ onChange });
    fireEvent.click(screen.getByTestId("scope-ai-btn"));
    await waitFor(() => expect(screen.getByText("设计评审")).toBeInTheDocument());
    fireEvent.click(screen.getByText("设计评审"));
    expect(onChange).toHaveBeenCalledWith("设计评审");
  });

  it("does not render AI chips when AI returns empty", async () => {
    mockedGetRecommendations.mockResolvedValueOnce(AI_RESPONSE);
    renderField();
    fireEvent.click(screen.getByTestId("scope-ai-btn"));
    await waitFor(() => expect(mockedGetRecommendations).toHaveBeenCalled());
    expect(screen.queryByText("故障树分析(FTA)")).not.toBeInTheDocument();
  });

  it("does not render AI chips when the call rejects", async () => {
    mockedGetRecommendations.mockRejectedValueOnce(new Error("boom"));
    renderField();
    fireEvent.click(screen.getByTestId("scope-ai-btn"));
    await waitFor(() => expect(mockedGetRecommendations).toHaveBeenCalled());
    expect(screen.queryByText("故障树分析(FTA)")).not.toBeInTheDocument();
  });

  it("passes trigger_type, scope and include_graph:false to getRecommendations", async () => {
    mockedGetRecommendations.mockResolvedValueOnce(AI_RESPONSE);
    renderField({ triggerType: "dfmea_trend" });
    fireEvent.click(screen.getByTestId("scope-ai-btn"));
    await waitFor(() => expect(mockedGetRecommendations).toHaveBeenCalled());
    const arg = mockedGetRecommendations.mock.calls[0][1];
    expect(arg.trigger_type).toBe("dfmea_trend");
    expect(arg.scope).toBe("current_product_line");
    expect(arg.include_graph).toBe(false);
  });
});

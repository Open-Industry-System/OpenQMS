import { describe, it, expect, afterAll, vi } from "vitest";
import { render, screen, fireEvent, configure } from "@testing-library/react";
import { ConfigProvider } from "antd";
import { LateralDiffusionModal } from "./LateralDiffusionModal";
import type { LateralDiffusionProjection } from "../../types";

configure({ testIdAttribute: "data-e2e" });
afterAll(() => configure({ testIdAttribute: "data-testid" }));

const baseProjection: LateralDiffusionProjection = {
  check_id: "c1",
  status: "done",
  llm_status: "done",
  truncated: false,
  decision: null,
  similar_products: [
    {
      product_type_code: "DC-DC",
      hit_criteria: ["same_product_type"],
      suggestion_direction: "x",
      product_lines: [{ code: "PL-2", factory_id: "f" }],
      evidence: {},
    },
  ],
  notifications: [],
};

describe("LateralDiffusionModal", () => {
  it("renders all hit types without subset checkboxes", () => {
    render(
      <ConfigProvider>
        <LateralDiffusionModal open projection={baseProjection} onDecide={() => {}} />
      </ConfigProvider>,
    );
    expect(screen.getByTestId("lateral-hit-DC-DC")).toBeInTheDocument();
    expect(screen.getByTestId("lateral-decide-notify")).toBeInTheDocument();
    expect(screen.getByTestId("lateral-decide-skip")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("requires skip reason when skipping", () => {
    const onDecide = vi.fn();
    render(
      <ConfigProvider>
        <LateralDiffusionModal open projection={baseProjection} onDecide={onDecide} />
      </ConfigProvider>,
    );
    const skipBtn = screen.getByTestId("lateral-decide-skip");
    expect(skipBtn).toBeDisabled();
    fireEvent.change(screen.getByTestId("lateral-skip-reason"), {
      target: { value: "无需扩散" },
    });
    expect(skipBtn).not.toBeDisabled();
    fireEvent.click(skipBtn);
    expect(onDecide).toHaveBeenCalledWith("skip", "无需扩散");
  });
});

import { render } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import RiskHeatmap from "./RiskHeatmap";
import type { HeatmapResponse } from "../../../types";

const chart = vi.hoisted(() => ({ option: null as any }));
vi.mock("echarts-for-react", () => ({ default: ({ option }: any) => { chart.option = option; return null; } }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (_key: string, options?: any) => options?.source ?? _key }) }));

it("renders all tooltip values as literal text while retaining formatting", () => {
  const malicious = '<img src=x onerror="window.pwned=1">';
  const data = {
    columns: [{ key: "custom", label: malicious }],
    rows: [{ supplier_id: "one", supplier_name: malicious, cells: [{ value: 1, risk_index: 1, source: malicious }] }],
  } as unknown as HeatmapResponse;
  render(<RiskHeatmap data={data} />);
  const output = chart.option.tooltip.formatter({ data: [0, 0] });
  const tooltip = document.createElement("div");
  if (typeof output === "string") tooltip.innerHTML = output;
  else tooltip.append(output);
  expect(tooltip.querySelector("img")).toBeNull();
  expect(tooltip.querySelector("[onerror]")).toBeNull();
  expect(tooltip.textContent?.split(malicious)).toHaveLength(4);
  expect(tooltip.querySelector("strong")?.textContent).toBe(malicious);
});

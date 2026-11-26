import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import i18n from "../../../i18n";
import type { HeatmapCell, HeatmapResponse } from "../../../types";
import RiskHeatmap from "./RiskHeatmap";

beforeEach(async () => {
  await i18n.changeLanguage("en-US");
});

function fixture(): HeatmapResponse {
  return {
    period: "2026-11",
    prev_period: "2026-10",
    product_line_code: "PR59-A",
    columns: [
      { key: "open_scar_count", label: "Open SCAR", type: "count", polarity: "higher_is_risk" },
      { key: "erp_on_time_rate", label: "ERP On-Time Rate", type: "percent", polarity: "lower_is_risk" },
      { key: "purchase_amount_pct", label: "Purchase Amount %", type: "percent", polarity: "neutral_exposure" },
    ],
    rows: [{
      supplier_id: "supplier-1",
      supplier_name: "PR59 Sample Supplier",
      cells: [
        { key: "purchase_amount_pct", value: 90, risk_index: 90, level: null, diff: null, source: "erp_po" },
        { key: "open_scar_count", value: 0, risk_index: 0, level: null, diff: -1, source: "risk_evaluation" },
        { key: "erp_on_time_rate", value: null, risk_index: null, level: null, diff: null, source: "missing" },
      ],
    }],
  };
}

it("labels the matrix and shows distinct zero, missing data and neutral exposure", () => {
  render(<RiskHeatmap data={fixture()} />);

  const table = screen.getByRole("table", { name: "Supplier Risk Matrix" });
  expect(within(table).getByRole("columnheader", { name: "Supplier" })).toBeVisible();
  expect(within(table).getByRole("columnheader", { name: "Open SCAR" })).toBeVisible();
  expect(within(table).getByRole("rowheader", { name: "PR59 Sample Supplier" })).toBeVisible();

  const [scar, erp, purchase] = within(table).getAllByRole("cell");
  expect(within(scar).getByText("0")).toHaveAttribute("data-tone", "low");
  expect(within(scar).getByText("0")).toHaveAttribute("title", expect.stringContaining("Change from prior period: -1"));
  expect(within(erp).getByText("—")).toHaveAttribute("data-tone", "missing");
  expect(within(purchase).getByText("90%")).toHaveAttribute("data-tone", "neutral");
});

it("keeps name and cell selection tied to the correct supplier", () => {
  const select = vi.fn();
  const data = fixture();
  const { rerender } = render(<RiskHeatmap data={data} onSupplierClick={select} />);
  const name = screen.getByRole("button", { name: "PR59 Sample Supplier" });
  expect(name).toHaveAttribute("aria-pressed", "false");
  fireEvent.click(name);
  fireEvent.click(screen.getByRole("button", { name: /open scar/i }));
  expect(select.mock.calls).toEqual([["supplier-1"], ["supplier-1"]]);

  rerender(<RiskHeatmap data={data} selectedSupplierIds={["supplier-1"]} onSupplierClick={select} />);
  expect(name).toHaveAttribute("aria-pressed", "true");
});

it("renders supplier names, metric headers and tooltip values as literal text", () => {
  const malicious = '<img src=x onerror="window.pwned=1">';
  const data = fixture();
  data.columns = [{ key: "custom", label: malicious, type: "count", polarity: "higher_is_risk" }];
  data.rows[0].supplier_name = malicious;
  data.rows[0].cells = [{
    key: "custom", value: 1, risk_index: 1, diff: null, level: null,
    source: malicious as HeatmapCell["source"],
  }];

  const { container } = render(<RiskHeatmap data={data} />);
  expect(screen.getByRole("columnheader", { name: malicious })).toBeVisible();
  expect(screen.getByRole("rowheader", { name: malicious })).toBeVisible();
  expect(screen.getByText("1")).toHaveAttribute("title", expect.stringContaining(`Source: ${malicious}`));
  expect(container.querySelector("img, [onerror]")).toBeNull();
});

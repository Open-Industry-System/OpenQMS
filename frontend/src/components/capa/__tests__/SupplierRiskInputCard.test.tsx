import { describe, it, expect, vi, beforeEach, afterAll } from "vitest";
import { render, screen, fireEvent, configure } from "@testing-library/react";
import { SupplierRiskInputCard } from "../SupplierRiskInputCard";
import i18n from "../../../i18n";

configure({ testIdAttribute: "data-e2e" });
afterAll(() => configure({ testIdAttribute: "data-testid" }));

const base = {
  input_id: "i1",
  status: "processed" as const,
  repeat_suggested: true,
  repeat_detection_status: "matched" as const,
  repeat_confirmed: null,
  matched_capa_nos: ["8D-2025-001"],
  evaluated_risk_level: "high",
  evaluated_risk_score: 80,
  linked_alert: null,
};

beforeEach(async () => {
  await i18n.changeLanguage("zh-CN");
});

describe("SupplierRiskInputCard", () => {
  it("shows confirm buttons when processed and repeat_confirmed null and editable", () => {
    const onConfirm = vi.fn();
    render(<SupplierRiskInputCard input={base} canEdit={true} onConfirm={onConfirm} />);
    expect(screen.getByText(/系统判定曾复发/)).toBeInTheDocument();
    fireEvent.click(screen.getByText(/是，属复发/));
    expect(onConfirm).toHaveBeenCalledWith(true);
  });

  it("disables buttons when not processed", () => {
    render(
      <SupplierRiskInputCard
        input={{ ...base, status: "pending" }}
        canEdit={true}
        onConfirm={vi.fn()}
      />,
    );
    expect(screen.queryByText(/是，属复发/)).not.toBeInTheDocument();
  });

  it("shows unavailable message when no FMEA", () => {
    render(
      <SupplierRiskInputCard
        input={{ ...base, repeat_detection_status: "unavailable" }}
        canEdit={true}
        onConfirm={vi.fn()}
      />,
    );
    expect(screen.getByText(/未关联 FMEA/)).toBeInTheDocument();
  });

  it("shows fixed state when confirmed", () => {
    render(
      <SupplierRiskInputCard
        input={{ ...base, repeat_confirmed: true }}
        canEdit={true}
        onConfirm={vi.fn()}
      />,
    );
    expect(screen.getByText(/已确认：复发/)).toBeInTheDocument();
  });
});

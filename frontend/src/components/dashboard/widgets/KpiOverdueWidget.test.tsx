import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import KpiOverdueWidget from "./KpiOverdueWidget";
import type { DashboardWidgetsData } from "./types";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  canView: vi.fn((_m: string) => true),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../../hooks/usePermission", () => ({
  usePermission: () => ({ canView: mocks.canView }),
}));

const data = {
  kpi: {}, alerts: {}, recent_actions: [],
  spc: {}, msa: {}, iqc: {}, mes: {}, supplier: {}, quality_trend: {}, errors: {},
} as DashboardWidgetsData;

describe("KpiOverdueWidget", () => {
  afterEach(() => {
    mocks.navigate.mockClear();
    mocks.canView.mockReset();
    mocks.canView.mockReturnValue(true);
  });

  it("有 capa 权限时点击卡片下钻到 /capa?overdue=true", () => {
    render(<KpiOverdueWidget data={data} loading={false} error={false} onRetry={() => {}} />);
    fireEvent.click(screen.getByRole("button"));
    expect(mocks.navigate).toHaveBeenCalledWith("/capa?overdue=true");
  });

  it("无 capa 权限时卡片禁用，点击不下钻", () => {
    mocks.canView.mockImplementation((m) => m !== "capa");
    render(<KpiOverdueWidget data={data} loading={false} error={false} onRetry={() => {}} />);
    fireEvent.click(screen.getByRole("button"));
    expect(mocks.navigate).not.toHaveBeenCalled();
  });
});

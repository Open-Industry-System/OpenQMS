import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import AlertHighRpnWidget from "./AlertHighRpnWidget";
import type { DashboardWidgetsData } from "./types";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  canView: vi.fn(() => true),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../../hooks/usePermission", () => ({
  usePermission: () => ({ canView: mocks.canView }),
}));

const data = {
  kpi: {},
  alerts: {
    high_rpn_fmeas: [
      { fmea_id: "f-1", document_no: "PFMEA-2026-001", node_name: "焊接", rpn: 200 },
    ],
  },
  recent_actions: [], spc: {}, msa: {}, iqc: {}, mes: {}, supplier: {}, quality_trend: {}, errors: {},
} as DashboardWidgetsData;

describe("AlertHighRpnWidget", () => {
  afterEach(() => {
    mocks.navigate.mockClear();
    mocks.canView.mockReset();
    mocks.canView.mockReturnValue(true);
  });

  it("有 fmea 权限时点击行跳转详情页 /fmea/:id", () => {
    render(<AlertHighRpnWidget data={data} loading={false} error={false} onRetry={() => {}} />);
    fireEvent.click(screen.getByRole("button"));
    expect(mocks.navigate).toHaveBeenCalledWith("/fmea/f-1");
  });

  it("无 fmea 权限时行不可点击（无 role=button）", () => {
    mocks.canView.mockReturnValue(false);
    render(<AlertHighRpnWidget data={data} loading={false} error={false} onRetry={() => {}} />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(mocks.navigate).not.toHaveBeenCalled();
  });
});

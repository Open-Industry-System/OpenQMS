import { describe, it, expect, vi, beforeEach, afterAll } from "vitest";
import { render, screen, fireEvent, waitFor, configure } from "@testing-library/react";
configure({ testIdAttribute: "data-e2e" }); // 生产组件用 data-e2e（计划 Global Constraint），切 Testing Library 的 testIdAttribute
afterAll(() => configure({ testIdAttribute: "data-testid" })); // 复位默认，防止 vitest 非默认隔离配置下泄漏到后续测试文件
import { App, ConfigProvider } from "antd";
import { MemoryRouter } from "react-router-dom";
import D7RecPanel from "./D7RecPanel";

vi.mock("../../api/capa", () => ({
  getD7Recommendations: vi.fn().mockResolvedValue({ recommendations: [
    { fmea_id: "f1", fmea_document_no: "PFMEA-1", failure_mode_node_id: "fm1", failure_mode_name: "虚焊",
      failure_cause_node_id: "c1", failure_cause_name: "参数偏移",
      prevention_control_node_id: null, prevention_control_name: null,
      match_source: "linked", match_reason: "r", related_d4_keywords: [], suggested_prevention: null },
  ] }),
  recordD7Action: vi.fn().mockResolvedValue({ action_id: "a1", action: "confirmed" }),
  listD7Actions: vi.fn().mockResolvedValue([]),
  autoFillD7: vi.fn().mockResolvedValue({ action_id: "a2", prevention_control_node_id: "ctrl", prevention_control_name_after: "监控", is_new_control: true }),
}));

import { recordD7Action, autoFillD7, listD7Actions } from "../../api/capa";

const renderPanel = (props = {}) => render(
  <ConfigProvider><App><MemoryRouter>
    <D7RecPanel capaId="c1" d5Correction="监控" onConfirmationChange={vi.fn()} {...props} />
  </MemoryRouter></App></ConfigProvider>
);

beforeEach(() => vi.clearAllMocks());

describe("D7RecPanel", () => {
  it("records confirmed action via endpoint", async () => {
    renderPanel();
    await waitFor(() => expect(screen.queryByTestId("d7-confirm")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("d7-confirm"));
    await waitFor(() => expect(recordD7Action).toHaveBeenCalledWith("c1", expect.objectContaining({
      action: "confirmed", fmea_id: "f1", failure_mode_node_id: "fm1", failure_cause_node_id: "c1",
    })));
  });

  it("auto-fills via backend endpoint", async () => {
    renderPanel();
    await waitFor(() => expect(screen.queryByTestId("d7-auto-fill")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("d7-auto-fill"));
    await waitFor(() => expect(autoFillD7).toHaveBeenCalledWith("c1", expect.objectContaining({
      fmea_id: "f1", failure_cause_node_id: "c1", match_source: "linked",
    })));
  });

  it("reloads actions on mount (persistence)", async () => {
    renderPanel();
    await waitFor(() => expect(listD7Actions).toHaveBeenCalledWith("c1"));
  });
});

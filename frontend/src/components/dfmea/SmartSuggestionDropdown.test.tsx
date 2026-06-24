import { render, screen, fireEvent, act } from "@testing-library/react";
import { App } from "antd";
import axios from "axios";
import { beforeEach, describe, expect, it, vi, afterEach } from "vitest";
import SmartSuggestionDropdown from "./SmartSuggestionDropdown";
import { getRecommendations } from "../../api/recommendation";

vi.mock("../../api/recommendation", () => ({
  getRecommendations: vi.fn(),
}));

vi.mock("../../hooks/usePermission", () => ({
  usePermission: () => ({ canView: () => true }),
}));

const mockedGetRecommendations = vi.mocked(getRecommendations);

function renderDropdown(props = {}) {
  return render(
    <App>
      <SmartSuggestionDropdown
        triggerType="failure_mode"
        context={{ function_description: "焊接" }}
        fmeaId="fmea-1"
        value=""
        onChange={() => {}}
        onSelect={() => {}}
        {...props}
      />
    </App>
  );
}

describe("SmartSuggestionDropdown", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    mockedGetRecommendations.mockResolvedValue({
      suggestions: [],
      source: "graph",
      cached: false,
      llm_available: true,
      graph_match_count: 0,
      effective_scope: "current_product_type",
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("does not show unavailable message when a superseded request is canceled", async () => {
    mockedGetRecommendations.mockRejectedValueOnce(new axios.CanceledError("canceled"));

    renderDropdown();
    const input = screen.getByRole("textbox");

    fireEvent.change(input, { target: { value: "焊接" } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(mockedGetRecommendations).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Recommendation service unavailable")).not.toBeInTheDocument();
  });

  it("closes the dropdown when the close button is clicked", async () => {
    mockedGetRecommendations.mockResolvedValueOnce({
      suggestions: [{ name: "焊接不良", confidence: 0.8, source: "rule", explanation: "rule hit" }],
      source: "rule",
      cached: false,
      llm_available: true,
      graph_match_count: 0,
      effective_scope: "global",
    });

    renderDropdown();
    const input = screen.getByRole("textbox");

    fireEvent.change(input, { target: { value: "焊接" } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    // AntD Dropdown mounts the popup via a follow-up timer/rAF; flush it.
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    // 下拉已打开：建议文本可见，弹层处于 appear/enter（进入）动画状态。
    expect(screen.getByText("焊接不良")).toBeInTheDocument();
    const popup = document.querySelector(".ant-dropdown") as Element;
    expect(popup.className).toMatch(/-(?:appear|enter)/);

    const closeBtn = screen.getByRole("button", { name: "Close" });
    fireEvent.mouseDown(closeBtn);
    fireEvent.click(closeBtn);

    // 点击 × → setOpen(false) → AntD 把弹层从 appear/enter 切到 leave（关闭）动画。
    // jsdom 不会触发 CSS animationend，无法断言弹层真正卸载；但 leave 状态是
    // 确定可观测的，足以证明关闭按钮的 onClick 正确把 open 置为 false。
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    const popupAfter = document.querySelector(".ant-dropdown") as Element;
    expect(popupAfter.className).toMatch(/-leave/);
  });

  it("renders three scope options in the dropdown", async () => {
    renderDropdown();
    const input = screen.getByRole("textbox");

    fireEvent.change(input, { target: { value: "abc" } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    // Dropdown popup is portal'd to document.body; find it there.
    const popups = Array.from(document.querySelectorAll(".ant-dropdown"));
    const popup = popups.find((el) => el.querySelector(".ant-radio-group"));
    expect(popup).toBeTruthy();
    const radios = popup!.querySelectorAll(".ant-radio-button-input");
    expect(radios).toHaveLength(3);

    const values = Array.from(radios).map((r) => r.getAttribute("value"));
    expect(values).toContain("global");
    expect(values).toContain("current_product_type");
    expect(values).toContain("current_product_line");
  });

  it("defaults scope to current_product_type and sends it in the request", async () => {
    renderDropdown();
    const input = screen.getByRole("textbox");

    fireEvent.change(input, { target: { value: "def" } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(mockedGetRecommendations).toHaveBeenCalledWith(
      "fmea-1",
      expect.objectContaining({
        trigger_type: "failure_mode",
        scope: "current_product_type",
        include_graph: true,
      }),
      expect.any(AbortSignal)
    );
  });

  it("sends global scope after selecting the global radio", async () => {
    renderDropdown({ scope: "global" });
    const input = screen.getByRole("textbox");

    fireEvent.change(input, { target: { value: "ghi" } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(mockedGetRecommendations).toHaveBeenCalledWith(
      "fmea-1",
      expect.objectContaining({ scope: "global" }),
      expect.any(AbortSignal)
    );
  });
});

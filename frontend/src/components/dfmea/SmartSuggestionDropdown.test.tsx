import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { App } from "antd";
import axios from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SmartSuggestionDropdown from "./SmartSuggestionDropdown";
import { getRecommendations } from "../../api/recommendation";

vi.mock("../../api/recommendation", () => ({
  getRecommendations: vi.fn(),
}));

vi.mock("../../hooks/usePermission", () => ({
  usePermission: () => ({ canView: () => true }),
}));

const mockedGetRecommendations = vi.mocked(getRecommendations);

function renderDropdown() {
  return render(
    <App>
      <SmartSuggestionDropdown
        triggerType="failure_mode"
        context={{ function_description: "焊接" }}
        fmeaId="fmea-1"
        value=""
        onChange={() => {}}
        onSelect={() => {}}
      />
    </App>
  );
}

describe("SmartSuggestionDropdown", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
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
});

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { App } from "antd";
import FMEAListPage from "./FMEAListPage";

// vi.mock factory 被 hoist，必须用 vi.hoisted 暴露 mock 函数给测试体引用
const mocks = vi.hoisted(() => ({
  listFMEAs: vi.fn(),
  createFMEA: vi.fn(),
}));

vi.mock("../../../api/fmea", () => ({
  listFMEAs: mocks.listFMEAs,
  createFMEA: mocks.createFMEA,
}));

// store 以 selector 方式调用，mock 必须执行 selector
vi.mock("../../../store/authStore", () => ({
  useAuthStore: (selector: (s: { user: unknown }) => unknown) =>
    selector({ user: { user_id: "u1", role: "admin" } }),
}));

vi.mock("../../../hooks/usePermission", () => ({
  usePermission: () => ({ canEdit: () => true }),
}));

vi.mock("../../../store/productLineStore", () => ({
  useProductLineStore: (selector: (s: { selected: string }) => unknown) =>
    selector({ selected: "DC-DC-100" }),
}));

function renderAt(path: string) {
  return render(
    <App>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/fmea" element={<FMEAListPage />} />
        </Routes>
      </MemoryRouter>
    </App>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listFMEAs.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
});

describe("FMEAListPage filters", () => {
  it("renders without crashing and requests first page", async () => {
    renderAt("/fmea");
    await vi.waitFor(() => expect(mocks.listFMEAs).toHaveBeenCalled());
  });

  it("reads legacy ?risk=high and sends high_rpn=true", async () => {
    renderAt("/fmea?risk=high");
    await vi.waitFor(() => {
      const call = mocks.listFMEAs.mock.calls[mocks.listFMEAs.mock.calls.length - 1][0];
      expect(call.high_rpn).toBe(true);
    });
  });

  it("reads legacy ?pending_approval=true and sends status=in_review", async () => {
    renderAt("/fmea?pending_approval=true");
    await vi.waitFor(() => {
      const call = mocks.listFMEAs.mock.calls[mocks.listFMEAs.mock.calls.length - 1][0];
      expect(call.status).toBe("in_review");
    });
  });

  it("changing type filter sends fmea_type and resets to page 1", async () => {
    renderAt("/fmea");
    await vi.waitFor(() => expect(mocks.listFMEAs).toHaveBeenCalled());

    // antd 5 Select opens on mouseDown of the .ant-select-selector (not the inner
    // combobox input). The filter bar renders two selects (status, type); the
    // modal's type select is not mounted while the modal is closed.
    // The option's visible text lives in a child .ant-select-item-option-content
    // span, so getByText can't target the clickable option element reliably —
    // query the .ant-select-item-option element directly by its textContent.
    const typeSelectSelector = document.querySelectorAll(".ant-select-selector")[1];
    fireEvent.mouseDown(typeSelectSelector);
    let option: HTMLElement | undefined;
    await vi.waitFor(() => {
      option = Array.from(
        document.querySelectorAll<HTMLElement>(".ant-select-item-option")
      ).find((el) => el.textContent === "DFMEA");
      expect(option).toBeTruthy();
    });
    fireEvent.mouseDown(option!);
    fireEvent.click(option!);

    await vi.waitFor(() => {
      const call = mocks.listFMEAs.mock.calls[mocks.listFMEAs.mock.calls.length - 1][0];
      expect(call.fmea_type).toBe("DFMEA");
      expect(call.page).toBe(1);
    });
  });

  it("search onSearch sends search param", async () => {
    renderAt("/fmea");
    await vi.waitFor(() => expect(mocks.listFMEAs).toHaveBeenCalled());

    const searchInput = screen.getByPlaceholderText(/search|搜索/i);
    fireEvent.change(searchInput, { target: { value: "焊接" } });
    fireEvent.keyDown(searchInput, { key: "Enter", code: "Enter" });

    await vi.waitFor(() => {
      const call = mocks.listFMEAs.mock.calls[mocks.listFMEAs.mock.calls.length - 1][0];
      expect(call.search).toBe("焊接");
    });
  });

  it("reset clears all filters incl. legacy params and requests unfiltered list", async () => {
    // 初始 URL 同时含新参数与旧兼容参数 risk / pending_approval
    renderAt("/fmea?status=draft&type=PFMEA&high_rpn=true&search=foo&risk=high&pending_approval=true");
    await vi.waitFor(() => expect(mocks.listFMEAs).toHaveBeenCalled());

    const resetBtn = screen.getByRole("button", { name: /reset|重置/i });
    fireEvent.click(resetBtn);

    await vi.waitFor(() => {
      const call = mocks.listFMEAs.mock.calls[mocks.listFMEAs.mock.calls.length - 1][0];
      expect(call.status).toBeUndefined();
      expect(call.fmea_type).toBeUndefined();
      expect(call.high_rpn).toBeUndefined();
      expect(call.search).toBeUndefined();
    });
  });
});

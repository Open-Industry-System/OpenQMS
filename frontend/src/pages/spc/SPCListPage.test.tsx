import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { App } from "antd";
import SPCListPage from "./SPCListPage";

const mocks = vi.hoisted(() => ({
  listInspectionCharacteristics: vi.fn(),
  createInspectionCharacteristic: vi.fn(),
  deleteInspectionCharacteristic: vi.fn(),
}));

vi.mock("../../api/spc", () => ({
  listInspectionCharacteristics: mocks.listInspectionCharacteristics,
  createInspectionCharacteristic: mocks.createInspectionCharacteristic,
  deleteInspectionCharacteristic: mocks.deleteInspectionCharacteristic,
}));

vi.mock("../../store/authStore", () => ({
  useAuthStore: (selector: (s: { user: unknown }) => unknown) =>
    selector({ user: { user_id: "u1", role: "admin" } }),
}));

vi.mock("../../hooks/usePermission", () => ({
  usePermission: () => ({ canEdit: () => true }),
}));

vi.mock("../../store/productLineStore", () => ({
  useProductLineStore: (selector: (s: { selected: string }) => unknown) =>
    selector({ selected: "DC-DC-100" }),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => vi.fn() };
});

function renderAt(path: string) {
  return render(
    <App>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/spc" element={<SPCListPage />} />
        </Routes>
      </MemoryRouter>
    </App>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listInspectionCharacteristics.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
});

describe("SPCListPage abnormal drilldown", () => {
  it("reads ?abnormal=true (dashboard drilldown) and sends abnormal=true", async () => {
    renderAt("/spc?abnormal=true");
    await vi.waitFor(() => {
      const call = mocks.listInspectionCharacteristics.mock.calls[
        mocks.listInspectionCharacteristics.mock.calls.length - 1
      ][0];
      expect(call.abnormal).toBe(true);
    });
  });

  it("without ?abnormal sends abnormal undefined", async () => {
    renderAt("/spc");
    await vi.waitFor(() => {
      const call = mocks.listInspectionCharacteristics.mock.calls[
        mocks.listInspectionCharacteristics.mock.calls.length - 1
      ][0];
      expect(call.abnormal).toBeUndefined();
    });
  });
});

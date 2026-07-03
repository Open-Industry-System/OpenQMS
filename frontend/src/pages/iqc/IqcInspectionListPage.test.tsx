import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { App } from "antd";
import IqcInspectionListPage from "./IqcInspectionListPage";

const mocks = vi.hoisted(() => ({
  listInspections: vi.fn(),
  getIqcStats: vi.fn(),
}));

vi.mock("../../api/iqc", () => ({
  listInspections: mocks.listInspections,
  getIqcStats: mocks.getIqcStats,
}));

vi.mock("../../hooks/usePermission", () => ({
  usePermission: () => ({ canEdit: () => true }),
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
          <Route path="/iqc/inspections" element={<IqcInspectionListPage />} />
        </Routes>
      </MemoryRouter>
    </App>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listInspections.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
  mocks.getIqcStats.mockResolvedValue({
    total_inspections: 0,
    accepted_count: 0,
    rejected_count: 0,
    concession_count: 0,
    acceptance_rate: 0,
    rejection_rate: 0,
  });
});

describe("IqcInspectionListPage status drilldown", () => {
  it("reads ?status=pending (dashboard drilldown) and initializes filterStatus=pending", async () => {
    renderAt("/iqc/inspections?status=pending");
    await vi.waitFor(() => {
      const call = mocks.listInspections.mock.calls[mocks.listInspections.mock.calls.length - 1][0];
      expect(call.status).toBe("pending");
    });
  });

  it("without ?status does not send a status filter", async () => {
    renderAt("/iqc/inspections");
    await vi.waitFor(() => {
      const call = mocks.listInspections.mock.calls[mocks.listInspections.mock.calls.length - 1][0];
      expect(call.status).toBeUndefined();
    });
  });
});

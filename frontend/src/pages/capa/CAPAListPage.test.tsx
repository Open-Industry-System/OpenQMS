import { render, screen, fireEvent, waitFor, configure } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterAll } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { App } from "antd";
import { useAuthStore } from "../../store/authStore";
import * as capaApi from "../../api/capa";
import CAPAListPage from "./CAPAListPage";

configure({ testIdAttribute: "data-e2e" });
afterAll(() => configure({ testIdAttribute: "data-testid" }));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (_k: string, fallback?: string) => fallback || _k }),
}));

vi.mock("../../api/capa");
vi.mock("../../api/supplier", () => ({
  listSuppliers: vi.fn().mockResolvedValue({
    items: [
      { supplier_id: "sup-1", supplier_no: "S-001", name: "Acme" },
      { supplier_id: "sup-2", supplier_no: "S-002", name: "Bolt" },
    ],
    total: 2,
    page: 1,
    page_size: 20,
  }),
}));

function renderPage() {
  return render(
    <App>
      <BrowserRouter>
        <CAPAListPage />
      </BrowserRouter>
    </App>
  );
}

describe("CAPAListPage create form supplier select", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(capaApi.listCAPAs).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    vi.mocked(capaApi.createCAPA).mockResolvedValue({
      report_id: "r-1",
      document_no: "8D-2026-001",
      title: "T",
      status: "D1_TEAM",
      severity: "一般",
    } as any);
    useAuthStore.setState({
      user: {
        user_id: "u1",
        username: "engineer",
        role_key: "quality_engineer",
        permissions: { capa: 3 },
        product_lines: [{ product_line_code: "DC-DC-100" }],
      } as any,
      token: "test-token",
    });
  });

  it("renders optional supplier select", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /新建/ }));

    await waitFor(() => {
      expect(screen.getByLabelText(/关联供应商/)).toBeInTheDocument();
    });
  });

  it("includes supplier_id in create request when selected", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /新建/ }));

    await waitFor(() => expect(screen.getByLabelText(/关联供应商/)).toBeInTheDocument());

    // document_no
    fireEvent.change(screen.getByPlaceholderText(/如 8D-2026-001/), {
      target: { value: "8D-2026-001" },
    });
    // title
    fireEvent.change(screen.getByPlaceholderText(/如 焊接不良客诉/), {
      target: { value: "T" },
    });

    // open supplier select and choose first option
    fireEvent.mouseDown(screen.getByLabelText(/关联供应商/));
    await waitFor(() => expect(screen.getByText("S-001 - Acme")).toBeInTheDocument());
    fireEvent.click(screen.getByText("S-001 - Acme"));

    // submit modal
    fireEvent.click(screen.getByRole("button", { name: /OK|确 定|确定/ }));

    await waitFor(() => {
      expect(capaApi.createCAPA).toHaveBeenCalledWith(
        expect.objectContaining({ supplier_id: "sup-1" })
      );
    });
  });
});

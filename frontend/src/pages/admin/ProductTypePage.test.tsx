import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "antd";
import ProductTypePage from "./ProductTypePage";

vi.mock("../../api/productType", () => ({
  listProductTypes: vi.fn().mockResolvedValue([{ code: "POWER", name: "电源类", description: null, is_active: true, created_at: "", updated_at: "" }]),
  createProductType: vi.fn().mockResolvedValue({}),
  updateProductType: vi.fn(),
  deleteProductType: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

describe("ProductTypePage", () => {
  it("lists existing product types", async () => {
    render(<App><MemoryRouter><ProductTypePage /></MemoryRouter></App>);
    await waitFor(() => expect(screen.getByText("POWER")).toBeInTheDocument());
  });
});

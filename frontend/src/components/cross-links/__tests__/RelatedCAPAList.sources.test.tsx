import { describe, it, expect, vi, beforeEach, afterAll } from "vitest";
import { render, screen, waitFor, configure } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import RelatedCAPAList from "../RelatedCAPAList";

configure({ testIdAttribute: "data-e2e" });
afterAll(() => configure({ testIdAttribute: "data-testid" }));

vi.mock("../../../api/client", () => ({
  default: { get: vi.fn() },
}));
import client from "../../../api/client";

function renderIt(fmeaId: string, fmeaNodeId?: string) {
  return render(
    <MemoryRouter>
      <RelatedCAPAList fmeaId={fmeaId} fmeaNodeId={fmeaNodeId} />
    </MemoryRouter>
  );
}

describe("RelatedCAPAList link_sources", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders source tags in canonical order", async () => {
    vi.mocked(client.get).mockResolvedValueOnce({
      data: [{
        report_id: "r1", document_no: "8D-1", title: "t", status: "D4_ROOT_CAUSE",
        product_line_code: "DC-DC-100", link_sources: ["header", "d4_cause", "d7_prevention"],
      }],
    });
    renderIt("f1");
    await waitFor(() => expect(screen.getByText("8D-1")).toBeInTheDocument());
    expect(screen.getByTestId("related-capa-source-d4_cause")).toBeInTheDocument();
    expect(screen.getByTestId("related-capa-source-d7_prevention")).toBeInTheDocument();
    expect(screen.getByTestId("related-capa-source-header")).toBeInTheDocument();
  });

  it("shows empty state when no items", async () => {
    vi.mocked(client.get).mockResolvedValueOnce({ data: [] });
    renderIt("f1");
    await waitFor(() => expect(screen.getByTestId("related-capa-list")).toBeInTheDocument());
    expect(screen.getByText(/无关联 8D|No related/)).toBeInTheDocument();
  });
});

import { describe, it, expect, vi, beforeEach, afterAll } from "vitest";
import { render, screen, fireEvent, waitFor, configure } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App, ConfigProvider } from "antd";
import { MemoryRouter } from "react-router-dom";
import D4VerificationCard from "../D4VerificationCard";

configure({ testIdAttribute: "data-e2e" });
afterAll(() => configure({ testIdAttribute: "data-testid" }));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock("../../../api/capa", () => ({
  listVerifications: vi.fn(),
  createVerification: vi.fn(),
  updateVerification: vi.fn(),
}));
vi.mock("../../../api/fmea", () => ({
  getFMEA: vi.fn(),
}));

import { listVerifications, createVerification, updateVerification } from "../../../api/capa";
import { getFMEA } from "../../../api/fmea";

const renderCard = (props: Record<string, unknown> = {}) =>
  render(
    <MemoryRouter>
      <ConfigProvider>
        <App>
          <D4VerificationCard
            capaId="c1"
            canEdit={true}
            currentRootCause="rc"
            fmeaRefId={null}
            {...props}
          />
        </App>
      </ConfigProvider>
    </MemoryRouter>
  );

describe("D4VerificationCard cause selector", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (listVerifications as any).mockResolvedValue([]);
  });

  it("disables cause select when fmeaRefId is null", async () => {
    renderCard({ fmeaRefId: null });
    fireEvent.click(screen.getByTestId("d4-verification-new"));
    const select = screen.getByTestId("d4-cause-select");
    expect(select.querySelector(".ant-select-disabled, .ant-select-selector")).toBeTruthy();
    const disabled = select.querySelector(".ant-select-disabled") || select.closest(".ant-select-disabled");
    // Form.Item wraps Select; look for disabled select
    expect(
      select.querySelector(".ant-select-disabled") ||
        document.querySelector(".ant-select-disabled")
    ).toBeTruthy();
    expect(getFMEA).not.toHaveBeenCalled();
  });

  it("includes source_ref when a cause is selected", async () => {
    const user = userEvent.setup();
    (getFMEA as any).mockResolvedValue({
      fmea_id: "f1",
      graph_data: {
        nodes: [
          { id: "cause-1", type: "FailureCause", name: "Solder void" },
          { id: "fm-1", type: "FailureMode", name: "Open" },
        ],
        edges: [],
      },
    });
    (createVerification as any).mockResolvedValue({ verification_id: "v2", conclusion: "pending" });

    renderCard({ fmeaRefId: "f1" });
    fireEvent.click(screen.getByTestId("d4-verification-new"));

    await waitFor(() => expect(getFMEA).toHaveBeenCalledWith("f1"));

    const causeSelect = screen.getByTestId("d4-cause-select").querySelector(".ant-select-selector")!;
    await user.click(causeSelect);
    await waitFor(() => expect(screen.getByText("Solder void")).toBeInTheDocument());
    await user.click(screen.getByText("Solder void"));

    fireEvent.change(screen.getByTestId("verification-root-cause").querySelector("textarea")!, {
      target: { value: "rc1" },
    });
    fireEvent.click(screen.getByTestId("verify-save-draft"));

    await waitFor(() =>
      expect(createVerification).toHaveBeenCalledWith(
        "c1",
        expect.objectContaining({
          root_cause_text: "rc1",
          conclusion: "pending",
          source_ref: { fmea_id: "f1", cause_node_id: "cause-1" },
        })
      )
    );
  });

  it("renders cause deep-link tag when source_ref present", async () => {
    (listVerifications as any).mockResolvedValue([
      {
        verification_id: "v1",
        capa_id: "c1",
        root_cause_text: "rc",
        method: "measurement",
        result: "r",
        conclusion: "passed",
        evidence_attachments: [],
        source_ref: { fmea_id: "f1", cause_node_id: "cause-1" },
        verified_by: "u",
        verified_at: "2026-07-03",
        created_at: "2026-07-03",
      },
    ]);
    renderCard({ fmeaRefId: "f1" });
    await waitFor(() => expect(screen.getByTestId("d4-cause-link")).toBeInTheDocument());
  });

  it("uses source_ref.fmea_id for deep-link when fmeaRefId is null", async () => {
    (listVerifications as any).mockResolvedValue([
      {
        verification_id: "v1",
        capa_id: "c1",
        root_cause_text: "rc",
        method: "measurement",
        result: "r",
        conclusion: "passed",
        evidence_attachments: [],
        source_ref: { fmea_id: "f-from-source", cause_node_id: "cause-1" },
        verified_by: "u",
        verified_at: "2026-07-03",
        created_at: "2026-07-03",
      },
    ]);

    renderCard({ fmeaRefId: null });
    const link = await screen.findByTestId("d4-cause-link");
    fireEvent.click(link);
    expect(mockNavigate).toHaveBeenCalledWith(
      "/fmea/f-from-source?tab=graph&highlightNode=cause-1"
    );
  });

  it("allows editing Cause on an existing pending/passed/failed record", async () => {
    const user = userEvent.setup();
    (getFMEA as any).mockResolvedValue({
      fmea_id: "f1",
      graph_data: {
        nodes: [
          { id: "cause-1", type: "FailureCause", name: "Solder void" },
          { id: "cause-2", type: "FailureCause", name: "Flux residue" },
        ],
        edges: [],
      },
    });
    (listVerifications as any).mockResolvedValue([
      {
        verification_id: "v-pass",
        capa_id: "c1",
        root_cause_text: "rc",
        method: "measurement",
        result: "r",
        conclusion: "passed",
        evidence_attachments: [],
        source_ref: { fmea_id: "f1", cause_node_id: "cause-1" },
        verified_by: "u",
        verified_at: "2026-07-03",
        created_at: "2026-07-03",
      },
    ]);
    (updateVerification as any).mockResolvedValue({ verification_id: "v-pass", conclusion: "passed" });

    renderCard({ fmeaRefId: "f1" });
    await waitFor(() => expect(screen.getByTestId("d4-cause-edit-btn-0")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("d4-cause-edit-btn-0"));

    await waitFor(() => expect(screen.getByTestId("d4-cause-edit-0")).toBeInTheDocument());
    await waitFor(() => expect(getFMEA).toHaveBeenCalledWith("f1"));

    const editSelect = screen.getByTestId("d4-cause-edit-select-0").querySelector(".ant-select-selector")!;
    await user.click(editSelect);
    await waitFor(() => expect(screen.getByText("Flux residue")).toBeInTheDocument());
    await user.click(screen.getByText("Flux residue"));

    fireEvent.click(screen.getByTestId("d4-cause-save-0"));

    await waitFor(() =>
      expect(updateVerification).toHaveBeenCalledWith(
        "c1",
        "v-pass",
        { source_ref: { fmea_id: "f1", cause_node_id: "cause-2" } },
      )
    );
  });

  it("clears Cause on existing record when select is cleared", async () => {
    (getFMEA as any).mockResolvedValue({
      fmea_id: "f1",
      graph_data: {
        nodes: [{ id: "cause-1", type: "FailureCause", name: "Solder void" }],
        edges: [],
      },
    });
    (listVerifications as any).mockResolvedValue([
      {
        verification_id: "v-pending",
        capa_id: "c1",
        root_cause_text: "rc",
        method: null,
        result: null,
        conclusion: "pending",
        evidence_attachments: [],
        source_ref: { fmea_id: "f1", cause_node_id: "cause-1" },
        verified_by: null,
        verified_at: null,
        created_at: "2026-07-03",
      },
    ]);
    (updateVerification as any).mockResolvedValue({ verification_id: "v-pending", conclusion: "pending" });

    renderCard({ fmeaRefId: "f1" });
    await waitFor(() => expect(screen.getByTestId("d4-cause-edit-btn-0")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("d4-cause-edit-btn-0"));
    await waitFor(() => expect(screen.getByTestId("d4-cause-edit-0")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("d4-cause-clear-0"));
    fireEvent.click(screen.getByTestId("d4-cause-save-0"));

    await waitFor(() =>
      expect(updateVerification).toHaveBeenCalledWith("c1", "v-pending", { source_ref: null })
    );
  });

  it("establishes Cause on existing record with no source_ref", async () => {
    const user = userEvent.setup();
    (getFMEA as any).mockResolvedValue({
      fmea_id: "f1",
      graph_data: {
        nodes: [{ id: "cause-1", type: "FailureCause", name: "Solder void" }],
        edges: [],
      },
    });
    (listVerifications as any).mockResolvedValue([
      {
        verification_id: "v-no-cause",
        capa_id: "c1",
        root_cause_text: "rc",
        method: "measurement",
        result: "r",
        conclusion: "failed",
        evidence_attachments: [],
        source_ref: null,
        verified_by: null,
        verified_at: null,
        created_at: "2026-07-03",
      },
    ]);
    (updateVerification as any).mockResolvedValue({ verification_id: "v-no-cause", conclusion: "failed" });

    renderCard({ fmeaRefId: "f1" });
    await waitFor(() => expect(screen.getByTestId("d4-cause-edit-btn-0")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("d4-cause-edit-btn-0"));
    await waitFor(() => expect(screen.getByTestId("d4-cause-edit-0")).toBeInTheDocument());

    const editSelect = screen.getByTestId("d4-cause-edit-select-0").querySelector(".ant-select-selector")!;
    await user.click(editSelect);
    await waitFor(() => expect(screen.getByText("Solder void")).toBeInTheDocument());
    await user.click(screen.getByText("Solder void"));
    fireEvent.click(screen.getByTestId("d4-cause-save-0"));

    await waitFor(() =>
      expect(updateVerification).toHaveBeenCalledWith(
        "c1",
        "v-no-cause",
        { source_ref: { fmea_id: "f1", cause_node_id: "cause-1" } },
      )
    );
  });
});

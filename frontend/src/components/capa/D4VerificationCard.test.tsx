import { describe, it, expect, vi, beforeEach, afterAll } from "vitest";
import { render, screen, fireEvent, waitFor, configure, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
configure({ testIdAttribute: "data-e2e" });
afterAll(() => configure({ testIdAttribute: "data-testid" }));
import { App, ConfigProvider } from "antd";
import { MemoryRouter } from "react-router-dom";
import D4VerificationCard from "./D4VerificationCard";

vi.mock("../../api/capa", () => ({
  listVerifications: vi.fn(),
  createVerification: vi.fn(),
  updateVerification: vi.fn(),
}));

import { listVerifications, createVerification, updateVerification } from "../../api/capa";

const renderCard = (props = {}) => render(
  <MemoryRouter>
    <ConfigProvider><App><D4VerificationCard capaId="c1" canEdit={true} currentRootCause="rc" fmeaRefId={null} {...props} /></App></ConfigProvider>
  </MemoryRouter>
);

beforeEach(() => vi.clearAllMocks());

describe("D4VerificationCard", () => {
  it("creates verification via POST with conclusion=passed + full payload", async () => {
    const user = userEvent.setup();
    (listVerifications as any).mockResolvedValue([]);
    (createVerification as any).mockResolvedValue({ verification_id: "v2", conclusion: "passed" });
    renderCard();
    fireEvent.click(screen.getByTestId("d4-verification-new"));
    fireEvent.change(screen.getByTestId("verification-root-cause").querySelector("textarea")!, { target: { value: "rc1" } });
    const methodSelect = screen.getByTestId("verification-method").querySelector(".ant-select-selector")!;
    await user.click(methodSelect);
    await waitFor(() => expect(screen.getByText("Measurement")).toBeInTheDocument());
    await user.click(screen.getByText("Measurement"));
    fireEvent.change(screen.getByTestId("verification-result").querySelector("textarea")!, { target: { value: "ok" } });
    fireEvent.click(screen.getByTestId("verify-pass"));
    await waitFor(() => expect(createVerification).toHaveBeenCalledWith("c1", {
      root_cause_text: "rc1",
      method: "measurement",
      result: "ok",
      conclusion: "passed",
      evidence_attachments: [],
      source_ref: null,
    }, expect.any(AbortSignal)));
  });

  it("patches existing record conclusion=failed via list inline button (PATCH not re-POST)", async () => {
    (listVerifications as any).mockResolvedValue([
      { verification_id: "v1", capa_id: "c1", root_cause_text: "rc", method: "measurement",
        result: "r", conclusion: "pending", evidence_attachments: [], source_ref: null,
        verified_by: null, verified_at: null, created_at: "2026-07-03" },
    ]);
    (updateVerification as any).mockResolvedValue({ verification_id: "v1", conclusion: "failed" });
    renderCard();
    await waitFor(() => expect(screen.queryByTestId("verification-item-0")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("verify-fail-0"));
    await waitFor(() => expect(updateVerification).toHaveBeenCalledWith("c1", "v1", { conclusion: "failed" }, expect.any(AbortSignal)));
    expect(createVerification).not.toHaveBeenCalled();
  });

  it("patches existing draft->passed via list inline button", async () => {
    (listVerifications as any).mockResolvedValue([
      { verification_id: "v1", capa_id: "c1", root_cause_text: "rc", method: "observation",
        result: "r", conclusion: "pending", evidence_attachments: [{ filename: "a.jpg", size: 1 }], source_ref: null,
        verified_by: null, verified_at: null, created_at: "2026-07-03" },
    ]);
    (updateVerification as any).mockResolvedValue({ verification_id: "v1", conclusion: "passed" });
    renderCard();
    await waitFor(() => expect(screen.queryByTestId("verification-item-0")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("verify-pass-0"));
    await waitFor(() => expect(updateVerification).toHaveBeenCalledWith("c1", "v1", { conclusion: "passed" }, expect.any(AbortSignal)));
  });

  it("passed submit blocked when all details empty (cross-field validator)", async () => {
    (listVerifications as any).mockResolvedValue([]);
    (createVerification as any).mockResolvedValue({ verification_id: "v2", conclusion: "passed" });
    renderCard();
    fireEvent.click(screen.getByTestId("d4-verification-new"));
    fireEvent.click(screen.getByTestId("verify-pass"));
    await waitFor(() => expect(createVerification).not.toHaveBeenCalled());
  });

  it("renders conclusion three-state tag (draft/passed/failed), not 2-state is_verified", async () => {
    (listVerifications as any).mockResolvedValue([
      { verification_id: "v1", capa_id: "c1", root_cause_text: "rc1", method: "measurement",
        result: "r", conclusion: "pending", evidence_attachments: [], source_ref: null,
        verified_by: null, verified_at: null, created_at: "2026-07-03" },
      { verification_id: "v2", capa_id: "c1", root_cause_text: "rc2", method: "observation",
        result: "r", conclusion: "passed", evidence_attachments: [], source_ref: null,
        verified_by: "u", verified_at: "2026-07-03", created_at: "2026-07-03" },
      { verification_id: "v3", capa_id: "c1", root_cause_text: "rc3", method: "reproduction",
        result: "r", conclusion: "failed", evidence_attachments: [], source_ref: null,
        verified_by: null, verified_at: null, created_at: "2026-07-03" },
    ]);
    renderCard();
    await waitFor(() => expect(screen.queryByTestId("verification-conclusion-0")).toBeInTheDocument());
    expect(screen.getByTestId("verification-conclusion-0").textContent).toContain("⏳");
    expect(screen.getByTestId("verification-conclusion-1").textContent).toContain("✅");
    expect(screen.getByTestId("verification-conclusion-2").textContent).toContain("❌");
    expect(screen.queryByTestId("verification-is-verified")).not.toBeInTheDocument();
  });

  it("save-draft creates pending record without detail validation", async () => {
    (listVerifications as any).mockResolvedValue([]);
    (createVerification as any).mockResolvedValue({ verification_id: "v2", conclusion: "pending" });
    renderCard();
    fireEvent.click(screen.getByTestId("d4-verification-new"));
    fireEvent.change(screen.getByTestId("verification-root-cause").querySelector("textarea")!, { target: { value: "rc1" } });
    fireEvent.click(screen.getByTestId("verify-save-draft"));
    await waitFor(() => expect(createVerification).toHaveBeenCalledWith("c1", {
      root_cause_text: "rc1",
      method: undefined,
      result: undefined,
      conclusion: "pending",
      evidence_attachments: [],
      source_ref: null,
    }, expect.any(AbortSignal)));
  });

  it("renders method Select with three options", async () => {
    const user = userEvent.setup();
    (listVerifications as any).mockResolvedValue([]);
    renderCard();
    fireEvent.click(screen.getByTestId("d4-verification-new"));
    const methodSelect = screen.getByTestId("verification-method").querySelector(".ant-select-selector")!;
    await user.click(methodSelect);
    await waitFor(() => {
      expect(screen.getByText("Measurement")).toBeInTheDocument();
      expect(screen.getByText("Observation")).toBeInTheDocument();
      expect(screen.getByText("Reproduction")).toBeInTheDocument();
    });
  });
});

it('retains readonly known source restrictions when current reference is cleared',async()=>{
 (listVerifications as any).mockResolvedValue([{verification_id:'v1',capa_id:'c1',root_cause_text:'rc',method:null,result:null,conclusion:'pending',is_verified:false,evidence_attachments:[],source_ref:null,known_source_origins:[{kind:'fmea',fmea_id:'historical-fmea',cause_node_id:'historical-cause',factory_id:'factory',product_line_code:'line'}],verified_by:null,verified_at:null,created_at:'2026-11-16'}]);
 renderCard({currentRootCause:null,fmeaRefId:null,canEdit:false});
 expect(await screen.findByText(/historical-fmea/)).toBeInTheDocument();
 expect(screen.getByText(/清空或替换当前引用不解除已知来源限制/)).toBeInTheDocument();
});

it('clears retained verification evidence after a later read revokes source access',async()=>{
 (listVerifications as any).mockResolvedValue([{verification_id:'v1',capa_id:'c1',root_cause_text:'protected-verification',method:null,result:null,conclusion:'pending',is_verified:false,evidence_attachments:[],source_ref:null,known_source_origins:[],verified_by:null,verified_at:null,created_at:'2026-11-16'}]);
 renderCard({canEdit:false});await screen.findByText('protected-verification');
 (listVerifications as any).mockRejectedValue({response:{status:403}});
 await waitFor(()=>expect(screen.queryByText('protected-verification')).toBeNull(),{timeout:3000});
});

it('does not restore an older authorized verification body after a newer poll returns 403',async()=>{
 let resolve!:(v:any)=>void;
 (listVerifications as any).mockReturnValueOnce(new Promise(r=>resolve=r)).mockRejectedValue({response:{status:403}});
 renderCard({canEdit:false});
 await waitFor(()=>expect(listVerifications).toHaveBeenCalledTimes(2),{timeout:3000});
 await act(async()=>resolve([{verification_id:'old-v',capa_id:'c1',root_cause_text:'revoked-old-root',method:null,result:null,conclusion:'pending',is_verified:false,evidence_attachments:[],source_ref:null,known_source_origins:[{kind:'fmea',fmea_id:'revoked-fmea',cause_node_id:'revoked-cause',factory_id:'factory',product_line_code:'line'}],verified_by:null,verified_at:null,created_at:'2026-11-16'}]));
 expect(screen.queryByText('revoked-old-root')).toBeNull();
 expect(screen.queryByText(/revoked-fmea/)).toBeNull();
});

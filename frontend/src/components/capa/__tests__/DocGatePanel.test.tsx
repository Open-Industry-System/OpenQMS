import { describe, it, expect, vi, afterAll } from "vitest";
import { render, screen, configure } from "@testing-library/react";
configure({ testIdAttribute: "data-e2e" });
afterAll(() => configure({ testIdAttribute: "data-testid" }));
import { App, ConfigProvider } from "antd";
import DocGatePanel from "../DocGatePanel";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback || key,
  }),
}));

vi.mock("../../../api/capa", () => ({
  docGateImpact: vi.fn(),
  getDocGateImpact: vi.fn(),
  runDocGateAudit: vi.fn(),
  getDocGateAudit: vi.fn().mockResolvedValue({ audit_run_id: null, audits: [] }),
  recordDocGateDefer: vi.fn(),
  confirmNoAffected: vi.fn(),
  getDocGateDecision: vi.fn().mockResolvedValue({ decision: null }),
  advanceCAPA: vi.fn(),
}));

function wrap(ui: React.ReactElement) {
  return render(
    <ConfigProvider>
      <App>{ui}</App>
    </ConfigProvider>,
  );
}

describe("DocGatePanel", () => {
  it("renders blocked banner when no LLM", () => {
    wrap(
      <DocGatePanel
        capaId="x"
        analysis={{ status: "failed", error: "LLM 未配置" }}
        decision={null}
        canEdit
      />,
    );
    expect(screen.getByTestId("doc-gate-blocked-banner")).toBeInTheDocument();
  });

  it("hides advance button when decision not passed", () => {
    wrap(
      <DocGatePanel
        capaId="x"
        analysis={{ status: "done", affected_docs: [{ doc_type: "fmea", doc_id: "1", doc_name: "F", key_points: [{}], update_suggestion: "s" }] }}
        decision={{ decision: "blocked" }}
        canEdit
      />,
    );
    expect(screen.queryByTestId("doc-gate-advance")).not.toBeInTheDocument();
  });

  it("shows advance button when decision passed", () => {
    wrap(
      <DocGatePanel
        capaId="x"
        analysis={{ status: "done", affected_docs: [{ doc_type: "fmea", doc_id: "1", doc_name: "F", key_points: [{}], update_suggestion: "s" }] }}
        decision={{ decision: "passed" }}
        canEdit
      />,
    );
    expect(screen.getByTestId("doc-gate-advance")).toBeInTheDocument();
  });

  it("shows empty-list confirm when affected_docs empty", () => {
    wrap(
      <DocGatePanel
        capaId="x"
        analysis={{ status: "done", affected_docs: [] }}
        decision={null}
        canEdit
      />,
    );
    expect(screen.getByTestId("doc-gate-empty-list")).toBeInTheDocument();
    expect(screen.getByTestId("doc-gate-confirm-empty")).toBeInTheDocument();
  });

  it("hides generate for read-only", () => {
    wrap(
      <DocGatePanel
        capaId="x"
        analysis={null}
        decision={null}
        canEdit={false}
      />,
    );
    expect(screen.queryByTestId("doc-gate-generate")).not.toBeInTheDocument();
  });

  it("renders version before→after and coverage details when audits present", () => {
    wrap(
      <DocGatePanel
        capaId="x"
        analysis={{
          status: "done",
          affected_docs: [
            {
              doc_type: "fmea",
              doc_id: "d1",
              doc_name: "FMEA-1",
              key_points: [{}],
              update_suggestion: "s",
            },
          ],
        }}
        decision={{ decision: "blocked" }}
        audits={[
          {
            doc_type: "fmea",
            doc_id: "d1",
            doc_name: "FMEA-1",
            status: "incomplete",
            version_bump: true,
            covered_count: 0,
            total_count: 1,
            version_before: { major: 1, minor: 0 },
            version_after: { major: 1, minor: 1 },
            coverage: [
              {
                covered: false,
                key_point: {
                  expected_action: "modify",
                  target_kind: "fmea_node",
                  target_key: "node-1",
                  field: "prevention_control",
                },
              },
            ],
          },
        ]}
        canEdit
      />,
    );
    expect(screen.getByTestId("doc-gate-audit-table")).toBeInTheDocument();
    expect(screen.getByText("v1.0 → v1.1")).toBeInTheDocument();
    // expandable coverage row content is rendered when expanded; count column still shows
    expect(screen.getByText("0/1")).toBeInTheDocument();
  });
});

import { describe, it, expect, vi, beforeEach, afterAll } from "vitest";
import { render, screen, fireEvent, waitFor, configure } from "@testing-library/react";
configure({ testIdAttribute: "data-e2e" }); // 生产组件用 data-e2e（计划 Global Constraint），切 Testing Library 的 testIdAttribute
afterAll(() => configure({ testIdAttribute: "data-testid" })); // 复位默认，防止 vitest 非默认隔离配置下泄漏到后续测试文件
import { App, ConfigProvider } from "antd";
import D4VerificationCard from "./D4VerificationCard";

vi.mock("../../api/capa", () => ({
  listVerifications: vi.fn(),
  createVerification: vi.fn(),
  updateVerification: vi.fn(),
}));

import { listVerifications, createVerification, updateVerification } from "../../api/capa";

const renderCard = (props = {}) => render(
  <ConfigProvider><App><D4VerificationCard capaId="c1" canEdit={true} currentRootCause="rc" {...props} /></App></ConfigProvider>
);

beforeEach(() => vi.clearAllMocks());

describe("D4VerificationCard", () => {
  it("renders existing verification records", async () => {
    (listVerifications as any).mockResolvedValue([
      { verification_id: "v1", capa_id: "c1", root_cause_text: "rc", method: "m",
        result: "r", is_verified: true, evidence_attachments: [], source_ref: null,
        verified_by: "u", verified_at: "2026-07-03", created_at: "2026-07-03" },
    ]);
    renderCard();
    await waitFor(() => expect(screen.queryByTestId("verification-item-0")).toBeInTheDocument());
    // test-setup.ts 把 i18n 切到 en-US，不要断言中文文案；组件 verified 时渲染 "✅"，按图标断言语言无关
    expect(screen.getByTestId("verification-status").textContent).toContain("✅");
  });

  it("creates a verification record on submit", async () => {
    (listVerifications as any).mockResolvedValue([]);
    (createVerification as any).mockResolvedValue({ verification_id: "v2", is_verified: true });
    renderCard();
    fireEvent.click(screen.getByTestId("d4-verification-new"));
    fireEvent.change(screen.getByTestId("verification-root-cause").querySelector("textarea")!, { target: { value: "新根因" } });
    fireEvent.click(screen.getByTestId("verification-submit"));
    await waitFor(() => expect(createVerification).toHaveBeenCalledWith("c1", expect.objectContaining({ root_cause_text: "新根因" })));
  });

  it("PATCHes is_verified via switch", async () => {
    (listVerifications as any).mockResolvedValue([
      { verification_id: "v1", capa_id: "c1", root_cause_text: "rc", method: "", result: "",
        is_verified: false, evidence_attachments: [], source_ref: null,
        verified_by: null, verified_at: null, created_at: "2026-07-03" },
    ]);
    (updateVerification as any).mockResolvedValue({ verification_id: "v1", is_verified: true });
    renderCard();
    await waitFor(() => expect(screen.queryByTestId("verification-item-0")).toBeInTheDocument());
    // Ant Switch 根节点本身就是 <button>，data-e2e 落在根 button 上——直接 click testid 节点，
    // 不要再 .querySelector("button")（Switch 内部无子 button，会返回 null 导致 NPE）
    fireEvent.click(screen.getByTestId("verification-is-verified"));
    await waitFor(() => expect(updateVerification).toHaveBeenCalledWith("c1", "v1", expect.objectContaining({ is_verified: true })));
  });
});

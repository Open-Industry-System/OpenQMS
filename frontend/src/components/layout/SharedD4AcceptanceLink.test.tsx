import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SharedD4AcceptanceLink } from "./AppLayout";

const SHARED_HOSTNAME = "test.preview.openqms.smartindustry.world";

describe("SharedD4AcceptanceLink", () => {
  it.each(["field_qe", "manager"])("directs %s to the trusted D4 portal", (roleKey) => {
    render(<SharedD4AcceptanceLink roleKey={roleKey} hostname={SHARED_HOSTNAME} />);

    const link = screen.getByRole("link", { name: "D4 Acceptance" });
    expect(link).toHaveAttribute("href", "https://d4.preview.openqms.smartindustry.world/");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it.each([undefined, "viewer", "admin"])("hides the entry for %s", (roleKey) => {
    render(<SharedD4AcceptanceLink roleKey={roleKey} hostname={SHARED_HOSTNAME} />);

    expect(screen.queryByRole("link", { name: "D4 Acceptance" })).toBeNull();
  });

  it.each([
    "qms.smartindustry.world",
    "pr-45.preview.openqms.smartindustry.world",
    "test.preview.openqms.smartindustry.world.example",
  ])("hides the entry outside the shared site at %s", (hostname) => {
    render(<SharedD4AcceptanceLink roleKey="manager" hostname={hostname} />);

    expect(screen.queryByRole("link", { name: "D4 Acceptance" })).toBeNull();
  });
});

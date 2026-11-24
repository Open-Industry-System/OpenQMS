import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SharedD4AcceptanceLink } from "./AppLayout";

const SHARED_HOSTNAME = "test.preview.openqms.smartindustry.world";

describe("SharedD4AcceptanceLink", () => {
  it.each([
    ["engineer", "field_qe"],
    ["manager", "manager"],
  ])("directs the private %s account to the trusted D4 portal", (username, roleKey) => {
    render(<SharedD4AcceptanceLink username={username} roleKey={roleKey} hostname={SHARED_HOSTNAME} />);

    const link = screen.getByRole("link", { name: "D4 Acceptance" });
    expect(link).toHaveAttribute("href", "https://d4.preview.openqms.smartindustry.world/");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it.each([
    [undefined, undefined],
    ["viewer", "viewer"],
    ["admin", "admin"],
    ["engineer", undefined],
    ["engineer", "manager"],
    ["demo-engineer", "field_qe"],
    ["demo-manager", "manager"],
  ])("hides the entry for %s with role %s", (username, roleKey) => {
    render(<SharedD4AcceptanceLink username={username} roleKey={roleKey} hostname={SHARED_HOSTNAME} />);

    expect(screen.queryByRole("link", { name: "D4 Acceptance" })).toBeNull();
  });

  it.each([
    "qms.smartindustry.world",
    "pr-45.preview.openqms.smartindustry.world",
    "test.preview.openqms.smartindustry.world.example",
  ])("hides the entry outside the shared site at %s", (hostname) => {
    render(<SharedD4AcceptanceLink username="manager" roleKey="manager" hostname={hostname} />);

    expect(screen.queryByRole("link", { name: "D4 Acceptance" })).toBeNull();
  });
});

import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import GraphToolbar from "../GraphToolbar";

describe("GraphToolbar direction selector", () => {
  it("enables the direction Segmented when layout is dagre", () => {
    render(
      <GraphToolbar
        layout="dagre"
        direction="TB"
        onLayoutChange={() => {}}
        onDirectionChange={() => {}}
        onZoomIn={() => {}}
        onZoomOut={() => {}}
        onFitView={() => {}}
        onDownload={() => {}}
      />,
    );
    // The "Top to Bottom" option is the selected (active) segment — not disabled.
    const tb = screen.getByText("Top to Bottom").closest("button") ?? screen.getByText("Top to Bottom");
    expect((tb as HTMLElement).closest("[aria-disabled='true']")).toBeNull();
  });

  it("disables the direction Segmented when layout is force", () => {
    const onDirectionChange = vi.fn();
    render(
      <GraphToolbar
        layout="force"
        direction="TB"
        onLayoutChange={() => {}}
        onDirectionChange={onDirectionChange}
        onZoomIn={() => {}}
        onZoomOut={() => {}}
        onFitView={() => {}}
        onDownload={() => {}}
      />,
    );
    const segmented = screen.getByText("Top to Bottom").closest(".ant-segmented");
    expect(segmented?.className).toContain("ant-segmented-disabled");
    // Clicking the disabled segmented item does not fire onDirectionChange.
    fireEvent.click(screen.getByText("Top to Bottom"));
    expect(onDirectionChange).not.toHaveBeenCalled();
  });

  it("lets the hierarchical button switch back to dagre from force", () => {
    const onLayoutChange = vi.fn();
    render(
      <GraphToolbar
        layout="force"
        direction="TB"
        onLayoutChange={onLayoutChange}
        onDirectionChange={() => {}}
        onZoomIn={() => {}}
        onZoomOut={() => {}}
        onFitView={() => {}}
        onDownload={() => {}}
      />,
    );
    // Tests run in en-US (see src/test-setup.ts), so toolbar.hierarchical renders as
    // "Hierarchical" — NOT "Hierarchy" (which would not match). The button must be
    // enabled so the user can switch back to dagre from force/compact-tree.
    const hierBtn = screen.getByRole("button", { name: /Hierarchical/ });
    expect(hierBtn).not.toBeDisabled();
    fireEvent.click(hierBtn);
    expect(onLayoutChange).toHaveBeenCalledWith("dagre");
  });
});

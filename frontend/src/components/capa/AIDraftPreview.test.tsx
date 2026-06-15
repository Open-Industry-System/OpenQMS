import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import AIDraftPreview from "./AIDraftPreview";

describe("AIDraftPreview", () => {
  it("renders when open", () => {
    render(
      <AIDraftPreview open={true} content="Test content" onClose={vi.fn()} onReplace={vi.fn()} onAppend={vi.fn()} />
    );
    expect(screen.getByText("AI Draft Preview")).toBeInTheDocument();
    expect(screen.getByText("Test content")).toBeInTheDocument();
  });

  it("does not render when closed", () => {
    render(
      <AIDraftPreview open={false} content="Test content" onClose={vi.fn()} onReplace={vi.fn()} onAppend={vi.fn()} />
    );
    expect(screen.queryByText("AI Draft Preview")).not.toBeInTheDocument();
  });

  it("shows warning about AI-generated content", () => {
    render(
      <AIDraftPreview open={true} content="Content" onClose={vi.fn()} onReplace={vi.fn()} onAppend={vi.fn()} />
    );
    expect(screen.getByText(/AI-generated draft/)).toBeInTheDocument();
  });

  it("calls onReplace when replace button clicked", () => {
    const onReplace = vi.fn();
    render(
      <AIDraftPreview open={true} content="Content" onClose={vi.fn()} onReplace={onReplace} onAppend={vi.fn()} />
    );
    const replaceBtn = screen.getByRole("button", { name: /Replace|Re place/ });
    fireEvent.click(replaceBtn);
    expect(onReplace).toHaveBeenCalledOnce();
  });

  it("calls onAppend when append button clicked", () => {
    const onAppend = vi.fn();
    render(
      <AIDraftPreview open={true} content="Content" onClose={vi.fn()} onReplace={vi.fn()} onAppend={onAppend} />
    );
    const appendBtn = screen.getByRole("button", { name: /Append|Ap pend/ });
    fireEvent.click(appendBtn);
    expect(onAppend).toHaveBeenCalledOnce();
  });

  it("calls onClose when cancel button clicked", () => {
    const onClose = vi.fn();
    render(
      <AIDraftPreview open={true} content="Content" onClose={onClose} onReplace={vi.fn()} onAppend={vi.fn()} />
    );
    const cancelBtn = screen.getByRole("button", { name: /Cancel|Can cel/ });
    fireEvent.click(cancelBtn);
    expect(onClose).toHaveBeenCalledOnce();
  });
});

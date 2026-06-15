import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import AIDraftButton from "./AIDraftButton";

describe("AIDraftButton", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders AI Draft button", () => {
    const onGenerate = vi.fn();
    render(<AIDraftButton loading={false} tempUnavailable={false} onGenerate={onGenerate} />);
    expect(screen.getByText("AI Draft")).toBeInTheDocument();
  });

  it("shows loading state", () => {
    const onGenerate = vi.fn();
    render(<AIDraftButton loading={true} tempUnavailable={false} onGenerate={onGenerate} />);
    expect(screen.getByText("Drafting...")).toBeInTheDocument();
  });

  it("calls onGenerate with structured format by default", () => {
    const onGenerate = vi.fn();
    render(<AIDraftButton loading={false} tempUnavailable={false} onGenerate={onGenerate} />);
    fireEvent.click(screen.getByText("AI Draft"));
    expect(onGenerate).toHaveBeenCalledWith("structured");
  });

  it("reads format from localStorage on mount", () => {
    localStorage.setItem("openqms_ai_draft_preference", JSON.stringify({ format: "paragraph" }));
    const onGenerate = vi.fn();

    render(<AIDraftButton loading={false} tempUnavailable={false} onGenerate={onGenerate} />);
    fireEvent.click(screen.getByText("AI Draft"));

    expect(onGenerate).toHaveBeenCalledWith("paragraph");
  });

  it("defaults to structured when localStorage has invalid value", () => {
    localStorage.setItem("openqms_ai_draft_preference", "invalid");
    const onGenerate = vi.fn();

    render(<AIDraftButton loading={false} tempUnavailable={false} onGenerate={onGenerate} />);
    fireEvent.click(screen.getByText("AI Draft"));

    expect(onGenerate).toHaveBeenCalledWith("structured");
  });

  it("persists format to localStorage with correct schema", () => {
    const onGenerate = vi.fn();
    render(<AIDraftButton loading={false} tempUnavailable={false} onGenerate={onGenerate} />);
    fireEvent.click(screen.getByText("AI Draft"));

    const stored = JSON.parse(localStorage.getItem("openqms_ai_draft_preference")!);
    expect(stored).toEqual({ format: "structured" });
  });

  it("is disabled when tempUnavailable", () => {
    const onGenerate = vi.fn();
    render(<AIDraftButton loading={false} tempUnavailable={true} onGenerate={onGenerate} />);
    const btn = screen.getByText("AI Draft").closest("button");
    expect(btn).toBeDisabled();
  });

  it("shows danger style when error is present", () => {
    const onGenerate = vi.fn();
    render(
      <AIDraftButton loading={false} tempUnavailable={false} error="Something went wrong" onGenerate={onGenerate} />
    );
    const btn = screen.getByText("AI Draft").closest("button");
    expect(btn?.title).toBe("Something went wrong");
  });
});

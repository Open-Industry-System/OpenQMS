import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import AIDraftButton from "./AIDraftButton";

describe("AIDraftButton", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders AI草拟 button", () => {
    const onGenerate = vi.fn();
    render(<AIDraftButton loading={false} tempUnavailable={false} onGenerate={onGenerate} />);
    expect(screen.getByText("AI草拟")).toBeInTheDocument();
  });

  it("shows loading state", () => {
    const onGenerate = vi.fn();
    render(<AIDraftButton loading={true} tempUnavailable={false} onGenerate={onGenerate} />);
    expect(screen.getByText("草拟中...")).toBeInTheDocument();
  });

  it("calls onGenerate with structured format by default", () => {
    const onGenerate = vi.fn();
    render(<AIDraftButton loading={false} tempUnavailable={false} onGenerate={onGenerate} />);
    fireEvent.click(screen.getByText("AI草拟"));
    expect(onGenerate).toHaveBeenCalledWith("structured");
  });

  it("reads format from localStorage on mount", () => {
    localStorage.setItem("capa_draft_format", "paragraph");
    const onGenerate = vi.fn();

    render(<AIDraftButton loading={false} tempUnavailable={false} onGenerate={onGenerate} />);
    fireEvent.click(screen.getByText("AI草拟"));

    expect(onGenerate).toHaveBeenCalledWith("paragraph");
  });

  it("defaults to structured when localStorage has invalid value", () => {
    localStorage.setItem("capa_draft_format", "invalid");
    const onGenerate = vi.fn();

    render(<AIDraftButton loading={false} tempUnavailable={false} onGenerate={onGenerate} />);
    fireEvent.click(screen.getByText("AI草拟"));

    expect(onGenerate).toHaveBeenCalledWith("structured");
  });

  it("is disabled when tempUnavailable", () => {
    const onGenerate = vi.fn();
    render(<AIDraftButton loading={false} tempUnavailable={true} onGenerate={onGenerate} />);
    const btn = screen.getByText("AI草拟").closest("button");
    expect(btn).toBeDisabled();
  });

  it("shows danger style when error is present", () => {
    const onGenerate = vi.fn();
    render(
      <AIDraftButton loading={false} tempUnavailable={false} error="出错了" onGenerate={onGenerate} />
    );
    const btn = screen.getByText("AI草拟").closest("button");
    expect(btn?.title).toBe("出错了");
  });
});
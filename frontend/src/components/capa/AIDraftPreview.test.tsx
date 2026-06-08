import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import AIDraftPreview from "./AIDraftPreview";

describe("AIDraftPreview", () => {
  it("renders when open", () => {
    render(
      <AIDraftPreview open={true} content="测试内容" onClose={vi.fn()} onReplace={vi.fn()} onAppend={vi.fn()} />
    );
    expect(screen.getByText("AI 草稿预览")).toBeInTheDocument();
    expect(screen.getByText("测试内容")).toBeInTheDocument();
  });

  it("does not render when closed", () => {
    render(
      <AIDraftPreview open={false} content="测试内容" onClose={vi.fn()} onReplace={vi.fn()} onAppend={vi.fn()} />
    );
    expect(screen.queryByText("AI 草稿预览")).not.toBeInTheDocument();
  });

  it("shows warning about AI-generated content", () => {
    render(
      <AIDraftPreview open={true} content="内容" onClose={vi.fn()} onReplace={vi.fn()} onAppend={vi.fn()} />
    );
    expect(screen.getByText(/AI 生成的草稿/)).toBeInTheDocument();
  });

  it("calls onReplace when replace button clicked", () => {
    const onReplace = vi.fn();
    render(
      <AIDraftPreview open={true} content="内容" onClose={vi.fn()} onReplace={onReplace} onAppend={vi.fn()} />
    );
    // Ant Design inserts spaces in button text: "替 换"
    const replaceBtn = screen.getByRole("button", { name: /替换|替 换/ });
    fireEvent.click(replaceBtn);
    expect(onReplace).toHaveBeenCalledOnce();
  });

  it("calls onAppend when append button clicked", () => {
    const onAppend = vi.fn();
    render(
      <AIDraftPreview open={true} content="内容" onClose={vi.fn()} onReplace={vi.fn()} onAppend={onAppend} />
    );
    const appendBtn = screen.getByRole("button", { name: /追加|追 加/ });
    fireEvent.click(appendBtn);
    expect(onAppend).toHaveBeenCalledOnce();
  });

  it("calls onClose when cancel button clicked", () => {
    const onClose = vi.fn();
    render(
      <AIDraftPreview open={true} content="内容" onClose={onClose} onReplace={vi.fn()} onAppend={vi.fn()} />
    );
    const cancelBtn = screen.getByRole("button", { name: /取消|取 消/ });
    fireEvent.click(cancelBtn);
    expect(onClose).toHaveBeenCalledOnce();
  });
});
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import EffectLinesEditor from "./EffectLinesEditor";
import type { GraphNode } from "../../types";

const mkNode = (id: string, name = ""): GraphNode => ({ id, type: "FailureEffect", name, severity: 0, occurrence: 0, detection: 0 });
const nodeMap = (nodes: GraphNode[]) => new Map(nodes.map((n) => [n.id, n]));

const baseProps = (overrides: Partial<Parameters<typeof EffectLinesEditor>[0]> = {}) => ({
  effectIds: ["fe1", "fe2"],
  nodeMap: nodeMap([mkNode("fe1", "烧毁电路"), mkNode("fe2", "机壳变形")]),
  fmeaId: "doc1",
  functionDescription: "供电",
  failureModeName: "过压",
  disabled: false,
  updateNode: vi.fn(),
  onAddEffect: vi.fn(),
  onDeleteEffect: vi.fn(),
  ...overrides,
});

describe("EffectLinesEditor", () => {
  it("renders one dropdown per effect", () => {
    render(<EffectLinesEditor {...baseProps()} />);
    expect(screen.getByDisplayValue("烧毁电路")).toBeInTheDocument();
    expect(screen.getByDisplayValue("机壳变形")).toBeInTheDocument();
  });

  it("add button calls onAddEffect", () => {
    const props = baseProps();
    render(<EffectLinesEditor {...props} />);
    fireEvent.click(screen.getByRole("button", { name: /添加失效影响/i }));
    expect(props.onAddEffect).toHaveBeenCalledTimes(1);
  });

  it("delete button calls onDeleteEffect with the effect id", () => {
    const props = baseProps();
    render(<EffectLinesEditor {...props} />);
    const deleteBtns = screen.getAllByRole("button", { name: /删除后果/i });
    fireEvent.click(deleteBtns[0]); // delete fe1
    expect(props.onDeleteEffect).toHaveBeenCalledWith("fe1");
  });
});

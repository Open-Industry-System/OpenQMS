import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { GraphNode, GraphEdge } from "../../types";
import { toolsRequiringNodeType } from "../../utils/wizardToolStructure";

// 最小 harness：复刻 renderStep1 里引导卡的渲染条件 + 一键创建回调。
function GuideHarness({ nodes, edges, selectedTools, map, onAdd }: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedTools: string[];
  map: Record<string, string>;
  onAdd: (nodeType: "Interface" | "DesignParameter") => void;
}) {
  const attachedCount = (nt: "Interface" | "DesignParameter") =>
    edges.filter(ed => ed.type === "HAS_PARAMETER"
      && nodes.find(nd => nd.id === ed.target)?.type === nt
      && ["System", "Subsystem", "Component"].includes(nodes.find(nd => nd.id === ed.source)?.type ?? "")).length;
  const guideNodeTypes: ("Interface" | "DesignParameter")[] = attachedCount("Interface") === 0 ? ["Interface"] : [];
  if (attachedCount("DesignParameter") === 0) guideNodeTypes.push("DesignParameter");
  const guideRows = guideNodeTypes
    .map(nt => {
      const tools = toolsRequiringNodeType(selectedTools, map, nt);
      return tools.length > 0 ? { nodeType: nt, tool: tools[0] } : null;
    })
    .filter((r): r is { nodeType: "Interface" | "DesignParameter"; tool: string } => r !== null);
  if (guideRows.length === 0) return null;
  return (
    <div data-testid="guide-card">
      {guideRows.map(row => (
        <button key={row.nodeType} data-testid={`add-${row.nodeType}`} onClick={() => onAdd(row.nodeType)}>
          add {row.nodeType}
        </button>
      ))}
    </div>
  );
}

const MAP: Record<string, string> = { "接口矩阵": "Interface", "P图/参数图": "DesignParameter" };
const n = (id: string, type: string): GraphNode => ({ id, type, name: id, severity: 0, occurrence: 0, detection: 0 });

describe("ToolStructureGuide card", () => {
  it("shows the card with an Interface add button when 接口矩阵 selected and no attached Interface", () => {
    const nodes = [n("comp1", "Component")];
    const onAdd = vi.fn();
    render(<GuideHarness nodes={nodes} edges={[]} selectedTools={["接口矩阵"]} map={MAP} onAdd={onAdd} />);
    expect(screen.getByTestId("guide-card")).toBeInTheDocument();
    expect(screen.getByTestId("add-Interface")).toBeInTheDocument();
  });

  it("does not show the card when the required node is already attached via HAS_PARAMETER", () => {
    const nodes = [n("comp1", "Component"), n("iface1", "Interface")];
    const edges: GraphEdge[] = [{ source: "comp1", target: "iface1", type: "HAS_PARAMETER" }];
    const onAdd = vi.fn();
    const { container } = render(<GuideHarness nodes={nodes} edges={edges} selectedTools={["接口矩阵"]} map={MAP} onAdd={onAdd} />);
    expect(container.querySelector("[data-testid='guide-card']")).toBeNull();
  });

  it("does not show the card when no structure-class tool is selected", () => {
    const nodes = [n("comp1", "Component")];
    const onAdd = vi.fn();
    const { container } = render(<GuideHarness nodes={nodes} edges={[]} selectedTools={["功能分析"]} map={MAP} onAdd={onAdd} />);
    expect(container.querySelector("[data-testid='guide-card']")).toBeNull();
  });

  it("calls onAdd with the nodeType when the add button is clicked", () => {
    const nodes = [n("comp1", "Component")];
    const onAdd = vi.fn();
    render(<GuideHarness nodes={nodes} edges={[]} selectedTools={["P图/参数图"]} map={MAP} onAdd={onAdd} />);
    fireEvent.click(screen.getByTestId("add-DesignParameter"));
    expect(onAdd).toHaveBeenCalledWith("DesignParameter");
  });
});

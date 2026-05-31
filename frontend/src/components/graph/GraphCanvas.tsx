import { forwardRef, useEffect, useRef, useCallback, useImperativeHandle } from "react";
import { Graph } from "@antv/g6";
import type { GraphNode, GraphEdge } from "../../api/graph";
import type { GraphLayout } from "./GraphToolbar";

interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  mode: "single-fmea" | "global";
  layout?: GraphLayout;
  highlightNodes?: string[];
  dimOthers?: boolean;
  onNodeClick?: (node: GraphNode) => void;
  onNodeDoubleClick?: (node: GraphNode) => void;
  onNodeContextMenu?: (node: GraphNode, event: MouseEvent) => void;
}

const NODE_TYPE_COLORS: Record<string, string> = {
  System: "#1890ff",
  ProcessItem: "#1890ff",
  Subsystem: "#69c0ff",
  ProcessStep: "#69c0ff",
  Component: "#36cfc9",
  ProcessWorkElement: "#36cfc9",
  Function: "#52c41a",
  FailureMode: "#ff4d4f",
  FailureEffect: "#fa8c16",
  FailureCause: "#faad14",
  PreventionControl: "#73d13d",
  DetectionControl: "#722ed1",
  RecommendedAction: "#8c8c8c",
};

const NODE_TYPE_SHAPES: Record<string, string> = {
  System: "rect",
  ProcessItem: "rect",
  Subsystem: "rect",
  ProcessStep: "rect",
  Component: "rect",
  ProcessWorkElement: "rect",
  Function: "rect",
  FailureMode: "diamond",
  FailureEffect: "ellipse",
  FailureCause: "ellipse",
  PreventionControl: "circle",
  DetectionControl: "circle",
  RecommendedAction: "rect",
};

function toG6Data(nodes: GraphNode[], edges: GraphEdge[]) {
  const g6Nodes = nodes.map((n) => ({
    id: n.id,
    data: {
      label: n.properties.name || n.label,
      type: n.label,
    },
    style: {
      fill: NODE_TYPE_COLORS[n.label] || "#e8e8e8",
      stroke: NODE_TYPE_COLORS[n.label] || "#8c8c8c",
      lineWidth: 1,
      // G6 v5 Size type: number | [number, number] | [number, number, number]
      size: (n.label === "FailureMode"
        ? [80, 50]
        : n.label?.includes("Control")
          ? 30
          : [100, 40]) as [number, number] | number,
    },
  }));

  const g6Edges = edges.map((e, i) => ({
    id: `e${i}`,
    source: e.source,
    target: e.target,
    data: { label: e.label },
    style: {
      stroke: "#8c8c8c",
      lineWidth: 1,
      endArrow: true,
    },
  }));

  return { nodes: g6Nodes, edges: g6Edges };
}

export interface GraphCanvasRef {
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: () => void;
  download: () => void;
}

const GraphCanvas = forwardRef<GraphCanvasRef, GraphCanvasProps>(function GraphCanvas(
  {
    nodes,
    edges,
    mode,
    layout = mode === "single-fmea" ? "dagre" : "force",
    highlightNodes = [],
    dimOthers = false,
    onNodeClick,
    onNodeDoubleClick,
    onNodeContextMenu,
  }: GraphCanvasProps,
  ref
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<Graph | null>(null);

  const initGraph = useCallback(() => {
    if (!containerRef.current) return;

    const graph = new Graph({
      container: containerRef.current,
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight || 600,
      autoFit: "view",
      data: toG6Data(nodes, edges),
      node: {
        type: (datum: { data?: { type?: string } }) =>
          NODE_TYPE_SHAPES[datum.data?.type || ""] || "rect",
        style: {
          labelText: (datum: { data?: { label?: string } }) => datum.data?.label || "",
          labelFontSize: 10,
          labelPlacement: "center",
          labelFill: "#333",
        },
      },
      edge: {
        type: "line",
        style: {
          endArrow: true,
          labelText: (datum: { data?: { label?: string } }) => datum.data?.label || "",
          labelFontSize: 9,
          labelFill: "#666",
        },
      },
      layout: {
        type: layout,
        rankdir: layout === "dagre" ? "LR" : undefined,
        animation: true,
      } as const,
      behaviors: [
        "drag-canvas",
        "zoom-canvas",
        "drag-element",
        {
          type: "collapse-expand",
          trigger: "dblclick",
        },
      ],
      plugins: [
        {
          type: "minimap",
          size: [150, 100],
        },
      ],
    });

    graphRef.current = graph;

    if (onNodeClick) {
      graph.on("node:click", (evt) => {
        // @ts-expect-error G6 v5 event type: target exists on element events
        const nodeId = evt.target?.id as string;
        const node = nodes.find((n) => n.id === nodeId);
        if (node) onNodeClick(node);
      });
    }

    if (onNodeDoubleClick) {
      graph.on("node:dblclick", (evt) => {
        // @ts-expect-error G6 v5 event type: target exists on element events
        const nodeId = evt.target?.id as string;
        const node = nodes.find((n) => n.id === nodeId);
        if (node) onNodeDoubleClick(node);
      });
    }

    if (onNodeContextMenu) {
      graph.on("node:contextmenu", (evt) => {
        // @ts-expect-error G6 v5 event type: originalEvent exists on pointer events
        evt.originalEvent?.preventDefault();
        // @ts-expect-error G6 v5 event type: target exists on element events
        const nodeId = evt.target?.id as string;
        const node = nodes.find((n) => n.id === nodeId);
        // @ts-expect-error G6 v5 event type: originalEvent exists on pointer events
        if (node) onNodeContextMenu(node, evt.originalEvent as MouseEvent);
      });
    }
  }, [nodes, edges, layout, mode, onNodeClick, onNodeDoubleClick, onNodeContextMenu]);

  // Apply highlight/dim
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;

    if (highlightNodes.length > 0 && dimOthers) {
      graph.getNodeData().forEach((node) => {
        const isHighlighted = highlightNodes.includes(node.id);
        graph.updateNodeData([
          {
            id: node.id,
            style: {
              ...node.style,
              opacity: isHighlighted ? 1 : 0.2,
            },
          },
        ]);
      });
      graph.getEdgeData().forEach((edge) => {
        // EdgeData.id is optional in G6 v5 types, but we always set it in toG6Data
        const edgeId = edge.id!;
        const isHighlighted =
          highlightNodes.includes(edge.source) && highlightNodes.includes(edge.target);
        graph.updateEdgeData([
          {
            id: edgeId,
            style: {
              ...edge.style,
              opacity: isHighlighted ? 1 : 0.1,
              stroke: isHighlighted ? "#ff4d4f" : "#8c8c8c",
              lineWidth: isHighlighted ? 2 : 1,
            },
          },
        ]);
      });
    } else {
      // Reset
      graph.getNodeData().forEach((node) => {
        graph.updateNodeData([
          {
            id: node.id,
            style: {
              ...node.style,
              opacity: 1,
            },
          },
        ]);
      });
      graph.getEdgeData().forEach((edge) => {
        const edgeId = edge.id!;
        graph.updateEdgeData([
          {
            id: edgeId,
            style: {
              ...edge.style,
              opacity: 1,
              stroke: "#8c8c8c",
              lineWidth: 1,
            },
          },
        ]);
      });
    }
  }, [highlightNodes, dimOthers]);

  useEffect(() => {
    initGraph();
    return () => {
      graphRef.current?.destroy();
      graphRef.current = null;
    };
  }, [initGraph]);

  // Resize handler
  useEffect(() => {
    const handleResize = () => {
      if (containerRef.current && graphRef.current) {
        graphRef.current.resize(
          containerRef.current.clientWidth,
          containerRef.current.clientHeight || 600,
        );
      }
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Expose imperative methods for GraphToolbar
  useImperativeHandle(ref, () => ({
    zoomIn: () => graphRef.current?.zoomBy(1.2),
    zoomOut: () => graphRef.current?.zoomBy(0.8),
    fitView: () => {
      const g = graphRef.current;
      if (g) {
        g.fitCenter().catch(() => {});
      }
    },
    download: () => {
      const canvas = containerRef.current?.querySelector("canvas");
      if (canvas) {
        const link = document.createElement("a");
        link.download = "graph.png";
        link.href = (canvas as HTMLCanvasElement).toDataURL();
        link.click();
      }
    },
  }));

  return (
    <div
      ref={containerRef}
      style={{
        width: "100%",
        height: "100%",
        minHeight: 500,
        border: "1px solid #f0f0f0",
        borderRadius: 4,
        background: "#fafafa",
      }}
    />
  );
});

export default GraphCanvas;

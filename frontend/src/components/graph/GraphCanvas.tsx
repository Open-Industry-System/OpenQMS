import { forwardRef, useEffect, useRef, useCallback, useImperativeHandle, useMemo } from "react";
import { Graph } from "@antv/g6";
import { useTranslation } from "react-i18next";
import type { GraphNode, GraphEdge } from "../../api/graph";
import type { GraphLayout } from "./GraphToolbar";
import { getEdgeTypeKey, getNodeStyle } from "../../utils/graphPresentation";

interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  mode: "single-fmea" | "global";
  layout?: GraphLayout;
  highlightNodes?: string[];
  dimOthers?: boolean;
  onNodeClick?: (node: GraphNode) => void;
  onNodeDoubleClick?: (node: GraphNode) => void;
  onNodeContextMenu?: (node: GraphNode, event: { clientX: number; clientY: number }) => void;
}

type GraphT = (key: string, options?: { defaultValue?: string }) => string;

function toG6Data(nodes: GraphNode[], edges: GraphEdge[], t: GraphT) {
  const g6Nodes = nodes.map((n) => {
    const nodeStyle = getNodeStyle(n.label);
    return {
      id: n.id,
      data: {
        label: n.properties.name || n.label,
        type: n.label,
      },
      style: {
        ...nodeStyle,
      },
    };
  });

  const g6Edges = edges.map((e) => {
    const rawLabel = e.label || "edge";
    return {
      id: `${e.source}-${e.target}-${rawLabel}`,
      source: e.source,
      target: e.target,
      data: {
        label: t(getEdgeTypeKey(rawLabel), { defaultValue: rawLabel }),
        rawLabel,
      },
      style: {
        stroke: "#9aa7b8",
        lineWidth: 1,
        endArrow: true,
      },
    };
  });

  return { nodes: g6Nodes, edges: g6Edges };
}

function graphLayoutOptions(layout: GraphLayout) {
  if (layout === "dagre") {
    return {
      type: "dagre",
      rankdir: "LR",
      nodesep: 70,
      ranksep: 110,
      controlPoints: false,
      animation: true,
    } as const;
  }

  return {
    type: layout,
    animation: true,
  } as const;
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
  const { t, i18n } = useTranslation("graph");
  const graphData = useMemo(
    () => toG6Data(nodes, edges, t),
    [nodes, edges, t, i18n.language],
  );

  // Keep handlers in refs so initGraph only depends on structural inputs (layout/nodes);
  // edge changes flow through graphData and the data-refresh effect below.
  const handlersRef = useRef({ onNodeClick, onNodeDoubleClick, onNodeContextMenu });
  useEffect(() => {
    handlersRef.current = { onNodeClick, onNodeDoubleClick, onNodeContextMenu };
  });

  const initGraph = useCallback(() => {
    if (!containerRef.current) return;

    if (graphRef.current) return;

    const graph = new Graph({
      container: containerRef.current,
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight || 600,
      autoFit: "view",
      data: graphData,
      node: {
        type: "rect",
        style: {
          labelText: (datum: { data?: { label?: string } }) => datum.data?.label || "",
          labelFontSize: 12,
          labelPlacement: "center",
          labelFill: "#1f2937",
          labelTextAlign: "center",
          labelWordWrap: true,
          labelMaxWidth: 120,
          labelWordWrapWidth: 120,
          labelMaxLines: 2,
          labelTextOverflow: "ellipsis",
        },
      },
      edge: {
        type: "line",
        style: {
          endArrow: true,
          stroke: "#9aa7b8",
          lineWidth: 1,
          labelText: (datum: { data?: { label?: string } }) => datum.data?.label || "",
          labelFontSize: 11,
          labelFill: "#4b5563",
          labelPlacement: "center",
          labelOffsetY: -4,
          labelBackground: true,
          labelBackgroundFill: "#ffffff",
          labelBackgroundOpacity: 0.92,
          labelBackgroundPadding: [2, 6],
        },
      },
      layout: graphLayoutOptions(layout),
      behaviors: [
        "drag-canvas",
        "zoom-canvas",
        "drag-element",
      ],
      plugins: [
        {
          type: "minimap",
          size: [150, 100],
        },
      ],
    });

    graphRef.current = graph;

    graph.on("node:click", (evt) => {
      const h = handlersRef.current.onNodeClick;
      if (!h) return;
      const g6Evt = evt as unknown as {
        target?: { id?: string };
        item?: { id?: string };
      };
      const nodeId = g6Evt.target?.id ?? g6Evt.item?.id;
      const node = nodes.find((n) => n.id === nodeId);
      if (node) h(node);
    });

    graph.on("node:dblclick", (evt) => {
      const h = handlersRef.current.onNodeDoubleClick;
      if (!h) return;
      const g6Evt = evt as unknown as {
        target?: { id?: string };
        item?: { id?: string };
      };
      const nodeId = g6Evt.target?.id ?? g6Evt.item?.id;
      const node = nodes.find((n) => n.id === nodeId);
      if (node) h(node);
    });

    graph.on("node:contextmenu", (evt) => {
      const h = handlersRef.current.onNodeContextMenu;
      if (!h) return;
      const g6Evt = evt as unknown as {
        target?: { id?: string };
        item?: { id?: string };
        clientX?: number;
        clientY?: number;
        preventDefault?: () => void;
      };
      g6Evt.preventDefault?.();
      const nodeId = g6Evt.target?.id ?? g6Evt.item?.id;
      const node = nodes.find((n) => n.id === nodeId);
      if (node) {
        h(node, {
          clientX: g6Evt.clientX ?? 0,
          clientY: g6Evt.clientY ?? 0,
        });
      }
    });

    graph.render().catch((err: unknown) => {
      console.error("G6 render failed:", err);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- graphData is intentionally
    // excluded so language changes do not recreate the G6 instance; the [graphData] effect
    // below is the data refresh path and preserves zoom/pan.
  }, [layout, nodes]);

  // Apply highlight/dim
  const applyHighlight = useCallback(() => {
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
        const edgeId = edge.id!;
        const isHighlighted =
          highlightNodes.includes(edge.source) && highlightNodes.includes(edge.target);
        graph.updateEdgeData([
          {
            id: edgeId,
            style: {
              ...edge.style,
              opacity: isHighlighted ? 1 : 0.1,
              stroke: isHighlighted ? "#ff4d4f" : "#9aa7b8",
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
              stroke: "#9aa7b8",
              lineWidth: 1,
            },
          },
        ]);
      });
    }
    graph.draw();
  }, [highlightNodes, dimOthers]);

  useEffect(() => {
    initGraph();
    return () => {
      graphRef.current?.destroy();
      graphRef.current = null;
    };
  }, [initGraph]);

  const prevGraphDataRef = useRef(graphData);
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;
    if (prevGraphDataRef.current !== graphData) {
      prevGraphDataRef.current = graphData;
      graph.setData(graphData);
    }
    applyHighlight();
  }, [graphData, applyHighlight]);

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
      const g = graphRef.current;
      if (g) {
        // Use G6's toDataURL instead of querySelector to avoid capturing minimap
        g.toDataURL()
          .then((url: string) => {
            const link = document.createElement("a");
            link.download = "graph.png";
            link.href = url;
            link.click();
          })
          .catch((err: unknown) => {
            console.error("Graph download failed:", err);
          });
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
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        background: "#f8fafc",
      }}
    />
  );
});

export default GraphCanvas;

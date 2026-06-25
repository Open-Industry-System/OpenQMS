import { forwardRef, useEffect, useRef, useCallback, useImperativeHandle, useMemo } from "react";
import { Graph } from "@antv/g6";
import { useTranslation } from "react-i18next";
import type { GraphNode, GraphEdge } from "../../api/graph";
import { toG6Data, graphLayoutOptions } from "../../utils/graphLayout";
import type { GraphLayout, GraphDirection } from "../../utils/graphLayout";
import { getHighlightedEdgeStyle } from "../../utils/graphPresentation";
import {
  EDGE_LABEL_BG,
  EDGE_LABEL_FILL,
  EDGE_STROKE,
  GRAPH_BG,
  GRAPH_BORDER,
  NODE_LABEL_FILL,
} from "../../utils/graphPresentation";

interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  mode: "single-fmea" | "global";
  /** FMEA family of the document being viewed — drives DFMEA-aware edge labels. */
  fmeaType?: string;
  layout?: GraphLayout;
  /** Hierarchy reading direction — only applies to dagre. */
  direction?: GraphDirection;
  highlightNodes?: string[];
  dimOthers?: boolean;
  onNodeClick?: (node: GraphNode) => void;
  onNodeDoubleClick?: (node: GraphNode) => void;
  onNodeContextMenu?: (node: GraphNode, event: { clientX: number; clientY: number }) => void;
}

function graphBehaviors(layout: GraphLayout) {
  // drag-element-force re-heats the d3-force simulation on drag so other nodes
  // follow the dragged one; use plain drag-element for the static layouts.
  const dragBehavior =
    layout === "force"
      ? { type: "drag-element-force", fixed: false }
      : { type: "drag-element" };
  return ["drag-canvas", "zoom-canvas", dragBehavior];
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
    fmeaType,
    layout = mode === "single-fmea" ? "dagre" : "force",
    direction = "TB",
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
  const { t } = useTranslation("graph");
  const graphData = useMemo(
    () => toG6Data(nodes, edges, t, fmeaType),
    [nodes, edges, t, fmeaType],
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
          labelFill: NODE_LABEL_FILL,
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
          stroke: EDGE_STROKE,
          lineWidth: 1,
          labelText: (datum: { data?: { label?: string } }) => datum.data?.label || "",
          labelFontSize: 11,
          labelFill: EDGE_LABEL_FILL,
          labelPlacement: "center",
          labelOffsetY: -4,
          labelBackground: true,
          labelBackgroundFill: EDGE_LABEL_BG,
          labelBackgroundOpacity: 0.92,
          labelBackgroundPadding: [2, 6],
        },
      },
      layout: graphLayoutOptions(layout, direction),
      behaviors: graphBehaviors(layout),
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
    // graphData is intentionally excluded so language changes do not recreate the G6 instance;
    // the [graphData] effect below is the data refresh path and preserves zoom/pan.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout, direction, nodes]);

  // Apply highlight/dim
  const applyHighlight = useCallback(() => {
    const graph = graphRef.current;
    if (!graph) return;
    const dimmed = highlightNodes.length > 0 && dimOthers;

    graph.getNodeData().forEach((node) => {
      const isHighlighted = highlightNodes.includes(node.id);
      graph.updateNodeData([
        {
          id: node.id,
          style: {
            ...node.style,
            opacity: dimmed ? (isHighlighted ? 1 : 0.2) : 1,
          },
        },
      ]);
    });

    graph.getEdgeData().forEach((edge) => {
      const edgeId = edge.id!;
      const rawLabel = (edge.data as { rawLabel?: string } | undefined)?.rawLabel ?? "";
      const isHighlighted =
        highlightNodes.includes(edge.source) && highlightNodes.includes(edge.target);
      const style = getHighlightedEdgeStyle(rawLabel, isHighlighted, dimmed);
      graph.updateEdgeData([
        {
          id: edgeId,
          style: { ...edge.style, ...style },
        },
      ]);
    });

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
      if (!g) return;
      // G6's toDataURL captures only the canvas (transparent background); the dark
      // GRAPH_BG lives in the container CSS, so the raw export is invisible on a
      // white viewer. Composite the export onto a GRAPH_BG-filled canvas first.
      g.toDataURL()
        .then((url: string) => {
          const img = new Image();
          img.onload = () => {
            const canvas = document.createElement("canvas");
            canvas.width = img.width;
            canvas.height = img.height;
            const ctx = canvas.getContext("2d");
            if (!ctx) return;
            ctx.fillStyle = GRAPH_BG;
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(img, 0, 0);
            const link = document.createElement("a");
            link.download = "graph.png";
            link.href = canvas.toDataURL("image/png");
            link.click();
          };
          img.onerror = (err: unknown) => {
            console.error("Graph download image load failed:", err);
          };
          img.src = url;
        })
        .catch((err: unknown) => {
          console.error("Graph download failed:", err);
        });
    },
  }));

  return (
    <div
      ref={containerRef}
      style={{
        width: "100%",
        height: "100%",
        minHeight: 500,
        border: `1px solid ${GRAPH_BORDER}`,
        borderRadius: 8,
        background: GRAPH_BG,
      }}
    />
  );
});

export default GraphCanvas;

import { Drawer, Descriptions, Tag, Space } from "antd";
import type { GraphNode, GraphEdge } from "../../api/graph";
import { calculateAP } from "../../utils/fmea";

interface NodeDetailDrawerProps {
  node: GraphNode | null;
  visible: boolean;
  onClose: () => void;
  /** 提供完整图数据用于 FailureMode 的 RPN 行级计算（与风险地图口径一致） */
  allNodes?: GraphNode[];
  allEdges?: GraphEdge[];
}

function apTag(ap: string | undefined) {
  if (ap === "H") return <Tag color="red">高 (H)</Tag>;
  if (ap === "M") return <Tag color="orange">中 (M)</Tag>;
  if (ap === "L") return <Tag color="green">低 (L)</Tag>;
  return <Tag>未评级</Tag>;
}

function computeFailureModeRPN(
  fmId: string,
  allNodes: GraphNode[],
  allEdges: GraphEdge[],
): { s: number; o: number; d: number; rpn: number; ap: string } {
  const nodeMap = new Map(allNodes.map((n) => [n.id, n]));

  // S: 第一个 FailureEffect
  const effectEdge = allEdges.find((e) => e.source === fmId && e.label === "EFFECT_OF");
  const effect = effectEdge ? nodeMap.get(effectEdge.target) : null;
  const s = (effect?.properties.severity as number) ?? 0;

  // D helper: 第一个 DetectionControl
  const firstDet = (sourceId: string): number => {
    const detEdge = allEdges.find((e) => e.source === sourceId && e.label === "DETECTED_BY");
    return detEdge ? ((nodeMap.get(detEdge.target)?.properties.detection as number) ?? 0) : 0;
  };

  // 按 cause 逐行计算 RPN，取最大真实行
  const causeEdges = allEdges.filter((e) => e.target === fmId && e.label === "CAUSE_OF");
  let bestRPN = 0;
  let bestO = 0;
  let bestD = 0;

  if (causeEdges.length === 0) {
    bestD = firstDet(fmId);
  } else {
    for (const ce of causeEdges) {
      const cause = nodeMap.get(ce.source);
      const o = (cause?.properties.occurrence as number) ?? 0;
      const causeDets = allEdges.filter((e) => e.source === ce.source && e.label === "DETECTED_BY");
      const d = causeDets.length > 0 ? firstDet(ce.source) : firstDet(fmId);
      const rpn = s * o * d;
      if (rpn > bestRPN) {
        bestRPN = rpn;
        bestO = o;
        bestD = d;
      }
    }
  }

  const ap = s > 0 && bestO > 0 && bestD > 0 ? calculateAP(s, bestO, bestD) : "";
  return { s, o: bestO, d: bestD, rpn: bestRPN, ap };
}

export default function NodeDetailDrawer({
  node,
  visible,
  onClose,
  allNodes,
  allEdges,
}: NodeDetailDrawerProps) {
  if (!node) return null;

  const p = node.properties;

  // FailureMode: 按行计算 RPN（与风险地图口径一致）
  // 其他节点：直接用节点属性
  const isFailureMode = node.label === "FailureMode";
  const rpnData =
    isFailureMode && allNodes && allEdges
      ? computeFailureModeRPN(node.id, allNodes, allEdges)
      : null;

  const s = rpnData?.s ?? (p.severity as number ?? 0);
  const o = rpnData?.o ?? (p.occurrence as number ?? 0);
  const d = rpnData?.d ?? (p.detection as number ?? 0);
  const rpn = rpnData?.rpn ?? s * o * d;
  const computedAP = rpnData?.ap ?? (s > 0 && o > 0 && d > 0 ? calculateAP(s, o, d) : "");

  return (
    <Drawer title={p.name || "节点详情"} open={visible} onClose={onClose} width={400}>
      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label="节点 ID">{node.id}</Descriptions.Item>
        <Descriptions.Item label="节点类型">
          <Tag>{node.label}</Tag>
        </Descriptions.Item>
        {s > 0 && (
          <Descriptions.Item label="严重度 (S)">{String(s)}</Descriptions.Item>
        )}
        {o > 0 && (
          <Descriptions.Item label="发生度 (O)">{String(o)}</Descriptions.Item>
        )}
        {d > 0 && (
          <Descriptions.Item label="探测度 (D)">{String(d)}</Descriptions.Item>
        )}
        {rpn > 0 && (
          <Descriptions.Item label="RPN">
            {s} × {o} × {d} = <strong>{rpn}</strong>
          </Descriptions.Item>
        )}
        {computedAP && (
          <Descriptions.Item label="行动优先级 (AP)">
            <Space>
              {apTag(computedAP)}
              {p.ap && p.ap !== computedAP && (
                <span style={{ fontSize: 12, color: "#888" }}>
                  (节点值: {String(p.ap)})
                </span>
              )}
            </Space>
          </Descriptions.Item>
        )}
        {p.revised_severity !== undefined && (
          <Descriptions.Item label="修订严重度">{String(p.revised_severity)}</Descriptions.Item>
        )}
        {p.revised_occurrence !== undefined && (
          <Descriptions.Item label="修订发生度">{String(p.revised_occurrence)}</Descriptions.Item>
        )}
        {p.revised_detection !== undefined && (
          <Descriptions.Item label="修订探测度">{String(p.revised_detection)}</Descriptions.Item>
        )}
        {p.status !== undefined && p.status !== "" && (
          <Descriptions.Item label="状态">{String(p.status)}</Descriptions.Item>
        )}
        {p.responsible !== undefined && p.responsible !== "" && (
          <Descriptions.Item label="责任人">{String(p.responsible)}</Descriptions.Item>
        )}
        {p.due_date !== undefined && p.due_date !== "" && (
          <Descriptions.Item label="截止日期">{String(p.due_date)}</Descriptions.Item>
        )}
      </Descriptions>
    </Drawer>
  );
}

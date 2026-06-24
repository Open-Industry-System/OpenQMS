import { Drawer, Descriptions, Tag, Space } from "antd";
import { useTranslation } from "react-i18next";
import type { GraphNode, GraphEdge } from "../../api/graph";
import { calculateAP } from "../../utils/fmea";
import { getNodeTypeKey } from "../../utils/graphPresentation";

interface NodeDetailDrawerProps {
  node: GraphNode | null;
  visible: boolean;
  onClose: () => void;
  /** FMEA family — drives DFMEA-aware node-type labels. */
  fmeaType?: string;
  /** Provides full graph data for FailureMode RPN row-level calculation (consistent with risk map). */
  allNodes?: GraphNode[];
  allEdges?: GraphEdge[];
}

function apTag(ap: string | undefined, t: (key: string) => string) {
  if (ap === "H") return <Tag color="red">{t("nodeDetail.apHigh")}</Tag>;
  if (ap === "M") return <Tag color="orange">{t("nodeDetail.apMedium")}</Tag>;
  if (ap === "L") return <Tag color="green">{t("nodeDetail.apLow")}</Tag>;
  return <Tag>{t("nodeDetail.apUnrated")}</Tag>;
}

function computeFailureModeRPN(
  fmId: string,
  allNodes: GraphNode[],
  allEdges: GraphEdge[],
): { s: number; o: number; d: number; rpn: number; ap: string } {
  const nodeMap = new Map(allNodes.map((n) => [n.id, n]));

  // S: first FailureEffect
  const effectEdge = allEdges.find((e) => e.source === fmId && e.label === "EFFECT_OF");
  const effect = effectEdge ? nodeMap.get(effectEdge.target) : null;
  const s = (effect?.properties.severity as number) ?? 0;

  // D helper: first DetectionControl
  const firstDet = (sourceId: string): number => {
    const detEdge = allEdges.find((e) => e.source === sourceId && e.label === "DETECTED_BY");
    return detEdge ? ((nodeMap.get(detEdge.target)?.properties.detection as number) ?? 0) : 0;
  };

  // Calculate RPN per cause and take the maximum real row
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
  fmeaType,
  allNodes,
  allEdges,
}: NodeDetailDrawerProps) {
  const { t } = useTranslation("graph");
  if (!node) return null;

  const p = node.properties;

  // FailureMode: calculate RPN per row (consistent with risk map)
  // Other nodes: use node properties directly
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
    <Drawer title={p.name || t("nodeDetail.title")} open={visible} onClose={onClose} width={400}>
      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label={t("nodeDetail.nodeId")}>{node.id}</Descriptions.Item>
        <Descriptions.Item label={t("nodeDetail.nodeType")}>
          <Tag>{t(getNodeTypeKey(node.label, fmeaType), { defaultValue: node.label })}</Tag>
        </Descriptions.Item>
        {s > 0 && (
          <Descriptions.Item label={t("nodeDetail.severity")}>{String(s)}</Descriptions.Item>
        )}
        {o > 0 && (
          <Descriptions.Item label={t("nodeDetail.occurrence")}>{String(o)}</Descriptions.Item>
        )}
        {d > 0 && (
          <Descriptions.Item label={t("nodeDetail.detection")}>{String(d)}</Descriptions.Item>
        )}
        {rpn > 0 && (
          <Descriptions.Item label={t("nodeDetail.rpn")}>
            {t("nodeDetail.rpnFormula", { s, o, d, rpn })}
          </Descriptions.Item>
        )}
        {computedAP && (
          <Descriptions.Item label={t("nodeDetail.ap")}>
            <Space>
              {apTag(computedAP, t)}
              {p.ap && p.ap !== computedAP && (
                <span style={{ fontSize: 12, color: "#888" }}>
                  {t("nodeDetail.nodeValue", { value: String(p.ap) })}
                </span>
              )}
            </Space>
          </Descriptions.Item>
        )}
        {p.revised_severity !== undefined && (
          <Descriptions.Item label={t("nodeDetail.revisedSeverity")}>{String(p.revised_severity)}</Descriptions.Item>
        )}
        {p.revised_occurrence !== undefined && (
          <Descriptions.Item label={t("nodeDetail.revisedOccurrence")}>{String(p.revised_occurrence)}</Descriptions.Item>
        )}
        {p.revised_detection !== undefined && (
          <Descriptions.Item label={t("nodeDetail.revisedDetection")}>{String(p.revised_detection)}</Descriptions.Item>
        )}
        {p.status !== undefined && p.status !== "" && (
          <Descriptions.Item label={t("nodeDetail.status")}>{String(p.status)}</Descriptions.Item>
        )}
        {p.responsible !== undefined && p.responsible !== "" && (
          <Descriptions.Item label={t("nodeDetail.responsible")}>{String(p.responsible)}</Descriptions.Item>
        )}
        {p.due_date !== undefined && p.due_date !== "" && (
          <Descriptions.Item label={t("nodeDetail.dueDate")}>{String(p.due_date)}</Descriptions.Item>
        )}
      </Descriptions>
    </Drawer>
  );
}

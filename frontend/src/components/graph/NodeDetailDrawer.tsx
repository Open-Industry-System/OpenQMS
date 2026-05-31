import { Drawer, Descriptions, Tag, Space } from "antd";
import type { GraphNode } from "../../api/graph";
import { calculateAP } from "../../utils/fmea";

interface NodeDetailDrawerProps {
  node: GraphNode | null;
  visible: boolean;
  onClose: () => void;
}

function apTag(ap: string | undefined) {
  if (ap === "H") return <Tag color="red">高 (H)</Tag>;
  if (ap === "M") return <Tag color="orange">中 (M)</Tag>;
  if (ap === "L") return <Tag color="green">低 (L)</Tag>;
  return <Tag>未评级</Tag>;
}

export default function NodeDetailDrawer({
  node,
  visible,
  onClose,
}: NodeDetailDrawerProps) {
  if (!node) return null;

  const p = node.properties;
  const s = p.severity ?? 0;
  const o = p.occurrence ?? 0;
  const d = p.detection ?? 0;
  const rpn = s * o * d;
  const computedAP = s > 0 && o > 0 && d > 0 ? calculateAP(s, o, d) : "";

  return (
    <Drawer title={p.name || "节点详情"} open={visible} onClose={onClose} width={400}>
      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label="节点 ID">{node.id}</Descriptions.Item>
        <Descriptions.Item label="节点类型">
          <Tag>{node.label}</Tag>
        </Descriptions.Item>
        {p.severity !== undefined && (
          <Descriptions.Item label="严重度 (S)">{String(p.severity)}</Descriptions.Item>
        )}
        {p.occurrence !== undefined && (
          <Descriptions.Item label="发生度 (O)">{String(p.occurrence)}</Descriptions.Item>
        )}
        {p.detection !== undefined && (
          <Descriptions.Item label="探测度 (D)">{String(p.detection)}</Descriptions.Item>
        )}
        {rpn > 0 && (
          <Descriptions.Item label="RPN">
            {s} × {o} × {d} = <strong>{rpn}</strong>
          </Descriptions.Item>
        )}
        {(p.ap || computedAP) && (
          <Descriptions.Item label="行动优先级 (AP)">
            <Space>
              {apTag(p.ap)}
              {computedAP && p.ap !== computedAP && (
                <span style={{ fontSize: 12, color: "#888" }}>
                  (计算值: {computedAP})
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

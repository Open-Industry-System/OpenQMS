import { List, Collapse, Tag, Typography } from "antd";
import type { AffectedNode } from "../../api/changeImpact";

interface AffectedNodeListProps {
  nodes: AffectedNode[];
}

const { Text } = Typography;

export default function AffectedNodeList({ nodes }: AffectedNodeListProps) {
  if (nodes.length === 0) {
    return <Text type="secondary">无受影响节点</Text>;
  }

  return (
    <List
      dataSource={nodes}
      renderItem={(node) => (
        <List.Item>
          <Collapse ghost style={{ width: "100%" }}>
            <Collapse.Panel
              key={node.node_id}
              header={
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <Text strong>{node.name}</Text>
                  <Tag>{node.node_type}</Tag>
                  <Tag color="blue">{node.impact_type}</Tag>
                  <Text type="secondary">{node.hop_distance} 跳</Text>
                </div>
              }
            >
              <div style={{ paddingLeft: 16 }}>
                <div>
                  <Text type="secondary">路径：</Text>
                  <Text>{node.path.join(" → ")}</Text>
                </div>
                {node.risk_change && (
                  <div style={{ marginTop: 8 }}>
                    <Text type="secondary">风险变更：</Text>
                    <pre style={{ margin: 0, background: "#f5f5f5", padding: 8, borderRadius: 4 }}>
                      {JSON.stringify(node.risk_change, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            </Collapse.Panel>
          </Collapse>
        </List.Item>
      )}
    />
  );
}

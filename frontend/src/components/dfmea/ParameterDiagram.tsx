import { useState, useEffect, useRef, useCallback } from "react";
import { Input, Button, Typography, Empty } from "antd";
import { PlusOutlined, DeleteOutlined } from "@ant-design/icons";
import type { GraphNode } from "../../types";

const { Text } = Typography;

interface ParameterDiagramProps {
  node: GraphNode | null;
  onUpdateNode: (nodeId: string, updates: Partial<GraphNode>) => void;
  isViewer: boolean;
}

interface PDiagramData {
  inputs: string[];
  outputs: string[];
  controls: string[];
  noise_factors: string[];
}

const SECTION_CONFIG: { key: keyof PDiagramData; label: string; color: string }[] = [
  { key: "inputs", label: "输入信号", color: "#1890ff" },
  { key: "outputs", label: "输出响应", color: "#52c41a" },
  { key: "controls", label: "控制因素", color: "#fa8c16" },
  { key: "noise_factors", label: "噪声因素", color: "#ff4d4f" },
];

const EMPTY_P_DIAGRAM: PDiagramData = {
  inputs: [],
  outputs: [],
  controls: [],
  noise_factors: [],
};

export default function ParameterDiagram({
  node,
  onUpdateNode,
  isViewer,
}: ParameterDiagramProps) {
  const [pDiagram, setPDiagram] = useState<PDiagramData>(EMPTY_P_DIAGRAM);
  const nodeIdRef = useRef<string | null>(null);

  // Sync local state when node changes (different node selected)
  useEffect(() => {
    if (node) {
      if (node.id !== nodeIdRef.current) {
        nodeIdRef.current = node.id;
        setPDiagram(node.p_diagram || EMPTY_P_DIAGRAM);
      }
    } else {
      nodeIdRef.current = null;
      setPDiagram(EMPTY_P_DIAGRAM);
    }
  }, [node]);

  const updateItem = useCallback(
    (section: keyof PDiagramData, index: number, value: string) => {
      if (!node) return;
      const updated = { ...pDiagram };
      updated[section] = [...updated[section]];
      updated[section][index] = value;
      setPDiagram(updated);
      onUpdateNode(node.id, { p_diagram: updated });
    },
    [node, pDiagram, onUpdateNode]
  );

  const addItem = useCallback(
    (section: keyof PDiagramData) => {
      if (!node) return;
      const updated = { ...pDiagram };
      updated[section] = [...updated[section], ""];
      setPDiagram(updated);
      onUpdateNode(node.id, { p_diagram: updated });
    },
    [node, pDiagram, onUpdateNode]
  );

  const deleteItem = useCallback(
    (section: keyof PDiagramData, index: number) => {
      if (!node) return;
      const updated = { ...pDiagram };
      updated[section] = updated[section].filter((_, i) => i !== index);
      setPDiagram(updated);
      onUpdateNode(node.id, { p_diagram: updated });
    },
    [node, pDiagram, onUpdateNode]
  );

  if (!node) {
    return (
      <div style={{ textAlign: "center", padding: 40 }}>
        <Empty description="请在左侧结构树中选择一个零部件节点" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Text strong style={{ fontSize: 16 }}>
          参数图 (P-Diagram): {node.name}
        </Text>
      </div>

      {SECTION_CONFIG.map((section) => (
        <div key={section.key} style={{ marginBottom: 20 }}>
          {/* Section header with colored bar */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              marginBottom: 8,
              padding: "6px 12px",
              borderRadius: 4,
              backgroundColor: `${section.color}15`,
              borderLeft: `4px solid ${section.color}`,
            }}
          >
            <Text strong style={{ color: section.color }}>
              {section.label}
            </Text>
            <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
              ({pDiagram[section.key].length})
            </Text>
          </div>

          {/* Items */}
          <div style={{ paddingLeft: 12 }}>
            {pDiagram[section.key].length === 0 && (
              <Text type="secondary" style={{ fontSize: 12, fontStyle: "italic" }}>
                暂无项目
              </Text>
            )}
            {pDiagram[section.key].map((item, index) => (
              <div
                key={index}
                style={{ display: "flex", alignItems: "center", marginBottom: 6, gap: 6 }}
              >
                <Input
                  value={item}
                  placeholder={`${section.label} ${index + 1}`}
                  disabled={isViewer}
                  onChange={(e) => updateItem(section.key, index, e.target.value)}
                  size="small"
                  style={{ flex: 1 }}
                />
                {!isViewer && (
                  <Button
                    size="small"
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={() => deleteItem(section.key, index)}
                  />
                )}
              </div>
            ))}
          </div>

          {/* Add button */}
          {!isViewer && (
            <Button
              type="dashed"
              size="small"
              icon={<PlusOutlined />}
              onClick={() => addItem(section.key)}
              style={{ marginLeft: 12, marginTop: 4 }}
            >
              添加
            </Button>
          )}
        </div>
      ))}
    </div>
  );
}

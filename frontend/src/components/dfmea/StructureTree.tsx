import { useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Tree, Button, Space, Input, Modal, Form, App } from "antd";
import { PlusOutlined, EditOutlined, DeleteOutlined } from "@ant-design/icons";
import type { GraphNode, GraphEdge } from "../../types";

interface StructureTreeProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onUpdateNodes: (nodes: GraphNode[]) => void;
  onUpdateEdges: (edges: GraphEdge[]) => void;
  isViewer: boolean;
  onSelectNode?: (node: GraphNode) => void;
}

const STRUCTURE_TYPES = ["System", "Subsystem", "Component"];
const CHILD_EDGE_TYPES: Record<string, string> = {
  System: "HAS_PROCESS_STEP",
  Subsystem: "HAS_WORK_ELEMENT",
};
const VALID_EDGE_TYPES = new Set(Object.values(CHILD_EDGE_TYPES));

export default function StructureTree({
  nodes,
  edges,
  onUpdateNodes,
  onUpdateEdges,
  isViewer,
  onSelectNode,
}: StructureTreeProps) {
  const { t } = useTranslation("dfmea");
  const { t: tc } = useTranslation("common");
  const { t: tv } = useTranslation("validation");
  const { message } = App.useApp();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingNode, setEditingNode] = useState<GraphNode | null>(null);
  const [parentId, setParentId] = useState<string | null>(null);
  const [form] = Form.useForm();
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);

  const typeLabel = useCallback((type: string) => {
    return t(`structureTree.typeLabels.${type}`, { defaultValue: type });
  }, [t]);

  const buildTreeData = useCallback(() => {
    const structureNodes = nodes.filter((n) => STRUCTURE_TYPES.includes(n.type));
    const nodeMap = new Map(structureNodes.map((n) => [n.id, n]));
    const edgeMap = new Map<string, string[]>();

    for (const edge of edges) {
      if (!VALID_EDGE_TYPES.has(edge.type)) continue;
      if (!edgeMap.has(edge.source)) edgeMap.set(edge.source, []);
      edgeMap.get(edge.source)!.push(edge.target);
    }

    const buildNode = (nodeId: string): any => {
      const node = nodeMap.get(nodeId);
      if (!node) return null;
      const children =
        edgeMap.get(nodeId)?.map((childId) => buildNode(childId)).filter(Boolean) || [];

      return {
        key: node.id,
        title: (
          <Space>
            <span style={{ fontWeight: node.type === "System" ? 600 : 400 }}>{node.name}</span>
            <span style={{ fontSize: 11, color: "#999" }}>
              {typeLabel(node.type)}
            </span>
          </Space>
        ),
        children,
        node,
      };
    };

    const childrenIds = new Set(
      edges.filter((e) => VALID_EDGE_TYPES.has(e.type)).map((e) => e.target)
    );
    const roots = structureNodes.filter((n) => !childrenIds.has(n.id));
    return roots.map((r) => buildNode(r.id)).filter(Boolean);
  }, [nodes, edges, typeLabel]);

  const handleAdd = (parentNodeId?: string) => {
    setEditingNode(null);
    setParentId(parentNodeId || null);
    form.resetFields();
    if (parentNodeId) {
      const parent = nodes.find((n) => n.id === parentNodeId);
      const childType = parent?.type === "System" ? "Subsystem" : "Component";
      form.setFieldsValue({ type: childType });
    } else {
      form.setFieldsValue({ type: "System" });
    }
    setModalOpen(true);
  };

  const handleEdit = (node: GraphNode) => {
    setEditingNode(node);
    setParentId(null);
    form.setFieldsValue({ name: node.name, description: node.specification || "" });
    setModalOpen(true);
  };

  const handleDelete = (nodeId: string) => {
    const toDelete = new Set<string>();
    const collectDescendants = (id: string) => {
      toDelete.add(id);
      edges
        .filter((e) => e.source === id && VALID_EDGE_TYPES.has(e.type))
        .forEach((e) => collectDescendants(e.target));
    };
    collectDescendants(nodeId);

    onUpdateNodes(nodes.filter((n) => !toDelete.has(n.id)));
    onUpdateEdges(edges.filter((e) => !toDelete.has(e.source) && !toDelete.has(e.target)));
    message.success(tc("messages.deleteSuccess"));
  };

  const handleSave = (values: { name: string; type: string; description?: string }) => {
    if (editingNode) {
      onUpdateNodes(
        nodes.map((n) =>
          n.id === editingNode.id
            ? { ...n, name: values.name, specification: values.description || n.specification }
            : n
        )
      );
    } else {
      const newNode: GraphNode = {
        id: `n${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
        type: values.type,
        name: values.name,
        specification: values.description || "",
        severity: 0,
        occurrence: 0,
        detection: 0,
      };
      const updatedNodes = [...nodes, newNode];
      onUpdateNodes(updatedNodes);

      if (parentId) {
        const parent = nodes.find((n) => n.id === parentId);
        const edgeType = parent ? (CHILD_EDGE_TYPES[parent.type] || "HAS_FUNCTION") : "HAS_FUNCTION";
        onUpdateEdges([...edges, { source: parentId, target: newNode.id, type: edgeType }]);
      }
    }
    setModalOpen(false);
  };

  const treeData = buildTreeData();

  return (
    <div>
      {!isViewer && (
        <div style={{ marginBottom: 12 }}>
          <Button size="small" icon={<PlusOutlined />} onClick={() => handleAdd()}>
            {t("structureTree.addSystem")}
          </Button>
        </div>
      )}

      {treeData.length === 0 && (
        <div style={{ textAlign: "center", padding: 40, color: "#999" }}>
          {t("structureTree.empty")}
        </div>
      )}

      <Tree
        treeData={treeData}
        selectedKeys={selectedKeys}
        onSelect={(keys, info) => {
          setSelectedKeys(keys as string[]);
          if (info.selected && (info.node as any).node) {
            onSelectNode?.((info.node as any).node as GraphNode);
          }
        }}
        titleRender={(nodeData: any) => (
          <Space style={{ width: "100%", justifyContent: "space-between" }}>
            <span>{nodeData.title}</span>
            {!isViewer && (
              <Space size={4}>
                {nodeData.node?.type !== "Component" && (
                  <Button
                    size="small"
                    type="text"
                    icon={<PlusOutlined />}
                    onClick={(e) => { e.stopPropagation(); handleAdd(nodeData.key); }}
                  />
                )}
                <Button
                  size="small"
                  type="text"
                  icon={<EditOutlined />}
                  onClick={(e) => { e.stopPropagation(); handleEdit(nodeData.node); }}
                />
                <Button
                  size="small"
                  type="text"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={(e) => { e.stopPropagation(); handleDelete(nodeData.key); }}
                />
              </Space>
            )}
          </Space>
        )}
      />

      <Modal
        title={editingNode ? t("structureTree.editNode") : t("structureTree.addNode")}
        open={modalOpen}
        onOk={() => form.submit()}
        onCancel={() => setModalOpen(false)}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={handleSave}>
          <Form.Item name="type" label={t("structureTree.type")} rules={[{ required: true }]}>
            <Input disabled />
          </Form.Item>
          <Form.Item name="name" label={t("structureTree.name")} rules={[{ required: true, message: tv("required", { field: t("structureTree.name") }) }]}>
            <Input placeholder={t("structureTree.namePlaceholder")} />
          </Form.Item>
          <Form.Item name="description" label={t("structureTree.description")}>
            <Input.TextArea rows={2} placeholder={t("structureTree.descriptionPlaceholder")} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

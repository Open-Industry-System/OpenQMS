import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Button, Space, Tag, Typography, Input, Select, Table, Card,
  Row, Col, Divider, message, Spin, Popconfirm, Empty,
} from "antd";
import {
  SaveOutlined, ArrowLeftOutlined, SendOutlined,
  CheckOutlined, UndoOutlined, PlusOutlined, DeleteOutlined,
  NodeIndexOutlined,
} from "@ant-design/icons";
import { getFMEA, updateFMEA, transitionFMEA } from "../../api/fmea";
import type { FMEADocument, GraphNode, GraphEdge } from "../../types";
import { useAuthStore } from "../../store/authStore";


const { Title, Text } = Typography;

const nodeTypes = [
  { value: "Process", label: "工序" },
  { value: "Function", label: "功能" },
  { value: "FailureMode", label: "失效模式" },
  { value: "FailureCause", label: "失效原因" },
  { value: "FailureEffect", label: "失效影响" },
  { value: "ControlMeasure", label: "控制措施" },
];

const edgeTypes = [
  { value: "HAS_FUNCTION", label: "包含功能" },
  { value: "HAS_FAILURE_MODE", label: "存在失效模式" },
  { value: "HAS_CAUSE", label: "失效原因" },
  { value: "HAS_EFFECT", label: "失效影响" },
  { value: "CONTROLLED_BY", label: "控制措施" },
  { value: "DETECTED_BY", label: "检测措施" },
];

const statusLabels: Record<string, string> = {
  draft: "草稿", in_review: "审核中", approved: "已批准",
  rework: "返工中", archived: "已归档",
};

const nextTransitions: Record<string, { label: string; target: string; icon: React.ReactNode }[]> = {
  draft: [
    { label: "提交审核", target: "in_review", icon: <SendOutlined /> },
    { label: "归档", target: "archived", icon: <CheckOutlined /> },
  ],
  in_review: [
    { label: "批准", target: "approved", icon: <CheckOutlined /> },
    { label: "打回修改", target: "rework", icon: <UndoOutlined /> },
  ],
  approved: [
    { label: "打回修改", target: "rework", icon: <UndoOutlined /> },
    { label: "归档", target: "archived", icon: <CheckOutlined /> },
  ],
  rework: [
    { label: "重新提交", target: "in_review", icon: <SendOutlined /> },
  ],
};

export default function FMEAEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [fmea, setFmea] = useState<FMEADocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [selectedProcessId, setSelectedProcessId] = useState<string | null>(null);

  const user = useAuthStore((s) => s.user);
  const isViewer = user?.role === "viewer";
  const isAdminOrManager = user?.role === "admin" || user?.role === "manager";

  useEffect(() => {
    if (!id) return;
    getFMEA(id)
      .then((doc) => {
        setFmea(doc);
        setNodes(doc.graph_data?.nodes || []);
        setEdges(doc.graph_data?.edges || []);
      })
      .finally(() => setLoading(false));
  }, [id]);

  const save = useCallback(async () => {
    if (!id || !fmea) return;
    setSaving(true);
    try {
      const updated = await updateFMEA(id, {
        title: fmea.title,
        graph_data: { nodes, edges },
      });
      setFmea(updated);
      message.success("保存成功");
    } catch {
      message.error("保存失败");
    } finally {
      setSaving(false);
    }
  }, [id, fmea, nodes, edges]);

  const handleTransition = async (target: string) => {
    if (!id) return;
    try {
      const updated = await transitionFMEA(id, target);
      setFmea(updated);
      message.success(`状态已变更为: ${statusLabels[target] || target}`);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err?.response?.data?.detail || "操作失败");
    }
  };

  const addNode = () => {
    const type = selectedProcessId ? "Function" : "Process";
    const name = type === "Process"
      ? `OP${(nodes.filter((n) => n.type === "Process").length + 1) * 10}`
      : "新节点";
    setNodes([
      ...nodes,
      {
        id: `n${Date.now()}`,
        type,
        name,
        severity: 0,
        occurrence: 0,
        detection: 0,
      },
    ]);
  };

  const deleteNode = (nodeId: string) => {
    setNodes(nodes.filter((n) => n.id !== nodeId));
    setEdges(edges.filter((e) => e.source !== nodeId && e.target !== nodeId));
  };

  const updateNode = (nodeId: string, field: string, value: unknown) => {
    setNodes(nodes.map((n) => (n.id === nodeId ? { ...n, [field]: value } : n)));
  };

  const addEdge = () => {
    if (nodes.length < 2) {
      message.warning("需要至少两个节点才能添加关系");
      return;
    }
    setEdges([
      ...edges,
      { source: nodes[0].id, target: nodes[1].id, type: "HAS_FUNCTION" },
    ]);
  };

  const deleteEdge = (index: number) => {
    setEdges(edges.filter((_, i) => i !== index));
  };

  const processNodes = nodes.filter((n) => n.type === "Process");

  if (loading) return <Spin size="large" style={{ display: "block", margin: "100px auto" }} />;
  if (!fmea) return <Empty description="FMEA 未找到" />;

  return (
    <div>
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
        }}
      >
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/fmea")}>
            返回
          </Button>
          <Title level={4} style={{ margin: 0 }}>
            {fmea.title}
          </Title>
          <Tag>{statusLabels[fmea.status] || fmea.status}</Tag>
          <Text type="secondary">
            {fmea.document_no} v{fmea.version}
          </Text>
        </Space>
        <Space>
          {nextTransitions[fmea.status]
            ?.filter((t) => {
              if (isViewer) return false;
              if (t.target === "approved" && !isAdminOrManager) return false;
              return true;
            })
            ?.map((t) => (
              <Popconfirm
                key={t.target}
                title={`确认${t.label}？`}
                onConfirm={() => handleTransition(t.target)}
              >
                <Button icon={t.icon}>{t.label}</Button>
              </Popconfirm>
            ))}
          {!isViewer && (
            <Button type="primary" icon={<SaveOutlined />} onClick={save} loading={saving}>
              保存
            </Button>
          )}
        </Space>
      </div>

      <Row gutter={16}>
        {/* Left: Process Flow */}
        <Col span={6}>
          <Card
            title="工序流"
            size="small"
            extra={
              !isViewer && (
                <Button size="small" icon={<PlusOutlined />} onClick={addNode}>
                  添加工序
                </Button>
              )
            }
          >
            {processNodes.map((node) => (
              <div
                key={node.id}
                onClick={() => setSelectedProcessId(node.id)}
                style={{
                  padding: "8px 12px",
                  marginBottom: 8,
                  borderRadius: 6,
                  cursor: "pointer",
                  background: selectedProcessId === node.id ? "#e6f4ff" : "#f5f5f5",
                  border:
                    selectedProcessId === node.id
                      ? "1px solid #1677FF"
                      : "1px solid #d9d9d9",
                }}
              >
                <div style={{ fontWeight: 600 }}>{node.name}</div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {node.process_number}
                </Text>
              </div>
            ))}
            {processNodes.length === 0 && (
              <Empty
                description="暂无工序，点击上方按钮添加"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            )}
          </Card>
        </Col>

        {/* Right: Nodes & Edges */}
        <Col span={18}>
          <Card
            title="FMEA 数据"
            size="small"
            extra={
              !isViewer && (
                <Space>
                  <Button size="small" icon={<PlusOutlined />} onClick={addNode}>
                    添加节点
                  </Button>
                  <Button size="small" icon={<NodeIndexOutlined />} onClick={addEdge}>
                    添加关系
                  </Button>
                </Space>
              )
            }
          >
            {/* Node Table */}
            <Table
              dataSource={nodes}
              rowKey="id"
              size="small"
              pagination={false}
              scroll={{ y: 300 }}
              columns={[
                {
                  title: "类型",
                  dataIndex: "type",
                  key: "type",
                  width: 120,
                  render: (t: string, record: GraphNode) => (
                    <Select
                      value={t}
                      size="small"
                      disabled={isViewer}
                      style={{ width: 110 }}
                      options={nodeTypes}
                      onChange={(v) => updateNode(record.id, "type", v)}
                    />
                  ),
                },
                {
                  title: "名称",
                  dataIndex: "name",
                  key: "name",
                  render: (t: string, record: GraphNode) => (
                    <Input
                      value={t}
                      size="small"
                      disabled={isViewer}
                      onChange={(e) => updateNode(record.id, "name", e.target.value)}
                    />
                  ),
                },
                {
                  title: "工序号",
                  dataIndex: "process_number",
                  key: "process_number",
                  width: 100,
                  render: (t: string, record: GraphNode) =>
                    record.type === "Process" ? (
                      <Input
                        value={t}
                        size="small"
                        disabled={isViewer}
                        onChange={(e) =>
                          updateNode(record.id, "process_number", e.target.value)
                        }
                      />
                    ) : null,
                },
                {
                  title: "S",
                  key: "severity",
                  width: 60,
                  render: (_: unknown, record: GraphNode) =>
                    record.type === "FailureMode" ? (
                      <Input
                        size="small"
                        type="number"
                        min={1}
                        max={10}
                        disabled={isViewer}
                        value={record.severity || ""}
                        onChange={(e) =>
                          updateNode(record.id, "severity", Number(e.target.value))
                        }
                      />
                    ) : null,
                },
                {
                  title: "O",
                  key: "occurrence",
                  width: 60,
                  render: (_: unknown, record: GraphNode) =>
                    record.type === "FailureMode" ? (
                      <Input
                        size="small"
                        type="number"
                        min={1}
                        max={10}
                        disabled={isViewer}
                        value={record.occurrence || ""}
                        onChange={(e) =>
                          updateNode(record.id, "occurrence", Number(e.target.value))
                        }
                      />
                    ) : null,
                },
                {
                  title: "D",
                  key: "detection",
                  width: 60,
                  render: (_: unknown, record: GraphNode) =>
                    record.type === "FailureMode" ? (
                      <Input
                        size="small"
                        type="number"
                        min={1}
                        max={10}
                        disabled={isViewer}
                        value={record.detection || ""}
                        onChange={(e) =>
                          updateNode(record.id, "detection", Number(e.target.value))
                        }
                      />
                    ) : null,
                },
                {
                  title: "RPN",
                  key: "rpn",
                  width: 70,
                  render: (_: unknown, record: GraphNode) => {
                    if (record.type !== "FailureMode") return null;
                    const rpn = record.severity * record.occurrence * record.detection;
                    const color =
                      rpn >= 100 ? "#FF4D4F" : rpn >= 50 ? "#FAAD14" : "#52C41A";
                    return <Tag color={color}>{rpn || 0}</Tag>;
                  },
                },
                {
                  title: "",
                  key: "actions",
                  width: 40,
                  render: (_: unknown, record: GraphNode) => (
                    <Button
                      type="text"
                      danger
                      size="small"
                      disabled={isViewer}
                      icon={<DeleteOutlined />}
                      onClick={() => deleteNode(record.id)}
                    />
                  ),
                },
              ]}
            />

            <Divider orientation="left" plain style={{ fontSize: 13 }}>
              关系 (Edges)
            </Divider>

            {/* Edge Table */}
            <Table
              dataSource={edges}
              rowKey={(_, i) => String(i)}
              size="small"
              pagination={false}
              scroll={{ y: 200 }}
              columns={[
                {
                  title: "源节点",
                  key: "source",
                  width: 200,
                  render: (_: unknown, record: GraphEdge) => (
                    <Select
                      value={record.source}
                      size="small"
                      disabled={isViewer}
                      style={{ width: 180 }}
                      onChange={(v) => {
                        const newEdges = [...edges];
                        const idx = newEdges.indexOf(record);
                        newEdges[idx] = { ...newEdges[idx], source: v };
                        setEdges(newEdges);
                      }}
                      options={nodes.map((n) => ({
                        value: n.id,
                        label: `${n.name} (${n.type})`,
                      }))}
                    />
                  ),
                },
                {
                  title: "关系类型",
                  key: "type",
                  width: 150,
                  render: (_: unknown, record: GraphEdge) => (
                    <Select
                      value={record.type}
                      size="small"
                      disabled={isViewer}
                      style={{ width: 130 }}
                      options={edgeTypes}
                      onChange={(v) => {
                        const newEdges = [...edges];
                        const idx = newEdges.indexOf(record);
                        newEdges[idx] = { ...newEdges[idx], type: v };
                        setEdges(newEdges);
                      }}
                    />
                  ),
                },
                {
                  title: "目标节点",
                  key: "target",
                  width: 200,
                  render: (_: unknown, record: GraphEdge) => (
                    <Select
                      value={record.target}
                      size="small"
                      disabled={isViewer}
                      style={{ width: 180 }}
                      onChange={(v) => {
                        const newEdges = [...edges];
                        const idx = newEdges.indexOf(record);
                        newEdges[idx] = { ...newEdges[idx], target: v };
                        setEdges(newEdges);
                      }}
                      options={nodes.map((n) => ({
                        value: n.id,
                        label: `${n.name} (${n.type})`,
                      }))}
                    />
                  ),
                },
                {
                  title: "",
                  key: "actions",
                  width: 40,
                  render: (_: unknown, _record: GraphEdge, index: number) => (
                    <Button
                      type="text"
                      danger
                      size="small"
                      disabled={isViewer}
                      icon={<DeleteOutlined />}
                      onClick={() => deleteEdge(index)}
                    />
                  ),
                },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
}

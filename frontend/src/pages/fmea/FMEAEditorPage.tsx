import { useEffect, useState, useCallback, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Button, Space, Tag, Typography, Input, Table, Card,
  Row, Col, message, Spin, Popconfirm, Empty, Tooltip,
  Descriptions, Divider,
} from "antd";
import {
  SaveOutlined, ArrowLeftOutlined, SendOutlined,
  CheckOutlined, UndoOutlined, PlusOutlined, DeleteOutlined,
} from "@ant-design/icons";
import { getFMEA, updateFMEA, transitionFMEA } from "../../api/fmea";
import type { FMEADocument, GraphNode, GraphEdge } from "../../types";
import { useAuthStore } from "../../store/authStore";
import { calculateAP } from "../../utils/fmea";
import { buildRows, createRowNodes, type FMEARow } from "../../utils/fmeaTable";

const { Title, Text } = Typography;

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

function getStructureNodes(nodes: GraphNode[], fmeaType: string): GraphNode[] {
  if (fmeaType === "DFMEA") {
    return nodes.filter((n) => ["System", "Subsystem", "Component"].includes(n.type));
  }
  return nodes.filter((n) => ["ProcessItem", "ProcessStep", "ProcessWorkElement"].includes(n.type));
}

function getFunctionNodes(nodes: GraphNode[], fmeaType: string): GraphNode[] {
  if (fmeaType === "DFMEA") {
    return nodes.filter((n) =>
      ["System", "Subsystem", "Component", "ProcessItemFunction", "ProcessStepFunction", "ProcessWorkElementFunction"].includes(n.type)
    );
  }
  return nodes.filter((n) =>
    ["ProcessItem", "ProcessStep", "ProcessWorkElement", "ProcessItemFunction", "ProcessStepFunction", "ProcessWorkElementFunction"].includes(n.type)
  );
}

export default function FMEAEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [fmea, setFmea] = useState<FMEADocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [selectedFunctionId, setSelectedFunctionId] = useState<string | null>(null);

  const user = useAuthStore((s) => s.user);
  const isViewer = user?.role === "viewer";
  const isAdminOrManager = user?.role === "admin" || user?.role === "manager";

  useEffect(() => {
    if (!id) return;
    getFMEA(id)
      .then((doc) => {
        setFmea(doc);
        const loadedNodes = doc.graph_data?.nodes || [];
        setNodes(loadedNodes);
        setEdges(doc.graph_data?.edges || []);
        // Auto-select first function node so "添加行" is immediately usable
        const firstFn = loadedNodes.find((n: GraphNode) =>
          ["ProcessItem", "ProcessStep", "ProcessWorkElement",
           "System", "Subsystem", "Component",
           "ProcessItemFunction", "ProcessStepFunction", "ProcessWorkElementFunction"].includes(n.type)
        );
        if (firstFn) setSelectedFunctionId(firstFn.id);
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

  const updateNode = useCallback((nodeId: string, field: string, value: unknown) => {
    setNodes((prev) => prev.map((n) => (n.id === nodeId ? { ...n, [field]: value } : n)));
  }, []);

  const nodeMap = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  const rows = useMemo(() => buildRows(nodes, edges), [nodes, edges]);

  const rowsByFunction = useMemo(() => {
    const groups: Record<string, FMEARow[]> = {};
    for (const row of rows) {
      if (!groups[row.functionNodeId]) groups[row.functionNodeId] = [];
      groups[row.functionNodeId].push(row);
    }
    return groups;
  }, [rows]);

  const addRow = useCallback(() => {
    if (!selectedFunctionId || !fmea) {
      message.warning("请先在左侧选择一个功能/工序节点");
      return;
    }
    const { newNodes, newEdges } = createRowNodes(selectedFunctionId, fmea.fmea_type);
    setNodes((prev) => [...prev, ...newNodes]);
    setEdges((prev) => [...prev, ...newEdges]);
  }, [selectedFunctionId, fmea]);

  const deleteRow = useCallback((row: FMEARow) => {
    // Only delete nodes that are NOT shared with other rows
    const otherRows = rows.filter((r) => r.key !== row.key);
    const nodesUsedByOthers = new Set<string>();
    for (const r of otherRows) {
      nodesUsedByOthers.add(r.failureModeNodeId);
      if (r.failureEffectNodeId) nodesUsedByOthers.add(r.failureEffectNodeId);
      if (r.failureCauseNodeId) nodesUsedByOthers.add(r.failureCauseNodeId);
    }

    const idsToDelete = new Set<string>();
    // Always delete this row's unique edges
    const edgesToDelete = new Set<string>();
    edgesToDelete.add(row.failureModeNodeId);

    if (row.failureCauseNodeId && !nodesUsedByOthers.has(row.failureCauseNodeId)) {
      idsToDelete.add(row.failureCauseNodeId);
    }
    if (row.failureEffectNodeId && !nodesUsedByOthers.has(row.failureEffectNodeId)) {
      idsToDelete.add(row.failureEffectNodeId);
    }
    if (!nodesUsedByOthers.has(row.failureModeNodeId)) {
      idsToDelete.add(row.failureModeNodeId);
    }
    row.preventionControlIds.forEach((id) => idsToDelete.add(id));
    row.detectionControlIds.forEach((id) => idsToDelete.add(id));
    row.recommendedActionIds.forEach((id) => idsToDelete.add(id));

    setNodes((prev) => prev.filter((n) => !idsToDelete.has(n.id)));
    // Delete edges connected to deleted nodes AND edges specific to this row
    setEdges((prev) => prev.filter((e) => {
      if (idsToDelete.has(e.source) || idsToDelete.has(e.target)) return false;
      // Delete the specific cause→mode edge for this row
      if (e.source === row.failureCauseNodeId && e.target === row.failureModeNodeId && e.type === "CAUSE_OF") return false;
      return true;
    }));
  }, [rows]);

  const structureNodes = fmea ? getStructureNodes(nodes, fmea.fmea_type) : [];
  const functionNodes = fmea ? getFunctionNodes(nodes, fmea.fmea_type) : [];

  if (loading) return <Spin size="large" style={{ display: "block", margin: "100px auto" }} />;
  if (!fmea) return <Empty description="FMEA 未找到" />;

  const isDFMEA = fmea.fmea_type === "DFMEA";

    const columns = [
    {
      title: "过程项 / 功能要求",
      key: "function",
      width: 140,
      fixed: "left" as const,
      render: (_: unknown, row: FMEARow) => {
        const funcNode = nodeMap.get(row.functionNodeId);
        return (
          <div>
            <div style={{ fontWeight: 600, fontSize: 12 }}>{funcNode?.name || "-"}</div>
            {funcNode?.specification && (
              <Text type="secondary" style={{ fontSize: 10 }}>{funcNode.specification}</Text>
            )}
            {funcNode?.requirement && (
              <div><Text type="secondary" style={{ fontSize: 10, color: "#8c8c8c" }}>{funcNode.requirement}</Text></div>
            )}
          </div>
        );
      },
    },
    {
      title: "失效模式",
      key: "failureMode",
      width: 130,
      render: (_: unknown, row: FMEARow) => {
        const node = nodeMap.get(row.failureModeNodeId);
        return (
          <Input.TextArea
            value={node?.name || ""}
            rows={2}
            disabled={isViewer}
            onChange={(e) => updateNode(row.failureModeNodeId, "name", e.target.value)}
          />
        );
      },
    },
    {
      title: "失效影响",
      key: "failureEffect",
      width: 140,
      render: (_: unknown, row: FMEARow) => {
        if (!row.failureEffectNodeId) return "-";
        const node = nodeMap.get(row.failureEffectNodeId);
        return (
          <Input.TextArea
            value={node?.name || ""}
            rows={2}
            disabled={isViewer}
            onChange={(e) => updateNode(row.failureEffectNodeId!, "name", e.target.value)}
          />
        );
      },
    },
    {
      title: <Tooltip title="严重度 (1-10, 10最严重)">S</Tooltip>,
      key: "severity",
      width: 60,
      align: "center" as const,
      render: (_: unknown, row: FMEARow) => {
        if (!row.failureEffectNodeId) return "-";
        const node = nodeMap.get(row.failureEffectNodeId);
        return (
          <Input
            min={1}
            max={10}
            size="small"
            value={node?.severity || undefined}
            disabled={isViewer}
            style={{ width: 55, textAlign: "center" }}
            onChange={(e) => updateNode(row.failureEffectNodeId!, "severity", Number(e.target.value) || 0)}
          />
        );
      },
    },
    {
      title: <Tooltip title="分类 (CC/SC)">Class</Tooltip>,
      key: "class",
      width: 60,
      align: "center" as const,
      render: (_: unknown, row: FMEARow) => {
        const node = nodeMap.get(row.failureModeNodeId);
        return (
          <Input
            size="small"
            value={node?.classification || ""}
            disabled={isViewer}
            style={{ width: 55, textAlign: "center" }}
            onChange={(e) => updateNode(row.failureModeNodeId, "classification", e.target.value)}
          />
        );
      },
    },
    {
      title: "失效起因",
      key: "failureCause",
      width: 140,
      render: (_: unknown, row: FMEARow) => {
        if (!row.failureCauseNodeId) return "-";
        const node = nodeMap.get(row.failureCauseNodeId);
        return (
          <Input.TextArea
            value={node?.name || ""}
            rows={2}
            disabled={isViewer}
            onChange={(e) => updateNode(row.failureCauseNodeId!, "name", e.target.value)}
          />
        );
      },
    },
    {
      title: <Tooltip title="发生度 (1-10, 10最高)">O</Tooltip>,
      key: "occurrence",
      width: 60,
      align: "center" as const,
      render: (_: unknown, row: FMEARow) => {
        if (!row.failureCauseNodeId) return "-";
        const node = nodeMap.get(row.failureCauseNodeId);
        return (
          <Input
            min={1}
            max={10}
            size="small"
            value={node?.occurrence || undefined}
            disabled={isViewer}
            style={{ width: 55, textAlign: "center" }}
            onChange={(e) => updateNode(row.failureCauseNodeId!, "occurrence", Number(e.target.value) || 0)}
          />
        );
      },
    },
    {
      title: "预防控制",
      key: "preventionControl",
      width: 130,
      render: (_: unknown, row: FMEARow) => {
        if (row.preventionControlIds.length === 0) return "-";
        const node = nodeMap.get(row.preventionControlIds[0]);
        return (
          <Input.TextArea
            value={node?.name || ""}
            rows={2}
            disabled={isViewer}
            onChange={(e) => updateNode(row.preventionControlIds[0], "name", e.target.value)}
          />
        );
      },
    },
    {
      title: "探测控制",
      key: "detectionControl",
      width: 130,
      render: (_: unknown, row: FMEARow) => {
        if (row.detectionControlIds.length === 0) return "-";
        const node = nodeMap.get(row.detectionControlIds[0]);
        return (
          <Input.TextArea
            value={node?.name || ""}
            rows={2}
            disabled={isViewer}
            onChange={(e) => updateNode(row.detectionControlIds[0], "name", e.target.value)}
          />
        );
      },
    },
    {
      title: <Tooltip title="探测度 (1-10, 10最低)">D</Tooltip>,
      key: "detection",
      width: 60,
      align: "center" as const,
      render: (_: unknown, row: FMEARow) => {
        if (row.detectionControlIds.length === 0) return "-";
        const node = nodeMap.get(row.detectionControlIds[0]);
        return (
          <Input
            min={1}
            max={10}
            size="small"
            value={node?.detection || undefined}
            disabled={isViewer}
            style={{ width: 55, textAlign: "center" }}
            onChange={(e) => updateNode(row.detectionControlIds[0], "detection", Number(e.target.value) || 0)}
          />
        );
      },
    },
    {
      title: <Tooltip title="风险优先数 S×O×D">RPN</Tooltip>,
      key: "rpn",
      width: 60,
      align: "center" as const,
      render: (_: unknown, row: FMEARow) => {
        const effectNode = row.failureEffectNodeId ? nodeMap.get(row.failureEffectNodeId) : null;
        const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
        const detectionNode = row.detectionControlIds.length > 0 ? nodeMap.get(row.detectionControlIds[0]) : null;

        const s = effectNode?.severity || 0;
        const o = causeNode?.occurrence || 0;
        const d = detectionNode?.detection || 0;
        const rpn = s * o * d;

        const bgColor = rpn >= 100 ? "#ff4d4f" : rpn >= 50 ? "#fa8c16" : rpn > 0 ? "#52c41a" : "#d9d9d9";
        return (
          <Tag color={rpn >= 100 ? "red" : rpn >= 50 ? "orange" : rpn > 0 ? "green" : "default"}
            style={{ fontWeight: 700, fontSize: 13, minWidth: 48, textAlign: "center" }}>
            {rpn || 0}
          </Tag>
        );
      },
    },
    {
      title: <Tooltip title="措施优先级 H/M/L">AP</Tooltip>,
      key: "ap",
      width: 55,
      align: "center" as const,
      render: (_: unknown, row: FMEARow) => {
        const effectNode = row.failureEffectNodeId ? nodeMap.get(row.failureEffectNodeId) : null;
        const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
        const detectionNode = row.detectionControlIds.length > 0 ? nodeMap.get(row.detectionControlIds[0]) : null;

        const s = effectNode?.severity || 0;
        const o = causeNode?.occurrence || 0;
        const d = detectionNode?.detection || 0;
        const ap = calculateAP(s, o, d);

        if (!ap) return <Text type="secondary">-</Text>;
        const apColors: Record<string, { bg: string; text: string }> = {
          H: { bg: "#fff1f0", text: "#cf1322" },
          M: { bg: "#fff7e6", text: "#d46b08" },
          L: { bg: "#f6ffed", text: "#389e0d" },
        };
        const c = apColors[ap];
        return (
          <Tag style={{ background: c.bg, color: c.text, borderColor: c.text, fontWeight: 700, fontSize: 13, minWidth: 36, textAlign: "center" }}>
            {ap}
          </Tag>
        );
      },
    },
    {
      title: "建议措施",
      key: "recommendedAction",
      width: 140,
      render: (_: unknown, row: FMEARow) => {
        if (row.recommendedActionIds.length === 0) {
          return (
            <Button
              size="small"
              type="dashed"
              disabled={isViewer}
              onClick={() => {
                const ts = Date.now();
                const raId = `n${ts}_ra`;
                const newNode: GraphNode = {
                  id: raId,
                  type: "RecommendedAction",
                  name: "新建议措施",
                  severity: 0,
                  occurrence: 0,
                  detection: 0,
                };
                const sourceId = row.failureCauseNodeId || row.failureModeNodeId;
                const newEdge: GraphEdge = { source: sourceId, target: raId, type: "OPTIMIZED_BY" };
                setNodes((prev) => [...prev, newNode]);
                setEdges((prev) => [...prev, newEdge]);
              }}
            >
              + 添加
            </Button>
          );
        }
        const node = nodeMap.get(row.recommendedActionIds[0]);
        return (
          <Input.TextArea
            value={node?.name || ""}
            rows={2}
            disabled={isViewer}
            onChange={(e) => updateNode(row.recommendedActionIds[0], "name", e.target.value)}
          />
        );
      },
    },
    {
      title: "责任人 / 期限",
      key: "responsibility",
      width: 120,
      render: (_: unknown, row: FMEARow) => {
        if (row.recommendedActionIds.length === 0) return "-";
        const node = nodeMap.get(row.recommendedActionIds[0]);
        return (
          <div>
            <Input
              size="small"
              placeholder="责任人"
              value={node?.responsible || ""}
              disabled={isViewer}
              style={{ marginBottom: 4 }}
              onChange={(e) => updateNode(row.recommendedActionIds[0], "responsible", e.target.value)}
            />
            <Input
              size="small"
              placeholder="YYYY-MM-DD"
              value={node?.due_date || ""}
              disabled={isViewer}
              onChange={(e) => updateNode(row.recommendedActionIds[0], "due_date", e.target.value)}
            />
          </div>
        );
      },
    },
    {
      title: "已采取措施",
      key: "actionsTaken",
      width: 130,
      render: (_: unknown, row: FMEARow) => {
        if (row.recommendedActionIds.length === 0) return "-";
        const node = nodeMap.get(row.recommendedActionIds[0]);
        return (
          <Input.TextArea
            value={node?.action_taken || ""}
            rows={2}
            disabled={isViewer}
            onChange={(e) => updateNode(row.recommendedActionIds[0], "action_taken", e.target.value)}
          />
        );
      },
    },
    {
      title: <Tooltip title="改进后严重度">S'</Tooltip>,
      key: "revisedSeverity",
      width: 55,
      align: "center" as const,
      render: (_: unknown, row: FMEARow) => {
        if (row.recommendedActionIds.length === 0) return "-";
        const node = nodeMap.get(row.recommendedActionIds[0]);
        return (
          <Input
            min={1}
            max={10}
            size="small"
            value={node?.revised_severity || undefined}
            disabled={isViewer}
            style={{ width: 48, textAlign: "center" }}
            onChange={(e) => updateNode(row.recommendedActionIds[0], "revised_severity", Number(e.target.value) || 0)}
          />
        );
      },
    },
    {
      title: <Tooltip title="改进后发生度">O'</Tooltip>,
      key: "revisedOccurrence",
      width: 55,
      align: "center" as const,
      render: (_: unknown, row: FMEARow) => {
        if (row.recommendedActionIds.length === 0) return "-";
        const node = nodeMap.get(row.recommendedActionIds[0]);
        return (
          <Input
            min={1}
            max={10}
            size="small"
            value={node?.revised_occurrence || undefined}
            disabled={isViewer}
            style={{ width: 48, textAlign: "center" }}
            onChange={(e) => updateNode(row.recommendedActionIds[0], "revised_occurrence", Number(e.target.value) || 0)}
          />
        );
      },
    },
    {
      title: <Tooltip title="改进后探测度">D'</Tooltip>,
      key: "revisedDetection",
      width: 55,
      align: "center" as const,
      render: (_: unknown, row: FMEARow) => {
        if (row.recommendedActionIds.length === 0) return "-";
        const node = nodeMap.get(row.recommendedActionIds[0]);
        return (
          <Input
            min={1}
            max={10}
            size="small"
            value={node?.revised_detection || undefined}
            disabled={isViewer}
            style={{ width: 48, textAlign: "center" }}
            onChange={(e) => updateNode(row.recommendedActionIds[0], "revised_detection", Number(e.target.value) || 0)}
          />
        );
      },
    },
    {
      title: <Tooltip title="改进后RPN">RPN'</Tooltip>,
      key: "revisedRpn",
      width: 60,
      align: "center" as const,
      render: (_: unknown, row: FMEARow) => {
        if (row.recommendedActionIds.length === 0) return "-";
        const node = nodeMap.get(row.recommendedActionIds[0]);
        const s = node?.revised_severity || 0;
        const o = node?.revised_occurrence || 0;
        const d = node?.revised_detection || 0;
        const rpn = s * o * d;
        const bgColor = rpn >= 100 ? "#ff4d4f" : rpn >= 50 ? "#fa8c16" : rpn > 0 ? "#52c41a" : "#d9d9d9";
        return (
          <Tag color={rpn >= 100 ? "red" : rpn >= 50 ? "orange" : rpn > 0 ? "green" : "default"}
            style={{ fontWeight: 700, fontSize: 13, minWidth: 48, textAlign: "center" }}>
            {rpn || 0}
          </Tag>
        );
      },
    },
    {
      title: "",
      key: "actions",
      width: 40,
      fixed: "right" as const,
      render: (_: unknown, row: FMEARow) => (
        <Popconfirm title="确认删除此行？" onConfirm={() => deleteRow(row)}>
          <Button type="text" danger size="small" disabled={isViewer} icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ];

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/fmea")}>返回</Button>
          <Title level={4} style={{ margin: 0 }}>{fmea.title}</Title>
          <Tag color={isDFMEA ? "green" : "blue"}>{isDFMEA ? "DFMEA" : "PFMEA"}</Tag>
          <Tag>{statusLabels[fmea.status] || fmea.status}</Tag>
          <Text type="secondary">{fmea.document_no} v{fmea.version}</Text>
        </Space>
        <Space>
          {nextTransitions[fmea.status]
            ?.filter((t) => {
              if (isViewer) return false;
              if (t.target === "approved" && !isAdminOrManager) return false;
              return true;
            })
            ?.map((t) => (
              <Popconfirm key={t.target} title={`确认${t.label}？`} onConfirm={() => handleTransition(t.target)}>
                <Button icon={t.icon}>{t.label}</Button>
              </Popconfirm>
            ))}
          {!isViewer && (
            <Button type="primary" icon={<SaveOutlined />} onClick={save} loading={saving}>保存</Button>
          )}
        </Space>
      </div>

      {/* FMEA Header Info */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Descriptions size="small" column={4}>
          <Descriptions.Item label={isDFMEA ? "系统" : "过程项"}>
            {structureNodes.find((n) => n.type === (isDFMEA ? "System" : "ProcessItem"))?.name || "-"}
          </Descriptions.Item>
          <Descriptions.Item label={isDFMEA ? "设计责任" : "过程责任"}>
            <Input size="small" placeholder="责任部门" style={{ width: 150 }} disabled={isViewer} />
          </Descriptions.Item>
          <Descriptions.Item label="FMEA 编号">{fmea.document_no}</Descriptions.Item>
          <Descriptions.Item label="关键日期">
            <Input size="small" placeholder="YYYY-MM-DD" style={{ width: 100 }} disabled={isViewer} />
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Row gutter={16}>
        {/* Left: Structure/Function Tree */}
        <Col span={5}>
          <Card
            title={isDFMEA ? "结构 / 功能" : "工序 / 功能"}
            size="small"
            extra={
              !isViewer && (
                <Button size="small" icon={<PlusOutlined />} onClick={addRow} disabled={!selectedFunctionId}>
                  添加行
                </Button>
              )
            }
          >
            {functionNodes.map((node) => {
              const isStructure = ["ProcessItem", "ProcessStep", "ProcessWorkElement", "System", "Subsystem", "Component"].includes(node.type);
              const indent = ["ProcessStep", "Subsystem", "ProcessStepFunction"].includes(node.type)
                ? 12
                : ["ProcessWorkElement", "Component", "ProcessWorkElementFunction"].includes(node.type)
                  ? 24
                  : 0;
              const hasRows = rowsByFunction[node.id]?.length > 0;
              return (
                <div
                  key={node.id}
                  onClick={() => setSelectedFunctionId(node.id)}
                  style={{
                    padding: "5px 10px",
                    marginBottom: 4,
                    marginLeft: indent,
                    borderRadius: 4,
                    cursor: "pointer",
                    background: selectedFunctionId === node.id ? "#e6f4ff" : isStructure ? "#fafafa" : "#fff",
                    border: selectedFunctionId === node.id ? "1px solid #1677FF" : "1px solid #f0f0f0",
                    fontSize: 12,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                  }}
                >
                  <div>
                    <div style={{ fontWeight: isStructure ? 600 : 400 }}>{node.name}</div>
                    {node.process_number && <Text type="secondary" style={{ fontSize: 10 }}>{node.process_number}</Text>}
                  </div>
                  {hasRows && (
                    <Tag color="processing" style={{ fontSize: 10, marginLeft: 4, lineHeight: "16px" }}>
                      {rowsByFunction[node.id].length}
                    </Tag>
                  )}
                </div>
              );
            })}
            {functionNodes.length === 0 && <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
          </Card>
        </Col>

        {/* Right: FMEA Table */}
        <Col span={19}>
          <Card
            title={
              <span style={{ fontSize: 14 }}>
                {isDFMEA ? "设计失效模式与影响分析 (DFMEA)" : "过程失效模式与影响分析 (PFMEA)"}
              </span>
            }
            size="small"
            bodyStyle={{ padding: "8px 0" }}
          >
            <Table
              dataSource={rows}
              columns={columns}
              rowKey="key"
              size="small"
              pagination={false}
              scroll={{ x: 1700, y: 520 }}
              bordered
              rowClassName={(row: FMEARow) => {
                if (selectedFunctionId && row.functionNodeId === selectedFunctionId) return "fmea-row-highlight";
                return "";
              }}
            />
            {rows.length === 0 && (
              <div style={{ textAlign: "center", padding: 40 }}>
                <Text type="secondary">选择左侧功能节点后点击"添加行"开始分析</Text>
              </div>
            )}
          </Card>
        </Col>
      </Row>

      <style>{`
        .fmea-row-highlight td {
          background-color: #e6f4ff !important;
          transition: background-color 0.2s;
        }
        .fmea-row-highlight td:first-child {
          border-left: 3px solid #1677ff !important;
        }
      `}</style>

      <Divider />
      <Text type="secondary" style={{ fontSize: 11 }}>
        S=严重度 O=发生度 D=探测度 | RPN=风险优先数 | AP=措施优先级 (H=高 M=中 L=低) | 带 ' = 改进后评分
      </Text>
    </div>
  );
}

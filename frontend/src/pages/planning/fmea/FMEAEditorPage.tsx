import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import {
  Button, Space, Tag, Typography, Input, Select, Table, Card, Tabs,
  Row, Col, App, Spin, Popconfirm, Empty, Tooltip,
  Descriptions, Divider, Modal, Radio,
} from "antd";
import {
  SaveOutlined, ArrowLeftOutlined, SendOutlined,
  CheckOutlined, UndoOutlined, PlusOutlined, DeleteOutlined,
  HistoryOutlined, RadarChartOutlined,
} from "@ant-design/icons";
import { getFMEA, updateFMEA, transitionFMEA } from "../../../api/fmea";
import { syncFromFMEA, getSeverityWarnings } from "../../../api/specialCharacteristic";
import type { FMEADocument, GraphNode, GraphEdge } from "../../../types";
import { useAuthStore } from "../../../store/authStore";
import { usePermission } from "../../../hooks/usePermission";
import { calculateAP } from "../../../utils/fmea";
import { buildRows, createRowNodes, type FMEARow } from "../../../utils/fmeaTable";
import StructureTree from "../../../components/dfmea/StructureTree";
import ParameterDiagram from "../../../components/dfmea/ParameterDiagram";
import SmartSuggestionDropdown from "../../../components/dfmea/SmartSuggestionDropdown";
import VersionHistoryTab from "../../../components/version/VersionHistoryTab";
import CreateVersionModal from "../../../components/version/CreateVersionModal";
import RollbackConfirmModal from "../../../components/version/RollbackConfirmModal";
import VersionCompareView from "../../../components/version/VersionCompareView";
import RelatedCAPAList from "../../../components/cross-links/RelatedCAPAList";
import { Dropdown } from "antd";
import type { MenuProps } from "antd";
import { GraphCanvas, GraphToolbar, NodeDetailDrawer, GraphLegend } from "../../../components/graph";
import type { GraphLayout, GraphCanvasRef } from "../../../components/graph";
import type { GraphNode as APIGraphNode } from "../../../api/graph";
import { getImpactChain, getCauseChain, normalizeGraphData } from "../../../api/graph";
import { analyzeChangeImpact } from "../../../api/changeImpact";
import { ImpactReportPanel } from "../../../components/change-impact";
import type { AnalyzeChangeImpactRequest, ChangeImpactAnalysis } from "../../../api/changeImpact";
import { useCollaboration } from "../../../hooks/useCollaboration";
import { CollaborationBar, ActiveUserIndicator, ConflictResolutionModal } from "../../../components/collaboration";
import { diffGraphs } from "../../../utils/graphDiff";
import type { ConflictInfo } from "../../../types/collaboration";
import type { GraphDiff } from "../../../utils/graphDiff";

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
  const { message } = App.useApp();
  const { id } = useParams<{ id: string }>();
  const fmeaId = id || "";
  const navigate = useNavigate();
  const [fmea, setFmea] = useState<FMEADocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [selectedFunctionId, setSelectedFunctionId] = useState<string | null>(null);

  const [searchParams] = useSearchParams();
  const highlightNodeId = searchParams.get("node");
  const [highlightedRowKey, setHighlightedRowKey] = useState<string | null>(null);

  const user = useAuthStore((s) => s.user);
  const { canEdit, canApprove } = usePermission();
  const [activeTab, setActiveTab] = useState("failure");
  const [outerTab, setOuterTab] = useState("editor");
  const [createVersionOpen, setCreateVersionOpen] = useState(false);
  const [rollbackTarget, setRollbackTarget] = useState<{ major_no: number; minor_no: number } | null>(null);
  const [compareState, setCompareState] = useState<{ major1: number; minor1: number; major2: number; minor2: number } | null>(null);
  const [selectedStructureNode, setSelectedStructureNode] = useState<GraphNode | null>(null);
  const [severityWarnings, setSeverityWarnings] = useState<string[]>([]);
  const graphDataRef = useRef<{ nodes: APIGraphNode[]; edges: import("../../../api/graph").GraphEdge[] } | null>(null);
  const [selectedGraphNode, setSelectedGraphNode] = useState<APIGraphNode | null>(null);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [graphLayout, setGraphLayout] = useState<GraphLayout>("dagre");
  const [highlightNodes, setHighlightNodes] = useState<string[]>([]);
  const [dimOthers, setDimOthers] = useState(false);
  const [graphLoading, setGraphLoading] = useState(false);
  const canvasRef = useRef<GraphCanvasRef>(null);

  const { activeUsers, startEditing, stopEditing, isSyncing } = useCollaboration("fmea", fmeaId);

  // Base snapshot for three-way diff
  const baseGraphRef = useRef<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(null);

  // Conflict resolution state
  const [conflictVisible, setConflictVisible] = useState(false);
  const [conflictInfo, setConflictInfo] = useState<ConflictInfo | null>(null);
  const [conflictDiff, setConflictDiff] = useState<GraphDiff | null>(null);

  // Change impact analysis state
  const [impactModalOpen, setImpactModalOpen] = useState(false);
  const [impactLoading, setImpactLoading] = useState(false);
  const [impactResult, setImpactResult] = useState<ChangeImpactAnalysis | null>(null);
  const [impactForm, setImpactForm] = useState({
    change_type: "attribute" as "attribute" | "structural",
    field_name: "",
    new_value: "",
  });

  // 右键菜单状态
  const [contextMenuOpen, setContextMenuOpen] = useState(false);
  const [contextMenuPos, setContextMenuPos] = useState({ x: 0, y: 0 });
  const [contextMenuNode, setContextMenuNode] = useState<APIGraphNode | null>(null);
  const [pendingHighlightNode, setPendingHighlightNode] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    getFMEA(id)
      .then((doc) => {
        setFmea(doc);
        const loadedNodes = doc.graph_data?.nodes || [];
        setNodes(loadedNodes);
        setEdges(doc.graph_data?.edges || []);
        // Save base snapshot for conflict diff
        baseGraphRef.current = {
          nodes: JSON.parse(JSON.stringify(doc.graph_data?.nodes || [])),
          edges: JSON.parse(JSON.stringify(doc.graph_data?.edges || [])),
        };
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

  useEffect(() => {
    if (!id) return;
    getSeverityWarnings(id)
      .then((warnings) => setSeverityWarnings(warnings.map((w) => w.node_id)))
      .catch(() => {});
  }, [id]);

  const loadGraphData = useCallback(async () => {
    if (!id || graphDataRef.current) return;
    setGraphLoading(true);
    try {
      const doc = await getFMEA(id);
      const rawNodes = doc.graph_data?.nodes || [];
      const rawEdges = doc.graph_data?.edges || [];
      graphDataRef.current = normalizeGraphData(rawNodes as unknown as Array<Record<string, unknown>>, rawEdges as unknown as Array<Record<string, unknown>>);
      if (pendingHighlightNode) {
        setHighlightNodes([pendingHighlightNode]);
        setDimOthers(true);
        setPendingHighlightNode(null);
      }
    } catch {
      message.error("图谱数据加载失败");
    } finally {
      setGraphLoading(false);
    }
  }, [id, message, pendingHighlightNode]);

  const handleTraceImpact = async (nodeId: string) => {
    if (!id) return;
    try {
      const chain = await getImpactChain(id, nodeId);
      const { nodes } = normalizeGraphData(chain.nodes, chain.edges);
      setHighlightNodes(nodes.map((n) => n.id));
      setDimOthers(true);
    } catch {
      message.error("影响链查询失败");
    }
  };

  const handleTraceCause = async (nodeId: string) => {
    if (!id) return;
    try {
      const chain = await getCauseChain(id, nodeId);
      const { nodes } = normalizeGraphData(chain.nodes, chain.edges);
      setHighlightNodes(nodes.map((n) => n.id));
      setDimOthers(true);
    } catch {
      message.error("原因链查询失败");
    }
  };

  const handleAnalyzeImpact = async () => {
    if (!selectedGraphNode) return;
    setImpactLoading(true);
    try {
      const request: AnalyzeChangeImpactRequest = {
        fmea_id: fmeaId,
        node_id: selectedGraphNode.id,
        node_type: selectedGraphNode.label || "",
        node_name: selectedGraphNode.properties?.name || selectedGraphNode.label || "",
        change_type: impactForm.change_type,
        field_name: impactForm.field_name || undefined,
        new_value: impactForm.new_value || undefined,
      };
      const result = await analyzeChangeImpact(request);
      setImpactResult(result);
      message.success("分析完成");
    } catch {
      message.error("分析失败");
    } finally {
      setImpactLoading(false);
    }
  };

  const save = useCallback(async () => {
    if (!id || !fmea) return;
    setSaving(true);
    try {
      const updated = await updateFMEA(id, {
        title: fmea.title,
        graph_data: { nodes, edges },
        lock_version: fmea.lock_version,
      });
      setFmea(updated);
      // Update base snapshot after successful save
      baseGraphRef.current = {
        nodes: JSON.parse(JSON.stringify(nodes)),
        edges: JSON.parse(JSON.stringify(edges)),
      };
      graphDataRef.current = null; // 保存后清空缓存，下次切回 graph 时重新加载
      message.success("保存成功");
      try {
        if (id) await syncFromFMEA(id);
      } catch { /* silent */ }
    } catch (e: unknown) {
      const err = e as { response?: { status?: number; data?: { detail?: string | object } } };
      if (err.response?.status === 409) {
        const detail = err.response.data?.detail;
        const conflictData = typeof detail === "string" ? JSON.parse(detail) : detail;
        setConflictInfo({
          saved_by: conflictData.conflict?.saved_by || null,
          saved_at: conflictData.conflict?.saved_at || null,
          latest_lock_version: conflictData.conflict?.latest_lock_version || 0,
        });

        // Fetch latest data and compute three-way diff
        try {
          const latestDoc = await getFMEA(id);
          const base = baseGraphRef.current;
          if (base) {
            const diff = diffGraphs(
              base.nodes, base.edges,
              latestDoc.graph_data?.nodes || [], latestDoc.graph_data?.edges || [],
              nodes, edges
            );
            setConflictDiff(diff);
          }
        } catch {
          /* silently ignore diff failure */
        }
        setConflictVisible(true);
      } else {
        message.error("保存失败");
      }
    } finally {
      setSaving(false);
    }
  }, [id, fmea, nodes, edges]);

  const handleConflictRefresh = () => {
    setConflictVisible(false);
    window.location.reload();
  };

  const handleConflictForceSave = async () => {
    if (!id || !fmea || !conflictInfo) return;
    setSaving(true);
    try {
      const updated = await updateFMEA(id, {
        title: fmea.title,
        graph_data: { nodes, edges },
        lock_version: fmea.lock_version,
        confirmed_latest_lock_version: conflictInfo.latest_lock_version,
      });
      setFmea(updated);
      baseGraphRef.current = {
        nodes: JSON.parse(JSON.stringify(nodes)),
        edges: JSON.parse(JSON.stringify(edges)),
      };
      setConflictVisible(false);
      message.success("强制保存成功");
    } catch (e: unknown) {
      const err = e as { response?: { status?: number; data?: { detail?: string } } };
      if (err.response?.status === 409) {
        message.error("文档又被修改了，请刷新后重试");
      } else {
        message.error("强制保存失败");
      }
    } finally {
      setSaving(false);
    }
  };

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

  // Auto-compute initial AP on cause nodes when S/O/D risk ratings change
  const nodesRiskKey = nodes
    .filter((n) => n.type === "FailureCause")
    .map((n) => `${n.id}:${n.severity}:${n.occurrence}:${n.detection}`)
    .join("|");

  useEffect(() => {
    setNodes((prev) => {
      let changed = false;
      const updated = prev.map((n) => {
        if (n.type !== "FailureCause") return n;
        const computed = calculateAP(n.severity || 0, n.occurrence || 0, n.detection || 0);
        if (computed && n.ap !== computed) { changed = true; return { ...n, ap: computed }; }
        if (!computed && n.ap) { changed = true; return { ...n, ap: undefined }; }
        return n;
      });
      return changed ? updated : prev;
    });
  }, [nodesRiskKey]);

  const nodeMap = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  const rows = useMemo(() => buildRows(nodes, edges), [nodes, edges]);

  useEffect(() => {
    if (outerTab === "graph") {
      loadGraphData();
    }
  }, [outerTab, loadGraphData]);

  // 响应 URL ?tab=graph&highlightNode=... 参数
  useEffect(() => {
    const tabParam = searchParams.get("tab");
    const highlightParam = searchParams.get("highlightNode");
    if (tabParam === "graph") {
      setOuterTab("graph");
      if (highlightParam) {
        setPendingHighlightNode(highlightParam);
      }
    }
  }, [searchParams]);

  // 如果图谱数据已缓存，直接应用待高亮节点
  useEffect(() => {
    if (pendingHighlightNode && graphDataRef.current) {
      setHighlightNodes([pendingHighlightNode]);
      setDimOthers(true);
      setPendingHighlightNode(null);
    }
  }, [pendingHighlightNode]);

  useEffect(() => {
    if (highlightNodeId && rows.length > 0) {
      const targetRow = rows.find(
        (r) => r.failureModeNodeId === highlightNodeId
      );
      if (targetRow) {
        setHighlightedRowKey(targetRow.key);
        setTimeout(() => {
          const el = document.querySelector(`[data-row-key="${targetRow.key}"]`);
          el?.scrollIntoView({ behavior: "smooth", block: "center" });
        }, 300);
      }
    }
  }, [highlightNodeId, rows]);

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
          <div
            tabIndex={0}
            style={{ outline: "none" }}
          >
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
          <SmartSuggestionDropdown
            triggerType="failure_mode"
            context={{
              function_description: nodeMap.get(row.functionNodeId)?.name || "",
            }}
            fmeaId={fmeaId}
            value={node?.name || ""}
            onChange={(val) => updateNode(row.failureModeNodeId, "name", val)}
            onSelect={(s) => updateNode(row.failureModeNodeId, "name", s.name)}
            disabled={!canEdit('fmea')}
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
          <SmartSuggestionDropdown
            triggerType="failure_effect"
            context={{
              failure_mode: nodeMap.get(row.failureModeNodeId)?.name || "",
              function_description: nodeMap.get(row.functionNodeId)?.name || "",
            }}
            fmeaId={fmeaId}
            value={node?.name || ""}
            onChange={(val) => updateNode(row.failureEffectNodeId!, "name", val)}
            onSelect={(s) => updateNode(row.failureEffectNodeId!, "name", s.name)}
            disabled={!canEdit('fmea')}
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
          <div>
            <Input
              min={1}
              max={10}
              size="small"
              value={node?.severity ?? undefined}
              disabled={!canEdit('fmea')}
              style={{ width: 55, textAlign: "center" }}
              onFocus={() => startEditing({ row_key: row.key, field: "severity", node_id: row.failureModeNodeId })}
              onBlur={stopEditing}
              onChange={(e) => updateNode(row.failureEffectNodeId!, "severity", Number(e.target.value) || 0)}
            />
            <ActiveUserIndicator
              activeUsers={activeUsers}
              rowKey={row.key}
              field="severity"
            />
          </div>
        );
      },
    },
    {
      title: <Tooltip title={fmea.fmea_type === "DFMEA" ? "筛选器代码 (Filter Code)" : "分类 (CC/SC)"}>Class</Tooltip>,
      key: "class",
      width: 70,
      align: "center" as const,
      render: (_: unknown, row: FMEARow) => {
        const node = nodeMap.get(row.failureModeNodeId);
        const classValue = node?.classification || "";
        const bgStyle = classValue === "CC" ? { background: "#fff1f0" } : classValue === "SC" ? { background: "#fffbe6" } : {};
        return (
          <Select
            size="small"
            value={classValue || undefined}
            onChange={(value) => updateNode(row.failureModeNodeId, "classification", value || "")}
            disabled={!canEdit('fmea')}
            style={{ width: 60, ...bgStyle }}
            options={[{ value: "", label: "-" }, { value: "CC", label: "CC" }, { value: "SC", label: "SC" }]}
          />
        );
      },
    },
    {
      title: "失效原因",
      key: "failureCause",
      width: 140,
      render: (_: unknown, row: FMEARow) => {
        if (!row.failureCauseNodeId) return "-";
        const node = nodeMap.get(row.failureCauseNodeId);
        const effectNode = row.failureEffectNodeId ? nodeMap.get(row.failureEffectNodeId) : null;
        return (
          <SmartSuggestionDropdown
            triggerType="failure_cause"
            context={{
              failure_mode: nodeMap.get(row.failureModeNodeId)?.name || "",
              function_description: nodeMap.get(row.functionNodeId)?.name || "",
              severity: effectNode?.severity || 0,
            }}
            fmeaId={fmeaId}
            value={node?.name || ""}
            onChange={(val) => updateNode(row.failureCauseNodeId!, "name", val)}
            onSelect={(s) => updateNode(row.failureCauseNodeId!, "name", s.name)}
            disabled={!canEdit('fmea')}
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
          <div>
            <Input
              min={1}
              max={10}
              size="small"
              value={node?.occurrence ?? undefined}
              disabled={!canEdit('fmea')}
              style={{ width: 55, textAlign: "center" }}
              onFocus={() => startEditing({ row_key: row.key, field: "occurrence", node_id: row.failureModeNodeId })}
              onBlur={stopEditing}
              onChange={(e) => updateNode(row.failureCauseNodeId!, "occurrence", Number(e.target.value) || 0)}
            />
            <ActiveUserIndicator
              activeUsers={activeUsers}
              rowKey={row.key}
              field="occurrence"
            />
          </div>
        );
      },
    },
    {
      title: "预防措施",
      key: "preventionControl",
      width: 140,
      render: (_: unknown, row: FMEARow) => {
        const nodeId = row.preventionControlIds[0];
        if (!nodeId) return "-";
        const node = nodeMap.get(nodeId);
        const effectNode = row.failureEffectNodeId ? nodeMap.get(row.failureEffectNodeId) : null;
        const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
        const detNode = row.detectionControlIds.length > 0 ? nodeMap.get(row.detectionControlIds[0]) : null;
        const ap = calculateAP(effectNode?.severity || 0, causeNode?.occurrence || 0, detNode?.detection || 0);
        return (
          <SmartSuggestionDropdown
            triggerType="measure"
            context={{
              failure_mode: nodeMap.get(row.failureModeNodeId)?.name || "",
              ap: ap,
            }}
            fmeaId={fmeaId}
            value={node?.name || ""}
            onChange={(val) => updateNode(nodeId, "name", val)}
            onSelect={(s) => updateNode(nodeId, "name", s.name)}
            disabled={!canEdit('fmea')}
          />
        );
      },
    },
    {
      title: "检测措施",
      key: "detectionControl",
      width: 140,
      render: (_: unknown, row: FMEARow) => {
        const nodeId = row.detectionControlIds[0];
        if (!nodeId) return "-";
        const node = nodeMap.get(nodeId);
        const effectNode = row.failureEffectNodeId ? nodeMap.get(row.failureEffectNodeId) : null;
        const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
        const ap = calculateAP(effectNode?.severity || 0, causeNode?.occurrence || 0, node?.detection || 0);
        return (
          <SmartSuggestionDropdown
            triggerType="measure"
            context={{
              failure_mode: nodeMap.get(row.failureModeNodeId)?.name || "",
              ap: ap,
            }}
            fmeaId={fmeaId}
            value={node?.name || ""}
            onChange={(val) => updateNode(nodeId, "name", val)}
            onSelect={(s) => updateNode(nodeId, "name", s.name)}
            disabled={!canEdit('fmea')}
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
          <div>
            <Input
              min={1}
              max={10}
              size="small"
              value={node?.detection ?? undefined}
              disabled={!canEdit('fmea')}
              style={{ width: 55, textAlign: "center" }}
              onFocus={() => startEditing({ row_key: row.key, field: "detection", node_id: row.failureModeNodeId })}
              onBlur={stopEditing}
              onChange={(e) => updateNode(row.detectionControlIds[0], "detection", Number(e.target.value) || 0)}
            />
            <ActiveUserIndicator
              activeUsers={activeUsers}
              rowKey={row.key}
              field="detection"
            />
          </div>
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
              disabled={!canEdit('fmea')}
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
        const nodeId = row.recommendedActionIds[0];
        const node = nodeMap.get(nodeId);
        const effectNode = row.failureEffectNodeId ? nodeMap.get(row.failureEffectNodeId) : null;
        const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
        const detNode = row.detectionControlIds.length > 0 ? nodeMap.get(row.detectionControlIds[0]) : null;
        return (
          <SmartSuggestionDropdown
            triggerType="optimization"
            context={{
              failure_mode: nodeMap.get(row.failureModeNodeId)?.name || "",
              severity: effectNode?.severity || 0,
              occurrence: causeNode?.occurrence || 0,
              detection: detNode?.detection || 0,
              ap: calculateAP(effectNode?.severity || 0, causeNode?.occurrence || 0, detNode?.detection || 0),
            }}
            fmeaId={fmeaId}
            value={node?.name || ""}
            onChange={(val) => updateNode(nodeId, "name", val)}
            onSelect={(s) => updateNode(nodeId, "name", s.name)}
            disabled={!canEdit('fmea')}
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
              disabled={!canEdit('fmea')}
              style={{ marginBottom: 4 }}
              onChange={(e) => updateNode(row.recommendedActionIds[0], "responsible", e.target.value)}
            />
            <Input
              size="small"
              placeholder="YYYY-MM-DD"
              value={node?.due_date || ""}
              disabled={!canEdit('fmea')}
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
            disabled={!canEdit('fmea')}
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
            value={node?.revised_severity ?? undefined}
            disabled={!canEdit('fmea')}
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
            value={node?.revised_occurrence ?? undefined}
            disabled={!canEdit('fmea')}
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
            value={node?.revised_detection ?? undefined}
            disabled={!canEdit('fmea')}
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
          <Button type="text" danger size="small" disabled={!canEdit('fmea')} icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ];

  return (
    <div>
      <CollaborationBar activeUsers={activeUsers} isSyncing={isSyncing} />

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
              if (!canEdit('fmea')) return false;
              if (t.target === "approved" && !canApprove('fmea')) return false;
              return true;
            })
            ?.map((t) => (
              <Popconfirm key={t.target} title={`确认${t.label}？`} onConfirm={() => handleTransition(t.target)}>
                <Button icon={t.icon}>{t.label}</Button>
              </Popconfirm>
            ))}
          {canEdit('fmea') && (
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
            <Input size="small" placeholder="责任部门" style={{ width: 150 }} disabled={!canEdit('fmea')} />
          </Descriptions.Item>
          <Descriptions.Item label="FMEA 编号">{fmea.document_no}</Descriptions.Item>
          <Descriptions.Item label="关键日期">
            <Input size="small" placeholder="YYYY-MM-DD" style={{ width: 100 }} disabled={!canEdit('fmea')} />
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Tabs activeKey={outerTab} onChange={setOuterTab} style={{ marginBottom: 16 }}>
        <Tabs.TabPane tab="编辑器" key="editor">
          <Tabs activeKey={activeTab} onChange={setActiveTab} style={{ marginBottom: 16 }}>
        <Tabs.TabPane tab="失效分析" key="failure">
          <Row gutter={16}>
            {/* Left: Structure/Function Tree */}
            <Col span={5}>
          <Card
            title={isDFMEA ? "结构 / 功能" : "工序 / 功能"}
            size="small"
            extra={
              canEdit('fmea') && (
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
                const classes = [];
                if (selectedFunctionId && row.functionNodeId === selectedFunctionId) classes.push("fmea-row-highlight");
                if (severityWarnings.includes(row.failureModeNodeId)) classes.push("severity-warning-row");
                if (row.key === highlightedRowKey) classes.push("highlighted-row");
                return classes.join(" ");
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
        </Tabs.TabPane>
        <Tabs.TabPane tab="结构分析" key="structure">
          <Row gutter={16}>
            <Col span={8}>
              <Card title="结构树" size="small">
                <StructureTree
                  nodes={nodes}
                  edges={edges}
                  onUpdateNodes={setNodes}
                  onUpdateEdges={setEdges}
                  isViewer={!canEdit('fmea')}
                  onSelectNode={(node) => setSelectedStructureNode(node)}
                />
              </Card>
            </Col>
            <Col span={16}>
              <Card title="节点详情" size="small">
                <ParameterDiagram
                  node={selectedStructureNode}
                  onUpdateNode={(nodeId, updates) => {
                    setNodes((prev) => prev.map((n) => (n.id === nodeId ? { ...n, ...updates } : n)));
                  }}
                  isViewer={!canEdit('fmea')}
                />
              </Card>
            </Col>
          </Row>
        </Tabs.TabPane>
      </Tabs>

      <style>{`
        .fmea-row-highlight td {
          background-color: #e6f4ff !important;
          transition: background-color 0.2s;
        }
        .fmea-row-highlight td:first-child {
          border-left: 3px solid #1677ff !important;
        }
        .severity-warning-row td {
          background-color: #fffbe6 !important;
        }
        .severity-warning-row td:first-child {
          border-left: 3px solid #faad14 !important;
        }
        .highlighted-row td {
          background-color: #fffbe6 !important;
        }
        .highlighted-row td:first-child {
          border-left: 3px solid #faad14 !important;
        }
      `}</style>

      <Divider />
      <Text type="secondary" style={{ fontSize: 11 }}>
        S=严重度 O=发生度 D=探测度 | RPN=风险优先数 | AP=措施优先级 (H=高 M=中 L=低) | 带 ' = 改进后评分
      </Text>
        </Tabs.TabPane>
        <Tabs.TabPane tab="🕸️ 图谱" key="graph">
          <div style={{ display: "flex", gap: 16, height: "calc(100vh - 240px)" }}>
            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 8 }}>
              <GraphToolbar
                layout={graphLayout}
                onLayoutChange={setGraphLayout}
                onZoomIn={() => canvasRef.current?.zoomIn()}
                onZoomOut={() => canvasRef.current?.zoomOut()}
                onFitView={() => canvasRef.current?.fitView()}
                onDownload={() => canvasRef.current?.download()}
              />
              {graphLoading ? (
                <Spin size="large" style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }} />
              ) : graphDataRef.current ? (
                <>
                  <GraphCanvas
                    ref={canvasRef}
                    nodes={graphDataRef.current.nodes}
                    edges={graphDataRef.current.edges}
                    mode="single-fmea"
                    layout={graphLayout}
                    highlightNodes={highlightNodes}
                    dimOthers={dimOthers}
                    onNodeClick={(node) => {
                      setSelectedGraphNode(node);
                      setDrawerVisible(true);
                    }}
                    onNodeContextMenu={(node, evt) => {
                      setContextMenuNode(node);
                      setContextMenuPos({ x: evt.clientX, y: evt.clientY });
                      setContextMenuOpen(true);
                    }}
                  />
                  <Dropdown
                    open={contextMenuOpen}
                    onOpenChange={setContextMenuOpen}
                    menu={{
                      items: [
                        { key: "impact", label: "追溯影响" },
                        { key: "cause", label: "追溯原因" },
                      ],
                      onClick: ({ key }) => {
                        setContextMenuOpen(false);
                        if (key === "impact" && contextMenuNode) handleTraceImpact(contextMenuNode.id);
                        if (key === "cause" && contextMenuNode) handleTraceCause(contextMenuNode.id);
                      },
                    }}
                  >
                    <span style={{
                      position: "fixed",
                      left: contextMenuPos.x,
                      top: contextMenuPos.y,
                      zIndex: 1050,
                    }} />
                  </Dropdown>
                </>
              ) : (
                <Empty description="暂无图谱数据" style={{ flex: 1 }} />
              )}
            </div>
            <div style={{ width: 220, display: "flex", flexDirection: "column", gap: 16 }}>
              <GraphLegend />
              {highlightNodes.length > 0 && (
                <Button onClick={() => { setHighlightNodes([]); setDimOthers(false); }}>
                  清除高亮
                </Button>
              )}
              <Card title="变更影响分析" size="small">
                <Space direction="vertical" style={{ width: "100%" }}>
                  <Text type="secondary">分析此节点的变更对上下游的影响范围</Text>
                  <Button
                    type="primary"
                    icon={<RadarChartOutlined />}
                    onClick={() => { setImpactModalOpen(true); setImpactResult(null); }}
                    disabled={!canEdit("fmea") || !selectedGraphNode}
                  >
                    分析影响范围
                  </Button>
                </Space>
              </Card>
            </div>
          </div>
          <NodeDetailDrawer
            node={selectedGraphNode}
            visible={drawerVisible}
            onClose={() => setDrawerVisible(false)}
            allNodes={graphDataRef.current?.nodes}
            allEdges={graphDataRef.current?.edges}
          />
          <Modal
            title="变更影响分析"
            open={impactModalOpen}
            onCancel={() => setImpactModalOpen(false)}
            width={800}
            footer={
              impactResult ? (
                <Button onClick={() => setImpactModalOpen(false)}>关闭</Button>
              ) : (
                <>
                  <Button onClick={() => setImpactModalOpen(false)}>取消</Button>
                  <Button type="primary" onClick={handleAnalyzeImpact} loading={impactLoading}>执行分析</Button>
                </>
              )
            }
          >
            {impactResult ? (
              <ImpactReportPanel
                analysis={impactResult}
                onViewGraph={() => {
                  const url = `/fmea/${fmeaId}?tab=graph&highlightNode=${impactResult.node_id}`;
                  window.open(url, "_blank");
                }}
              />
            ) : (
              <Space direction="vertical" style={{ width: "100%" }}>
                <Radio.Group
                  value={impactForm.change_type}
                  onChange={(e) => setImpactForm({ ...impactForm, change_type: e.target.value })}
                >
                  <Radio.Button value="attribute">属性变更</Radio.Button>
                  <Radio.Button value="structural">结构变更</Radio.Button>
                </Radio.Group>
                {impactForm.change_type === "attribute" && (
                  <>
                    <Input placeholder="字段名（如 design_parameter）" value={impactForm.field_name} onChange={(e) => setImpactForm({ ...impactForm, field_name: e.target.value })} />
                    <Input placeholder="新值" value={impactForm.new_value} onChange={(e) => setImpactForm({ ...impactForm, new_value: e.target.value })} />
                  </>
                )}
              </Space>
            )}
          </Modal>
        </Tabs.TabPane>
        <Tabs.TabPane tab="关联 CAPA" key="related-capa">
          {selectedFunctionId ? (
            <RelatedCAPAList
              fmeaId={fmea!.fmea_id}
              fmeaNodeId={selectedFunctionId}
            />
          ) : (
            <Typography.Text type="secondary">
              请先在编辑器中选择一个失效模式行
            </Typography.Text>
          )}
        </Tabs.TabPane>
        <Tabs.TabPane tab={<span><HistoryOutlined /> 版本历史</span>} key="history">
          <VersionHistoryTab
            documentId={id!}
            documentType="fmea"
            canCreate={canEdit('fmea')}
            canRollback={canApprove('fmea')}
            isDraft={fmea.status === "draft"}
            onViewSnapshot={(major, minor) => message.info(`查看版本 v${major}.${minor} 快照（功能开发中）`)}
            onCompare={(major1, minor1, major2, minor2) => setCompareState({ major1, minor1, major2, minor2 })}
            onRollback={(major, minor) => setRollbackTarget({ major_no: major, minor_no: minor })}
            onCreateVersion={() => setCreateVersionOpen(true)}
          />
        </Tabs.TabPane>
      </Tabs>

      <CreateVersionModal
        open={createVersionOpen}
        documentId={id!}
        documentType="fmea"
        onClose={() => setCreateVersionOpen(false)}
        onSuccess={() => setCreateVersionOpen(false)}
      />
      <RollbackConfirmModal
        open={!!rollbackTarget}
        targetVersion={rollbackTarget}
        documentId={id!}
        documentType="fmea"
        onClose={() => setRollbackTarget(null)}
        onSuccess={() => setRollbackTarget(null)}
      />
      {compareState && (
        <Modal
          open={!!compareState}
          title="版本对比"
          width={900}
          footer={null}
          onCancel={() => setCompareState(null)}
        >
          <VersionCompareView
            documentId={id!}
            documentType="fmea"
            major1={compareState.major1}
            minor1={compareState.minor1}
            major2={compareState.major2}
            minor2={compareState.minor2}
          />
        </Modal>
      )}
      <ConflictResolutionModal
        visible={conflictVisible}
        conflictInfo={conflictInfo}
        diff={conflictDiff}
        onRefresh={handleConflictRefresh}
        onForceSave={handleConflictForceSave}
      />
    </div>
  );
}

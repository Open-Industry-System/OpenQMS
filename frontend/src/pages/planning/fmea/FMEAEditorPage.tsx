import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { useParams, useNavigate, useSearchParams, useLocation } from "react-router-dom";
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
import type { FMEADocument, GraphNode, GraphEdge, LessonsLearnedResponse } from "../../../types";
import LessonsLearnedModal from "../../../components/lessons/LessonsLearnedModal";
import { getFMEALessons } from "../../../api/lessonsLearned";
import axios from "axios";
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
import { useTranslation } from "react-i18next";

const { Title, Text } = Typography;

function useStatusLabels(): Record<string, string> {
  const { t } = useTranslation("fmea");
  return {
    draft: t("status.draft"),
    in_review: t("status.in_review"),
    approved: t("status.approved"),
    rework: t("status.rework"),
    archived: t("status.archived"),
  };
}

function useNextTransitions(): Record<string, { label: string; target: string; icon: React.ReactNode }[]> {
  const { t } = useTranslation("fmea");
  return {
    draft: [
      { label: t("transition.submitReview"), target: "in_review", icon: <SendOutlined /> },
      { label: t("transition.archive"), target: "archived", icon: <CheckOutlined /> },
    ],
    in_review: [
      { label: t("transition.approve"), target: "approved", icon: <CheckOutlined /> },
      { label: t("transition.rework"), target: "rework", icon: <UndoOutlined /> },
    ],
    approved: [
      { label: t("transition.rework"), target: "rework", icon: <UndoOutlined /> },
      { label: t("transition.archive"), target: "archived", icon: <CheckOutlined /> },
    ],
    rework: [
      { label: t("transition.resubmit"), target: "in_review", icon: <SendOutlined /> },
    ],
  };
}

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
  const { t } = useTranslation("fmea");
  const { t: tc } = useTranslation("common");
  const statusLabels = useStatusLabels();
  const nextTransitions = useNextTransitions();
  const [fmea, setFmea] = useState<FMEADocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [selectedFunctionId, setSelectedFunctionId] = useState<string | null>(null);

  const [searchParams] = useSearchParams();
  const highlightNodeId = searchParams.get("node");
  const [highlightedRowKey, setHighlightedRowKey] = useState<string | null>(null);

  const _user = useAuthStore((s) => s.user);
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

  // Lessons learned modal
  const location = useLocation();
  const [lessonsModalOpen, setLessonsModalOpen] = useState(false);
  const [lessonsLoading, setLessonsLoading] = useState(false);
  const [lessonsData, setLessonsData] = useState<LessonsLearnedResponse | null>(null);
  const lessonsShownRef = useRef(false);

  useEffect(() => {
    if (location.state?.showLessonsLearned && !lessonsShownRef.current) {
      lessonsShownRef.current = true;
      setLessonsModalOpen(true);
      setLessonsLoading(true);

      const controller = new AbortController();
      const timeoutId = setTimeout(() => {
        controller.abort();
        setLessonsLoading(false);
        setLessonsModalOpen(false);
        message.warning(t("messages.searchTimeout"));
      }, 10000);

      const problemDescription = location.state?.problemDescription;
      getFMEALessons(
        fmeaId,
        problemDescription ? { problem_description: problemDescription } : undefined,
        { signal: controller.signal }
      )
        .then((res) => {
          clearTimeout(timeoutId);
          setLessonsData(res);
          setLessonsLoading(false);
        })
        .catch((err) => {
          clearTimeout(timeoutId);
          if (!axios.isCancel(err)) {
            message.error(t("messages.searchFailed"));
          }
          setLessonsLoading(false);
        });

      return () => {
        clearTimeout(timeoutId);
        controller.abort();
      };
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state, fmeaId]);
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
      message.error(t("messages.graphLoadFailed"));
    } finally {
      setGraphLoading(false);
    }
  }, [id, message, pendingHighlightNode, t]);

  const handleTraceImpact = async (nodeId: string) => {
    if (!id) return;
    try {
      const chain = await getImpactChain(id, nodeId);
      const { nodes } = normalizeGraphData(chain.nodes, chain.edges);
      setHighlightNodes(nodes.map((n) => n.id));
      setDimOthers(true);
    } catch {
      message.error(t("messages.impactChainFailed"));
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
      message.error(t("messages.causeChainFailed"));
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
      message.success(t("messages.analysisComplete"));
    } catch {
      message.error(t("messages.analysisFailed"));
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
      message.success(t("messages.saveSuccess"));
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
        message.error(t("messages.saveFailed"));
      }
    } finally {
      setSaving(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
      message.success(t("messages.forceSaveSuccess"));
    } catch (e: unknown) {
      const err = e as { response?: { status?: number; data?: { detail?: string } } };
      if (err.response?.status === 409) {
        message.error(t("messages.concurrentUpdate"));
      } else {
        message.error(t("messages.forceSaveFailed"));
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
      message.success(t("messages.statusChanged", { status: statusLabels[target] || target }));
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err?.response?.data?.detail || t("messages.operationFailed"));
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
      message.warning(t("table.selectFunctionFirst"));
      return;
    }
    const { newNodes, newEdges } = createRowNodes(selectedFunctionId, fmea.fmea_type);
    setNodes((prev) => [...prev, ...newNodes]);
    setEdges((prev) => [...prev, ...newEdges]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedFunctionId, fmea]);

  const deleteRow = useCallback((row: FMEARow) => {
    // Only delete nodes that are NOT shared with other rows
    const otherRows = rows.filter((r) => r.key !== row.key);
    const nodesUsedByOthers = new Set<string>();
    for (const r of otherRows) {
      nodesUsedByOthers.add(r.failureModeNodeId);
      if (r.failureEffectNodeId) nodesUsedByOthers.add(r.failureEffectNodeId);
      if (r.failureCauseNodeId) nodesUsedByOthers.add(r.failureCauseNodeId);
      r.preventionControlIds?.forEach(id => nodesUsedByOthers.add(id));
      r.detectionControlIds?.forEach(id => nodesUsedByOthers.add(id));
      r.recommendedActionIds?.forEach(id => nodesUsedByOthers.add(id));
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
    row.preventionControlIds.forEach((id) => { if (!nodesUsedByOthers.has(id)) idsToDelete.add(id); });
    row.detectionControlIds.forEach((id) => { if (!nodesUsedByOthers.has(id)) idsToDelete.add(id); });
    row.recommendedActionIds.forEach((id) => { if (!nodesUsedByOthers.has(id)) idsToDelete.add(id); });

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
  if (!fmea) return <Empty description={t("messages.fmeaNotFound")} />;

  const isDFMEA = fmea.fmea_type === "DFMEA";

    const columns = [
    {
      title: t("table.processFunction"),
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
      title: t("table.failureMode"),
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
      title: t("table.failureEffect"),
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
      title: <Tooltip title={t("table.severity")}>{t("table.severityShort")}</Tooltip>,
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
      title: <Tooltip title={t("table.class")}>{t("table.classShort")}</Tooltip>,
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
      title: t("table.failureCause"),
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
      title: <Tooltip title={t("table.occurrence")}>{t("table.occurrenceShort")}</Tooltip>,
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
      title: t("table.preventionControl"),
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
      title: t("table.detectionControl"),
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
      title: <Tooltip title={t("table.detection")}>{t("table.detectionShort")}</Tooltip>,
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
      title: <Tooltip title={t("table.rpn")}>{t("table.rpnShort")}</Tooltip>,
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

        const _bgColor = rpn >= 100 ? "#ff4d4f" : rpn >= 50 ? "#fa8c16" : rpn > 0 ? "#52c41a" : "#d9d9d9";
        return (
          <Tag color={rpn >= 100 ? "red" : rpn >= 50 ? "orange" : rpn > 0 ? "green" : "default"}
            style={{ fontWeight: 700, fontSize: 13, minWidth: 48, textAlign: "center" }}>
            {rpn || 0}
          </Tag>
        );
      },
    },
    {
      title: <Tooltip title={t("table.ap")}>{t("table.apShort")}</Tooltip>,
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
      title: t("table.recommendedAction"),
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
                  name: t("table.newRecommendedAction"),
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
              {t("table.addRecommendedAction")}
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
      title: t("table.responsibility"),
      key: "responsibility",
      width: 120,
      render: (_: unknown, row: FMEARow) => {
        if (row.recommendedActionIds.length === 0) return "-";
        const node = nodeMap.get(row.recommendedActionIds[0]);
        return (
          <div>
            <Input
              size="small"
              placeholder={t("table.responsiblePlaceholder")}
              value={node?.responsible || ""}
              disabled={!canEdit('fmea')}
              style={{ marginBottom: 4 }}
              onChange={(e) => updateNode(row.recommendedActionIds[0], "responsible", e.target.value)}
            />
            <Input
              size="small"
              placeholder={t("table.dueDatePlaceholder")}
              value={node?.due_date || ""}
              disabled={!canEdit('fmea')}
              onChange={(e) => updateNode(row.recommendedActionIds[0], "due_date", e.target.value)}
            />
          </div>
        );
      },
    },
    {
      title: t("table.actionsTaken"),
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
      title: <Tooltip title={t("table.revisedSeverity")}>{t("table.revisedSeverityShort")}</Tooltip>,
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
      title: <Tooltip title={t("table.revisedOccurrence")}>{t("table.revisedOccurrenceShort")}</Tooltip>,
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
      title: <Tooltip title={t("table.revisedDetection")}>{t("table.revisedDetectionShort")}</Tooltip>,
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
      title: <Tooltip title={t("table.revisedRpn")}>{t("table.revisedRpnShort")}</Tooltip>,
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
        const _bgColor = rpn >= 100 ? "#ff4d4f" : rpn >= 50 ? "#fa8c16" : rpn > 0 ? "#52c41a" : "#d9d9d9";
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
        <Popconfirm title={t("table.confirmDeleteRow")} onConfirm={() => deleteRow(row)}>
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
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/fmea")}>{tc("actions.back")}</Button>
          <Title level={4} style={{ margin: 0 }}>{fmea.title}</Title>
          <Tag color={isDFMEA ? "green" : "blue"}>{isDFMEA ? "DFMEA" : "PFMEA"}</Tag>
          <Tag>{statusLabels[fmea.status] || fmea.status}</Tag>
          <Text type="secondary">{fmea.document_no} v{fmea.version}</Text>
        </Space>
        <Space>
          {nextTransitions[fmea.status]
            ?.filter((trans) => {
              if (!canEdit('fmea')) return false;
              if (trans.target === "approved" && !canApprove('fmea')) return false;
              return true;
            })
            ?.map((trans) => (
              <Popconfirm key={trans.target} title={`${tc("actions.confirm")} ${trans.label}？`} onConfirm={() => handleTransition(trans.target)}>
                <Button icon={trans.icon}>{trans.label}</Button>
              </Popconfirm>
            ))}
          {canEdit('fmea') && (
            <Button type="primary" icon={<SaveOutlined />} onClick={save} loading={saving}>{tc("actions.save")}</Button>
          )}
        </Space>
      </div>

      {/* FMEA Header Info */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Descriptions size="small" column={4}>
          <Descriptions.Item label={isDFMEA ? t("header.system") : t("header.processItem")}>
            {structureNodes.find((n) => n.type === (isDFMEA ? "System" : "ProcessItem"))?.name || "-"}
          </Descriptions.Item>
          <Descriptions.Item label={isDFMEA ? t("header.designResponsibility") : t("header.processResponsibility")}>
            <Input size="small" placeholder={t("header.departmentPlaceholder")} style={{ width: 150 }} disabled={!canEdit('fmea')} />
          </Descriptions.Item>
          <Descriptions.Item label={t("header.fmeaNumber")}>{fmea.document_no}</Descriptions.Item>
          <Descriptions.Item label={t("header.keyDate")}>
            <Input size="small" placeholder={t("header.datePlaceholder")} style={{ width: 100 }} disabled={!canEdit('fmea')} />
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Tabs activeKey={outerTab} onChange={setOuterTab} style={{ marginBottom: 16 }} items={[
        { key: "editor", label: t("editor.title"), children: <>
          <Tabs activeKey={activeTab} onChange={setActiveTab} style={{ marginBottom: 16 }} items={[
            { key: "failure", label: t("editor.failureAnalysis"), children: <>
          <Row gutter={16}>
            {/* Left: Structure/Function Tree */}
            <Col span={5}>
          <Card
            title={isDFMEA ? t("table.structureFunctionTitle") : t("table.processFunctionTitle")}
            size="small"
            extra={
              canEdit('fmea') && (
                <Button size="small" icon={<PlusOutlined />} onClick={addRow} disabled={!selectedFunctionId}>
                  {t("table.addRow")}
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
            {functionNodes.length === 0 && <Empty description={t("table.noData")} image={Empty.PRESENTED_IMAGE_SIMPLE} />}
          </Card>
        </Col>

        {/* Right: FMEA Table */}
        <Col span={19}>
          <Card
            title={
              <span style={{ fontSize: 14 }}>
                {isDFMEA ? t("table.dfmeaTitle") : t("table.pfmeaTitle")}
              </span>
            }
            size="small"
            styles={{ body: { padding: "8px 0" } }}
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
                <Text type="secondary">{t("table.startAnalysisHint")}</Text>
              </div>
            )}
          </Card>
        </Col>
      </Row>
        </>},
            { key: "structure", label: t("editor.structureAnalysis"), children: <>
          <Row gutter={16}>
            <Col span={8}>
              <Card title={t("editor.structureTree")} size="small">
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
              <Card title={t("editor.nodeDetail")} size="small">
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
        </>},
          ]} />

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
        {t("table.footer")}
      </Text>
        </>},
        { key: "graph", label: t("editor.graph"), children: <>
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
                        { key: "impact", label: t("messages.traceImpact") },
                        { key: "cause", label: t("messages.traceCause") },
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
                <Empty description={t("messages.noGraphData")} style={{ flex: 1 }} />
              )}
            </div>
            <div style={{ width: 220, display: "flex", flexDirection: "column", gap: 16 }}>
              <GraphLegend />
              {highlightNodes.length > 0 && (
                <Button onClick={() => { setHighlightNodes([]); setDimOthers(false); }}>
                  {t("messages.clearHighlight")}
                </Button>
              )}
              <Card title={t("messages.changeImpactAnalysis")} size="small">
                <Space direction="vertical" style={{ width: "100%" }}>
                  <Text type="secondary">{t("messages.changeImpactDescription")}</Text>
                  <Button
                    type="primary"
                    icon={<RadarChartOutlined />}
                    onClick={() => { setImpactModalOpen(true); setImpactResult(null); }}
                    disabled={!canEdit("fmea") || !selectedGraphNode}
                  >
                    {t("messages.analyzeImpactScope")}
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
            title={t("messages.changeImpactAnalysis")}
            open={impactModalOpen}
            onCancel={() => setImpactModalOpen(false)}
            width={800}
            footer={
              impactResult ? (
                <Button onClick={() => setImpactModalOpen(false)}>{t("messages.close")}</Button>
              ) : (
                <>
                  <Button onClick={() => setImpactModalOpen(false)}>{t("messages.cancel")}</Button>
                  <Button type="primary" onClick={handleAnalyzeImpact} loading={impactLoading}>{t("messages.executeAnalysis")}</Button>
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
                  <Radio.Button value="attribute">{t("messages.attributeChange")}</Radio.Button>
                  <Radio.Button value="structural">{t("messages.structuralChange")}</Radio.Button>
                </Radio.Group>
                {impactForm.change_type === "attribute" && (
                  <>
                    <Input placeholder={t("messages.fieldNamePlaceholder")} value={impactForm.field_name} onChange={(e) => setImpactForm({ ...impactForm, field_name: e.target.value })} />
                    <Input placeholder={t("messages.newValuePlaceholder")} value={impactForm.new_value} onChange={(e) => setImpactForm({ ...impactForm, new_value: e.target.value })} />
                  </>
                )}
              </Space>
            )}
          </Modal>
        </>},
        { key: "related-capa", label: t("editor.relatedCapa"), children: <>
          {selectedFunctionId ? (
            <RelatedCAPAList
              fmeaId={fmea!.fmea_id}
              fmeaNodeId={selectedFunctionId}
            />
          ) : (
            <Typography.Text type="secondary">
              {t("messages.selectFailureMode")}
            </Typography.Text>
          )}
        </>},
        { key: "history", label: <span><HistoryOutlined /> {t("editor.history")}</span>, children: <>
          <VersionHistoryTab
            documentId={id!}
            documentType="fmea"
            canCreate={canEdit('fmea')}
            canRollback={canApprove('fmea')}
            isDraft={fmea.status === "draft"}
            onViewSnapshot={(major, minor) => message.info(t("messages.viewSnapshot", { version: `${major}.${minor}` }))}
            onCompare={(major1, minor1, major2, minor2) => setCompareState({ major1, minor1, major2, minor2 })}
            onRollback={(major, minor) => setRollbackTarget({ major_no: major, minor_no: minor })}
            onCreateVersion={() => setCreateVersionOpen(true)}
          />
        </>},
      ]} />

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
          title={t("messages.versionCompare")}
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
      <LessonsLearnedModal
        open={lessonsModalOpen}
        loading={lessonsLoading}
        data={lessonsData}
        onClose={() => setLessonsModalOpen(false)}
        onViewDetail={(card) => {
          if (card.source_type === "fmea") {
            window.open(`/fmea/${card.source_id}`, "_blank");
          } else if (card.source_type === "capa") {
            window.open(`/capa/${card.source_id}`, "_blank");
          } else if (card.source_type === "audit") {
            const auditId = card.metadata?.audit_id;
            const category = card.metadata?.audit_category;
            if (auditId) {
              const path = category === "customer" ? `/customer-audits/${auditId}` : `/internal-audits/${auditId}`;
              window.open(path, "_blank");
            }
          }
        }}
      />
    </div>
  );
}

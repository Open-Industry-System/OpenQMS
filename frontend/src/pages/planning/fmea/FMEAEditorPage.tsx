import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { useParams, useNavigate, useSearchParams, useLocation } from "react-router-dom";
import {
  Button, Space, Tag, Typography, Input, Select, Table, Tabs,
  Row, Col, App, Spin, Popconfirm, Empty, Tooltip,
  Divider, Modal, Radio, Form, Dropdown,
} from "antd";
import {
  SaveOutlined, ArrowLeftOutlined, SendOutlined,
  CheckOutlined, UndoOutlined, PlusOutlined, DeleteOutlined,
  HistoryOutlined, RadarChartOutlined, HolderOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { getFMEA, updateFMEA, transitionFMEA } from "../../../api/fmea";
import { formatFMEAError } from "../../../utils/fmeaError";
import { syncFromFMEA, getSeverityWarnings } from "../../../api/specialCharacteristic";
import type { FMEADocument, GraphNode, GraphEdge, LessonsLearnedResponse } from "../../../types";
import LessonsLearnedModal from "../../../components/lessons/LessonsLearnedModal";
import { getFMEALessons } from "../../../api/lessonsLearned";
import axios from "axios";
import { useAuthStore } from "../../../store/authStore";
import { usePermission } from "../../../hooks/usePermission";
import { calculateAP } from "../../../utils/fmea";
import { buildRows, createRowNodes, getRowSeverity, computeRowSpans, addEffect, deleteEffect, addCause, type FMEARow } from "../../../utils/fmeaTable";
import { planCauseDeletion } from "./deleteRowHelpers";
import EffectLinesEditor from "../../../components/fmea/EffectLinesEditor";
import {
  buildStructureTree,
  createStructureChild,
  deleteSubtree,
  getStructureRowHeaderOrder,
  reorderStructureSiblings,
  canReorderStructureSiblings,
  STRUCTURE_CHILD_MAP,
  type StructureChildAction,
  type StructureDropPosition,
  type StructureTreeNode,
} from "../../../utils/structureTree";
import StructureTree from "../../../components/dfmea/StructureTree";
import ParameterDiagram from "../../../components/dfmea/ParameterDiagram";
import SmartSuggestionDropdown from "../../../components/dfmea/SmartSuggestionDropdown";
import VersionHistoryTab from "../../../components/version/VersionHistoryTab";
import CreateVersionModal from "../../../components/version/CreateVersionModal";
import RollbackConfirmModal from "../../../components/version/RollbackConfirmModal";
import VersionCompareView from "../../../components/version/VersionCompareView";
import RelatedCAPAList from "../../../components/cross-links/RelatedCAPAList";
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
import { PageShell, DataCard, StatusBadge } from "../../../components/design";

const { Text } = Typography;

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

/**
 * 拖拽 `dragId` 期间需要折叠子树的节点 ID 集合：被拖节点本身 + 其同级节点
 * （即其父节点的所有子节点），使被重排的同级层显示为紧凑单行；祖先链路与
 * 无关分支保持展开。若 dragId 是根节点（无父），仅折叠它自身。
 */
function dragCollapsedSubtreeRootIds(roots: StructureTreeNode[], dragId: string): Set<string> {
  const visit = (tn: StructureTreeNode): Set<string> | null => {
    const childIds = tn.children.map((c) => c.node.id);
    if (childIds.includes(dragId)) return new Set(childIds);
    for (const child of tn.children) {
      const found = visit(child);
      if (found) return found;
    }
    return null;
  };
  for (const root of roots) {
    const found = visit(root);
    if (found) return found;
  }
  return new Set([dragId]);
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
  const [addNodeOpen, setAddNodeOpen] = useState(false);
  const [addNodeParent, setAddNodeParent] = useState<GraphNode | null>(null);
  const [addNodeAction, setAddNodeAction] = useState<StructureChildAction | null>(null);
  const [addNodeForm] = Form.useForm();

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
  const dragStructureNodeIdRef = useRef<string | null>(null);
  const [dragOver, setDragOver] = useState<{ nodeId: string; position: StructureDropPosition; valid: boolean } | null>(null);
  const [draggingNodeId, setDraggingNodeId] = useState<string | null>(null);
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
            message.error(err?.response?.data?.detail || t("messages.searchFailed"));
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
        // Redirect draft DFMEAs that haven't completed the wizard
        if (
          doc.fmea_type === "DFMEA" &&
          doc.status === "draft" &&
          !doc.graph_data?.wizardScope?.wizard_completed
        ) {
          navigate(`/fmea/wizard/${id}`, { replace: true });
          return;
        }
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
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err?.response?.data?.detail || t("messages.graphLoadFailed"));
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
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err?.response?.data?.detail || t("messages.impactChainFailed"));
    }
  };

  const handleTraceCause = async (nodeId: string) => {
    if (!id) return;
    try {
      const chain = await getCauseChain(id, nodeId);
      const { nodes } = normalizeGraphData(chain.nodes, chain.edges);
      setHighlightNodes(nodes.map((n) => n.id));
      setDimOthers(true);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err?.response?.data?.detail || t("messages.causeChainFailed"));
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
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err?.response?.data?.detail || t("messages.analysisFailed"));
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
        const detail = err.response?.data?.detail;
        message.error(typeof detail === "string" ? detail : t("messages.saveFailed"));
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
        message.error(err.response?.data?.detail || t("messages.forceSaveFailed"));
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
      message.error(formatFMEAError(err?.response?.data?.detail, t) || t("messages.operationFailed"));
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

  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  useEffect(() => { nodesRef.current = nodes; }, [nodes]);
  useEffect(() => { edgesRef.current = edges; }, [edges]);

  const handleAddEffect = useCallback((fmId: string) => {
    const result = addEffect(fmId, nodesRef.current, edgesRef.current);
    nodesRef.current = result.nodes;   // advance ref synchronously so a second
    edgesRef.current = result.edges;   // click before the effect runs still sees fresh state
    setNodes(result.nodes);
    setEdges(result.edges);
  }, []);
  const handleDeleteEffect = useCallback((fmId: string, effectId: string) => {
    const result = deleteEffect(fmId, effectId, nodesRef.current, edgesRef.current);
    nodesRef.current = result.nodes;
    edgesRef.current = result.edges;
    setNodes(result.nodes);
    setEdges(result.edges);
  }, []);
  const handleAddFailureMode = useCallback((functionId: string) => {
    if (!fmea) return;
    const { newNodes, newEdges } = createRowNodes(functionId, fmea.fmea_type, t);
    nodesRef.current = [...nodesRef.current, ...newNodes];
    edgesRef.current = [...edgesRef.current, ...newEdges];
    setNodes(nodesRef.current);
    setEdges(edgesRef.current);
  }, [fmea, t]);
  const handleAddCause = useCallback((fmId: string) => {
    if (!fmea) return;
    const result = addCause(fmId, fmea.fmea_type, t, nodesRef.current, edgesRef.current);
    nodesRef.current = result.nodes;
    edgesRef.current = result.edges;
    setNodes(result.nodes);
    setEdges(result.edges);
  }, [fmea, t]);

  const fmeaType = fmea?.fmea_type;
  const isDFMEA = fmeaType === "DFMEA";
  const canDragSortStructure = canEdit("fmea");
  const structureTree = useMemo(() => buildStructureTree(nodes, edges), [nodes, edges]);
  // 拖拽期间折叠被拖节点 + 同级节点的子树（祖先链路与无关分支保持展开）
  const dragCollapseIds = useMemo(
    () => (draggingNodeId ? dragCollapsedSubtreeRootIds(structureTree, draggingNodeId) : new Set<string>()),
    [draggingNodeId, structureTree],
  );
  const structureRowHeaderOrder = useMemo(() => getStructureRowHeaderOrder(nodes, edges), [nodes, edges]);
  const rows = useMemo(
    () => buildRows(nodes, edges, structureRowHeaderOrder),
    [nodes, edges, structureRowHeaderOrder]
  );
  const rowSpans = useMemo(() => computeRowSpans(rows), [rows]);

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
      message.warning(t("messages.selectFunctionFirst"));
      return;
    }
    const { newNodes, newEdges } = createRowNodes(selectedFunctionId, fmea.fmea_type, t);
    setNodes((prev) => [...prev, ...newNodes]);
    setEdges((prev) => [...prev, ...newEdges]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedFunctionId, fmea]);

  const openAddNode = useCallback((parent: GraphNode, action: StructureChildAction) => {
    setAddNodeParent(parent);
    setAddNodeAction(action);
    addNodeForm.resetFields();
    setAddNodeOpen(true);
  }, [addNodeForm]);

  const submitAddNode = useCallback(() => {
    addNodeForm.validateFields().then((values: { name: string; specification?: string; requirement?: string }) => {
      if (!addNodeParent || !addNodeAction) return;
      const { node, edge } = createStructureChild(
        addNodeParent,
        addNodeAction,
        values.name,
        values.specification,
        values.requirement
      );
      setNodes((prev) => [...prev, node]);
      setEdges((prev) => [...prev, edge]);
      if (addNodeAction.kind === "function") {
        setSelectedFunctionId(node.id);
      }
      setAddNodeOpen(false);
    }).catch(() => { /* validation message shown by Form */ });
  }, [addNodeParent, addNodeAction, addNodeForm]);

  // Create a new top-level ProcessItem (PFMEA) / System (DFMEA) as a sibling root.
  const addRootStructureNode = useCallback(() => {
    if (!fmea) return;
    const isDf = fmea.fmea_type === "DFMEA";
    const id = `n${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    const newNode: GraphNode = {
      id,
      type: isDf ? "System" : "ProcessItem",
      name: t(isDf ? "editor.newSystem" : "editor.newProcessItem"),
      severity: 0,
      occurrence: 0,
      detection: 0,
    };
    setNodes((prev) => [...prev, newNode]);
    setSelectedFunctionId(id);
  }, [fmea, t]);

  // Cascade-delete a node, its structure/function descendants, and the failure
  // rows beneath them. Shared controls still referenced by surviving rows are
  // kept (see deleteSubtree).
  const deleteSubtreeNode = useCallback((node: GraphNode) => {
    const { nodes: nextNodes, edges: nextEdges } = deleteSubtree(nodes, edges, node.id);
    setNodes(nextNodes);
    setEdges(nextEdges);
    if (selectedFunctionId === node.id) setSelectedFunctionId(null);
  }, [nodes, edges, selectedFunctionId]);

  const getStructureDropPosition = useCallback((event: React.DragEvent<HTMLDivElement>): StructureDropPosition => {
    const rect = event.currentTarget.getBoundingClientRect();
    if (rect.height <= 0) return "inside";
    const offsetY = event.clientY - rect.top;
    if (offsetY < rect.height * 0.25) return "before";
    if (offsetY > rect.height * 0.75) return "after";
    return "inside";
  }, []);

  const handleStructureDragStart = useCallback((nodeId: string, event: React.DragEvent<HTMLElement>) => {
    if (!canDragSortStructure) return;
    dragStructureNodeIdRef.current = nodeId;
    setDraggingNodeId(nodeId);
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", nodeId);
    const rowEl = event.currentTarget.closest<HTMLElement>("[data-node-id]");
    if (rowEl) event.dataTransfer.setDragImage(rowEl, 0, 0);
  }, [canDragSortStructure]);

  const handleStructureDragOver = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    const dragNodeId = dragStructureNodeIdRef.current;
    if (!canDragSortStructure || !dragNodeId) return;
    const dropNodeId = (event.currentTarget as HTMLElement).dataset.nodeId;
    if (!dropNodeId) return;
    event.preventDefault();
    const position = getStructureDropPosition(event);
    const valid = canReorderStructureSiblings({ nodes, edges, dragNodeId, dropNodeId, dropPosition: position });
    event.dataTransfer.dropEffect = valid ? "move" : "none";
    setDragOver((prev) =>
      prev && prev.nodeId === dropNodeId && prev.position === position && prev.valid === valid
        ? prev
        : { nodeId: dropNodeId, position, valid }
    );
  }, [canDragSortStructure, edges, getStructureDropPosition, nodes]);

  const handleStructureDrop = useCallback((dropNodeId: string, event: React.DragEvent<HTMLDivElement>) => {
    if (!canDragSortStructure) return;
    event.preventDefault();
    event.stopPropagation();
    setDragOver(null);
    setDraggingNodeId(null);

    const dragNodeId = dragStructureNodeIdRef.current;
    dragStructureNodeIdRef.current = null;
    if (!dragNodeId) return;

    const result = reorderStructureSiblings({
      nodes,
      edges,
      dragNodeId,
      dropNodeId,
      dropPosition: getStructureDropPosition(event),
    });

    if (!result.changed) {
      if (result.reason === "invalid") message.warning(t("messages.sameLevelSortOnly"));
      return;
    }

    if (result.nodes !== nodes) setNodes(result.nodes);
    if (result.edges !== edges) setEdges(result.edges);
  }, [canDragSortStructure, edges, getStructureDropPosition, message, nodes, t]);

  const handleStructureDragEnd = useCallback(() => {
    dragStructureNodeIdRef.current = null;
    setDragOver(null);
    setDraggingNodeId(null);
  }, []);

  const deleteRow = useCallback((row: FMEARow) => {
    const { nodeIdsToDelete } = planCauseDeletion(row, rows);

    setNodes((prev) => prev.filter((n) => !nodeIdsToDelete.has(n.id)));
    setEdges((prev) => prev.filter((e) => {
      // Drop edges touching deleted nodes
      if (nodeIdsToDelete.has(e.source) || nodeIdsToDelete.has(e.target)) return false;
      // Drop this row's CAUSE_OF (cause → mode) edge specifically
      if (row.failureCauseNodeId && e.source === row.failureCauseNodeId && e.target === row.failureModeNodeId && e.type === "CAUSE_OF") return false;
      return true;
    }));
  }, [rows]);

  if (loading) return <Spin size="large" style={{ display: "block", margin: "100px auto" }} />;
  if (!fmea) return <Empty description={t("messages.notFound")} />;

    const columns = [
    {
      title: t("editor.columns.function"),
      key: "function",
      width: 200,
      fixed: "left" as const,
      onCell: (_row: FMEARow, index?: number) => ({ rowSpan: index != null ? rowSpans[index]?.function ?? 1 : 1 }),
      render: (_: unknown, row: FMEARow) => {
        const funcNode = nodeMap.get(row.functionNodeId);
        return (
          <div tabIndex={0} style={{ outline: "none", minWidth: 180 }}>
            <div style={{ fontWeight: 600, fontSize: 13, lineHeight: "1.5" }}>{funcNode?.name || "-"}</div>
            {funcNode?.specification && (
              <Text type="secondary" style={{ fontSize: 12 }}>{funcNode.specification}</Text>
            )}
            {funcNode?.requirement && (
              <div><Text type="secondary" style={{ fontSize: 12 }}>{funcNode.requirement}</Text></div>
            )}
            {canEdit('fmea') && (
              <Button
                size="small"
                type="dashed"
                icon={<PlusOutlined />}
                onClick={() => handleAddFailureMode(row.functionNodeId)}
                style={{ marginTop: 4 }}
              >
                {t("editor.addFailureMode")}
              </Button>
            )}
          </div>
        );
      },
    },
    {
      title: t("editor.columns.failureMode"),
      key: "failureMode",
      width: 180,
      onCell: (_row: FMEARow, index?: number) => ({ rowSpan: index != null ? rowSpans[index]?.mode ?? 1 : 1 }),
      render: (_: unknown, row: FMEARow) => {
        const node = nodeMap.get(row.failureModeNodeId);
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
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
            {canEdit('fmea') && (
              <Button
                size="small"
                type="dashed"
                icon={<PlusOutlined />}
                onClick={() => handleAddCause(row.failureModeNodeId)}
              >
                {t("editor.addFailureCause")}
              </Button>
            )}
          </div>
        );
      },
    },
    {
      title: t("editor.columns.failureEffect"),
      key: "failureEffect",
      width: 200,
      onCell: (_row: FMEARow, index?: number) => ({ rowSpan: index != null ? rowSpans[index]?.mode ?? 1 : 1 }),
      render: (_: unknown, row: FMEARow) => {
        return (
          <EffectLinesEditor
            effectIds={row.failureEffectNodeIds}
            nodeMap={nodeMap}
            fmeaId={fmeaId}
            functionDescription={nodeMap.get(row.functionNodeId)?.name || ""}
            failureModeName={nodeMap.get(row.failureModeNodeId)?.name || ""}
            disabled={!canEdit('fmea')}
            updateNode={updateNode}
            onAddEffect={() => handleAddEffect(row.failureModeNodeId)}
            onDeleteEffect={(effectId) => handleDeleteEffect(row.failureModeNodeId, effectId)}
          />
        );
      },
    },
    {
      title: <Tooltip title={t("editor.tooltips.severity")}>S</Tooltip>,
      key: "severity",
      width: 60,
      align: "center" as const,
      onCell: (_row: FMEARow, index?: number) => ({ rowSpan: index != null ? rowSpans[index]?.mode ?? 1 : 1 }),
      render: (_: unknown, row: FMEARow) => {
        if (row.failureEffectNodeIds.length === 0) return <Text type="secondary">-</Text>;
        const s = getRowSeverity(row, nodeMap);
        return (
          <div>
            <Input
              min={1}
              max={10}
              size="small"
              value={s || undefined}
              disabled={!canEdit('fmea')}
              style={{ width: 55, textAlign: "center" }}
              onFocus={() => startEditing({ row_key: row.key, field: "severity", node_id: row.failureModeNodeId })}
              onBlur={stopEditing}
              onChange={(e) => {
                const v = Number(e.target.value) || 0;
                row.failureEffectNodeIds.forEach((id) => updateNode(id, "severity", v));
              }}
            />
            <ActiveUserIndicator activeUsers={activeUsers} rowKey={row.key} field="severity" />
          </div>
        );
      },
    },
    {
      title: <Tooltip title={isDFMEA ? t("editor.tooltips.filterCode") : t("editor.tooltips.classification")}>Class</Tooltip>,
      key: "class",
      width: 70,
      align: "center" as const,
      onCell: (_row: FMEARow, index?: number) => ({ rowSpan: index != null ? rowSpans[index]?.mode ?? 1 : 1 }),
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
      title: t("editor.columns.failureCause"),
      key: "failureCause",
      width: 180,
      render: (_: unknown, row: FMEARow) => {
        if (!row.failureCauseNodeId) return "-";
        const node = nodeMap.get(row.failureCauseNodeId);
        return (
          <SmartSuggestionDropdown
            triggerType="failure_cause"
            context={{
              failure_mode: nodeMap.get(row.failureModeNodeId)?.name || "",
              function_description: nodeMap.get(row.functionNodeId)?.name || "",
              severity: getRowSeverity(row, nodeMap),
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
      title: <Tooltip title={t("editor.tooltips.occurrence")}>O</Tooltip>,
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
      title: t("editor.columns.preventionControl"),
      key: "preventionControl",
      width: 180,
      render: (_: unknown, row: FMEARow) => {
        const nodeId = row.preventionControlIds[0];
        if (!nodeId) return "-";
        const node = nodeMap.get(nodeId);
        const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
        const detNode = row.detectionControlIds.length > 0 ? nodeMap.get(row.detectionControlIds[0]) : null;
        const ap = calculateAP(getRowSeverity(row, nodeMap), causeNode?.occurrence || 0, detNode?.detection || 0);
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
      title: t("editor.columns.detectionControl"),
      key: "detectionControl",
      width: 180,
      render: (_: unknown, row: FMEARow) => {
        const nodeId = row.detectionControlIds[0];
        if (!nodeId) return "-";
        const node = nodeMap.get(nodeId);
        const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
        const ap = calculateAP(getRowSeverity(row, nodeMap), causeNode?.occurrence || 0, node?.detection || 0);
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
      title: <Tooltip title={t("editor.tooltips.detection")}>D</Tooltip>,
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
      title: <Tooltip title={t("editor.tooltips.rpn")}>RPN</Tooltip>,
      key: "rpn",
      width: 60,
      align: "center" as const,
      render: (_: unknown, row: FMEARow) => {
        const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
        const detectionNode = row.detectionControlIds.length > 0 ? nodeMap.get(row.detectionControlIds[0]) : null;

        const s = getRowSeverity(row, nodeMap);
        const o = causeNode?.occurrence || 0;
        const d = detectionNode?.detection || 0;
        const rpn = s * o * d;

        const rpnColor = rpn >= 100 ? "var(--qf-red)" : rpn >= 50 ? "var(--qf-amber)" : rpn > 0 ? "var(--qf-green)" : "var(--qf-text-tertiary)";
        const rpnBg = rpn >= 100 ? "var(--qf-red-dim)" : rpn >= 50 ? "var(--qf-amber-dim)" : rpn > 0 ? "var(--qf-green-dim)" : "rgba(139, 147, 167, 0.1)";
        return (
          <Tag
            style={{
              background: rpnBg,
              color: rpnColor,
              borderColor: rpnColor,
              fontWeight: 700,
              fontSize: 13,
              minWidth: 48,
              textAlign: "center",
              fontFamily: "var(--qf-font-mono)",
            }}
          >
            {rpn || 0}
          </Tag>
        );
      },
    },
    {
      title: <Tooltip title={t("editor.tooltips.ap")}>AP</Tooltip>,
      key: "ap",
      width: 55,
      align: "center" as const,
      render: (_: unknown, row: FMEARow) => {
        const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
        const detectionNode = row.detectionControlIds.length > 0 ? nodeMap.get(row.detectionControlIds[0]) : null;

        const s = getRowSeverity(row, nodeMap);
        const o = causeNode?.occurrence || 0;
        const d = detectionNode?.detection || 0;
        const ap = calculateAP(s, o, d);

        if (!ap) return <Text type="secondary">-</Text>;
        const apColors: Record<string, { bg: string; text: string }> = {
          H: { bg: "var(--qf-red-dim)", text: "var(--qf-red)" },
          M: { bg: "var(--qf-amber-dim)", text: "var(--qf-amber)" },
          L: { bg: "var(--qf-green-dim)", text: "var(--qf-green)" },
        };
        const c = apColors[ap];
        return (
          <Tag style={{ background: c.bg, color: c.text, borderColor: c.text, fontWeight: 700, fontSize: 13, minWidth: 36, textAlign: "center", fontFamily: "var(--qf-font-mono)" }}>
            {ap}
          </Tag>
        );
      },
    },
    {
      title: t("editor.columns.recommendedAction"),
      key: "recommendedAction",
      width: 180,
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
                  name: t("editor.newAction"),
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
              + {t("editor.add")}
            </Button>
          );
        }
        const nodeId = row.recommendedActionIds[0];
        const node = nodeMap.get(nodeId);
        const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
        const detNode = row.detectionControlIds.length > 0 ? nodeMap.get(row.detectionControlIds[0]) : null;
        const s = getRowSeverity(row, nodeMap);
        return (
          <SmartSuggestionDropdown
            triggerType="optimization"
            context={{
              failure_mode: nodeMap.get(row.failureModeNodeId)?.name || "",
              severity: s,
              occurrence: causeNode?.occurrence || 0,
              detection: detNode?.detection || 0,
              ap: calculateAP(s, causeNode?.occurrence || 0, detNode?.detection || 0),
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
      title: t("editor.columns.responsibility"),
      key: "responsibility",
      width: 150,
      render: (_: unknown, row: FMEARow) => {
        if (row.recommendedActionIds.length === 0) return "-";
        const node = nodeMap.get(row.recommendedActionIds[0]);
        return (
          <div>
            <Input
              size="small"
              placeholder={t("editor.placeholders.responsible")}
              value={node?.responsible || ""}
              disabled={!canEdit('fmea')}
              style={{ marginBottom: 4 }}
              onChange={(e) => updateNode(row.recommendedActionIds[0], "responsible", e.target.value)}
            />
            <Input
              size="small"
              placeholder={t("editor.placeholders.dueDate")}
              value={node?.due_date || ""}
              disabled={!canEdit('fmea')}
              onChange={(e) => updateNode(row.recommendedActionIds[0], "due_date", e.target.value)}
            />
          </div>
        );
      },
    },
    {
      title: t("editor.columns.actionsTaken"),
      key: "actionsTaken",
      width: 180,
      render: (_: unknown, row: FMEARow) => {
        if (row.recommendedActionIds.length === 0) return "-";
        const node = nodeMap.get(row.recommendedActionIds[0]);
        return (
          <Input.TextArea
            value={node?.action_taken || ""}
            autoSize={{ minRows: 2, maxRows: 8 }}
            disabled={!canEdit('fmea')}
            onChange={(e) => updateNode(row.recommendedActionIds[0], "action_taken", e.target.value)}
          />
        );
      },
    },
    {
      title: <Tooltip title={t("editor.tooltips.revisedSeverity")}>S'</Tooltip>,
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
      title: <Tooltip title={t("editor.tooltips.revisedOccurrence")}>O'</Tooltip>,
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
      title: <Tooltip title={t("editor.tooltips.revisedDetection")}>D'</Tooltip>,
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
      title: <Tooltip title={t("editor.tooltips.revisedRpn")}>RPN'</Tooltip>,
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
        const rpnColor = rpn >= 100 ? "var(--qf-red)" : rpn >= 50 ? "var(--qf-amber)" : rpn > 0 ? "var(--qf-green)" : "var(--qf-text-tertiary)";
        const rpnBg = rpn >= 100 ? "var(--qf-red-dim)" : rpn >= 50 ? "var(--qf-amber-dim)" : rpn > 0 ? "var(--qf-green-dim)" : "rgba(139, 147, 167, 0.1)";
        return (
          <Tag
            style={{
              background: rpnBg,
              color: rpnColor,
              borderColor: rpnColor,
              fontWeight: 700,
              fontSize: 13,
              minWidth: 48,
              textAlign: "center",
              fontFamily: "var(--qf-font-mono)",
            }}
          >
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
      render: (_: unknown, row: FMEARow) =>
        row.failureCauseNodeId ? (
          <Popconfirm title={t("editor.confirmDeleteRow")} onConfirm={() => deleteRow(row)}>
            <Button type="text" danger size="small" disabled={!canEdit('fmea')} icon={<DeleteOutlined />} />
          </Popconfirm>
        ) : null,
    },
  ];

  return (
    <PageShell
      title={
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/fmea")}>{tc("actions.back")}</Button>
          <span className="qf-display" style={{ fontSize: 20 }}>{fmea.title}</span>
        </div>
      }
      subtitle={
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            flexWrap: "wrap",
            padding: "6px 12px",
            marginTop: 4,
            background: "var(--qf-bg-elevated)",
            border: "1px solid var(--qf-border)",
            borderRadius: "var(--qf-radius-md)",
            width: "fit-content",
          }}
        >
          <StatusBadge status={isDFMEA ? "normal" : "info"}>{isDFMEA ? "DFMEA" : "PFMEA"}</StatusBadge>
          <StatusBadge status={fmea.status}>{statusLabels[fmea.status] || fmea.status}</StatusBadge>
          <span
            style={{
              color: "var(--qf-text-secondary)",
              fontFamily: "var(--qf-font-mono)",
              fontSize: 13,
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <span style={{ color: "var(--qf-cyan)" }}>{fmea.document_no}</span>
            <span style={{ color: "var(--qf-border-strong)" }}>·</span>
            <span>v{fmea.version}</span>
          </span>
        </div>
      }
      actions={
        <>
          {nextTransitions[fmea.status]
            ?.filter((trans) => {
              if (!canEdit('fmea')) return false;
              if (trans.target === "approved" && !canApprove('fmea')) return false;
              return true;
            })
            ?.map((trans) => (
              <Popconfirm key={trans.target} title={`${t("actions.confirm")}${trans.label}？`} onConfirm={() => handleTransition(trans.target)}>
                <Button icon={trans.icon}>{trans.label}</Button>
              </Popconfirm>
            ))}
          {canEdit('fmea') && (
            <Button type="primary" icon={<SaveOutlined />} onClick={save} loading={saving}>{t("actions.save")}</Button>
          )}
        </>
      }
    >
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16 }}>
        <CollaborationBar activeUsers={activeUsers} isSyncing={isSyncing} compact />
      </div>

      <Tabs activeKey={outerTab} onChange={setOuterTab} style={{ marginBottom: 16 }} items={[
        { key: "editor", label: t("tabs.editor"), children: <>
          <Tabs activeKey={activeTab} onChange={setActiveTab} style={{ marginBottom: 16 }} items={[
            { key: "failure", label: t("tabs.failureAnalysis"), children: <>
          <Row gutter={16}>
            {/* Left: Structure/Function Tree */}
            <Col span={6}>
          <DataCard
            title={isDFMEA ? t("tabs.structureFunction") : t("tabs.processFunction")}
            extra={
              canEdit('fmea') && (
                <Button size="small" icon={<PlusOutlined />} onClick={addRootStructureNode}>
                  {isDFMEA ? t("editor.newSystem") : t("editor.newProcessItem")}
                </Button>
              )
            }
          >
            {(() => {
              const renderTreeNode = (tn: StructureTreeNode) => {
                const node = tn.node;
                const isStructure = ["ProcessItem", "ProcessStep", "ProcessWorkElement", "System", "Subsystem", "Component"].includes(node.type);
                const actions = canEdit('fmea') ? (STRUCTURE_CHILD_MAP[node.type] || []) : [];
                const hasRows = rowsByFunction[node.id]?.length > 0;
                const isSelected = selectedFunctionId === node.id;
                const dragState =
                  dragOver && dragOver.nodeId === node.id
                    ? dragOver.valid
                      ? dragOver.position === "before"
                        ? "before"
                        : dragOver.position === "after"
                          ? "after"
                          : "invalid"
                      : "invalid"
                    : null;
                return (
                  <div key={node.id}>
                    <div
                      data-testid={`fmea-structure-node-${node.id}`}
                      data-node-id={node.id}
                      data-drag-state={dragState ?? undefined}
                      onDragOver={handleStructureDragOver}
                      onDrop={(e) => handleStructureDrop(node.id, e)}
                      onDragEnd={handleStructureDragEnd}
                      onClick={() => setSelectedFunctionId(node.id)}
                      style={{
                        padding: "8px 12px",
                        marginBottom: 6,
                        marginLeft: tn.depth * 14,
                        borderRadius: 6,
                        cursor: "pointer",
                        background: isSelected ? "rgba(0, 229, 255, 0.12)" : isStructure ? "var(--qf-bg-elevated)" : "var(--qf-bg-input)",
                        border: isSelected
                          ? "1px solid var(--qf-cyan)"
                          : dragState === "invalid"
                            ? "1px solid rgba(255, 77, 79, 0.7)"
                            : "1px solid var(--qf-border)",
                        boxShadow:
                          dragState === "before"
                            ? "0 -2px 0 0 var(--qf-cyan)"
                            : dragState === "after"
                              ? "0 2px 0 0 var(--qf-cyan)"
                              : undefined,
                        fontSize: 13,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        transition: "background 0.2s, border-color 0.2s",
                        color: isSelected ? "var(--qf-cyan)" : "var(--qf-text-primary)",
                      }}
                      onMouseEnter={(e) => { if (!isSelected && !dragState) e.currentTarget.style.background = "var(--qf-bg-hover)"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.background = isSelected ? "rgba(0, 229, 255, 0.12)" : isStructure ? "var(--qf-bg-elevated)" : "var(--qf-bg-input)"; }}
                    >
                      {canDragSortStructure && (
                        <span
                          data-testid={`fmea-structure-drag-handle-${node.id}`}
                          draggable
                          onDragStart={(e) => handleStructureDragStart(node.id, e)}
                          onDragEnd={handleStructureDragEnd}
                          onMouseEnter={(e) => { e.currentTarget.style.opacity = "1"; }}
                          onMouseLeave={(e) => { e.currentTarget.style.opacity = "0.35"; }}
                          title={t("editor.dragHandle")}
                          aria-label={t("editor.dragHandle")}
                          style={{
                            cursor: "grab",
                            color: "var(--qf-text-secondary)",
                            opacity: 0.35,
                            transition: "opacity 0.15s",
                            marginRight: 6,
                            flexShrink: 0,
                            display: "inline-flex",
                            alignItems: "center",
                          }}
                        >
                          <HolderOutlined />
                        </span>
                      )}
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <Input
                          variant="borderless"
                          value={node.name}
                          disabled={!canEdit('fmea')}
                          onChange={(e) => updateNode(node.id, "name", e.target.value)}
                          // Stop click/focus from racing the row's setSelectedFunctionId;
                          // select explicitly on focus instead so editing a name also
                          // selects its node (and drives the right-hand spreadsheet).
                          onClick={(e) => e.stopPropagation()}
                          onFocus={() => setSelectedFunctionId(node.id)}
                          style={{
                            padding: 0,
                            background: "transparent",
                            fontWeight: isStructure ? 600 : 400,
                            lineHeight: "1.5",
                            color: "inherit",
                          }}
                        />
                        {node.process_number && <Text type="secondary" style={{ fontSize: 11 }}>{node.process_number}</Text>}
                      </div>
                      <Space size={4} style={{ flexShrink: 0, marginLeft: 8 }}>
                        {hasRows && (
                          <Tag style={{ fontSize: 10, lineHeight: "16px", background: "var(--qf-cyan-dim)", color: "var(--qf-cyan)", borderColor: "var(--qf-cyan)" }}>
                            {rowsByFunction[node.id].length}
                          </Tag>
                        )}
                        {actions.length > 0 && (
                          <Dropdown
                            trigger={["click"]}
                            menu={{
                              items: actions.map((a) => ({
                                key: a.childType,
                                label: t(a.labelKey),
                                // Stop the menu-item click from bubbling to the
                                // outer row (which would select the parent node
                                // and race the later setSelectedFunctionId on
                                // function creation). openAddNode does not itself
                                // change selection, so selection stays stable
                                // until submit.
                                onClick: ({ domEvent }) => {
                                  domEvent.stopPropagation();
                                  openAddNode(node, a);
                                },
                              })),
                            }}
                          >
                            <Button
                              size="small"
                              type="text"
                              icon={<PlusOutlined />}
                              onClick={(e) => e.stopPropagation()}
                            />
                          </Dropdown>
                        )}
                        <Popconfirm
                          title={t("editor.confirmDeleteNode")}
                          onConfirm={() => deleteSubtreeNode(node)}
                          onCancel={(e) => e?.stopPropagation()}
                        >
                          <Button
                            size="small"
                            type="text"
                            danger
                            disabled={!canEdit('fmea')}
                            icon={<DeleteOutlined />}
                            onClick={(e) => e.stopPropagation()}
                          />
                        </Popconfirm>
                      </Space>
                    </div>
                    {!dragCollapseIds.has(node.id) && tn.children.map((c) => renderTreeNode(c))}
                  </div>
                );
              };
              return (
                <>
                  {structureTree.map((tn) => renderTreeNode(tn))}
                  {structureTree.length === 0 && <Empty description={t("messages.noData")} image={Empty.PRESENTED_IMAGE_SIMPLE} />}
                </>
              );
            })()}
          </DataCard>
        </Col>

        {/* Right: FMEA Table */}
        <Col span={18}>
          <DataCard
            title={
              <span style={{ fontSize: 14 }}>
                {isDFMEA ? t("editor.dfmeaTitle") : t("editor.pfmeaTitle")}
              </span>
            }
            extra={
              canEdit('fmea') && (
                <Button size="small" icon={<PlusOutlined />} onClick={addRow} disabled={!selectedFunctionId}>
                  {t("editor.addRow")}
                </Button>
              )
            }
            noPadding
          >
            <div style={{ padding: "8px 0" }}>
              <Table
                dataSource={rows}
                columns={columns}
                rowKey="key"
                size="small"
                pagination={false}
                scroll={{ x: 2400, y: 540 }}
                bordered
                className="qf-table fmea-editor-table"
                style={{ fontSize: 13 }}
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
                  <Text type="secondary">{t("editor.selectFunctionHint")}</Text>
                </div>
              )}
            </div>
          </DataCard>
        </Col>
      </Row>
        </>},
            { key: "structure", label: t("tabs.structureAnalysis"), children: <>
          <Row gutter={16}>
            <Col span={8}>
              <DataCard title={t("tabs.structureTree")}>
                <StructureTree
                  nodes={nodes}
                  edges={edges}
                  onUpdateNodes={setNodes}
                  onUpdateEdges={setEdges}
                  isViewer={!canEdit('fmea')}
                  onSelectNode={(node) => setSelectedStructureNode(node)}
                />
              </DataCard>
            </Col>
            <Col span={16}>
              <DataCard title={t("tabs.nodeDetails")}>
                <ParameterDiagram
                  node={selectedStructureNode}
                  onUpdateNode={(nodeId, updates) => {
                    setNodes((prev) => prev.map((n) => (n.id === nodeId ? { ...n, ...updates } : n)));
                  }}
                  isViewer={!canEdit('fmea')}
                />
              </DataCard>
            </Col>
          </Row>
        </>},
          ]} />

      <style>{`
        .fmea-editor-table .ant-table-cell {
          white-space: normal !important;
          word-break: break-all;
          vertical-align: top;
          padding: 10px 12px !important;
        }
        .fmea-editor-table .ant-input,
        .fmea-editor-table .ant-select,
        .fmea-editor-table .ant-select-selector {
          font-size: 13px;
        }
        .fmea-editor-table .ant-input::placeholder {
          font-size: 12px;
        }
        .fmea-row-highlight td {
          background-color: rgba(0, 229, 255, 0.08) !important;
          transition: background-color 0.2s;
        }
        .fmea-row-highlight td:first-child {
          border-left: 3px solid var(--qf-cyan) !important;
        }
        .severity-warning-row td {
          background-color: rgba(255, 184, 0, 0.08) !important;
        }
        .severity-warning-row td:first-child {
          border-left: 3px solid var(--qf-amber) !important;
        }
        .highlighted-row td {
          background-color: rgba(255, 184, 0, 0.12) !important;
        }
        .highlighted-row td:first-child {
          border-left: 3px solid var(--qf-amber) !important;
        }
      `}</style>

      <Divider />
      <Text type="secondary" style={{ fontSize: 11 }}>
        {t("editor.footerLegend")}
      </Text>
        </>},
        { key: "graph", label: t("tabs.graph"), children: <>
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
                        { key: "impact", label: t("graph.traceImpact") },
                        { key: "cause", label: t("graph.traceCause") },
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
                  {t("graph.clearHighlight")}
                </Button>
              )}
              <DataCard title={t("changeImpact.title")}>
                <Space direction="vertical" style={{ width: "100%" }}>
                  <Text type="secondary">{t("changeImpact.description")}</Text>
                  <Button
                    type="primary"
                    icon={<RadarChartOutlined />}
                    onClick={() => { setImpactModalOpen(true); setImpactResult(null); }}
                    disabled={!canEdit("fmea") || !selectedGraphNode}
                  >
                    {t("changeImpact.analyze")}
                  </Button>
                </Space>
              </DataCard>
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
            title={t("changeImpact.modalTitle")}
            open={impactModalOpen}
            onCancel={() => setImpactModalOpen(false)}
            width={800}
            footer={
              impactResult ? (
                <Button onClick={() => setImpactModalOpen(false)}>{t("actions.close")}</Button>
              ) : (
                <>
                  <Button onClick={() => setImpactModalOpen(false)}>{t("actions.cancel")}</Button>
                  <Button type="primary" onClick={handleAnalyzeImpact} loading={impactLoading}>{t("changeImpact.execute")}</Button>
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
                  <Radio.Button value="attribute">{t("changeImpact.attribute")}</Radio.Button>
                  <Radio.Button value="structural">{t("changeImpact.structural")}</Radio.Button>
                </Radio.Group>
                {impactForm.change_type === "attribute" && (
                  <>
                    <Input placeholder={t("changeImpact.fieldPlaceholder")} value={impactForm.field_name} onChange={(e) => setImpactForm({ ...impactForm, field_name: e.target.value })} />
                    <Input placeholder={t("changeImpact.valuePlaceholder")} value={impactForm.new_value} onChange={(e) => setImpactForm({ ...impactForm, new_value: e.target.value })} />
                  </>
                )}
              </Space>
            )}
          </Modal>
        </>},
        { key: "related-capa", label: t("tabs.relatedCapa"), children: <>
          {selectedFunctionId ? (
            <RelatedCAPAList
              fmeaId={fmea!.fmea_id}
              fmeaNodeId={selectedFunctionId}
            />
          ) : (
            <Typography.Text type="secondary">
              {t("messages.selectFailureModeFirst")}
            </Typography.Text>
          )}
        </>},
        { key: "history", label: <span><HistoryOutlined /> {t("tabs.versionHistory")}</span>, children: <>
          <VersionHistoryTab
            documentId={id!}
            documentType="fmea"
            canCreate={canEdit('fmea')}
            canRollback={canApprove('fmea')}
            isDraft={fmea.status === "draft"}
            onViewSnapshot={(major, minor) => message.info(t("messages.viewSnapshot", { major, minor }))}
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
          title={t("version.compareTitle")}
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
      <Modal
        title={t("editor.addNodeTitle")}
        open={addNodeOpen}
        onOk={submitAddNode}
        onCancel={() => setAddNodeOpen(false)}
        destroyOnHidden
      >
        <Form form={addNodeForm} layout="vertical">
          <Form.Item
            name="name"
            label={t("editor.nodeName")}
            rules={[{ required: true, message: t("editor.nodeNamePlaceholder") }]}
          >
            <Input placeholder={t("editor.nodeNamePlaceholder")} />
          </Form.Item>
          <Form.Item name="specification" label={t("editor.specification")}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="requirement" label={t("editor.requirement")}>
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
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
    </PageShell>
  );
}

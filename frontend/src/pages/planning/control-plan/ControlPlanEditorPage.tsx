import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Button, Space, Typography, Input, Table, Row, Col,
  App, Spin, Select, Alert, Tooltip, Tabs, Modal, Tag,
} from "antd";
import {
  SaveOutlined, ArrowLeftOutlined, PlusOutlined, DeleteOutlined,
  ImportOutlined, CheckCircleOutlined, ExclamationCircleOutlined,
  SyncOutlined, HistoryOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import {
  getControlPlan, createControlPlan, updateControlPlan,
  checkStaleItems, approveControlPlan, syncCSRToControlPlan,
} from "../../../api/controlPlan";
import type { ControlPlan, ControlPlanItem, CPVersionHeader } from "../../../types";
import { listCustomers } from "../../../api/customerQuality";
import type { CPSyncStatusItem } from "../../../types/specialCharacteristic";
import { useAuthStore } from "../../../store/authStore";
import { usePermission } from "../../../hooks/usePermission";
import { getCPSyncStatus, syncToCP } from "../../../api/specialCharacteristic";
import { getCPVersion } from "../../../api/version";
import { useCollaboration } from "../../../hooks/useCollaboration";
import { CollaborationBar, ActiveUserIndicator, ConflictResolutionModal } from "../../../components/collaboration";
import type { ConflictInfo } from "../../../types/collaboration";
import { diffControlPlanItems, adaptCPDiffToGraphDiff } from "../../../utils/controlPlanDiff";
import type { ControlPlanDiff } from "../../../utils/controlPlanDiff";
import ImportFromFMEAModal from "../../../components/control-plan/ImportFromFMEAModal";
import VersionHistoryTab from "../../../components/version/VersionHistoryTab";
import CreateVersionModal from "../../../components/version/CreateVersionModal";
import RollbackConfirmModal from "../../../components/version/RollbackConfirmModal";
import VersionCompareView from "../../../components/version/VersionCompareView";
import SyncPreviewDrawer from "../../../components/version/SyncPreviewDrawer";
import ValidationPanel from "../../../components/control-plan/ValidationPanel";
import PageShell from "../../../components/design/PageShell";
import DataCard from "../../../components/design/DataCard";
import StatusBadge from "../../../components/design/StatusBadge";

const { Text } = Typography;

function createBlankItem(sortOrder: number): ControlPlanItem {
  return {
    item_id: `temp-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    step_no: "",
    process_name: "",
    equipment: "",
    characteristic_no: "",
    product_characteristic: "",
    process_characteristic: "",
    special_class: "",
    specification_tolerance: "",
    evaluation_method: "",
    sample_size: "",
    sample_frequency: "",
    control_method: "",
    reaction_plan: "",
    source_fmea_node_id: null,
    sort_order: sortOrder,
  };
}

function useControlPlanOptions(t: (key: string) => string) {
  const phaseOptions = [
    { value: "sample", label: t("phase.sample") },
    { value: "trial", label: t("phase.trial") },
    { value: "production", label: t("phase.production") },
  ];

  const statusLabels: Record<string, string> = {
    draft: t("status.draft"),
    approved: t("status.approved"),
  };

  const specialClassOptions = [
    { value: "", label: t("specialClass.none") },
    { value: "CC", label: t("specialClass.CC") },
    { value: "SC", label: t("specialClass.SC") },
  ];

  return { phaseOptions, statusLabels, specialClassOptions };
}

export default function ControlPlanEditorPage() {
  const { t } = useTranslation("controlPlan");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isNew = id === "new";

  const { phaseOptions, statusLabels, specialClassOptions } = useControlPlanOptions(t);

  const [cp, setCp] = useState<ControlPlan | null>(null);
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [staleAlert, setStaleAlert] = useState<{ visible: boolean; stepNos: string[] }>({
    visible: false,
    stepNos: [],
  });
  const [syncStatus, setSyncStatus] = useState<CPSyncStatusItem[]>([]);
  const [outerTab, setOuterTab] = useState("editor");
  const [createVersionOpen, setCreateVersionOpen] = useState(false);
  const [rollbackTarget, setRollbackTarget] = useState<{ major_no: number; minor_no: number } | null>(null);
  const [compareState, setCompareState] = useState<{ major1: number; minor1: number; major2: number; minor2: number } | null>(null);
  const [syncDrawerOpen, setSyncDrawerOpen] = useState(false);
  const [csrSyncOpen, setCsrSyncOpen] = useState(false);
  const [csrCustomerIds, setCsrCustomerIds] = useState<string[]>([]);
  const [csrSyncing, setCsrSyncing] = useState(false);
  const [csrCustomers, setCsrCustomers] = useState<{ customer_id: string; name: string; csr_list: unknown[] | null }[]>([]);
  const [viewingVersion, setViewingVersion] = useState<{ major: number; minor: number } | null>(null);
  const [versionHeader, setVersionHeader] = useState<CPVersionHeader | null>(null);

  const _user = useAuthStore((s) => s.user);
  const { canEdit: canEditPerm, canApprove: rawCanApprove } = usePermission();
  const isApproved = cp?.status === "approved";
  const isViewingVersion = viewingVersion !== null;
  const canEdit = canEditPerm('planning') && !isApproved && !isViewingVersion;
  const canApproveAllowed = (m: "planning") => rawCanApprove(m) && !isViewingVersion;

  const cpId = id || "";
  const { activeUsers, isSyncing, startEditing: rawStartEditing, stopEditing } = useCollaboration("control_plan", cpId);
  const startEditing = useCallback((...args: Parameters<typeof rawStartEditing>) => {
    if (isViewingVersion) return;
    rawStartEditing(...args);
  }, [rawStartEditing, isViewingVersion]);

  // Conflict resolution state
  const [conflictVisible, setConflictVisible] = useState(false);
  const [conflictInfo, setConflictInfo] = useState<ConflictInfo | null>(null);
  const [conflictDiff, setConflictDiff] = useState<ControlPlanDiff | null>(null);

  // Base snapshot for diff
  const baseItemsRef = useRef<ControlPlanItem[] | null>(null);

  // Form state
  const [title, setTitle] = useState("");
  const [documentNo, setDocumentNo] = useState("");
  const [phase, setPhase] = useState("sample");
  const [partNo, setPartNo] = useState("");
  const [partName, setPartName] = useState("");
  const [contactInfo, setContactInfo] = useState("");
  const [coreGroup, setCoreGroup] = useState("");
  const [orgFactory, setOrgFactory] = useState("");
  const [drawingRev, setDrawingRev] = useState("");
  const [items, setItems] = useState<ControlPlanItem[]>([]);

  useEffect(() => {
    if (isNew) {
      setLoading(false);
      return;
    }
    if (!id) return;
    setLoading(true);
    getControlPlan(id)
      .then((doc) => {
        setCp(doc);
        setTitle(doc.title);
        setDocumentNo(doc.document_no);
        setPhase(doc.phase || "sample");
        setPartNo(doc.part_no || "");
        setPartName(doc.part_name || "");
        setContactInfo(doc.contact_info || "");
        setCoreGroup(doc.core_group || "");
        setOrgFactory(doc.org_factory || "");
        setDrawingRev(doc.drawing_rev || "");
        setItems(doc.items || []);
        baseItemsRef.current = JSON.parse(JSON.stringify(doc.items || []));
        if (id) {
          getCPSyncStatus(id).then((res) => setSyncStatus(res.items)).catch(() => {});
        }
      })
      .catch(() => {
        message.error(t("message.loadFailed"));
      })
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, isNew]);

  const loadVersionSnapshot = useCallback(async (major: number, minor: number) => {
    if (!id) return;
    try {
      const v = await getCPVersion(id, major, minor);
      const h = v.header_snapshot || {};
      setTitle(h.title || "");
      setDocumentNo(h.document_no || "");
      setPhase(h.phase || "sample");
      setPartNo(h.part_no || "");
      setPartName(h.part_name || "");
      setContactInfo(h.contact_info || "");
      setCoreGroup(h.core_group || "");
      setOrgFactory(h.org_factory || "");
      setDrawingRev(h.drawing_rev || "");
      setItems(v.items_snapshot || []);
      setVersionHeader(v.header_snapshot);
      setViewingVersion({ major, minor });
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      message.error(e?.response?.data?.detail || t("message.loadVersionFailed"));
    }
  }, [id, t, message]);

  const exitVersionSnapshot = useCallback(async () => {
    if (!id) return;
    try {
      const doc = await getControlPlan(id);
      setCp(doc);
      setTitle(doc.title);
      setDocumentNo(doc.document_no);
      setPhase(doc.phase || "sample");
      setPartNo(doc.part_no || "");
      setPartName(doc.part_name || "");
      setContactInfo(doc.contact_info || "");
      setCoreGroup(doc.core_group || "");
      setOrgFactory(doc.org_factory || "");
      setDrawingRev(doc.drawing_rev || "");
      setItems(doc.items || []);
      baseItemsRef.current = JSON.parse(JSON.stringify(doc.items || []));
      setVersionHeader(null);
      setViewingVersion(null);
    } catch {
      message.error(t("message.loadFailed"));
    }
  }, [id, t, message]);

  const updateItem = useCallback((index: number, field: keyof ControlPlanItem, value: string) => {
    setItems((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], [field]: value };
      return next;
    });
  }, []);

  const addItem = useCallback(() => {
    setItems((prev) => [...prev, createBlankItem(prev.length)]);
  }, []);

  const removeItem = useCallback((index: number) => {
    setItems((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const handleSave = async () => {
    if (!title.trim()) {
      message.warning(t("message.enterTitle"));
      return;
    }
    if (!documentNo.trim()) {
      message.warning(t("message.enterDocumentNo"));
      return;
    }

    setSaving(true);
    try {
      if (isNew) {
        const created = await createControlPlan({
          title: title.trim(),
          document_no: documentNo.trim(),
          phase,
          part_no: partNo.trim() || undefined,
          part_name: partName.trim() || undefined,
          contact_info: contactInfo.trim() || undefined,
          core_group: coreGroup.trim() || undefined,
          org_factory: orgFactory.trim() || undefined,
          drawing_rev: drawingRev.trim() || undefined,
        });
        // Save items separately via update
        if (items.length > 0) {
          await updateControlPlan(created.cp_id, { items });
        }
        message.success(tc("messages.saveSuccess"));
        navigate(`/control-plans/${created.cp_id}`);
      } else if (id) {
        const saveData = {
          title: title.trim(),
          phase,
          part_no: partNo.trim() || undefined,
          part_name: partName.trim() || undefined,
          contact_info: contactInfo.trim() || undefined,
          core_group: coreGroup.trim() || undefined,
          org_factory: orgFactory.trim() || undefined,
          drawing_rev: drawingRev.trim() || undefined,
          items,
        };
        try {
          const updated = await updateControlPlan(id, {
            ...saveData,
            lock_version: cp!.lock_version,
          });
          setCp(updated);
          baseItemsRef.current = JSON.parse(JSON.stringify(items));
          message.success(tc("messages.saveSuccess"));
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
            setConflictVisible(true);
            // Fetch latest and compute diff
            try {
              const latestDoc = await getControlPlan(id);
              const base = baseItemsRef.current;
              if (base) {
                const diff = diffControlPlanItems(
                  base,
                  latestDoc.items || [],
                  items  // current local items
                );
                setConflictDiff(diff);
              }
            } catch {
              /* silently ignore diff failure */
            }
          } else {
            throw e;
          }
        }
      }
    } catch (e: any) {
      message.error(e.response?.data?.detail || (isNew ? t("message.createFailed") : t("message.saveFailed")));
    } finally {
      setSaving(false);
    }
  };

  const handleConflictRefresh = () => {
    setConflictVisible(false);
    window.location.reload();
  };

  const handleConflictForceSave = async () => {
    if (!id || !cp || !conflictInfo) return;
    const saveData = {
      title: title.trim(),
      phase,
      part_no: partNo.trim() || undefined,
      part_name: partName.trim() || undefined,
      contact_info: contactInfo.trim() || undefined,
      core_group: coreGroup.trim() || undefined,
      org_factory: orgFactory.trim() || undefined,
      drawing_rev: drawingRev.trim() || undefined,
      items,
    };
    try {
      const updated = await updateControlPlan(id, {
        ...saveData,
        lock_version: cp.lock_version,
        confirmed_latest_lock_version: conflictInfo.latest_lock_version,
      });
      setCp(updated);
      baseItemsRef.current = JSON.parse(JSON.stringify(items));
      setConflictVisible(false);
      message.success(t("conflict.forceSaveSuccess"));
    } catch (e: unknown) {
      const err = e as { response?: { status?: number; data?: { detail?: string } } };
      if (err.response?.status === 409) {
        message.error(t("conflict.documentModified"));
      } else {
        message.error(t("conflict.forceSaveFailed"));
      }
    }
  };

  const handleCheckStale = async () => {
    if (!id || isNew) return;
    try {
      const result = await checkStaleItems(id);
      if (result.stale_items.length > 0) {
        const stepNos = result.stale_items.map((s) => s.step_no).filter(Boolean);
        setStaleAlert({ visible: true, stepNos });
      } else {
        message.success(t("staleAlert.noChange"));
        setStaleAlert({ visible: false, stepNos: [] });
      }
    } catch {
      message.error(t("message.checkFailed"));
    }
  };

  const handleApprove = async () => {
    if (!id || isNew) return;
    try {
      const updated = await approveControlPlan(id);
      setCp(updated);
      message.success(t("message.approveSuccess"));
    } catch (e: any) {
      message.error(e.response?.data?.detail || t("message.approveFailed"));
    }
  };

  const handleImportSuccess = async () => {
    if (!id || isNew) return;
    try {
      const refreshed = await getControlPlan(id);
      setCp(refreshed);
      setItems(refreshed.items || []);
      message.success(t("importModal.importSuccess"));
    } catch {
      message.error(t("message.refreshFailed"));
    }
  };

  const handleOpenCsrSync = async () => {
    setCsrSyncOpen(true);
    try {
      const res = await listCustomers({ page: 1, page_size: 200 });
      setCsrCustomers(res.items.filter((c: { csr_list: unknown[] | null }) => c.csr_list && c.csr_list.length > 0));
    } catch { /* silent */ }
  };

  const handleCsrSync = async () => {
    if (!id || csrCustomerIds.length === 0) return;
    setCsrSyncing(true);
    try {
      const refreshed = await syncCSRToControlPlan(id, csrCustomerIds);
      setCp(refreshed);
      setCsrSyncOpen(false);
      setCsrCustomerIds([]);
      message.success(t("message.syncSuccess"));
    } catch (e: any) {
      message.error(e.response?.data?.detail || t("message.syncFailed"));
    } finally {
      setCsrSyncing(false);
    }
  };

  const columns = [
    {
      title: t("column.stepNo"),
      dataIndex: "step_no",
      key: "step_no",
      width: 120,
      render: (_: string, record: ControlPlanItem, index: number) => (
        <div>
          <Input
            value={items[index]?.step_no || ""}
            onFocus={() => startEditing({ row_key: record.item_id, field: "step_no" })}
            onBlur={stopEditing}
            onChange={(e) => updateItem(index, "step_no", e.target.value)}
            disabled={!canEdit}
            size="small"
          />
          <ActiveUserIndicator
            activeUsers={activeUsers}
            rowKey={record.item_id}
            field="step_no"
          />
        </div>
      ),
    },
    {
      title: t("column.processName"),
      dataIndex: "process_name",
      key: "process_name",
      width: 160,
      render: (_: string, record: ControlPlanItem, index: number) => (
        <div>
          <Input
            value={items[index]?.process_name || ""}
            onFocus={() => startEditing({ row_key: record.item_id, field: "process_name" })}
            onBlur={stopEditing}
            onChange={(e) => updateItem(index, "process_name", e.target.value)}
            disabled={!canEdit}
            size="small"
          />
          <ActiveUserIndicator
            activeUsers={activeUsers}
            rowKey={record.item_id}
            field="process_name"
          />
        </div>
      ),
    },
    {
      title: t("column.equipment"),
      dataIndex: "equipment",
      key: "equipment",
      width: 140,
      render: (_: string, __: ControlPlanItem, index: number) => (
        <Input
          value={items[index]?.equipment || ""}
          onChange={(e) => updateItem(index, "equipment", e.target.value)}
          disabled={!canEdit}
          size="small"
        />
      ),
    },
    {
      title: t("column.characteristic"),
      children: [
        {
          title: t("column.characteristicNo"),
          dataIndex: "characteristic_no",
          key: "characteristic_no",
          width: 100,
          render: (_: string, __: ControlPlanItem, index: number) => (
            <Input
              value={items[index]?.characteristic_no || ""}
              onChange={(e) => updateItem(index, "characteristic_no", e.target.value)}
              disabled={!canEdit}
              size="small"
            />
          ),
        },
        {
          title: t("column.productCharacteristic"),
          dataIndex: "product_characteristic",
          key: "product_characteristic",
          width: 140,
          render: (_: string, record: ControlPlanItem, index: number) => (
            <div>
              <Input
                value={items[index]?.product_characteristic || ""}
                onFocus={() => startEditing({ row_key: record.item_id, field: "product_characteristic" })}
                onBlur={stopEditing}
                onChange={(e) => updateItem(index, "product_characteristic", e.target.value)}
                disabled={!canEdit}
                size="small"
              />
              <ActiveUserIndicator
                activeUsers={activeUsers}
                rowKey={record.item_id}
                field="product_characteristic"
              />
            </div>
          ),
        },
        {
          title: t("column.processCharacteristic"),
          dataIndex: "process_characteristic",
          key: "process_characteristic",
          width: 140,
          render: (_: string, record: ControlPlanItem, index: number) => (
            <div>
              <Input
                value={items[index]?.process_characteristic || ""}
                onFocus={() => startEditing({ row_key: record.item_id, field: "process_characteristic" })}
                onBlur={stopEditing}
                onChange={(e) => updateItem(index, "process_characteristic", e.target.value)}
                disabled={!canEdit}
                size="small"
              />
              <ActiveUserIndicator
                activeUsers={activeUsers}
                rowKey={record.item_id}
                field="process_characteristic"
              />
            </div>
          ),
        },
      ],
    },
    {
      title: t("column.specialClass"),
      dataIndex: "special_class",
      key: "special_class",
      width: 130,
      render: (_: string, record: ControlPlanItem, index: number) => {
        const syncItem = syncStatus.find((s) => s.item_id === record.item_id);
        const outOfSync = syncItem?.is_out_of_sync;
        return (
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <Select
              value={items[index]?.special_class || ""}
              onChange={(value) => updateItem(index, "special_class", value)}
              options={specialClassOptions}
              disabled={!canEdit}
              size="small"
              style={{ width: 80 }}
            />
            {outOfSync && (
              <Tooltip title={t("staleAlert.nodeChanged")}>
                <StatusBadge status="warning">!</StatusBadge>
              </Tooltip>
            )}
          </div>
        );
      },
    },
    {
      title: t("column.specificationTolerance"),
      dataIndex: "specification_tolerance",
      key: "specification_tolerance",
      width: 160,
      render: (_: string, __: ControlPlanItem, index: number) => (
        <Input
          value={items[index]?.specification_tolerance || ""}
          onChange={(e) => updateItem(index, "specification_tolerance", e.target.value)}
          disabled={!canEdit}
          size="small"
        />
      ),
    },
    {
      title: t("column.method"),
      children: [
        {
          title: t("column.evaluationMethod"),
          dataIndex: "evaluation_method",
          key: "evaluation_method",
          width: 140,
          render: (_: string, __: ControlPlanItem, index: number) => (
            <Input
              value={items[index]?.evaluation_method || ""}
              onChange={(e) => updateItem(index, "evaluation_method", e.target.value)}
              disabled={!canEdit}
              size="small"
            />
          ),
        },
      ],
    },
    {
      title: t("column.sample"),
      children: [
        {
          title: t("column.sampleSize"),
          dataIndex: "sample_size",
          key: "sample_size",
          width: 100,
          render: (_: string, __: ControlPlanItem, index: number) => (
            <Input
              value={items[index]?.sample_size || ""}
              onChange={(e) => updateItem(index, "sample_size", e.target.value)}
              disabled={!canEdit}
              size="small"
            />
          ),
        },
        {
          title: t("column.sampleFrequency"),
          dataIndex: "sample_frequency",
          key: "sample_frequency",
          width: 100,
          render: (_: string, __: ControlPlanItem, index: number) => (
            <Input
              value={items[index]?.sample_frequency || ""}
              onChange={(e) => updateItem(index, "sample_frequency", e.target.value)}
              disabled={!canEdit}
              size="small"
            />
          ),
        },
      ],
    },
    {
      title: t("column.controlMethod"),
      dataIndex: "control_method",
      key: "control_method",
      width: 140,
      render: (_: string, record: ControlPlanItem, index: number) => (
        <div>
          <Input
            value={items[index]?.control_method || ""}
            onFocus={() => startEditing({ row_key: record.item_id, field: "control_method" })}
            onBlur={stopEditing}
            onChange={(e) => updateItem(index, "control_method", e.target.value)}
            disabled={!canEdit}
            size="small"
          />
          <ActiveUserIndicator
            activeUsers={activeUsers}
            rowKey={record.item_id}
            field="control_method"
          />
        </div>
      ),
    },
    {
      title: t("column.reactionPlan"),
      dataIndex: "reaction_plan",
      key: "reaction_plan",
      width: 140,
      render: (_: string, record: ControlPlanItem, index: number) => (
        <div>
          <Input
            value={items[index]?.reaction_plan || ""}
            onFocus={() => startEditing({ row_key: record.item_id, field: "reaction_plan" })}
            onBlur={stopEditing}
            onChange={(e) => updateItem(index, "reaction_plan", e.target.value)}
            disabled={!canEdit}
            size="small"
          />
          <ActiveUserIndicator
            activeUsers={activeUsers}
            rowKey={record.item_id}
            field="reaction_plan"
          />
        </div>
      ),
    },
    {
      title: t("column.actions"),
      key: "actions",
      width: 80,
      fixed: "right" as const,
      render: (_: unknown, __: ControlPlanItem, index: number) => (
        canEdit ? (
          <Button
            type="link"
            danger
            size="small"
            icon={<DeleteOutlined />}
            onClick={() => removeItem(index)}
          >
            {tc("actions.delete")}
          </Button>
        ) : null
      ),
    },
  ];

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: 64 }}>
        <Spin size="large" />
      </div>
    );
  }

  const currentStatus = cp?.status || "draft";
  const displayStatus = isViewingVersion ? (versionHeader?.status || "") : currentStatus;

  return (
    <PageShell
      title={isNew ? t("pageTitle.newControlPlan") : title || t("pageTitle.controlPlanDetail")}
      subtitle={`${t("column.status")}：${statusLabels[displayStatus] || displayStatus}`}
      actions={
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/control-plans")}>
          {tc("actions.back")}
        </Button>
      }
    >
      <CollaborationBar activeUsers={activeUsers} isSyncing={isSyncing} />

      {/* Stale alert */}
      {staleAlert.visible && (
        <Alert
          type="warning"
          showIcon
          icon={<ExclamationCircleOutlined />}
          closable
          onClose={() => setStaleAlert({ visible: false, stepNos: [] })}
          message={t("staleAlert.message", { steps: staleAlert.stepNos.join(", ") })}
          style={{ marginBottom: 16 }}
        />
      )}

      {/* Sync pending banner */}
      {cp?.sync_pending && !isViewingVersion && (
        <Alert
          message={t("staleAlert.syncPending")}
          type="warning"
          showIcon
          action={
            <Button size="small" icon={<SyncOutlined />} onClick={() => setSyncDrawerOpen(true)}>
              {t("staleAlert.syncNow")}
            </Button>
          }
          style={{ marginBottom: 16 }}
        />
      )}

      {viewingVersion && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message={t("message.viewingVersion", { version: `${viewingVersion.major}.${viewingVersion.minor}` })}
          action={
            <Button size="small" onClick={exitVersionSnapshot}>
              {t("button.exitVersion")}
            </Button>
          }
        />
      )}

      <Tabs activeKey={outerTab} onChange={setOuterTab} items={[
        { key: "editor", label: t("pageTitle.controlPlanEditor"), children: <>

      {/* Action buttons */}
      <Space style={{ marginBottom: 16 }}>
        <Button
          type="primary"
          icon={<SaveOutlined />}
          loading={saving}
          onClick={handleSave}
          disabled={!canEdit}
        >
          {tc("actions.save")}
        </Button>
        {!isNew && canEdit && (
          <Button icon={<ImportOutlined />} onClick={() => setImportOpen(true)}>
            {t("button.importFromPFMEA")}
          </Button>
        )}
        {!isNew && !isViewingVersion && (
          <Button icon={<ExclamationCircleOutlined />} onClick={handleCheckStale}>
            {t("button.checkPFMEAChange")}
          </Button>
        )}
        {!isNew && canEdit && syncStatus.some((s) => s.is_out_of_sync) && (
          <Button
            icon={<SyncOutlined />}
            onClick={async () => {
              try {
                if (!id) return;
                await syncToCP(id);
                message.success(t("message.syncSuccess"));
                getCPSyncStatus(id).then((res) => setSyncStatus(res.items)).catch(() => {});
              } catch {
                message.error(t("message.syncFailed"));
              }
            }}
          >
            {t("button.syncSpecialCharacteristics")}
          </Button>
        )}
        {!isNew && canApproveAllowed('planning') && displayStatus !== "approved" && (
          <Button icon={<CheckCircleOutlined />} onClick={handleApprove}>
            {tc("actions.approve")}
          </Button>
        )}
        {!isNew && canEdit && (
          <Button icon={<SyncOutlined />} onClick={handleOpenCsrSync}>
            {t("button.syncCSR")}
          </Button>
        )}
      </Space>

      {/* Header info card */}
      <DataCard title={t("card.basicInfo")} style={{ marginBottom: 16 }}>
        <Row gutter={24}>
          <Col span={12}>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">{t("form.title")}</Text>
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                disabled={!canEdit}
                placeholder={t("placeholder.title")}
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">{t("form.documentNo")}</Text>
              <Input
                value={documentNo}
                onChange={(e) => setDocumentNo(e.target.value)}
                disabled={!isNew || !canEdit}
                placeholder={t("placeholder.documentNo")}
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">{t("form.partNo")}</Text>
              <Input
                value={partNo}
                onChange={(e) => setPartNo(e.target.value)}
                disabled={!canEdit}
                placeholder={t("placeholder.partNo")}
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">{t("form.partName")}</Text>
              <Input
                value={partName}
                onChange={(e) => setPartName(e.target.value)}
                disabled={!canEdit}
                placeholder={t("placeholder.partName")}
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">{t("form.contactInfo")}</Text>
              <Input
                value={contactInfo}
                onChange={(e) => setContactInfo(e.target.value)}
                disabled={!canEdit}
                placeholder={t("placeholder.contactInfo")}
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">{t("form.coreGroup")}</Text>
              <Input
                value={coreGroup}
                onChange={(e) => setCoreGroup(e.target.value)}
                disabled={!canEdit}
                placeholder={t("placeholder.coreGroup")}
              />
            </div>
          </Col>
          <Col span={12}>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">{t("form.orgFactory")}</Text>
              <Input
                value={orgFactory}
                onChange={(e) => setOrgFactory(e.target.value)}
                disabled={!canEdit}
                placeholder={t("placeholder.orgFactory")}
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">{t("form.drawingRev")}</Text>
              <Input
                value={drawingRev}
                onChange={(e) => setDrawingRev(e.target.value)}
                disabled={!canEdit}
                placeholder={t("placeholder.drawingRev")}
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">{t("form.phase")}</Text>
              <Select
                value={phase}
                onChange={(value) => setPhase(value)}
                options={phaseOptions}
                disabled={!canEdit}
                style={{ width: "100%" }}
                placeholder={t("placeholder.selectPhase")}
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">{t("form.relatedPFMEA")}</Text>
              <Input
                value={(isViewingVersion ? versionHeader?.fmea_ref_id : cp?.fmea_ref_id) || t("form.notAssociated")}
                disabled
              />
            </div>
          </Col>
        </Row>
      </DataCard>

      {/* Items table */}
      <DataCard title={t("card.controlPlanContent")}>
        <Table
          className="qf-table"
          columns={columns}
          dataSource={items}
          rowKey="item_id"
          pagination={false}
          scroll={{ x: 1600 }}
          size="small"
          bordered
          footer={() =>
            canEdit ? (
              <Button type="dashed" icon={<PlusOutlined />} onClick={addItem} block>
                {t("button.addRow")}
              </Button>
            ) : null
          }
        />
      </DataCard>

      {/* Import modal */}
      {!isNew && id && (
        <ImportFromFMEAModal
          cpId={id}
          open={importOpen}
          onClose={() => setImportOpen(false)}
          onSuccess={handleImportSuccess}
        />
      )}
        </>},
        { key: "history", label: <span><HistoryOutlined /> {t("pageTitle.versionHistory")}</span>, children: (
          <VersionHistoryTab
            documentId={id!}
            documentType="cp"
            canCreate={canEdit}
            canRollback={canApproveAllowed('planning')}
            isDraft={displayStatus === "draft"}
            onViewSnapshot={loadVersionSnapshot}
            onCompare={(major1, minor1, major2, minor2) => setCompareState({ major1, minor1, major2, minor2 })}
            onRollback={(major, minor) => setRollbackTarget({ major_no: major, minor_no: minor })}
            onCreateVersion={() => setCreateVersionOpen(true)}
          />
        )},
      ]} />

      {!isNew && id && !isViewingVersion && (
        <div style={{ marginTop: 16 }}>
          <ValidationPanel cpId={id} />
        </div>
      )}

      {!isNew && id && (
        <>
          <CreateVersionModal
            open={createVersionOpen}
            documentId={id}
            documentType="cp"
            onClose={() => setCreateVersionOpen(false)}
            onSuccess={() => setCreateVersionOpen(false)}
          />
          <RollbackConfirmModal
            open={!!rollbackTarget}
            targetVersion={rollbackTarget}
            documentId={id}
            documentType="cp"
            onClose={() => setRollbackTarget(null)}
            onSuccess={() => setRollbackTarget(null)}
          />
          {compareState && (
            <Modal
              open={!!compareState}
              title={t("pageTitle.versionCompare")}
              width={900}
              footer={null}
              onCancel={() => setCompareState(null)}
            >
              <VersionCompareView
                documentId={id}
                documentType="cp"
                major1={compareState.major1}
                minor1={compareState.minor1}
                major2={compareState.major2}
                minor2={compareState.minor2}
              />
            </Modal>
          )}
          <SyncPreviewDrawer
            open={syncDrawerOpen}
            cpId={id}
            onClose={() => setSyncDrawerOpen(false)}
            onSuccess={async () => {
              setSyncDrawerOpen(false);
              if (!id) return;
              try {
                const refreshed = await getControlPlan(id);
                setCp(refreshed);
              } catch { /* silent */ }
            }}
          />

          <ConflictResolutionModal
            visible={conflictVisible}
            conflictInfo={conflictInfo}
            diff={adaptCPDiffToGraphDiff(conflictDiff)}
            onRefresh={handleConflictRefresh}
            onForceSave={handleConflictForceSave}
          />

          <Modal
            title={t("csrModal.title")}
            open={csrSyncOpen}
            onOk={handleCsrSync}
            onCancel={() => { setCsrSyncOpen(false); setCsrCustomerIds([]); }}
            confirmLoading={csrSyncing}
            okButtonProps={{ disabled: csrCustomerIds.length === 0 }}
          >
            <Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
              {t("csrModal.description")}
            </Text>
            <Select
              mode="multiple"
              placeholder={t("csrModal.selectCustomers")}
              style={{ width: "100%" }}
              value={csrCustomerIds}
              onChange={setCsrCustomerIds}
              options={csrCustomers.map((c) => ({ value: c.customer_id, label: c.name }))}
              filterOption={(input, option) => (option?.label as string)?.toLowerCase().includes(input.toLowerCase())}
            />
            {cp?.customer_requirements && cp.customer_requirements.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <Text type="secondary">{t("csrModal.currentRequirements", { count: cp.customer_requirements.length })}</Text>
              </div>
            )}
          </Modal>
        </>
      )}
    </PageShell>
  );
}

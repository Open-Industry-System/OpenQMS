import { useEffect, useRef, useState } from "react";
import { Alert, Button, Drawer, Space, Spin, Table, Tag, message } from "antd";
import { useTranslation } from "react-i18next";
import { applySyncFromFMEA, getSyncPreview } from "../../api/version";
import type { SyncPreviewItem, SyncPreviewResponse } from "../../types";

interface SyncPreviewDrawerProps {
  open: boolean;
  cpId: string;
  sourceFmeaVersionId?: string;
  onClose: () => void;
  onSuccess: () => void | Promise<void>;
}

function isConflict(error: unknown): boolean {
  return typeof error === "object" && error !== null
    && "response" in error
    && (error as { response?: { status?: number } }).response?.status === 409;
}

function hasBlockingIssue(item: SyncPreviewItem): boolean {
  return !item.applicable || item.conflicts.length > 0;
}

function isBlockingIssue(issue: { blocking?: unknown }): boolean {
  return issue.blocking === true;
}

export default function SyncPreviewDrawer({
  open,
  cpId,
  sourceFmeaVersionId,
  onClose,
  onSuccess,
}: SyncPreviewDrawerProps) {
  const { t } = useTranslation("version");
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<SyncPreviewResponse | null>(null);
  const [selectedCandidateKeys, setSelectedCandidateKeys] = useState<React.Key[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [expired, setExpired] = useState(false);
  const [pendingCount, setPendingCount] = useState<number | null>(null);
  const [refreshFailed, setRefreshFailed] = useState(false);
  const contextRef = useRef(0);
  const operationRef = useRef(0);

  const invalidatePreview = () => {
    contextRef.current += 1;
    operationRef.current += 1;
    setPreview(null);
    setSelectedCandidateKeys([]);
    setSyncing(false);
  };

  const close = () => {
    invalidatePreview();
    onClose();
  };

  const load = async () => {
    const request = ++contextRef.current;
    operationRef.current += 1;
    setSyncing(false);
    setLoading(true);
    setPreview(null);
    setSelectedCandidateKeys([]);
    setExpired(false);
    setPendingCount(null);
    setRefreshFailed(false);
    try {
      const response = await getSyncPreview(cpId, sourceFmeaVersionId);
      if (request !== contextRef.current) return;
      setPreview(response);
      setSelectedCandidateKeys(response.items
        .filter((item) => item.action !== "delete" && !hasBlockingIssue(item))
        .map((item) => item.candidate_key));
    } catch {
      if (request === contextRef.current) message.error(t("syncPreview.loadFailed"));
    } finally {
      if (request === contextRef.current) setLoading(false);
    }
  };

  useEffect(() => {
    if (!open) {
      invalidatePreview();
      return;
    }
    void load();
    return () => { contextRef.current += 1; };
  // Loading must restart for the CP or selected approved FMEA snapshot, never reuse a prior preview.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, cpId, sourceFmeaVersionId]);

  const handleSync = async () => {
    if (!preview || syncing) return;
    const isNoop = preview.items.length === 0 && !preview.issues.some(isBlockingIssue);
    if (!selectedCandidateKeys.length && !isNoop) {
      message.warning(t("syncPreview.selectAtLeastOne"));
      return;
    }
    const operation = ++operationRef.current;
    const context = contextRef.current;
    const selectedKeys = selectedCandidateKeys as string[];
    const remainingCount = preview.items.filter((item) => !selectedKeys.includes(item.candidate_key)).length;
    setSyncing(true);
    try {
      await applySyncFromFMEA(cpId, {
        source_fmea_version_id: preview.source_fmea_version_id,
        expected_lock_version: preview.expected_lock_version,
        preview_digest: preview.preview_digest,
        selected_candidate_keys: selectedKeys,
      });
      if (operation !== operationRef.current || context !== contextRef.current) return;
      try {
        await onSuccess();
      } catch {
        if (operation === operationRef.current && context === contextRef.current) {
          setSyncing(false);
          if (remainingCount > 0) setPendingCount(remainingCount);
          setRefreshFailed(true);
          invalidatePreview();
          setExpired(true);
        }
        return;
      }
      if (operation !== operationRef.current || context !== contextRef.current) return;
      message.success(t("syncPreview.syncSuccess"));
      setSyncing(false);
      if (remainingCount > 0) {
        setPendingCount(remainingCount);
        invalidatePreview();
        setExpired(true);
      } else {
        close();
      }
    } catch (error) {
      if (operation !== operationRef.current || context !== contextRef.current) return;
      setSyncing(false);
      if (isConflict(error)) {
        invalidatePreview();
        setExpired(true);
      } else {
        message.error(t("syncPreview.syncFailed"));
      }
    } finally {
      if (operation === operationRef.current && context === contextRef.current) setSyncing(false);
    }
  };

  const getActionConfig = (action: string) => {
    switch (action) {
      case "add": return { label: t("syncPreview.actions.add"), color: "green" };
      case "sync": return { label: t("syncPreview.actions.sync"), color: "blue" };
      case "delete": return { label: t("syncPreview.actions.delete"), color: "red" };
      default: return { label: action, color: "default" };
    }
  };

  const formatDictValue = (value: Record<string, string | null> | null) => {
    if (!value) return <span style={{ color: "#999" }}>{t("syncPreview.none")}</span>;
    const entries = Object.entries(value).filter(([, entryValue]) => entryValue !== null && entryValue !== "");
    if (!entries.length) return <span style={{ color: "#999" }}>{t("syncPreview.none")}</span>;
    return <div style={{ fontSize: 12, lineHeight: 1.6 }}>{entries.map(([key, entryValue]) => <div key={key}>{key}: {entryValue}</div>)}</div>;
  };

  const isNoop = preview?.items.length === 0 && !preview.issues.some(isBlockingIssue);
  return (
    <Drawer
      open={open}
      title={t("syncPreview.title")}
      width={960}
      onClose={close}
      footer={<Space style={{ width: "100%", justifyContent: "flex-end" }}>
        <Button onClick={close}>{t("syncPreview.cancel")}</Button>
        {expired ? <Button type="primary" onClick={() => void load()}>{t("syncPreview.previewAgain")}</Button> : (
          <Button type="primary" onClick={handleSync} loading={syncing} disabled={syncing || !preview || (!isNoop && selectedCandidateKeys.length === 0)}>
            {isNoop ? t("syncPreview.confirmNoChanges") : t("syncPreview.confirmSync")}
          </Button>
        )}
      </Space>}
    >
      {expired && <Alert type="error" showIcon message={t("syncPreview.previewExpired")} style={{ marginBottom: 16 }} />}
      {pendingCount !== null && <Alert type="info" showIcon message={t("syncPreview.partialPending", { count: pendingCount })} style={{ marginBottom: 16 }} />}
      {refreshFailed && <Alert type="warning" showIcon message={t("syncPreview.refreshFailedAfterSync")} style={{ marginBottom: 16 }} />}
      {loading ? <div style={{ textAlign: "center", padding: 40 }}><Spin /></div> : preview ? <>
        <Alert
          message={t("syncPreview.source")}
          description={<div><p>{t("syncPreview.fmeaVersion", { version: preview.fmea_version })}</p><p style={{ marginTop: 4 }}>{t("syncPreview.addCount", { count: preview.summary.add_count })}{t("syncPreview.updateCount", { count: preview.summary.update_count })}{t("syncPreview.deleteCount", { count: preview.summary.delete_count })}</p></div>}
          type="info" showIcon style={{ marginBottom: 16 }}
        />
        {preview.issues.map((issue, index) => <Alert key={`${issue.code}-${index}`} type="warning" showIcon message={issue.message} style={{ marginBottom: 8 }} />)}
        <Table
          dataSource={preview.items}
          columns={[
            { title: t("syncPreview.columns.action"), dataIndex: "action", key: "action", width: 80, render: (action: string) => { const config = getActionConfig(action); return <Tag color={config.color}>{config.label}</Tag>; } },
            { title: t("syncPreview.columns.stepNo"), dataIndex: "step_no", key: "step_no", width: 100 },
            { title: t("syncPreview.columns.currentValue"), dataIndex: "current_value", key: "current_value", width: 180, render: formatDictValue },
            { title: t("syncPreview.columns.fmeaNewValue"), dataIndex: "fmea_new_value", key: "fmea_new_value", width: 180, render: formatDictValue },
            { title: t("syncPreview.columns.mergedValue"), dataIndex: "merged_value", key: "merged_value", width: 180, render: formatDictValue },
            { title: t("syncPreview.columns.issues"), key: "issues", width: 180, render: (_, item: SyncPreviewItem) => [...item.issues, ...item.conflicts].map((issue) => issue.message).join("；") || "-" },
          ]}
          rowKey="candidate_key"
          size="small"
          pagination={false}
          rowSelection={{
            selectedRowKeys: selectedCandidateKeys,
            onChange: (keys) => {
              if (syncing) return;
              operationRef.current += 1;
              setSelectedCandidateKeys(keys);
            },
            getCheckboxProps: (item: SyncPreviewItem) => ({ disabled: syncing || hasBlockingIssue(item) }),
          }}
        />
      </> : <div style={{ textAlign: "center", padding: 40 }}>{t("syncPreview.loadPreviewFailed")}</div>}
    </Drawer>
  );
}

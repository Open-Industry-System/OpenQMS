import { useEffect, useRef, useState } from "react";
import { Alert, App, Button, Modal, Select, Space, Table } from "antd";
import type { TableRowSelection } from "antd/es/table/interface";
import { useTranslation } from "react-i18next";
import { listFMEAs } from "../../api/fmea";
import { applyImportFromFMEA, previewImportFromFMEA } from "../../api/controlPlan";
import { getFMEAVersion, listFMEAVersions } from "../../api/version";
import type {
  CharacteristicImportCandidate,
  CharacteristicImportPreview,
  FMEADocument,
  FMEAVersion,
  GraphNode,
} from "../../types";

interface Props {
  cpId: string;
  expectedLockVersion: number | null;
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

interface StepRow {
  key: string;
  process_number: string;
  name: string;
}

function isApprovedSnapshot(version: FMEAVersion): boolean {
  return version.change_type === "approve" && version.major_no >= 1 && version.minor_no === 0;
}

function isConflict(error: unknown): boolean {
  return typeof error === "object" && error !== null
    && "response" in error
    && (error as { response?: { status?: number } }).response?.status === 409;
}

export default function ImportFromFMEAModal({
  cpId,
  expectedLockVersion,
  open,
  onClose,
  onSuccess,
}: Props) {
  const { t } = useTranslation("controlPlan");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const [fmeas, setFmeas] = useState<FMEADocument[]>([]);
  const [versions, setVersions] = useState<FMEAVersion[]>([]);
  const [selectedFmeaId, setSelectedFmeaId] = useState<string | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<FMEAVersion | null>(null);
  const [steps, setSteps] = useState<StepRow[]>([]);
  const [selectedStepKeys, setSelectedStepKeys] = useState<React.Key[]>([]);
  const [preview, setPreview] = useState<CharacteristicImportPreview | null>(null);
  const [selectedCandidateKeys, setSelectedCandidateKeys] = useState<React.Key[]>([]);
  const [loadingFmeas, setLoadingFmeas] = useState(false);
  const [loadingVersions, setLoadingVersions] = useState(false);
  const [loadingSteps, setLoadingSteps] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [partialPending, setPartialPending] = useState<number | null>(null);
  const contextRef = useRef(0);
  const operationRef = useRef(0);
  const lockVersionRef = useRef(expectedLockVersion);

  // The current CP changes when either its identity or server lock changes; neither may retain a preview.
  useEffect(() => {
    if (lockVersionRef.current === expectedLockVersion) return;
    lockVersionRef.current = expectedLockVersion;
    contextRef.current += 1;
    operationRef.current += 1;
    setPreview(null);
    setSelectedCandidateKeys([]);
  }, [expectedLockVersion]);

  const invalidatePreview = () => {
    contextRef.current += 1;
    operationRef.current += 1;
    setPreview(null);
    setSelectedCandidateKeys([]);
    setImporting(false);
    setPreviewing(false);
  };

  const close = () => {
    invalidatePreview();
    onClose();
  };

  useEffect(() => {
    if (!open) return;
    const request = ++contextRef.current;
    setSelectedFmeaId(null);
    setSelectedVersion(null);
    setVersions([]);
    setSteps([]);
    setSelectedStepKeys([]);
    setPreview(null);
    setSelectedCandidateKeys([]);
    setPartialPending(null);
    setLoadingFmeas(true);

    listFMEAs({ page_size: 100 })
      .then((resp) => {
        if (request === contextRef.current) {
          setFmeas(resp.items.filter((f) => f.fmea_type === "PFMEA"));
        }
      })
      .catch(() => {
        if (request === contextRef.current) message.error(t("importModal.loadFailed"));
      })
      .finally(() => {
        if (request === contextRef.current) setLoadingFmeas(false);
      });

    return () => { contextRef.current += 1; };
  // Modal context is reset when it opens or points at a different CP; t/message identity changes must not erase a selection.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, cpId]);

  useEffect(() => {
    if (!open || !selectedFmeaId) return;
    const request = ++contextRef.current;
    setLoadingVersions(true);
    setVersions([]);
    setSelectedVersion(null);
    setSteps([]);
    setSelectedStepKeys([]);
    setPreview(null);
    setSelectedCandidateKeys([]);

    listFMEAVersions(selectedFmeaId, { page_size: 100 })
      .then((resp) => {
        if (request === contextRef.current) {
          setVersions(resp.items.filter(isApprovedSnapshot));
        }
      })
      .catch(() => {
        if (request === contextRef.current) message.error(t("importModal.loadVersionsFailed"));
      })
      .finally(() => {
        if (request === contextRef.current) setLoadingVersions(false);
      });
  }, [open, selectedFmeaId, t, message]);

  useEffect(() => {
    if (!open || !selectedFmeaId || !selectedVersion) return;
    const request = ++contextRef.current;
    setLoadingSteps(true);
    setSteps([]);
    setSelectedStepKeys([]);
    setPreview(null);
    setSelectedCandidateKeys([]);

    getFMEAVersion(selectedFmeaId, selectedVersion.major_no, selectedVersion.minor_no)
      .then((detail) => {
        if (request !== contextRef.current) return;
        const snapshotSteps: StepRow[] = (detail.snapshot.nodes || [])
          .filter((node: GraphNode) => node.type === "ProcessStep")
          .map((node: GraphNode) => ({
            key: node.id,
            process_number: node.process_number || "",
            name: node.name,
          }));
        setSteps(snapshotSteps);
        setSelectedStepKeys(snapshotSteps.map((step) => step.key));
      })
      .catch(() => {
        if (request === contextRef.current) message.error(t("importModal.loadSnapshotFailed"));
      })
      .finally(() => {
        if (request === contextRef.current) setLoadingSteps(false);
      });
  }, [open, selectedFmeaId, selectedVersion, t, message]);

  const handleSelectFMEA = (fmeaId: string) => {
    invalidatePreview();
    setPartialPending(null);
    setSelectedFmeaId(fmeaId);
  };

  const handleSelectVersion = (versionId: string) => {
    invalidatePreview();
    setPartialPending(null);
    setSelectedVersion(versions.find((version) => version.version_id === versionId) || null);
  };

  const handlePreview = async () => {
    if (!selectedFmeaId || !selectedVersion || expectedLockVersion === null) {
      message.warning(t("importModal.selectVersionFirst"));
      return;
    }
    const request = ++contextRef.current;
    setPreviewing(true);
    setPreview(null);
    setSelectedCandidateKeys([]);
    try {
      const result = await previewImportFromFMEA(cpId, {
        fmea_id: selectedFmeaId,
        source_fmea_version_id: selectedVersion.version_id,
        expected_lock_version: expectedLockVersion,
        step_ids: steps.filter((step) => selectedStepKeys.includes(step.key)).map((step) => step.key),
      });
      if (request !== contextRef.current) return;
      setPreview(result);
      setSelectedCandidateKeys(result.items.filter((candidate) => !candidateHasBlockingIssue(candidate, result)).map((candidate) => candidate.candidate_key));
    } catch (error) {
      if (request === contextRef.current) message.error(error instanceof Error ? error.message : t("importModal.previewFailed"));
    } finally {
      if (request === contextRef.current) setPreviewing(false);
    }
  };

  const handleConfirm = async () => {
    if (!preview || !selectedFmeaId || !selectedVersion || expectedLockVersion === null || importing) return;
    if (preview.issues.some((issue) => issue.blocking)) {
      message.warning(t("importModal.previewBlocked"));
      return;
    }
    const operation = ++operationRef.current;
    const context = contextRef.current;
    setImporting(true);
    try {
      await applyImportFromFMEA(cpId, {
        fmea_id: selectedFmeaId,
        source_fmea_version_id: selectedVersion.version_id,
        expected_lock_version: preview.expected_lock_version,
        step_ids: steps.filter((step) => selectedStepKeys.includes(step.key)).map((step) => step.key),
        preview_digest: preview.preview_digest,
        selected_candidate_keys: selectedCandidateKeys as string[],
      });
      if (operation !== operationRef.current || context !== contextRef.current) return;
      const pending = preview.items.length - selectedCandidateKeys.length;
      message.success(t("importModal.importSuccess"));
      onSuccess();
      if (pending > 0) {
        setPartialPending(pending);
        invalidatePreview();
      } else {
        close();
      }
    } catch (error) {
      if (operation !== operationRef.current || context !== contextRef.current) return;
      if (isConflict(error)) {
        invalidatePreview();
        message.error(t("importModal.previewExpired"));
      } else {
        message.error(t("importModal.importFailed"));
      }
    } finally {
      if (operation === operationRef.current && context === contextRef.current) setImporting(false);
    }
  };

  const stepSelection: TableRowSelection<StepRow> = {
    selectedRowKeys: selectedStepKeys,
    onChange: (keys) => {
      if (importing) return;
      invalidatePreview();
      setSelectedStepKeys(keys);
    },
    getCheckboxProps: () => ({ disabled: importing }),
  };

  const previewBlocked = preview?.issues.some((issue) => issue.blocking) ?? false;
  const candidateSelection: TableRowSelection<CharacteristicImportCandidate> | undefined = preview ? {
    selectedRowKeys: selectedCandidateKeys,
    onChange: (keys) => {
      if (importing) return;
      operationRef.current += 1;
      setSelectedCandidateKeys(keys);
    },
    getCheckboxProps: (candidate) => ({ disabled: importing || candidateHasBlockingIssue(candidate, preview) }),
  } : undefined;

  const selectedFmea = fmeas.find((fmea) => fmea.fmea_id === selectedFmeaId);
  return (
    <Modal
      title={t("importModal.title")}
      open={open}
      onCancel={close}
      width={900}
      footer={<Space><Button onClick={close}>{tc("actions.cancel")}</Button>{preview ? (
        <Button type="primary" loading={importing} onClick={handleConfirm} disabled={importing || previewBlocked || selectedCandidateKeys.length === 0}>{t("importModal.confirmImport")}</Button>
      ) : (
        <Button type="primary" loading={previewing} onClick={handlePreview} disabled={importing || !selectedVersion || loadingSteps}>{t("importModal.preview")}</Button>
      )}</Space>}
    >
      {partialPending !== null && <Alert type="info" showIcon message={t("importModal.partialPending", { count: partialPending })} style={{ marginBottom: 16 }} />}
      {previewBlocked && <Alert type="error" showIcon message={t("importModal.previewBlocked")} style={{ marginBottom: 16 }} />}
      <Space direction="vertical" style={{ width: "100%" }} size="middle">
        <Select style={{ width: "100%" }} placeholder={t("importModal.selectPFMEA")} loading={loadingFmeas} disabled={importing} value={selectedFmeaId} onChange={handleSelectFMEA}
          options={fmeas.map((fmea) => ({ value: fmea.fmea_id, label: `${fmea.document_no} - ${fmea.title}` }))} />
        {selectedFmeaId && <Select style={{ width: "100%" }} placeholder={t("importModal.selectApprovedVersion")} loading={loadingVersions} disabled={importing} value={selectedVersion?.version_id} onChange={handleSelectVersion}
          options={versions.map((version) => ({ value: version.version_id, label: `v${version.major_no}.${version.minor_no}` }))} notFoundContent={loadingVersions ? undefined : t("importModal.noApprovedVersion")} />}
        {selectedFmea && selectedVersion && <Alert type="info" showIcon message={t("importModal.sourceSnapshot", { document: selectedFmea.document_no, version: `v${selectedVersion.major_no}.${selectedVersion.minor_no}` })} />}
        {steps.length > 0 && <Table rowSelection={stepSelection} columns={[
          { title: t("importModal.processNo"), dataIndex: "process_number", key: "process_number" },
          { title: t("importModal.processName"), dataIndex: "name", key: "name" },
        ]} dataSource={steps} pagination={false} size="small" loading={loadingSteps} rowKey="key" />}
        {preview && <>
          {preview.issues.map((issue) => <Alert key={`${issue.code}-${issue.node_id}`} type={issue.blocking ? "warning" : "info"} showIcon message={issue.message} style={{ marginBottom: 8 }} />)}
          <Table rowSelection={candidateSelection} columns={[
            { title: t("importModal.candidateAction"), dataIndex: "action", key: "action" },
            { title: t("importModal.processNo"), key: "step_no", render: (_, candidate) => candidate.fields.step_no || "-" },
            { title: t("importModal.productCharacteristic"), key: "product", render: (_, candidate) => candidate.fields.product_characteristic || "-" },
            { title: t("importModal.processCharacteristic"), key: "process", render: (_, candidate) => candidate.fields.process_characteristic || "-" },
          ]} dataSource={preview.items} pagination={false} size="small" rowKey="candidate_key" />
        </>}
      </Space>
    </Modal>
  );
}

function candidateHasBlockingIssue(candidate: CharacteristicImportCandidate, preview: CharacteristicImportPreview): boolean {
  const refs = [candidate.source_ref.step_id, candidate.source_ref.function_id, candidate.source_ref.work_element_id, candidate.source_ref.characteristic_id];
  return preview.issues.some((issue) => issue.blocking && refs.includes(issue.node_id));
}

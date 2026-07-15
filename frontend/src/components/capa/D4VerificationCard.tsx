import { useEffect, useState } from "react";
import { Card, List, Tag, Button, Form, Input, Space, App, Empty, Spin, Upload, Select } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { listVerifications, createVerification, updateVerification } from "../../api/capa";
import { getFMEA } from "../../api/fmea";
import type { Verification, VerificationConclusion } from "../../types";

const { Option } = Select;

interface Props {
  capaId: string;
  canEdit: boolean;
  currentRootCause: string | null;
  fmeaRefId: string | null;
}

interface CauseOption {
  id: string;
  name: string;
}

export default function D4VerificationCard({ capaId, canEdit, currentRootCause, fmeaRefId }: Props) {
  const { t } = useTranslation("capa");
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [items, setItems] = useState<Verification[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form] = Form.useForm();
  const [causeOptions, setCauseOptions] = useState<CauseOption[]>([]);
  const [selectedCause, setSelectedCause] = useState<string | undefined>(undefined);
  // Per-row Cause edit: verification_id currently being edited, value is node id or undefined (clear).
  const [editingCauseVid, setEditingCauseVid] = useState<string | null>(null);
  const [editCauseValue, setEditCauseValue] = useState<string | undefined>(undefined);

  const reload = async () => {
    setLoading(true);
    try { setItems(await listVerifications(capaId)); } catch { message.error(t("d4.verificationLoadFailed")); }
    finally { setLoading(false); }
  };
  useEffect(() => { reload(); /* eslint-disable-line react-hooks/exhaustive-deps */ }, [capaId]);

  useEffect(() => {
    if (!fmeaRefId) {
      setCauseOptions([]);
      return;
    }
    getFMEA(fmeaRefId)
      .then((doc) => {
        const nodes = doc.graph_data?.nodes ?? [];
        setCauseOptions(
          nodes
            .filter((n: { type?: string }) => n.type === "FailureCause")
            .map((n: { id: string; name?: string }) => ({ id: n.id, name: n.name || n.id }))
        );
      })
      .catch(() => setCauseOptions([]));
  }, [fmeaRefId]);

  const hasAtLeastOneDetail = (v: any): boolean =>
    !!((v.method && String(v.method).trim()) || (v.result && String(v.result).trim()) || ((v.evidence || []).length > 0));

  const submitCreate = async (conclusion: VerificationConclusion, requireDetail: boolean) => {
    const values = form.getFieldsValue();
    if (requireDetail && !hasAtLeastOneDetail(values)) {
      message.error(t("d4.needAtLeastOneDetail"));
      return;
    }
    const evidence = (values.evidence || []).map((f: any) => ({ filename: f.name, size: f.size }));
    const source_ref =
      fmeaRefId && selectedCause
        ? { fmea_id: fmeaRefId, cause_node_id: selectedCause }
        : null;
    try {
      await createVerification(capaId, {
        root_cause_text: values.root_cause_text ?? currentRootCause ?? "",
        method: values.method,
        result: values.result,
        conclusion,
        evidence_attachments: evidence,
        source_ref,
      });
      message.success(t("d4.verificationSaved"));
      form.resetFields();
      setSelectedCause(undefined);
      setShowForm(false);
      reload();
    } catch (e: any) {
      message.error(e.response?.data?.detail?.[0]?.msg ?? t("d4.verificationFailed"));
    }
  };

  const patchConclusion = async (rec: Verification, conclusion: VerificationConclusion) => {
    try {
      await updateVerification(capaId, rec.verification_id, { conclusion });
      message.success(t("d4.verificationSaved")); reload();
    } catch (e: any) {
      message.error(e.response?.data?.detail?.[0]?.msg ?? t("d4.verificationFailed"));
    }
  };

  const startEditCause = (rec: Verification) => {
    const sourceRef =
      rec.source_ref && typeof rec.source_ref === "object"
        ? (rec.source_ref as { cause_node_id?: string })
        : undefined;
    setEditingCauseVid(rec.verification_id);
    setEditCauseValue(sourceRef?.cause_node_id);
  };

  const cancelEditCause = () => {
    setEditingCauseVid(null);
    setEditCauseValue(undefined);
  };

  const saveEditCause = async (rec: Verification) => {
    // allowClear → undefined means clear Cause (source_ref: null).
    const source_ref =
      fmeaRefId && editCauseValue
        ? { fmea_id: fmeaRefId, cause_node_id: editCauseValue }
        : null;
    try {
      await updateVerification(capaId, rec.verification_id, { source_ref });
      message.success(t("d4.verificationSaved"));
      cancelEditCause();
      reload();
    } catch (e: any) {
      message.error(e.response?.data?.detail?.[0]?.msg ?? t("d4.verificationFailed"));
    }
  };

  return (
    <Card size="small" title={t("d4.verificationTitle")} data-e2e="d4-verification-card" style={{ marginTop: 16 }}>
      {loading ? <Spin size="small" /> : items.length === 0 && !showForm ? (
        <Empty description={t("d4.noVerification")} image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <List size="small" dataSource={items} renderItem={(rec, i) => {
          const sourceRef =
            rec.source_ref && typeof rec.source_ref === "object"
              ? (rec.source_ref as { fmea_id?: string; cause_node_id?: string })
              : undefined;
          const causeNodeId = sourceRef?.cause_node_id;
          const causeFmeaId = sourceRef?.fmea_id ?? fmeaRefId;
          const isEditingCause = editingCauseVid === rec.verification_id;
          return (
            <List.Item data-e2e={`verification-item-${i}`}>
              <Space direction="vertical" size={2} style={{ width: "100%" }}>
                <Space wrap>
                  <Tag data-e2e={`verification-conclusion-${i}`} color={
                    rec.conclusion === "passed" ? "green" : rec.conclusion === "failed" ? "red" : "default"}>
                    {rec.conclusion === "passed" ? `✅ ${t("verification.conclusion.passed")}`
                      : rec.conclusion === "failed" ? `❌ ${t("verification.conclusion.failed")}`
                      : `⏳ ${t("verification.conclusion.draft")}`}
                  </Tag>
                  <span>{rec.root_cause_text}</span>
                  {causeNodeId && causeFmeaId && !isEditingCause && (
                    <Tag
                      color="blue"
                      data-e2e="d4-cause-link"
                      style={{ cursor: "pointer" }}
                      onClick={() =>
                        navigate(`/fmea/${causeFmeaId}?tab=graph&highlightNode=${causeNodeId}`)
                      }
                    >
                      {t("d4.cause", "FMEA Cause")}
                    </Tag>
                  )}
                </Space>
                {rec.method && <span style={{ fontSize: 12 }}>{t("d4.method")}: {t(`verification.method.${rec.method}`)}</span>}
                {rec.result && <span style={{ fontSize: 12 }}>{t("d4.result")}: {rec.result}</span>}
                {rec.evidence_attachments?.length > 0 && (
                  <span style={{ fontSize: 12 }}>{t("d4.evidence")}: {rec.evidence_attachments.map((e: any) => e.filename).join(", ")}</span>
                )}
                {canEdit && rec.conclusion === "pending" && (
                  <Space>
                    <Button size="small" data-e2e={`verify-pass-${i}`}
                      onClick={() => patchConclusion(rec, "passed")}>{t("verification.conclusion.passed")}</Button>
                    <Button size="small" data-e2e={`verify-fail-${i}`}
                      onClick={() => patchConclusion(rec, "failed")}>{t("verification.conclusion.failed")}</Button>
                  </Space>
                )}
                {canEdit && isEditingCause && (
                  <Space data-e2e={`d4-cause-edit-${i}`} wrap>
                    <Select
                      size="small"
                      style={{ minWidth: 180 }}
                      allowClear
                      placeholder={
                        fmeaRefId
                          ? t("d4.selectCause", "选择失效原因")
                          : t("d4.linkFmeaFirst", "请先关联 FMEA")
                      }
                      disabled={!fmeaRefId}
                      value={editCauseValue}
                      onChange={(v) => setEditCauseValue(v)}
                      data-e2e={`d4-cause-edit-select-${i}`}
                    >
                      {causeOptions.map((c) => (
                        <Option key={c.id} value={c.id}>{c.name}</Option>
                      ))}
                    </Select>
                    <Button size="small" type="primary" data-e2e={`d4-cause-save-${i}`}
                      onClick={() => saveEditCause(rec)}>{t("d4.saveCause", "保存 Cause")}</Button>
                    <Button size="small" data-e2e={`d4-cause-clear-${i}`}
                      onClick={() => setEditCauseValue(undefined)}
                      disabled={!editCauseValue}>
                      {t("d4.clearCause", "清空")}
                    </Button>
                    <Button size="small" data-e2e={`d4-cause-cancel-${i}`}
                      onClick={cancelEditCause}>{t("d4.cancel")}</Button>
                  </Space>
                )}
                {canEdit && !isEditingCause && (
                  <Button
                    size="small"
                    type="link"
                    data-e2e={`d4-cause-edit-btn-${i}`}
                    onClick={() => startEditCause(rec)}
                    style={{ padding: 0, height: "auto" }}
                  >
                    {causeNodeId
                      ? t("d4.editCause", "修改 Cause")
                      : t("d4.setCause", "关联 Cause")}
                  </Button>
                )}
              </Space>
            </List.Item>
          );
        }} />
      )}
      {canEdit && !showForm && (
        <Button data-e2e="d4-verification-new" icon={<PlusOutlined />} size="small"
          onClick={() => {
            form.setFieldsValue({ root_cause_text: currentRootCause ?? "" });
            setSelectedCause(undefined);
            setShowForm(true);
          }}>
          {t("d4.newVerification")}
        </Button>
      )}
      {showForm && (
        <Form form={form} layout="vertical" size="small" style={{ marginTop: 12 }}>
          <Form.Item name="root_cause_text" label={t("d4.rootCause")} data-e2e="verification-root-cause">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="method" label={t("d4.method")} data-e2e="verification-method">
            <Select placeholder={t("d4.method")}>
              <Option value="measurement">{t("verification.method.measurement")}</Option>
              <Option value="observation">{t("verification.method.observation")}</Option>
              <Option value="reproduction">{t("verification.method.reproduction")}</Option>
            </Select>
          </Form.Item>
          <Form.Item name="result" label={t("d4.result")} data-e2e="verification-result">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="evidence" label={t("d4.evidence")} data-e2e="verification-evidence"
            valuePropName="fileList" getValueFromEvent={(e) => Array.isArray(e) ? e : e?.fileList ?? []}>
            <Upload beforeUpload={() => false} multiple>
              <Button size="small">{t("d4.addEvidence")}</Button>
            </Upload>
          </Form.Item>
          <Form.Item name="cause_node_id" label={t("d4.cause", "FMEA Cause")} data-e2e="d4-cause-select">
            <Select
              allowClear
              placeholder={
                fmeaRefId
                  ? t("d4.selectCause", "选择失效原因")
                  : t("d4.linkFmeaFirst", "请先关联 FMEA")
              }
              disabled={!fmeaRefId}
              onChange={(v) => setSelectedCause(v)}
            >
              {causeOptions.map((c) => (
                <Option key={c.id} value={c.id}>{c.name}</Option>
              ))}
            </Select>
          </Form.Item>
          <Space>
            <Button data-e2e="verify-pass" onClick={() => submitCreate("passed", true)}>{t("verification.conclusion.passed")}</Button>
            <Button data-e2e="verify-fail" onClick={() => submitCreate("failed", false)}>{t("verification.conclusion.failed")}</Button>
            <Button data-e2e="verify-save-draft" onClick={() => submitCreate("pending", false)}>{t("verification.conclusion.saveDraft")}</Button>
            <Button onClick={() => setShowForm(false)}>{t("d4.cancel")}</Button>
          </Space>
        </Form>
      )}
    </Card>
  );
}

import { useEffect, useState } from "react";
import { Card, List, Tag, Button, Form, Input, Space, App, Empty, Spin, Upload, Select } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { listVerifications, createVerification, updateVerification } from "../../api/capa";
import type { Verification, VerificationConclusion } from "../../types";

const { Option } = Select;

interface Props { capaId: string; canEdit: boolean; currentRootCause: string | null; }

export default function D4VerificationCard({ capaId, canEdit, currentRootCause }: Props) {
  const { t } = useTranslation("capa");
  const { message } = App.useApp();
  const [items, setItems] = useState<Verification[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form] = Form.useForm();

  const reload = async () => {
    setLoading(true);
    try { setItems(await listVerifications(capaId)); } catch { message.error(t("d4.verificationLoadFailed")); }
    finally { setLoading(false); }
  };
  useEffect(() => { reload(); /* eslint-disable-line react-hooks/exhaustive-deps */ }, [capaId]);

  const hasAtLeastOneDetail = (v: any): boolean =>
    !!((v.method && String(v.method).trim()) || (v.result && String(v.result).trim()) || ((v.evidence || []).length > 0));

  const submitCreate = async (conclusion: VerificationConclusion, requireDetail: boolean) => {
    const values = form.getFieldsValue();
    if (requireDetail && !hasAtLeastOneDetail(values)) {
      message.error(t("d4.needAtLeastOneDetail"));
      return;
    }
    const evidence = (values.evidence || []).map((f: any) => ({ filename: f.name, size: f.size }));
    try {
      await createVerification(capaId, {
        root_cause_text: values.root_cause_text ?? currentRootCause ?? "",
        method: values.method,
        result: values.result,
        conclusion,
        evidence_attachments: evidence,
      });
      message.success(t("d4.verificationSaved"));
      form.resetFields(); setShowForm(false); reload();
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

  return (
    <Card size="small" title={t("d4.verificationTitle")} data-e2e="d4-verification-card" style={{ marginTop: 16 }}>
      {loading ? <Spin size="small" /> : items.length === 0 && !showForm ? (
        <Empty description={t("d4.noVerification")} image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <List size="small" dataSource={items} renderItem={(rec, i) => (
          <List.Item data-e2e={`verification-item-${i}`}>
            <Space direction="vertical" size={2} style={{ width: "100%" }}>
              <Space>
                <Tag data-e2e={`verification-conclusion-${i}`} color={
                  rec.conclusion === "passed" ? "green" : rec.conclusion === "failed" ? "red" : "default"}>
                  {rec.conclusion === "passed" ? `✅ ${t("verification.conclusion.passed")}`
                    : rec.conclusion === "failed" ? `❌ ${t("verification.conclusion.failed")}`
                    : `⏳ ${t("verification.conclusion.draft")}`}
                </Tag>
                <span>{rec.root_cause_text}</span>
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
            </Space>
          </List.Item>
        )} />
      )}
      {canEdit && !showForm && (
        <Button data-e2e="d4-verification-new" icon={<PlusOutlined />} size="small"
          onClick={() => { form.setFieldsValue({ root_cause_text: currentRootCause ?? "" }); setShowForm(true); }}>
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

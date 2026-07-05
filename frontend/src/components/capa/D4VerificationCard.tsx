import { useEffect, useState } from "react";
import { Card, List, Tag, Button, Form, Input, Switch, Space, App, Empty, Spin, Upload } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { listVerifications, createVerification, updateVerification } from "../../api/capa";
import type { Verification } from "../../types";

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

  const submit = async (vals: any) => {
    const evidence = (vals.evidence || []).map((f: any) => ({ filename: f.name, size: f.size }));
    await createVerification(capaId, {
      root_cause_text: vals.root_cause_text ?? currentRootCause ?? "",
      method: vals.method, result: vals.result,
      is_verified: !!vals.is_verified, evidence_attachments: evidence,
    });
    message.success(t("d4.verificationSaved"));
    form.resetFields(); setShowForm(false); reload();
  };

  const toggleVerified = async (rec: Verification, checked: boolean) => {
    await updateVerification(capaId, rec.verification_id, { is_verified: checked });
    reload();
  };

  return (
    <Card size="small" title={t("d4.verificationTitle")} data-e2e="d4-verification-card" style={{ marginTop: 16 }}>
      {loading ? <Spin size="small" /> : items.length === 0 && !showForm ? (
        <Empty description={t("d4.noVerification")} image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <List size="small" dataSource={items} renderItem={(rec, i) => (
          <List.Item data-e2e={`verification-item-${i}`}>
            <Space direction="vertical" size={2} style={{ width: "100%" }}>
              <Space><Tag data-e2e="verification-status">
                {rec.is_verified ? `✅ ${t("d4.verified")}` : `⏳ ${t("d4.notVerified")}`}
              </Tag>
                <span>{rec.root_cause_text}</span></Space>
              {rec.method && <span style={{ fontSize: 12 }}>{t("d4.method")}: {rec.method}</span>}
              {rec.result && <span style={{ fontSize: 12 }}>{t("d4.result")}: {rec.result}</span>}
              {rec.evidence_attachments?.length > 0 && (
                <span style={{ fontSize: 12 }}>{t("d4.evidence")}: {rec.evidence_attachments.map((e: any) => e.filename).join(", ")}</span>
              )}
              <Space>
                <span style={{ fontSize: 12 }}>{t("d4.isVerified")}</span>
                <Switch data-e2e="verification-is-verified" disabled={!canEdit}
                  checked={rec.is_verified} onChange={(c) => toggleVerified(rec, c)} />
              </Space>
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
        <Form form={form} layout="vertical" size="small" onFinish={submit} style={{ marginTop: 12 }}>
          <Form.Item name="root_cause_text" label={t("d4.rootCause")} data-e2e="verification-root-cause">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="method" label={t("d4.method")} data-e2e="verification-method">
            <Input />
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
          <Form.Item name="is_verified" label={t("d4.isVerified")} valuePropName="checked">
            <Switch data-e2e="verification-form-is-verified" />
          </Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" data-e2e="verification-submit">{t("d4.save")}</Button>
            <Button onClick={() => setShowForm(false)}>{t("d4.cancel")}</Button>
          </Space>
        </Form>
      )}
    </Card>
  );
}

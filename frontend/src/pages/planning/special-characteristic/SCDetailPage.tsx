import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Button, Typography, Form, Input, Select, Switch, App,
  Spin, Row, Col, Descriptions, Space, Timeline, Collapse,
} from "antd";
import {
  ArrowLeftOutlined, SaveOutlined, LinkOutlined,
  SafetyCertificateOutlined, ExclamationCircleOutlined,
  CheckCircleOutlined, CloseCircleOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import {
  getSC, updateSC, createSC,
  safetySubmit, safetyApprove, safetyReject, safetyCancel,
} from "../../../api/specialCharacteristic";
import type { SpecialCharacteristic } from "../../../types";
import { useAuthStore } from "../../../store/authStore";
import { usePermission } from "../../../hooks/usePermission";
import { PageShell, DataCard, StatusBadge } from "../../../components/design";

const { Text } = Typography;
const { TextArea } = Input;

const scTypeVariant = (t: string): string => (t === "CC" ? "error" : "warning");
const sourceTypeVariant = (t: string): string => (t === "DFMEA" ? "info" : "success");
const msaStatusVariant = (s: string): string => {
  if (s === "PASS") return "success";
  if (s === "FAIL") return "error";
  return "warning";
};
const safetyStatusVariant = (s: string): string => {
  if (s === "approved") return "success";
  if (s === "rejected") return "error";
  if (s === "submitted") return "warning";
  return "info";
};

export default function SCDetailPage() {
  const { t } = useTranslation("specialCharacteristic");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [sc, setSc] = useState<SpecialCharacteristic | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();
  const [safetyForm] = Form.useForm();
  const [safetyPanelOpen, setSafetyPanelOpen] = useState(false);
  const [approvalLoading, setApprovalLoading] = useState(false);
  const isNew = id === "new";

  const _user = useAuthStore((s) => s.user);
  const { canEdit, canApprove } = usePermission();

  useEffect(() => {
    if (!id || isNew) { setLoading(false); return; }
    setLoading(true);
    getSC(id)
      .then((data) => {
        setSc(data);
        form.setFieldsValue({
          sc_name: data.sc_name,
          sc_category: data.sc_category,
          spec_requirement: data.spec_requirement,
          customer_symbol: data.customer_symbol,
          sop_ref: data.sop_ref,
          is_supplier_shared: data.is_supplier_shared,
          supplier_code: data.supplier_code,
        });
        safetyForm.setFieldsValue({
          safety_regulation_ref: data.safety_regulation_ref,
          safety_verification_method: data.safety_verification_method,
        });
        setSafetyPanelOpen(data.is_safety_related || data.is_safety_suggested);
      })
      .catch(() => message.error(t("message.loadFailed")))
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, isNew]);

  const handleSave = async (values: Partial<SpecialCharacteristic>) => {
    setSaving(true);
    try {
      if (isNew) {
        const created = await createSC(values);
        message.success(t("message.createSuccess"));
        navigate(`/special-characteristics/${created.sc_id}`, { replace: true });
      } else {
        if (!id) return;
        const updated = await updateSC(id, values);
        setSc(updated);
        message.success(t("message.saveSuccess"));
      }
    } catch {
      message.error(isNew ? t("message.createFailed") : t("message.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const handleSafetyToggle = async (checked: boolean) => {
    if (!sc || !id || isNew) return;
    if (!checked) {
      if (!canApprove('special_characteristic')) {
        message.error(t("message.adminOnlyCancel"));
        return;
      }
      try {
        const updated = await safetyCancel(id);
        setSc(updated);
        setSafetyPanelOpen(false);
        message.success(t("message.cancelSafetySuccess"));
      } catch {
        message.error(t("message.cancelFailed"));
      }
      return;
    }
    setSafetyPanelOpen(true);
    setSc({ ...sc, is_safety_related: true, safety_approval_status: "pending" });
  };

  const handleSafetySubmit = async (values: { safety_regulation_ref: string; safety_verification_method: string }) => {
    if (!id || isNew) return;
    setApprovalLoading(true);
    try {
      const updated = await safetySubmit(id, values);
      setSc(updated);
      message.success(t("message.safetySubmitted"));
    } catch (err: any) {
      message.error(err.response?.data?.detail || t("message.submitFailed"));
    } finally {
      setApprovalLoading(false);
    }
  };

  const handleSafetyApprove = async () => {
    if (!id || isNew || !canApprove('special_characteristic')) return;
    setApprovalLoading(true);
    try {
      const updated = await safetyApprove(id);
      setSc(updated);
      message.success(t("message.approved"));
    } catch {
      message.error(t("message.approveFailed"));
    } finally {
      setApprovalLoading(false);
    }
  };

  const handleSafetyReject = async () => {
    if (!id || isNew || !canApprove('special_characteristic')) return;
    setApprovalLoading(true);
    try {
      const updated = await safetyReject(id, t("action.reject"));
      setSc(updated);
      message.success(t("message.rejected"));
    } catch {
      message.error(t("message.rejectFailed"));
    } finally {
      setApprovalLoading(false);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!isNew && !sc) {
    return <div>{t("message.notFound")}</div>;
  }

  return (
    <PageShell
      title={
        isNew ? t("pageTitle.new") : (
          <Space size={12}>
            {`${sc!.sc_code} - ${sc!.sc_name}`}
            <StatusBadge status={scTypeVariant(sc!.sc_type)}>{sc!.sc_type}</StatusBadge>
          </Space>
        )
      }
      subtitle={isNew ? undefined : `${t("productLine")}：${sc!.product_line_code}`}
      actions={
        <Button
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate("/special-characteristics")}
        >
          {t("actions.backToList")}
        </Button>
      }
    >
      <Row gutter={16}>
        {/* Left: Read-only info (edit mode only) */}
        {!isNew && (
          <Col span={10}>
            <DataCard title={t("basicInfo.title")} style={{ marginBottom: 16 }}>
              <Descriptions column={1} size="small">
                <Descriptions.Item label={t("basicInfo.scCode")}>
                  {sc!.sc_code}
                </Descriptions.Item>
                <Descriptions.Item label={t("basicInfo.type")}>
                  <StatusBadge status={scTypeVariant(sc!.sc_type)}>
                    {sc!.sc_type === "CC" ? t("scType.critical") : t("scType.significant")}
                  </StatusBadge>
                </Descriptions.Item>
                <Descriptions.Item label={t("basicInfo.productLine")}>
                  {sc!.product_line_code}
                </Descriptions.Item>
                <Descriptions.Item label={t("basicInfo.sourceType")}>
                  <StatusBadge status={sourceTypeVariant(sc!.source_type)}>
                    {sc!.source_type}
                  </StatusBadge>
                </Descriptions.Item>
                <Descriptions.Item label={t("basicInfo.sourceFmea")}>
                  {sc!.source_fmea_document_no ? (
                    <Button
                      type="link"
                      size="small"
                      icon={<LinkOutlined />}
                      onClick={() => navigate(`/fmea/${sc!.source_fmea_id}`)}
                    >
                      {sc!.source_fmea_document_no}
                    </Button>
                  ) : (
                    "-"
                  )}
                </Descriptions.Item>
                <Descriptions.Item label={t("basicInfo.sourceNodeId")}>
                  <Text copyable>{sc!.source_node_id}</Text>
                </Descriptions.Item>
                <Descriptions.Item label={t("basicInfo.parentSc")}>
                  {sc!.parent_sc_id ? (
                    <Button
                      type="link"
                      size="small"
                      onClick={() =>
                        navigate(`/special-characteristics/${sc!.parent_sc_id}`)
                      }
                    >
                      {sc!.parent_sc_id}
                    </Button>
                  ) : (
                    "-"
                  )}
                </Descriptions.Item>
                <Descriptions.Item label={t("basicInfo.msaStatus")}>
                  <StatusBadge status={msaStatusVariant(sc!.msa_status)}>
                    {sc!.msa_status}
                  </StatusBadge>
                </Descriptions.Item>
              </Descriptions>
            </DataCard>

            {/* Source FMEA info */}
            {sc!.source_fmea_title && (
              <DataCard title={t("sourceFmea.title")}>
                <Descriptions column={1} size="small">
                  <Descriptions.Item label={t("sourceFmea.fmeaTitle")}>
                    {sc!.source_fmea_title}
                  </Descriptions.Item>
                  <Descriptions.Item label={t("sourceFmea.documentNo")}>
                    {sc!.source_fmea_document_no}
                  </Descriptions.Item>
                  <Descriptions.Item label={t("sourceFmea.viewFmea")}>
                    <Button
                      type="primary"
                      size="small"
                      onClick={() => navigate(`/fmea/${sc!.source_fmea_id}`)}
                    >
                      {t("sourceFmea.openEditor")}
                    </Button>
                  </Descriptions.Item>
                </Descriptions>
              </DataCard>
            )}
          </Col>
        )}

        {/* Right: Editable form */}
        <Col span={isNew ? 24 : 14}>
          <DataCard title={isNew ? t("createInfo.title") : t("editInfo.title")}>
            <Form
              form={form}
              layout="vertical"
              onFinish={handleSave}
              disabled={!canEdit('special_characteristic')}
            >
              {isNew && (
                <Form.Item
                  name="sc_type"
                  label={t("form.scType")}
                  rules={[{ required: true, message: t("form.scTypeRequired") }]}
                >
                  <Select placeholder={t("form.selectPlaceholder")}>
                    <Select.Option value="CC">{t("scType.critical")}</Select.Option>
                    <Select.Option value="SC">{t("scType.significant")}</Select.Option>
                  </Select>
                </Form.Item>
              )}

              <Form.Item
                name="sc_name"
                label={t("form.scName")}
                rules={[{ required: true, message: t("form.scNameRequired") }]}
              >
                <Input placeholder={t("form.scNamePlaceholder")} />
              </Form.Item>

              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="sc_category" label={t("form.category")}>
                    <Select placeholder={t("form.selectPlaceholder")} allowClear>
                      <Select.Option value="product">{t("category.product")}</Select.Option>
                      <Select.Option value="process">{t("category.process")}</Select.Option>
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="customer_symbol" label={t("form.customerSymbol")}>
                    <Input placeholder={t("form.customerSymbolPlaceholder")} />
                  </Form.Item>
                </Col>
              </Row>

              <Form.Item name="spec_requirement" label={t("form.specRequirement")}>
                <TextArea rows={4} placeholder={t("form.specRequirementPlaceholder")} />
              </Form.Item>

              <Form.Item name="sop_ref" label={t("form.sopRef")}>
                <Input placeholder={t("form.sopRefPlaceholder")} />
              </Form.Item>

              <Row gutter={16}>
                <Col span={8}>
                  <Form.Item
                    name="is_supplier_shared"
                    label={t("form.supplierShared")}
                    valuePropName="checked"
                  >
                    <Switch />
                  </Form.Item>
                </Col>
                <Col span={16}>
                  <Form.Item name="supplier_code" label={t("form.supplierCode")}>
                    <Input placeholder={t("form.supplierCodePlaceholder")} />
                  </Form.Item>
                </Col>
              </Row>

              {!!canEdit('special_characteristic') && (
                <Form.Item>
                  <Button
                    type="primary"
                    htmlType="submit"
                    icon={<SaveOutlined />}
                    loading={saving}
                  >
                    {t("actions.save")}
                  </Button>
                </Form.Item>
              )}
            </Form>
          </DataCard>

          {/* Safety Characteristic Panel */}
          {!isNew && sc && (
            <Collapse
              activeKey={safetyPanelOpen ? ["safety"] : []}
              onChange={(keys) => setSafetyPanelOpen(keys.includes("safety"))}
              style={{ marginTop: 16 }}
            >
              <Collapse.Panel
                header={
                  <Space>
                    <SafetyCertificateOutlined style={{ color: "#ff4d4f" }} />
                    <span>{t("safety.title")}</span>
                    {sc.safety_approval_status && (
                      <StatusBadge status={safetyStatusVariant(sc.safety_approval_status)}>
                        {sc.safety_approval_status === "pending" && t("approvalStatus.pending")}
                        {sc.safety_approval_status === "submitted" && t("approvalStatus.submitted")}
                        {sc.safety_approval_status === "approved" && t("approvalStatus.approved")}
                        {sc.safety_approval_status === "rejected" && t("approvalStatus.rejected")}
                      </StatusBadge>
                    )}
                  </Space>
                }
                key="safety"
              >
                <Space direction="vertical" style={{ width: "100%" }}>
                  <Form.Item label={t("safety.safetyRelated")}>
                    <Switch
                      checked={sc.is_safety_related}
                      onChange={handleSafetyToggle}
                      disabled={!canEdit('special_characteristic') || (sc.safety_approval_status === "submitted" && !canApprove('special_characteristic'))}
                    />
                  </Form.Item>

                  {sc.is_safety_related && (
                    <>
                      <StatusBadge status="info">{t("safety.autoSwitchHint")}</StatusBadge>
                      <Form
                        form={safetyForm}
                        layout="vertical"
                        onFinish={handleSafetySubmit}
                        disabled={!canEdit('special_characteristic') || sc.safety_approval_status === "submitted" || sc.safety_approval_status === "approved"}
                      >
                        <Form.Item
                          name="safety_regulation_ref"
                          label={t("safety.regulationRef")}
                          rules={[{ required: true, message: t("safety.regulationRefRequired") }]}
                        >
                          <Input placeholder={t("safety.regulationRefPlaceholder")} />
                        </Form.Item>
                        <Form.Item
                          name="safety_verification_method"
                          label={t("safety.verificationMethod")}
                          rules={[{ required: true, message: t("safety.verificationMethodRequired") }]}
                        >
                          <TextArea rows={3} placeholder={t("safety.verificationMethodPlaceholder")} />
                        </Form.Item>
                        {sc.safety_approval_status === "pending" && !!canEdit('special_characteristic') && (
                          <Button type="primary" htmlType="submit" loading={approvalLoading}>
                            {t("safety.submitApproval")}
                          </Button>
                        )}
                      </Form>

                      {/* Approval Timeline */}
                      {sc.safety_approval_status && (
                        <Timeline
                          items={[
                            {
                              dot: <ExclamationCircleOutlined style={{ color: "#faad14" }} />,
                              children: t("timeline.pendingDescription"),
                              color: sc.safety_approval_status === "pending" ? "blue" : "gray",
                            },
                            {
                              dot: <SafetyCertificateOutlined style={{ color: "#1677ff" }} />,
                              children: `${t("timeline.submitted")}：${sc.safety_submitted_at ? new Date(sc.safety_submitted_at).toLocaleString() : "-"}`,
                              color: sc.safety_approval_status === "submitted" ? "blue" : "gray",
                            },
                            sc.safety_approval_status === "approved" ? {
                              dot: <CheckCircleOutlined style={{ color: "#52c41a" }} />,
                              children: `${t("timeline.approved")}：${sc.safety_approved_at ? new Date(sc.safety_approved_at).toLocaleString() : "-"}`,
                              color: "green",
                            } : sc.safety_approval_status === "rejected" ? {
                              dot: <CloseCircleOutlined style={{ color: "#ff4d4f" }} />,
                              children: `${t("timeline.rejected")}：${sc.safety_approved_at ? new Date(sc.safety_approved_at).toLocaleString() : "-"}${sc.safety_approval_comment ? `（${sc.safety_approval_comment}）` : ""}`,
                              color: "red",
                            } : {
                              dot: <SafetyCertificateOutlined />,
                              children: t("timeline.result"),
                              color: "gray",
                            },
                          ].filter(Boolean) as any}
                        />
                      )}

                      {/* Approval Actions for manager/admin */}
                      {sc.safety_approval_status === "submitted" && canApprove('special_characteristic') && (
                        <Space>
                          <Button type="primary" onClick={handleSafetyApprove} loading={approvalLoading}>
                            {t("actions.approve")}
                          </Button>
                          <Button danger onClick={handleSafetyReject} loading={approvalLoading}>
                            {t("actions.reject")}
                          </Button>
                        </Space>
                      )}
                    </>
                  )}
                </Space>
              </Collapse.Panel>
            </Collapse>
          )}
        </Col>
      </Row>
    </PageShell>
  );
}

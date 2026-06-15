import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Button, Tag, Typography, Card, Form, Input, Select, Switch, App,
  Spin, Row, Col, Descriptions, Space, Timeline, Collapse,
} from "antd";
import {
  ArrowLeftOutlined, SaveOutlined, LinkOutlined,
  SafetyCertificateOutlined, ExclamationCircleOutlined,
  CheckCircleOutlined, CloseCircleOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { formatDateTime } from "../../../utils/dateTime";
import {
  getSC, updateSC, createSC,
  safetySubmit, safetyApprove, safetyReject, safetyCancel,
} from "../../../api/specialCharacteristic";
import type { SpecialCharacteristic } from "../../../types";
import { useAuthStore } from "../../../store/authStore";
import { usePermission } from "../../../hooks/usePermission";

const { Title, Text } = Typography;
const { TextArea } = Input;

function useSCDetailLabels(t: (key: string) => string) {
  const typeOptions = [
    { value: "CC", label: t("scType.critical") },
    { value: "SC", label: t("scType.significant") },
  ];

  const categoryOptions = [
    { value: "product", label: t("category.product") },
    { value: "process", label: t("category.process") },
  ];

  const approvalStatusLabel = (status: string) => {
    if (status === "pending") return t("approvalStatus.pending");
    if (status === "submitted") return t("approvalStatus.submitted");
    if (status === "approved") return t("approvalStatus.approved");
    if (status === "rejected") return t("approvalStatus.rejected");
    return status;
  };

  const approvalStatusColor = (status: string) => {
    if (status === "approved") return "green";
    if (status === "rejected") return "red";
    if (status === "submitted") return "blue";
    return "orange";
  };

  return { typeOptions, categoryOptions, approvalStatusLabel, approvalStatusColor };
}

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

  const { typeOptions, categoryOptions, approvalStatusLabel, approvalStatusColor } = useSCDetailLabels(t);

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
    <div>
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
        }}
      >
        <Space>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate("/special-characteristics")}
          >
            {t("action.backToList")}
          </Button>
          <Title level={4} style={{ margin: 0 }}>
            {isNew ? t("pageTitle.newSC") : `${sc!.sc_code} - ${sc!.sc_name}`}
          </Title>
          {!isNew && (
            <Tag color={sc!.sc_type === "CC" ? "red" : "gold"}>
              {sc!.sc_type}
            </Tag>
          )}
        </Space>
      </div>

      <Row gutter={16}>
        {/* Left: Read-only info (edit mode only) */}
        {!isNew && (
          <Col span={10}>
            <Card title={t("card.basicInfo")} style={{ marginBottom: 16 }}>
              <Descriptions column={1} size="small">
                <Descriptions.Item label={t("label.scCode")}>
                  {sc!.sc_code}
                </Descriptions.Item>
                <Descriptions.Item label={t("label.type")}>
                  <span
                    style={{
                      backgroundColor: sc!.sc_type === "CC" ? "#fff1f0" : "#fffbe6",
                      padding: "2px 8px",
                      borderRadius: 4,
                    }}
                  >
                    <Tag color={sc!.sc_type === "CC" ? "red" : "gold"}>
                      {sc!.sc_type === "CC" ? t("scType.critical") : t("scType.significant")}
                    </Tag>
                  </span>
                </Descriptions.Item>
                <Descriptions.Item label={t("label.productLine")}>
                  {sc!.product_line_code}
                </Descriptions.Item>
                <Descriptions.Item label={t("label.sourceType")}>
                  <Tag color={sc!.source_type === "DFMEA" ? "blue" : "green"}>
                    {sc!.source_type}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label={t("label.sourceFMEADoc")}>
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
                <Descriptions.Item label={t("label.sourceNodeId")}>
                  <Text copyable>{sc!.source_node_id}</Text>
                </Descriptions.Item>
                <Descriptions.Item label={t("label.parentSC")}>
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
                <Descriptions.Item label={t("label.msaStatus")}>
                  <Tag
                    color={
                      sc!.msa_status === "PASS"
                        ? "green"
                        : sc!.msa_status === "FAIL"
                        ? "red"
                        : "orange"
                    }
                  >
                    {sc!.msa_status}
                  </Tag>
                </Descriptions.Item>
              </Descriptions>
            </Card>

            {/* Source FMEA info */}
            {sc!.source_fmea_title && (
              <Card title={t("card.sourceFMEAInfo")}>
                <Descriptions column={1} size="small">
                  <Descriptions.Item label={t("label.fmeaTitle")}>
                    {sc!.source_fmea_title}
                  </Descriptions.Item>
                  <Descriptions.Item label={t("label.sourceFMEADoc")}>
                    {sc!.source_fmea_document_no}
                  </Descriptions.Item>
                  <Descriptions.Item label={t("label.viewFMEA")}>
                    <Button
                      type="primary"
                      size="small"
                      onClick={() => navigate(`/fmea/${sc!.source_fmea_id}`)}
                    >
                      {t("label.viewFMEA")}
                    </Button>
                  </Descriptions.Item>
                </Descriptions>
              </Card>
            )}
          </Col>
        )}

        {/* Right: Editable form */}
        <Col span={isNew ? 24 : 14}>
          <Card title={isNew ? t("card.createInfo") : t("card.editInfo")}>
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
                  rules={[{ required: true, message: t("message.selectType") }]}
                >
                  <Select placeholder={t("placeholder.selectType")}>
                    {typeOptions.map((opt) => (
                      <Select.Option key={opt.value} value={opt.value}>{opt.label}</Select.Option>
                    ))}
                  </Select>
                </Form.Item>
              )}

              <Form.Item
                name="sc_name"
                label={t("form.scName")}
                rules={[{ required: true, message: t("message.enterName") }]}
              >
                <Input placeholder={t("placeholder.scName")} />
              </Form.Item>

              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="sc_category" label={t("form.scCategory")}>
                    <Select placeholder={t("placeholder.selectType")} allowClear>
                      {categoryOptions.map((opt) => (
                        <Select.Option key={opt.value} value={opt.value}>{opt.label}</Select.Option>
                      ))}
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="customer_symbol" label={t("form.customerSymbol")}>
                    <Input placeholder={t("placeholder.customerSymbol")} />
                  </Form.Item>
                </Col>
              </Row>

              <Form.Item name="spec_requirement" label={t("form.specRequirement")}>
                <TextArea rows={4} placeholder={t("placeholder.specRequirement")} />
              </Form.Item>

              <Form.Item name="sop_ref" label={t("form.sopRef")}>
                <Input placeholder={t("placeholder.sopRef")} />
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
                    <Input placeholder={t("placeholder.supplierCode")} />
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
                    {tc("actions.save")}
                  </Button>
                </Form.Item>
              )}
            </Form>
          </Card>

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
                    <span>{t("card.safetyCharacteristic")}</span>
                    {sc.safety_approval_status && (
                      <Tag color={approvalStatusColor(sc.safety_approval_status)}>
                        {approvalStatusLabel(sc.safety_approval_status)}
                      </Tag>
                    )}
                  </Space>
                }
                key="safety"
              >
                <Space direction="vertical" style={{ width: "100%" }}>
                  <Form.Item label={t("label.safetyRelated")}>
                    <Switch
                      checked={sc.is_safety_related}
                      onChange={handleSafetyToggle}
                      disabled={!canEdit('special_characteristic') || (sc.safety_approval_status === "submitted" && !canApprove('special_characteristic'))}
                    />
                  </Form.Item>

                  {sc.is_safety_related && (
                    <>
                      <Form
                        form={safetyForm}
                        layout="vertical"
                        onFinish={handleSafetySubmit}
                        disabled={!canEdit('special_characteristic') || sc.safety_approval_status === "submitted" || sc.safety_approval_status === "approved"}
                      >
                        <Form.Item
                          name="safety_regulation_ref"
                          label={t("label.safetyRegulationRef")}
                          rules={[{ required: true, message: t("message.enterRegulationRef") }]}
                        >
                          <Input placeholder={t("placeholder.safetyRegulationRef")} />
                        </Form.Item>
                        <Form.Item
                          name="safety_verification_method"
                          label={t("label.safetyVerificationMethod")}
                          rules={[{ required: true, message: t("message.enterVerificationMethod") }]}
                        >
                          <TextArea rows={3} placeholder={t("placeholder.safetyVerificationMethod")} />
                        </Form.Item>
                        {sc.safety_approval_status === "pending" && !!canEdit('special_characteristic') && (
                          <Button type="primary" htmlType="submit" loading={approvalLoading}>
                            {t("label.submitForApproval")}
                          </Button>
                        )}
                      </Form>

                      {/* Approval Timeline */}
                      {sc.safety_approval_status && (
                        <Timeline
                          items={[
                            {
                              dot: <ExclamationCircleOutlined style={{ color: "#faad14" }} />,
                              children: t("timeline.pending"),
                              color: sc.safety_approval_status === "pending" ? "blue" : "gray",
                            },
                            {
                              dot: <SafetyCertificateOutlined style={{ color: "#1677ff" }} />,
                              children: t("timeline.submitted", { time: sc.safety_submitted_at ? formatDateTime(sc.safety_submitted_at) : "-" }),
                              color: sc.safety_approval_status === "submitted" ? "blue" : "gray",
                            },
                            sc.safety_approval_status === "approved" ? {
                              dot: <CheckCircleOutlined style={{ color: "#52c41a" }} />,
                              children: t("timeline.approved", { time: sc.safety_approved_at ? formatDateTime(sc.safety_approved_at) : "-" }),
                              color: "green",
                            } : sc.safety_approval_status === "rejected" ? {
                              dot: <CloseCircleOutlined style={{ color: "#ff4d4f" }} />,
                              children: t("timeline.rejected", { time: sc.safety_approved_at ? formatDateTime(sc.safety_approved_at) : "-", comment: sc.safety_approval_comment ? `（${sc.safety_approval_comment}）` : "" }),
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
                            {tc("actions.approve")}
                          </Button>
                          <Button danger onClick={handleSafetyReject} loading={approvalLoading}>
                            {tc("actions.reject")}
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
    </div>
  );
}

import { useState, useEffect, useCallback } from "react";
import {
  Card,
  Button,
  Tag,
  Space,
  Form,
  Input,
  Select,
  DatePicker,
  App,
  Tabs,
  Table,
  List,
  Modal,
  Popconfirm,
  Row,
  Col,
  Steps,
  Slider,
  Spin,
  InputNumber,
  Typography,
} from "antd";
import {
  ArrowLeftOutlined,
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";
import type { Supplier, SupplierCertification, SupplierEvaluation, AuditPlan } from "../../types";
import client from "../../api/client";
import {
  getSupplier,
  createSupplier,
  updateSupplier,
  listCertifications,
  createCertification,
  updateCertification,
  deleteCertification,
  listEvaluations,
  createEvaluation,
  approveSupplier,
  rejectSupplier,
  confirmApproved,
  suspendSupplier,
  reinstateSupplier,
} from "../../api/supplier";
import { listAuditPlans } from "../../api/audit";
import dayjs from "dayjs";

const { Option } = Select;
const { TextArea } = Input;
const { Text } = Typography;

function useStatusMap(): Record<string, { label: string; color: string }> {
  const { t } = useTranslation("supplier");
  return {
    pending_review: { label: t("status.pending_review"), color: "default" },
    audit_required: { label: t("status.audit_required"), color: "processing" },
    approved: { label: t("status.approved"), color: "success" },
    rejected: { label: t("status.rejected"), color: "error" },
    suspended: { label: t("status.suspended"), color: "warning" },
  };
}

const GRADE_COLORS: Record<string, string> = {
  A: "green",
  B: "blue",
  C: "orange",
  D: "red",
};

function statusToStep(status: string): number {
  switch (status) {
    case "pending_review":
      return 0;
    case "audit_required":
      return 1;
    case "approved":
      return 2;
    case "rejected":
      return 2;
    case "suspended":
      return 2;
    default:
      return 0;
  }
}

function calcBaseScore(
  q: number,
  d: number,
  s: number,
): number {
  return Math.round((q * 0.35 + d * 0.3 + s * 0.15) * 10) / 10;
}

export default function SupplierDetailPage() {
  const { message } = App.useApp();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user: _user } = useAuthStore();
  const { t } = useTranslation("supplier");
  const { t: tc } = useTranslation("common");
  const STATUS_MAP = useStatusMap();

  const { canEdit, canApprove } = usePermission();

  const [supplier, setSupplier] = useState<Supplier | null>(null);
  const isNew = id === "new";
  const [loading, setLoading] = useState(!isNew);
  const [editing, setEditing] = useState(isNew);
  const [saving, setSaving] = useState(false);
  const [infoForm] = Form.useForm();

  const [certs, setCerts] = useState<SupplierCertification[]>([]);
  const [certsLoading, setCertsLoading] = useState(false);
  const [certModalOpen, setCertModalOpen] = useState(false);
  const [certEditing, setCertEditing] = useState<SupplierCertification | null>(null);
  const [certForm] = Form.useForm();
  const [certSaving, setCertSaving] = useState(false);

  const [evals, setEvals] = useState<SupplierEvaluation[]>([]);
  const [evalsLoading, setEvalsLoading] = useState(false);
  const [evalForm] = Form.useForm();
  const [evalSaving, setEvalSaving] = useState(false);
  const [evalPreview, setEvalPreview] = useState<number | null>(null);

  const [auditPlans, setAuditPlans] = useState<AuditPlan[]>([]);

  const [rejectModalVisible, setRejectModalVisible] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [suspendModalVisible, setSuspendModalVisible] = useState(false);
  const [suspendReason, setSuspendReason] = useState("");
  const [transitioning, setTransitioning] = useState(false);

  const [relatedData, setRelatedData] = useState<{
    complaints: Array<{ id: string; no: string; status: string }>;
    iqc_rejects: Array<{ id: string; no: string; result: string }>;
    scars: Array<{ id: string; no: string; status: string }>;
  }>({ complaints: [], iqc_rejects: [], scars: [] });

  const loadSupplier = useCallback(async () => {
    if (!id || id === "new") return;
    setLoading(true);
    try {
      const s = await getSupplier(id);
      setSupplier(s);
    } catch {
      message.error(t("messages.loadSupplierFailed"));
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const loadCerts = useCallback(async () => {
    if (!id || id === "new") return;
    setCertsLoading(true);
    try {
      const data = await listCertifications(id);
      setCerts(data);
    } catch {
      message.error(t("messages.loadCertificatesFailed"));
    } finally {
      setCertsLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const loadEvals = useCallback(async () => {
    if (!id || id === "new") return;
    setEvalsLoading(true);
    try {
      const data = await listEvaluations(id);
      setEvals(data);
    } catch {
      message.error(t("messages.loadEvaluationsFailed"));
    } finally {
      setEvalsLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const loadAuditPlans = useCallback(async () => {
    try {
      const resp = await listAuditPlans({ page_size: 200 });
      setAuditPlans(resp.items);
    } catch {
      // non-critical
    }
  }, []);

  const loadRelated = useCallback(async () => {
    if (!id || id === "new") return;
    try {
      const resp = await client.get(`/suppliers/${id}/related`);
      setRelatedData(resp.data);
    } catch {
      // non-critical
    }
  }, [id]);

  useEffect(() => {
    Promise.all([loadSupplier(), loadCerts(), loadEvals(), loadAuditPlans(), loadRelated()]);
  }, [loadSupplier, loadCerts, loadEvals, loadAuditPlans, loadRelated]);

  // Populate info form when supplier loads or editing starts
  useEffect(() => {
    if (supplier && editing) {
      infoForm.setFieldsValue({
        name: supplier.name,
        short_name: supplier.short_name,
        contact_name: supplier.contact_name,
        contact_phone: supplier.contact_phone,
        contact_email: supplier.contact_email,
        address: supplier.address,
        product_scope: supplier.product_scope,
        audit_plan_id: supplier.audit_plan_id,
      });
    }
  }, [supplier, editing, infoForm]);

  const handleSaveInfo = async () => {
    if (!id && !isNew) return;
    try {
      const values = await infoForm.validateFields();
      setSaving(true);
      if (isNew) {
        const created = await createSupplier(values);
        message.success(t("messages.createSuccess"));
        navigate(`/suppliers/${created.supplier_id}`, { replace: true });
      } else {
        const updated = await updateSupplier(id!, values);
        setSupplier(updated);
        setEditing(false);
        message.success(t("messages.saveSuccess"));
      }
    } catch (err: unknown) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      console.error(err);
      message.error(isNew ? t("messages.createFailed") : t("messages.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const handleCancelEdit = () => {
    if (isNew) {
      navigate("/suppliers");
    } else {
      setEditing(false);
      infoForm.resetFields();
    }
  };

  // --- Cert modal ---
  const openCertModal = (cert?: SupplierCertification) => {
    setCertEditing(cert ?? null);
    if (cert) {
      certForm.setFieldsValue({
        cert_type: cert.cert_type,
        cert_no: cert.cert_no,
        issued_by: cert.issued_by,
        issue_date: cert.issue_date ? dayjs(cert.issue_date) : null,
        expiry_date: cert.expiry_date ? dayjs(cert.expiry_date) : null,
      });
    } else {
      certForm.resetFields();
    }
    setCertModalOpen(true);
  };

  const handleCertSave = async () => {
    if (!id) return;
    try {
      const values = await certForm.validateFields();
      setCertSaving(true);
      const payload = {
        ...values,
        issue_date: values.issue_date ? values.issue_date.toISOString() : null,
        expiry_date: values.expiry_date ? values.expiry_date.toISOString() : null,
      };
      if (certEditing) {
        await updateCertification(id, certEditing.cert_id, payload);
        message.success(t("messages.certUpdateSuccess"));
      } else {
        await createCertification(id, payload);
        message.success(t("messages.certAddSuccess"));
      }
      setCertModalOpen(false);
      await loadCerts();
    } catch (err: unknown) {
      if (err && typeof err === "object" && "errorFields" in err) return; // Ant Design form validation error
      console.error(err);
      message.error(t("messages.certSaveFailed"));
    } finally {
      setCertSaving(false);
    }
  };

  const handleDeleteCert = async (certId: string) => {
    if (!id) return;
    try {
      await deleteCertification(id, certId);
      message.success(t("messages.certDeleteSuccess"));
      await loadCerts();
    } catch {
      message.error(t("messages.certDeleteFailed"));
    }
  };

  // --- Eval form (inline) ---

  const handleEvalValuesChange = () => {
    const vals = evalForm.getFieldsValue();
    const q = vals.quality_score ?? 0;
    const d = vals.delivery_score ?? 0;
    const s = vals.service_score ?? 0;
    setEvalPreview(calcBaseScore(q, d, s));
  };

  const handleEvalSave = async () => {
    if (!id) return;
    try {
      const values = await evalForm.validateFields();
      setEvalSaving(true);
      const payload = { ...values };
      await createEvaluation(id, payload);
        message.success(t("messages.evalSubmitSuccess"));
      evalForm.resetFields();
      evalForm.setFieldsValue({ quality_score: 80, delivery_score: 80, service_score: 80 });
      setEvalPreview(calcBaseScore(80, 80, 80));
      await loadEvals();
    } catch (err: unknown) {
      if (err && typeof err === "object" && "errorFields" in err) return; // Ant Design form validation error
      console.error(err);
      message.error(t("messages.evalSubmitFailed"));
    } finally {
      setEvalSaving(false);
    }
  };

  const handleApprove = async () => {
    if (!id) return;
    setTransitioning(true);
    try {
      await approveSupplier(id);
      message.success(t("messages.approveSuccess"));
      loadSupplier();
    } catch {
      message.error(t("messages.operationFailed"));
    } finally {
      setTransitioning(false);
    }
  };

  const handleReject = async () => {
    if (!id) return;
    setTransitioning(true);
    try {
      await rejectSupplier(id, rejectReason);
      message.success(t("messages.rejectSuccess"));
      setRejectModalVisible(false);
      setRejectReason("");
      loadSupplier();
    } catch {
      message.error(t("messages.operationFailed"));
    } finally {
      setTransitioning(false);
    }
  };

  const handleConfirmApproved = async () => {
    if (!id) return;
    setTransitioning(true);
    try {
      await confirmApproved(id);
      message.success(t("messages.confirmApproveSuccess"));
      loadSupplier();
    } catch {
      message.error(t("messages.operationFailed"));
    } finally {
      setTransitioning(false);
    }
  };

  const handleSuspend = async () => {
    if (!id) return;
    setTransitioning(true);
    try {
      await suspendSupplier(id, suspendReason);
      message.success(t("messages.suspendSuccess"));
      setSuspendModalVisible(false);
      setSuspendReason("");
      loadSupplier();
    } catch {
      message.error(t("messages.operationFailed"));
    } finally {
      setTransitioning(false);
    }
  };

  const handleReinstate = async () => {
    if (!id) return;
    setTransitioning(true);
    try {
      await reinstateSupplier(id);
      message.success(t("messages.resumeSuccess"));
      loadSupplier();
    } catch {
      message.error(t("messages.operationFailed"));
    } finally {
      setTransitioning(false);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!supplier && !isNew) {
    return <div style={{ padding: 24 }}>{t("messages.supplierNotFound")}</div>;
  }

  const statusInfo = supplier
    ? (STATUS_MAP[supplier.status] ?? { label: supplier.status, color: "default" })
    : { label: t("messages.new"), color: "processing" };

  // Cert table columns
  const certColumns = [
    { title: t("table.certType"), dataIndex: "cert_type", key: "cert_type" },
    { title: t("table.certNo"), dataIndex: "cert_no", key: "cert_no" },
    { title: t("table.issuedBy"), dataIndex: "issued_by", key: "issued_by" },
    {
      title: t("table.issueDate"),
      dataIndex: "issue_date",
      key: "issue_date",
      render: (v: string | null) => (v ? dayjs(v).format("YYYY-MM-DD") : "-"),
    },
    {
      title: t("table.expiryDate"),
      dataIndex: "expiry_date",
      key: "expiry_date",
      render: (v: string | null) => {
        if (!v) return "-";
        const daysLeft = dayjs(v).diff(dayjs(), "day");
        const isExpiringSoon = daysLeft <= 30;
        return (
          <span style={isExpiringSoon ? { color: "red", fontWeight: 500 } : {}}>
            {dayjs(v).format("YYYY-MM-DD")}
            {isExpiringSoon && daysLeft >= 0 && (
              <span style={{ marginLeft: 4, fontSize: 12 }}>({t("messages.daysLeft", { days: daysLeft })})</span>
            )}
            {daysLeft < 0 && <span style={{ marginLeft: 4, fontSize: 12 }}>({t("messages.expired")})</span>}
          </span>
        );
      },
    },
    ...(canEdit('supplier')
      ? [
          {
            title: t("table.operations"),
            key: "action",
            render: (_: unknown, record: SupplierCertification) => (
              <Space>
                <Button
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => openCertModal(record)}
                >
                  {t("table.edit")}
                </Button>
                <Popconfirm
                  title={t("messages.confirmDeleteCert")}
                  onConfirm={() => handleDeleteCert(record.cert_id)}
                >
                  <Button size="small" danger icon={<DeleteOutlined />}>
                    {t("table.delete")}
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]
      : []),
  ];

  const tabItems = [
    {
      key: "info",
      label: t("tabs.basicInfo"),
      children: (
        <Card
          extra={
            canEdit('supplier') && (
              <Space>
                {editing ? (
                  <>
                    <Button onClick={handleCancelEdit}>{tc("actions.cancel")}</Button>
                    <Button type="primary" loading={saving} onClick={handleSaveInfo}>
                      {tc("actions.save")}
                    </Button>
                  </>
                ) : (
                  <Button icon={<EditOutlined />} onClick={() => setEditing(true)}>
                    {t("table.edit")}
                  </Button>
                )}
              </Space>
            )
          }
        >
          {supplier?.reject_reason && (
            <div
              style={{
                background: "#fff2f0",
                border: "1px solid #ffccc7",
                borderRadius: 6,
                padding: "8px 12px",
                marginBottom: 16,
                color: "red",
              }}
            >
              <strong>{t("messages.rejectReason")}：</strong>
              {supplier.reject_reason}
            </div>
          )}
          {editing ? (
            <Form form={infoForm} layout="vertical">
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item label={t("form.supplierName")} name="name" rules={[{ required: true, message: t("form.enterName") }]}>
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label={t("form.shortName")} name="short_name" rules={[{ required: true, message: t("form.enterShortName") }]}>
                    <Input />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16}>
                <Col span={8}>
                  <Form.Item label={t("form.contactName")} name="contact_name">
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label={t("form.contactPhone")} name="contact_phone">
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label={t("form.contactEmail")} name="contact_email">
                    <Input />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item label={t("form.address")} name="address">
                <Input />
              </Form.Item>
              <Form.Item label={t("form.productScope")} name="product_scope">
                <TextArea rows={3} />
              </Form.Item>
              {supplier?.status === "audit_required" && (
                <Form.Item label={t("form.auditPlan")} name="audit_plan_id">
                  <Select allowClear placeholder={t("form.selectAuditPlan")}>
                    {auditPlans.map((p) => (
                      <Option key={p.audit_id} value={p.audit_id}>
                        {p.plan_no}
                      </Option>
                    ))}
                  </Select>
                </Form.Item>
              )}
            </Form>
          ) : supplier && (
            <Row gutter={[16, 8]}>
              <Col span={12}>
                <Text type="secondary">{t("detail.supplierNo")}</Text>
                <div>{supplier.supplier_no}</div>
              </Col>
              <Col span={12}>
                <Text type="secondary">{t("detail.supplierName")}</Text>
                <div>{supplier.name}</div>
              </Col>
              <Col span={12}>
                <Text type="secondary">{t("detail.shortName")}</Text>
                <div>{supplier.short_name}</div>
              </Col>
              <Col span={12}>
                <Text type="secondary">{t("detail.contactName")}</Text>
                <div>{supplier.contact_name ?? "-"}</div>
              </Col>
              <Col span={8}>
                <Text type="secondary">{t("detail.contactPhone")}</Text>
                <div>{supplier.contact_phone ?? "-"}</div>
              </Col>
              <Col span={8}>
                <Text type="secondary">{t("detail.contactEmail")}</Text>
                <div>{supplier.contact_email ?? "-"}</div>
              </Col>
              <Col span={24}>
                <Text type="secondary">{t("detail.address")}</Text>
                <div>{supplier.address ?? "-"}</div>
              </Col>
              <Col span={24}>
                <Text type="secondary">{t("detail.productScope")}</Text>
                <div style={{ whiteSpace: "pre-wrap" }}>{supplier.product_scope ?? "-"}</div>
              </Col>
              {supplier?.status === "audit_required" && (
                <Col span={24}>
                  <Text type="secondary">{t("detail.auditPlan")}</Text>
                  <div>
                    {auditPlans.find((p) => p.audit_id === supplier.audit_plan_id)?.plan_no ??
                      (supplier.audit_plan_id ? supplier.audit_plan_id : t("messages.notSpecified"))}
                  </div>
                </Col>
              )}
              <Col span={12}>
                <Text type="secondary">{t("detail.createdAt")}</Text>
                <div>{dayjs(supplier.created_at).format("YYYY-MM-DD HH:mm")}</div>
              </Col>
              <Col span={12}>
                <Text type="secondary">{t("detail.updatedAt")}</Text>
                <div>{dayjs(supplier.updated_at).format("YYYY-MM-DD HH:mm")}</div>
              </Col>
            </Row>
          )}
        </Card>
      ),
    },
    {
      key: "certs",
      label: t("tabs.certificates"),
      children: (
        <Card
          extra={
            canEdit('supplier') && (
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => openCertModal()}
              >
                {t("modal.addCert")}
              </Button>
            )
          }
        >
          <Table
            loading={certsLoading}
            dataSource={certs}
            rowKey="cert_id"
            columns={certColumns}
            pagination={false}
            size="middle"
            onRow={(record) => {
              const daysLeft = record.expiry_date
                ? dayjs(record.expiry_date).diff(dayjs(), "day")
                : null;
              return {
                style: daysLeft !== null && daysLeft <= 30 ? { background: "#fff1f0" } : {},
              };
            }}
          />
        </Card>
      ),
    },
    {
      key: "evals",
      label: t("tabs.evaluations"),
      children: (
        <Row gutter={24}>
          {/* Left: history list */}
          <Col span={12}>
            <Card title={t("detail.evalHistory")} size="small">
              {evalsLoading ? (
                <div style={{ textAlign: "center", padding: 40 }}>
                  <Spin />
                </div>
              ) : evals.length === 0 ? (
                <div style={{ textAlign: "center", color: "#999", padding: 40 }}>{t("messages.noEvalRecords")}</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {evals.map((ev) => (
                    <Card
                      key={ev.eval_id}
                      size="small"
                      title={
                        <Space>
                          <span>{ev.eval_period}</span>
                          <Tag color={GRADE_COLORS[ev.grade]}>{t("detail.grade", { grade: ev.grade })}</Tag>
                          <span style={{ fontWeight: 400, color: "#666" }}>
                            {t("detail.totalScore", { score: ev.total_score })}
                          </span>
                          <Tag>{ev.eval_type === "quarterly" ? t("form.quarterly") : t("form.annual")}</Tag>
                        </Space>
                      }
                    >
                      <Row gutter={16}>
                        <Col span={8}>
                          <Text type="secondary">{t("detail.qualityScore")}</Text>
                          <div>{ev.quality_score}</div>
                        </Col>
                        <Col span={8}>
                          <Text type="secondary">{t("detail.deliveryScore")}</Text>
                          <div>{ev.delivery_score}</div>
                        </Col>
                        <Col span={8}>
                          <Text type="secondary">{t("detail.serviceScore")}</Text>
                          <div>{ev.service_score}</div>
                        </Col>
                        <Col span={8}>
                          <Text type="secondary">{t("detail.evalTime")}</Text>
                          <div>{dayjs(ev.created_at).format("YYYY-MM-DD")}</div>
                        </Col>
                        {(ev.capa_count > 0 || ev.finding_count > 0 || ev.premium_freight_count > 0 || ev.customer_disruption_count > 0) && (
                          <>
                            <Col span={8}>
                              <Text type="secondary">{t("detail.capaCount")}</Text>
                              <div>{ev.capa_count}</div>
                            </Col>
                            <Col span={8}>
                              <Text type="secondary">{t("detail.findingCount")}</Text>
                              <div>{ev.finding_count}</div>
                            </Col>
                            {(ev.premium_freight_count > 0 || ev.customer_disruption_count > 0) && (
                              <>
                                <Col span={8}>
                                  <Text type="secondary">{t("detail.premiumFreight")}</Text>
                                  <div>{ev.premium_freight_count}</div>
                                </Col>
                                <Col span={8}>
                                  <Text type="secondary">{t("detail.customerDisruption")}</Text>
                                  <div>{ev.customer_disruption_count}</div>
                                </Col>
                              </>
                            )}
                          </>
                        )}
                        {ev.notes && (
                          <Col span={24}>
                            <Text type="secondary">{t("detail.remarks")}</Text>
                            <div>{ev.notes}</div>
                          </Col>
                        )}
                      </Row>
                    </Card>
                  ))}
                </div>
              )}
            </Card>
          </Col>

          {/* Right: inline create form */}
          {canEdit('supplier') && (
            <Col span={12}>
              <Card title={t("detail.newEvaluation")} size="small">
                <Form
                  form={evalForm}
                  layout="vertical"
                  onValuesChange={handleEvalValuesChange}
                  initialValues={{
                    quality_score: 80,
                    delivery_score: 80,
                    service_score: 80,
                  }}
                >
                  <Row gutter={16}>
                    <Col span={12}>
                      <Form.Item
                        label={t("form.evalPeriod")}
                        name="eval_period"
                        rules={[{ required: true, message: t("form.enterEvalPeriod") }]}
                      >
                        <Input placeholder={t("form.evalPeriodPlaceholder")} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item
                        label={t("form.evalType")}
                        name="eval_type"
                        rules={[{ required: true, message: t("form.selectEvalType") }]}
                      >
                        <Select>
                          <Option value="quarterly">{t("form.quarterly")}</Option>
                          <Option value="annual">{t("form.annual")}</Option>
                        </Select>
                      </Form.Item>
                    </Col>
                  </Row>

                  <Form.Item label={t("form.qualityScore", { score: evalForm.getFieldValue("quality_score") ?? 80 })} name="quality_score">
                    <Slider min={0} max={100} />
                  </Form.Item>
                  <Form.Item label={t("form.deliveryScore", { score: evalForm.getFieldValue("delivery_score") ?? 80 })} name="delivery_score">
                    <Slider min={0} max={100} />
                  </Form.Item>
                  <Form.Item label={t("form.serviceScore", { score: evalForm.getFieldValue("service_score") ?? 80 })} name="service_score">
                    <Slider min={0} max={100} />
                  </Form.Item>

                  <Row gutter={16}>
                    <Col span={12}>
                      <Form.Item label={t("form.capaCount")} name="capa_count" initialValue={0}>
                        <InputNumber min={0} style={{ width: "100%" }} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item label={t("form.findingCount")} name="finding_count" initialValue={0}>
                        <InputNumber min={0} style={{ width: "100%" }} />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Row gutter={16}>
                    <Col span={12}>
                      <Form.Item label={t("form.premiumFreightCount")} name="premium_freight_count" initialValue={0}>
                        <InputNumber min={0} style={{ width: "100%" }} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item label={t("form.customerDisruptionCount")} name="customer_disruption_count" initialValue={0}>
                        <InputNumber min={0} style={{ width: "100%" }} />
                      </Form.Item>
                    </Col>
                  </Row>

                  <Form.Item label={t("form.notes")} name="notes">
                    <TextArea rows={2} />
                  </Form.Item>

                  {evalPreview !== null && (
                    <div
                      style={{
                        background: "#f6ffed",
                        border: "1px solid #b7eb8f",
                        borderRadius: 6,
                        padding: "10px 16px",
                        marginBottom: 12,
                      }}
                    >
                      {t("messages.estimatedScore")}<strong>{evalPreview}</strong>
                    </div>
                  )}

                  <Form.Item>
                    <Button
                      type="primary"
                      loading={evalSaving}
                      onClick={handleEvalSave}
                      block
                    >
                      {t("detail.submitEvaluation")}
                    </Button>
                  </Form.Item>
                </Form>
              </Card>
            </Col>
          )}
        </Row>
      ),
    },
    {
      key: "complaints",
      label: t("tabs.complaints", { count: relatedData.complaints.length }),
      children: (
        <List
          dataSource={relatedData.complaints}
          locale={{ emptyText: t("messages.noRelatedComplaints") }}
          renderItem={(item) => (
            <List.Item
              style={{ cursor: "pointer" }}
              onClick={() => navigate(`/customer-quality/complaints/${item.id}`)}
            >
              <List.Item.Meta title={item.no} />
              <Tag>{item.status}</Tag>
            </List.Item>
          )}
        />
      ),
    },
    {
      key: "iqc",
      label: t("tabs.iqcRejects", { count: relatedData.iqc_rejects.length }),
      children: (
        <List
          dataSource={relatedData.iqc_rejects}
          locale={{ emptyText: t("messages.noIqcRejectRecords") }}
          renderItem={(item) => (
            <List.Item
              style={{ cursor: "pointer" }}
              onClick={() => navigate(`/iqc/inspections/${item.id}`)}
            >
              <List.Item.Meta title={item.no} />
              <Tag color="error">{item.result}</Tag>
            </List.Item>
          )}
        />
      ),
    },
    {
      key: "scars",
      label: t("tabs.scars", { count: relatedData.scars.length }),
      children: (
        <List
          dataSource={relatedData.scars}
          locale={{ emptyText: t("messages.noScarRecords") }}
          renderItem={(item) => (
            <List.Item
              style={{ cursor: "pointer" }}
              onClick={() => navigate(`/scars/${item.id}`)}
            >
              <List.Item.Meta title={item.no} />
              <Tag>{item.status}</Tag>
            </List.Item>
          )}
        />
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      {/* Header */}
      <div style={{ marginBottom: 16, display: "flex", alignItems: "center", gap: 12 }}>
        <Button
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate("/suppliers")}
        >
          {t("messages.back")}
        </Button>
        <h2 style={{ margin: 0, fontSize: 20 }}>{isNew ? t("messages.newSupplier") : supplier!.name}</h2>
        {!isNew && <Tag color={statusInfo.color}>{statusInfo.label}</Tag>}
        {!isNew && supplier && canApprove('supplier') && (
          <Space style={{ marginLeft: "auto" }}>
            {supplier.status === "pending_review" && (
              <>
                <Button
                  type="primary"
                  loading={transitioning}
                  onClick={handleApprove}
                >
                  {t("messages.approve")}
                </Button>
                <Button
                  danger
                  loading={transitioning}
                  onClick={() => { setRejectReason(""); setRejectModalVisible(true); }}
                >
                  {t("messages.reject")}
                </Button>
              </>
            )}
            {supplier.status === "audit_required" && (
              <>
                <Popconfirm
                  title={t("messages.confirmApproveSupplier")}
                  onConfirm={handleConfirmApproved}
                  okText={tc("actions.confirm")}
                  cancelText={tc("actions.cancel")}
                >
                  <Button type="primary" loading={transitioning}>
                    {t("messages.confirmApprove")}
                  </Button>
                </Popconfirm>
                <Button
                  danger
                  loading={transitioning}
                  onClick={() => { setRejectReason(""); setRejectModalVisible(true); }}
                >
                  {t("messages.reject")}
                </Button>
              </>
            )}
            {supplier.status === "approved" && (
              <Button
                danger
                loading={transitioning}
                onClick={() => { setSuspendReason(""); setSuspendModalVisible(true); }}
              >
                {t("messages.suspend")}
              </Button>
            )}
            {supplier.status === "suspended" && (
              <Popconfirm
                title={t("messages.confirmResumeSupplier")}
                onConfirm={handleReinstate}
                okText={tc("actions.confirm")}
                cancelText={tc("actions.cancel")}
              >
                <Button type="primary" loading={transitioning}>
                  {t("messages.resume")}
                </Button>
              </Popconfirm>
            )}
          </Space>
        )}
      </div>

      {/* Approval progress bar */}
      {!isNew && (
        <Card style={{ marginBottom: 16 }}>
          <Steps
            current={statusToStep(supplier!.status)}
            status={
              supplier!.status === "rejected" || supplier!.status === "suspended"
                ? "error"
                : "process"
            }
            items={[
              { title: t("messages.pending") },
              { title: t("messages.productAudit") },
              { title: supplier!.status === "rejected" ? t("messages.rejected") : t("messages.approved") },
            ]}
          />
        </Card>
      )}

      {/* Hidden evalForm to keep useForm connected when tab not rendered */}
      {isNew && (
        <div style={{ display: "none" }}>
          <Form form={evalForm} />
        </div>
      )}

      {/* Tabs */}
      <Tabs items={isNew ? tabItems.filter(t => t.key === "info") : tabItems} />

      {/* Certification Modal */}
      {!certModalOpen && (
        <div style={{ display: "none" }}>
          <Form form={certForm} />
        </div>
      )}
      <Modal
        title={certEditing ? t("modal.editCert") : t("modal.addCert")}
        open={certModalOpen}
        onCancel={() => setCertModalOpen(false)}
        onOk={handleCertSave}
        confirmLoading={certSaving}
        okText={tc("actions.save")}
        cancelText={tc("actions.cancel")}
        destroyOnHidden
      >
        <Form form={certForm} layout="vertical">
          <Form.Item
            label={t("form.certType")}
            name="cert_type"
            rules={[{ required: true, message: t("form.enterCertType") }]}
          >
            <Input placeholder={t("form.certTypePlaceholder")} />
          </Form.Item>
          <Form.Item
            label={t("form.certNo")}
            name="cert_no"
            rules={[{ required: true, message: t("form.enterCertNo") }]}
          >
            <Input />
          </Form.Item>
          <Form.Item label={t("form.issuedBy")} name="issued_by">
            <Input />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label={t("form.issueDate")} name="issue_date">
                <DatePicker style={{ width: "100%" }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label={t("form.expiryDate")} name="expiry_date">
                <DatePicker style={{ width: "100%" }} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      {/* Reject Modal */}
      <Modal
        title={t("messages.rejectReason")}
        open={rejectModalVisible}
        onCancel={() => setRejectModalVisible(false)}
        onOk={handleReject}
        confirmLoading={transitioning}
        okText={t("messages.confirmReject")}
        cancelText={tc("actions.cancel")}
        okButtonProps={{ danger: true }}
      >
        <TextArea
          rows={4}
          placeholder={t("messages.enterRejectReason")}
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
        />
      </Modal>

      {/* Suspend Modal */}
      <Modal
        title={t("messages.suspendReason")}
        open={suspendModalVisible}
        onCancel={() => setSuspendModalVisible(false)}
        onOk={handleSuspend}
        confirmLoading={transitioning}
        okText={t("messages.confirmSuspend")}
        cancelText={tc("actions.cancel")}
        okButtonProps={{ danger: true }}
      >
        <TextArea
          rows={4}
          placeholder={t("messages.enterSuspendReason")}
          value={suspendReason}
          onChange={(e) => setSuspendReason(e.target.value)}
        />
      </Modal>
    </div>
  );
}

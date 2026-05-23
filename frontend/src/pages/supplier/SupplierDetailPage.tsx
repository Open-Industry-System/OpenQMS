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
  Modal,
  Popconfirm,
  Row,
  Col,
  Steps,
  Slider,
  Spin,
  Typography,
} from "antd";
import {
  ArrowLeftOutlined,
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import type { Supplier, SupplierCertification, SupplierEvaluation, AuditPlan } from "../../types";
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

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending_review: { label: "待审核", color: "default" },
  audit_required: { label: "需审核", color: "processing" },
  approved: { label: "已批准", color: "success" },
  rejected: { label: "已拒绝", color: "error" },
  suspended: { label: "已暂停", color: "warning" },
};

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
  const { user } = useAuthStore();

  const isViewer = user?.role === "viewer";
  const isEngineerOrAbove =
    user?.role === "quality_engineer" ||
    user?.role === "manager" ||
    user?.role === "admin";
  const isManagerOrAdmin =
    user?.role === "manager" || user?.role === "admin";

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

  const loadSupplier = useCallback(async () => {
    if (!id || id === "new") return;
    setLoading(true);
    try {
      const s = await getSupplier(id);
      setSupplier(s);
    } catch {
      message.error("加载供应商信息失败");
    } finally {
      setLoading(false);
    }
  }, [id]);

  const loadCerts = useCallback(async () => {
    if (!id || id === "new") return;
    setCertsLoading(true);
    try {
      const data = await listCertifications(id);
      setCerts(data);
    } catch {
      message.error("加载证书失败");
    } finally {
      setCertsLoading(false);
    }
  }, [id]);

  const loadEvals = useCallback(async () => {
    if (!id || id === "new") return;
    setEvalsLoading(true);
    try {
      const data = await listEvaluations(id);
      setEvals(data);
    } catch {
      message.error("加载绩效评价失败");
    } finally {
      setEvalsLoading(false);
    }
  }, [id]);

  const loadAuditPlans = useCallback(async () => {
    try {
      const resp = await listAuditPlans({ page_size: 200 });
      setAuditPlans(resp.items);
    } catch {
      // non-critical
    }
  }, []);

  useEffect(() => {
    Promise.all([loadSupplier(), loadCerts(), loadEvals(), loadAuditPlans()]);
  }, [loadSupplier, loadCerts, loadEvals, loadAuditPlans]);

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
        message.success("供应商创建成功");
        navigate(`/suppliers/${created.supplier_id}`, { replace: true });
      } else {
        const updated = await updateSupplier(id!, values);
        setSupplier(updated);
        setEditing(false);
        message.success("保存成功");
      }
    } catch (err: unknown) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      console.error(err);
      message.error(isNew ? "创建失败" : "保存失败");
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
        message.success("证书已更新");
      } else {
        await createCertification(id, payload);
        message.success("证书已添加");
      }
      setCertModalOpen(false);
      await loadCerts();
    } catch (err: unknown) {
      if (err && typeof err === "object" && "errorFields" in err) return; // Ant Design form validation error
      console.error(err);
      message.error("保存证书失败");
    } finally {
      setCertSaving(false);
    }
  };

  const handleDeleteCert = async (certId: string) => {
    if (!id) return;
    try {
      await deleteCertification(id, certId);
      message.success("证书已删除");
      await loadCerts();
    } catch {
      message.error("删除证书失败");
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
      delete payload.capa_count;
      delete payload.finding_count;
      await createEvaluation(id, payload);
      message.success("评价已提交");
      evalForm.resetFields();
      evalForm.setFieldsValue({ quality_score: 80, delivery_score: 80, service_score: 80 });
      setEvalPreview(calcBaseScore(80, 80, 80));
      await loadEvals();
    } catch (err: unknown) {
      if (err && typeof err === "object" && "errorFields" in err) return; // Ant Design form validation error
      console.error(err);
      message.error("提交评价失败");
    } finally {
      setEvalSaving(false);
    }
  };

  const handleApprove = async () => {
    if (!id) return;
    setTransitioning(true);
    try {
      await approveSupplier(id);
      message.success("已批准准入");
      loadSupplier();
    } catch {
      message.error("操作失败");
    } finally {
      setTransitioning(false);
    }
  };

  const handleReject = async () => {
    if (!id) return;
    setTransitioning(true);
    try {
      await rejectSupplier(id, rejectReason);
      message.success("已拒绝");
      setRejectModalVisible(false);
      setRejectReason("");
      loadSupplier();
    } catch {
      message.error("操作失败");
    } finally {
      setTransitioning(false);
    }
  };

  const handleConfirmApproved = async () => {
    if (!id) return;
    setTransitioning(true);
    try {
      await confirmApproved(id);
      message.success("已确认批准");
      loadSupplier();
    } catch {
      message.error("操作失败");
    } finally {
      setTransitioning(false);
    }
  };

  const handleSuspend = async () => {
    if (!id) return;
    setTransitioning(true);
    try {
      await suspendSupplier(id, suspendReason);
      message.success("已暂停合作");
      setSuspendModalVisible(false);
      setSuspendReason("");
      loadSupplier();
    } catch {
      message.error("操作失败");
    } finally {
      setTransitioning(false);
    }
  };

  const handleReinstate = async () => {
    if (!id) return;
    setTransitioning(true);
    try {
      await reinstateSupplier(id);
      message.success("已恢复合作");
      loadSupplier();
    } catch {
      message.error("操作失败");
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
    return <div style={{ padding: 24 }}>供应商不存在</div>;
  }

  const statusInfo = supplier
    ? (STATUS_MAP[supplier.status] ?? { label: supplier.status, color: "default" })
    : { label: "新建", color: "processing" };

  // Cert table columns
  const certColumns = [
    { title: "证书类型", dataIndex: "cert_type", key: "cert_type" },
    { title: "证书编号", dataIndex: "cert_no", key: "cert_no" },
    { title: "颁发机构", dataIndex: "issued_by", key: "issued_by" },
    {
      title: "颁发日期",
      dataIndex: "issue_date",
      key: "issue_date",
      render: (v: string | null) => (v ? dayjs(v).format("YYYY-MM-DD") : "-"),
    },
    {
      title: "到期日期",
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
              <span style={{ marginLeft: 4, fontSize: 12 }}>({daysLeft}天)</span>
            )}
            {daysLeft < 0 && <span style={{ marginLeft: 4, fontSize: 12 }}>(已过期)</span>}
          </span>
        );
      },
    },
    ...(isEngineerOrAbove
      ? [
          {
            title: "操作",
            key: "action",
            render: (_: unknown, record: SupplierCertification) => (
              <Space>
                <Button
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => openCertModal(record)}
                >
                  编辑
                </Button>
                <Popconfirm
                  title="确认删除此证书？"
                  onConfirm={() => handleDeleteCert(record.cert_id)}
                >
                  <Button size="small" danger icon={<DeleteOutlined />}>
                    删除
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
      label: "基本信息",
      children: (
        <Card
          extra={
            !isViewer && (
              <Space>
                {editing ? (
                  <>
                    <Button onClick={handleCancelEdit}>取消</Button>
                    <Button type="primary" loading={saving} onClick={handleSaveInfo}>
                      保存
                    </Button>
                  </>
                ) : (
                  <Button icon={<EditOutlined />} onClick={() => setEditing(true)}>
                    编辑
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
              <strong>拒绝原因：</strong>
              {supplier.reject_reason}
            </div>
          )}
          {editing ? (
            <Form form={infoForm} layout="vertical">
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item label="供应商名称" name="name" rules={[{ required: true, message: "请输入名称" }]}>
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="简称" name="short_name" rules={[{ required: true, message: "请输入简称" }]}>
                    <Input />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16}>
                <Col span={8}>
                  <Form.Item label="联系人" name="contact_name">
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="联系电话" name="contact_phone">
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="联系邮箱" name="contact_email">
                    <Input />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item label="地址" name="address">
                <Input />
              </Form.Item>
              <Form.Item label="产品范围" name="product_scope">
                <TextArea rows={3} />
              </Form.Item>
              {supplier?.status === "audit_required" && (
                <Form.Item label="审核计划" name="audit_plan_id">
                  <Select allowClear placeholder="选择审核计划">
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
                <Text type="secondary">供应商编号</Text>
                <div>{supplier.supplier_no}</div>
              </Col>
              <Col span={12}>
                <Text type="secondary">供应商名称</Text>
                <div>{supplier.name}</div>
              </Col>
              <Col span={12}>
                <Text type="secondary">简称</Text>
                <div>{supplier.short_name}</div>
              </Col>
              <Col span={12}>
                <Text type="secondary">联系人</Text>
                <div>{supplier.contact_name ?? "-"}</div>
              </Col>
              <Col span={8}>
                <Text type="secondary">联系电话</Text>
                <div>{supplier.contact_phone ?? "-"}</div>
              </Col>
              <Col span={8}>
                <Text type="secondary">联系邮箱</Text>
                <div>{supplier.contact_email ?? "-"}</div>
              </Col>
              <Col span={24}>
                <Text type="secondary">地址</Text>
                <div>{supplier.address ?? "-"}</div>
              </Col>
              <Col span={24}>
                <Text type="secondary">产品范围</Text>
                <div style={{ whiteSpace: "pre-wrap" }}>{supplier.product_scope ?? "-"}</div>
              </Col>
              {supplier?.status === "audit_required" && (
                <Col span={24}>
                  <Text type="secondary">审核计划</Text>
                  <div>
                    {auditPlans.find((p) => p.audit_id === supplier.audit_plan_id)?.plan_no ??
                      (supplier.audit_plan_id ? supplier.audit_plan_id : "未指定")}
                  </div>
                </Col>
              )}
              <Col span={12}>
                <Text type="secondary">创建时间</Text>
                <div>{dayjs(supplier.created_at).format("YYYY-MM-DD HH:mm")}</div>
              </Col>
              <Col span={12}>
                <Text type="secondary">更新时间</Text>
                <div>{dayjs(supplier.updated_at).format("YYYY-MM-DD HH:mm")}</div>
              </Col>
            </Row>
          )}
        </Card>
      ),
    },
    {
      key: "certs",
      label: "资质证书",
      children: (
        <Card
          extra={
            isEngineerOrAbove && (
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => openCertModal()}
              >
                添加证书
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
      label: "绩效评价",
      children: (
        <Row gutter={24}>
          {/* Left: history list */}
          <Col span={12}>
            <Card title="历史评价记录" size="small">
              {evalsLoading ? (
                <div style={{ textAlign: "center", padding: 40 }}>
                  <Spin />
                </div>
              ) : evals.length === 0 ? (
                <div style={{ textAlign: "center", color: "#999", padding: 40 }}>暂无评价记录</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {evals.map((ev) => (
                    <Card
                      key={ev.eval_id}
                      size="small"
                      title={
                        <Space>
                          <span>{ev.eval_period}</span>
                          <Tag color={GRADE_COLORS[ev.grade]}>{ev.grade} 级</Tag>
                          <span style={{ fontWeight: 400, color: "#666" }}>
                            综合得分：{ev.total_score}
                          </span>
                          <Tag>{ev.eval_type === "quarterly" ? "季度评价" : "年度评价"}</Tag>
                        </Space>
                      }
                    >
                      <Row gutter={16}>
                        <Col span={8}>
                          <Text type="secondary">质量得分</Text>
                          <div>{ev.quality_score}</div>
                        </Col>
                        <Col span={8}>
                          <Text type="secondary">交付得分</Text>
                          <div>{ev.delivery_score}</div>
                        </Col>
                        <Col span={8}>
                          <Text type="secondary">服务得分</Text>
                          <div>{ev.service_score}</div>
                        </Col>
                        <Col span={8}>
                          <Text type="secondary">评价时间</Text>
                          <div>{dayjs(ev.created_at).format("YYYY-MM-DD")}</div>
                        </Col>
                        {(ev.capa_count > 0 || ev.finding_count > 0) && (
                          <>
                            <Col span={8}>
                              <Text type="secondary">CAPA数量</Text>
                              <div>{ev.capa_count}</div>
                            </Col>
                            <Col span={8}>
                              <Text type="secondary">发现问题数</Text>
                              <div>{ev.finding_count}</div>
                            </Col>
                          </>
                        )}
                        {ev.notes && (
                          <Col span={24}>
                            <Text type="secondary">备注</Text>
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
          {isEngineerOrAbove && (
            <Col span={12}>
              <Card title="新建评价" size="small">
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
                        label="评价周期"
                        name="eval_period"
                        rules={[{ required: true, message: "请输入评价周期" }]}
                      >
                        <Input placeholder="如: 2026-Q1" />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item
                        label="评价类型"
                        name="eval_type"
                        rules={[{ required: true, message: "请选择评价类型" }]}
                      >
                        <Select>
                          <Option value="quarterly">季度评价</Option>
                          <Option value="annual">年度评价</Option>
                        </Select>
                      </Form.Item>
                    </Col>
                  </Row>

                  <Form.Item label={`质量得分 (${evalForm.getFieldValue("quality_score") ?? 80})`} name="quality_score">
                    <Slider min={0} max={100} />
                  </Form.Item>
                  <Form.Item label={`交付得分 (${evalForm.getFieldValue("delivery_score") ?? 80})`} name="delivery_score">
                    <Slider min={0} max={100} />
                  </Form.Item>
                  <Form.Item label={`服务得分 (${evalForm.getFieldValue("service_score") ?? 80})`} name="service_score">
                    <Slider min={0} max={100} />
                  </Form.Item>

                  <div style={{ marginBottom: 16, color: "#888", fontSize: 13 }}>
                    CAPA 数与发现问题数：提交后由系统自动统计
                  </div>

                  <Form.Item label="备注" name="notes">
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
                      预计得分（不含系统扣分）：<strong>{evalPreview}</strong>
                    </div>
                  )}

                  <Form.Item>
                    <Button
                      type="primary"
                      loading={evalSaving}
                      onClick={handleEvalSave}
                      block
                    >
                      提交评价
                    </Button>
                  </Form.Item>
                </Form>
              </Card>
            </Col>
          )}
        </Row>
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
          返回
        </Button>
        <h2 style={{ margin: 0, fontSize: 20 }}>{isNew ? "新建供应商" : supplier!.name}</h2>
        {!isNew && <Tag color={statusInfo.color}>{statusInfo.label}</Tag>}
        {!isNew && supplier && isManagerOrAdmin && (
          <Space style={{ marginLeft: "auto" }}>
            {supplier.status === "pending_review" && (
              <>
                <Button
                  type="primary"
                  loading={transitioning}
                  onClick={handleApprove}
                >
                  批准准入
                </Button>
                <Button
                  danger
                  loading={transitioning}
                  onClick={() => { setRejectReason(""); setRejectModalVisible(true); }}
                >
                  拒绝
                </Button>
              </>
            )}
            {supplier.status === "audit_required" && (
              <>
                <Popconfirm
                  title="确认批准该供应商？"
                  onConfirm={handleConfirmApproved}
                  okText="确认"
                  cancelText="取消"
                >
                  <Button type="primary" loading={transitioning}>
                    确认批准
                  </Button>
                </Popconfirm>
                <Button
                  danger
                  loading={transitioning}
                  onClick={() => { setRejectReason(""); setRejectModalVisible(true); }}
                >
                  拒绝
                </Button>
              </>
            )}
            {supplier.status === "approved" && (
              <Button
                danger
                loading={transitioning}
                onClick={() => { setSuspendReason(""); setSuspendModalVisible(true); }}
              >
                暂停合作
              </Button>
            )}
            {supplier.status === "suspended" && (
              <Popconfirm
                title="确认恢复与该供应商的合作？"
                onConfirm={handleReinstate}
                okText="确认"
                cancelText="取消"
              >
                <Button type="primary" loading={transitioning}>
                  恢复合作
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
              { title: "待审核" },
              { title: "产品审核" },
              { title: supplier!.status === "rejected" ? "已拒绝" : "已批准" },
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
        title={certEditing ? "编辑证书" : "添加证书"}
        open={certModalOpen}
        onCancel={() => setCertModalOpen(false)}
        onOk={handleCertSave}
        confirmLoading={certSaving}
        okText="保存"
        cancelText="取消"
        destroyOnHidden
      >
        <Form form={certForm} layout="vertical">
          <Form.Item
            label="证书类型"
            name="cert_type"
            rules={[{ required: true, message: "请输入证书类型" }]}
          >
            <Input placeholder="如: ISO 9001, IATF 16949" />
          </Form.Item>
          <Form.Item
            label="证书编号"
            name="cert_no"
            rules={[{ required: true, message: "请输入证书编号" }]}
          >
            <Input />
          </Form.Item>
          <Form.Item label="颁发机构" name="issued_by">
            <Input />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="颁发日期" name="issue_date">
                <DatePicker style={{ width: "100%" }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="到期日期" name="expiry_date">
                <DatePicker style={{ width: "100%" }} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      {/* Reject Modal */}
      <Modal
        title="拒绝原因"
        open={rejectModalVisible}
        onCancel={() => setRejectModalVisible(false)}
        onOk={handleReject}
        confirmLoading={transitioning}
        okText="确认拒绝"
        cancelText="取消"
        okButtonProps={{ danger: true }}
      >
        <TextArea
          rows={4}
          placeholder="请输入拒绝原因"
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
        />
      </Modal>

      {/* Suspend Modal */}
      <Modal
        title="暂停合作原因"
        open={suspendModalVisible}
        onCancel={() => setSuspendModalVisible(false)}
        onOk={handleSuspend}
        confirmLoading={transitioning}
        okText="确认暂停"
        cancelText="取消"
        okButtonProps={{ danger: true }}
      >
        <TextArea
          rows={4}
          placeholder="请输入暂停原因"
          value={suspendReason}
          onChange={(e) => setSuspendReason(e.target.value)}
        />
      </Modal>
    </div>
  );
}

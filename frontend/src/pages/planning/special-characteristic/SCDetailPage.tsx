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
import {
  getSC, updateSC, createSC,
  safetySubmit, safetyApprove, safetyReject, safetyCancel,
} from "../../../api/specialCharacteristic";
import type { SpecialCharacteristic } from "../../../types";
import { useAuthStore } from "../../../store/authStore";
import { usePermission } from "../../../hooks/usePermission";
import PageShell from "../../../components/design/PageShell";
import DataCard from "../../../components/design/DataCard";
import StatusBadge from "../../../components/design/StatusBadge";

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
      .catch(() => message.error("加载特殊特性失败"))
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, isNew]);

  const handleSave = async (values: Partial<SpecialCharacteristic>) => {
    setSaving(true);
    try {
      if (isNew) {
        const created = await createSC(values);
        message.success("创建成功");
        navigate(`/special-characteristics/${created.sc_id}`, { replace: true });
      } else {
        if (!id) return;
        const updated = await updateSC(id, values);
        setSc(updated);
        message.success("保存成功");
      }
    } catch {
      message.error(isNew ? "创建失败" : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleSafetyToggle = async (checked: boolean) => {
    if (!sc || !id || isNew) return;
    if (!checked) {
      if (!canApprove('special_characteristic')) {
        message.error("仅管理员或经理可取消安全标记");
        return;
      }
      try {
        const updated = await safetyCancel(id);
        setSc(updated);
        setSafetyPanelOpen(false);
        message.success("已取消安全标记");
      } catch {
        message.error("取消失败");
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
      message.success("安全特性已提交审批");
    } catch (err: any) {
      message.error(err.response?.data?.detail || "提交失败");
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
      message.success("已批准");
    } catch {
      message.error("审批失败");
    } finally {
      setApprovalLoading(false);
    }
  };

  const handleSafetyReject = async () => {
    if (!id || isNew || !canApprove('special_characteristic')) return;
    setApprovalLoading(true);
    try {
      const updated = await safetyReject(id, "审批驳回");
      setSc(updated);
      message.success("已驳回");
    } catch {
      message.error("驳回失败");
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
    return <div>未找到特殊特性</div>;
  }

  return (
    <PageShell
      title={
        isNew ? "新建特殊特性" : (
          <Space size={12}>
            {`${sc!.sc_code} - ${sc!.sc_name}`}
            <StatusBadge status={scTypeVariant(sc!.sc_type)}>{sc!.sc_type}</StatusBadge>
          </Space>
        )
      }
      subtitle={isNew ? undefined : `产品线：${sc!.product_line_code}`}
      actions={
        <Button
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate("/special-characteristics")}
        >
          返回列表
        </Button>
      }
    >
      <Row gutter={16}>
        {/* Left: Read-only info (edit mode only) */}
        {!isNew && (
          <Col span={10}>
            <DataCard title="基本信息" style={{ marginBottom: 16 }}>
              <Descriptions column={1} size="small">
                <Descriptions.Item label="SC编号">
                  {sc!.sc_code}
                </Descriptions.Item>
                <Descriptions.Item label="类型">
                  <StatusBadge status={scTypeVariant(sc!.sc_type)}>
                    {sc!.sc_type === "CC" ? "关键特性 (CC)" : "重要特性 (SC)"}
                  </StatusBadge>
                </Descriptions.Item>
                <Descriptions.Item label="产品线">
                  {sc!.product_line_code}
                </Descriptions.Item>
                <Descriptions.Item label="来源类型">
                  <StatusBadge status={sourceTypeVariant(sc!.source_type)}>
                    {sc!.source_type}
                  </StatusBadge>
                </Descriptions.Item>
                <Descriptions.Item label="来源FMEA文档">
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
                <Descriptions.Item label="来源节点ID">
                  <Text copyable>{sc!.source_node_id}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="父级特性">
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
                <Descriptions.Item label="MSA状态">
                  <StatusBadge status={msaStatusVariant(sc!.msa_status)}>
                    {sc!.msa_status}
                  </StatusBadge>
                </Descriptions.Item>
              </Descriptions>
            </DataCard>

            {/* Source FMEA info */}
            {sc!.source_fmea_title && (
              <DataCard title="来源FMEA信息">
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="FMEA标题">
                    {sc!.source_fmea_title}
                  </Descriptions.Item>
                  <Descriptions.Item label="文档编号">
                    {sc!.source_fmea_document_no}
                  </Descriptions.Item>
                  <Descriptions.Item label="查看FMEA">
                    <Button
                      type="primary"
                      size="small"
                      onClick={() => navigate(`/fmea/${sc!.source_fmea_id}`)}
                    >
                      打开FMEA编辑器
                    </Button>
                  </Descriptions.Item>
                </Descriptions>
              </DataCard>
            )}
          </Col>
        )}

        {/* Right: Editable form */}
        <Col span={isNew ? 24 : 14}>
          <DataCard title={isNew ? "创建信息" : "编辑信息"}>
            <Form
              form={form}
              layout="vertical"
              onFinish={handleSave}
              disabled={!canEdit('special_characteristic')}
            >
              {isNew && (
                <Form.Item
                  name="sc_type"
                  label="特性类型"
                  rules={[{ required: true, message: "请选择特性类型" }]}
                >
                  <Select placeholder="请选择">
                    <Select.Option value="CC">关键特性 (CC)</Select.Option>
                    <Select.Option value="SC">重要特性 (SC)</Select.Option>
                  </Select>
                </Form.Item>
              )}

              <Form.Item
                name="sc_name"
                label="特性名称"
                rules={[{ required: true, message: "请输入特性名称" }]}
              >
                <Input placeholder="请输入特性名称" />
              </Form.Item>

              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="sc_category" label="特性分类">
                    <Select placeholder="请选择" allowClear>
                      <Select.Option value="产品特性">
                        产品特性
                      </Select.Option>
                      <Select.Option value="过程特性">
                        过程特性
                      </Select.Option>
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="customer_symbol" label="客户符号">
                    <Input placeholder="客户特殊符号标识" />
                  </Form.Item>
                </Col>
              </Row>

              <Form.Item name="spec_requirement" label="规格要求">
                <TextArea rows={4} placeholder="请输入规格要求" />
              </Form.Item>

              <Form.Item name="sop_ref" label="SOP参考">
                <Input placeholder="SOP文档编号" />
              </Form.Item>

              <Row gutter={16}>
                <Col span={8}>
                  <Form.Item
                    name="is_supplier_shared"
                    label="供应商共享"
                    valuePropName="checked"
                  >
                    <Switch />
                  </Form.Item>
                </Col>
                <Col span={16}>
                  <Form.Item name="supplier_code" label="供应商代码">
                    <Input placeholder="供应商代码" />
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
                    保存
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
                    <span>安全特性</span>
                    {sc.safety_approval_status && (
                      <StatusBadge status={safetyStatusVariant(sc.safety_approval_status)}>
                        {sc.safety_approval_status === "pending" && "待提交"}
                        {sc.safety_approval_status === "submitted" && "待审批"}
                        {sc.safety_approval_status === "approved" && "已批准"}
                        {sc.safety_approval_status === "rejected" && "已驳回"}
                      </StatusBadge>
                    )}
                  </Space>
                }
                key="safety"
              >
                <Space direction="vertical" style={{ width: "100%" }}>
                  <Form.Item label="安全相关">
                    <Switch
                      checked={sc.is_safety_related}
                      onChange={handleSafetyToggle}
                      disabled={!canEdit('special_characteristic') || (sc.safety_approval_status === "submitted" && !canApprove('special_characteristic'))}
                    />
                  </Form.Item>

                  {sc.is_safety_related && (
                    <>
                      <StatusBadge status="info">待模块上线后自动切换</StatusBadge>
                      <Form
                        form={safetyForm}
                        layout="vertical"
                        onFinish={handleSafetySubmit}
                        disabled={!canEdit('special_characteristic') || sc.safety_approval_status === "submitted" || sc.safety_approval_status === "approved"}
                      >
                        <Form.Item
                          name="safety_regulation_ref"
                          label="安全法规引用"
                          rules={[{ required: true, message: "请输入法规引用" }]}
                        >
                          <Input placeholder="例：UN ECE R100, GB/T 18384" />
                        </Form.Item>
                        <Form.Item
                          name="safety_verification_method"
                          label="安全验证方法"
                          rules={[{ required: true, message: "请输入验证方法" }]}
                        >
                          <TextArea rows={3} placeholder="例：100% 高压绝缘测试" />
                        </Form.Item>
                        {sc.safety_approval_status === "pending" && !!canEdit('special_characteristic') && (
                          <Button type="primary" htmlType="submit" loading={approvalLoading}>
                            提交审批
                          </Button>
                        )}
                      </Form>

                      {/* Approval Timeline */}
                      {sc.safety_approval_status && (
                        <Timeline
                          items={[
                            {
                              dot: <ExclamationCircleOutlined style={{ color: "#faad14" }} />,
                              children: "待提交：填写安全信息并提交审批",
                              color: sc.safety_approval_status === "pending" ? "blue" : "gray",
                            },
                            {
                              dot: <SafetyCertificateOutlined style={{ color: "#1677ff" }} />,
                              children: `已提交：${sc.safety_submitted_at ? new Date(sc.safety_submitted_at).toLocaleString() : "-"}`,
                              color: sc.safety_approval_status === "submitted" ? "blue" : "gray",
                            },
                            sc.safety_approval_status === "approved" ? {
                              dot: <CheckCircleOutlined style={{ color: "#52c41a" }} />,
                              children: `已批准：${sc.safety_approved_at ? new Date(sc.safety_approved_at).toLocaleString() : "-"}`,
                              color: "green",
                            } : sc.safety_approval_status === "rejected" ? {
                              dot: <CloseCircleOutlined style={{ color: "#ff4d4f" }} />,
                              children: `已驳回：${sc.safety_approved_at ? new Date(sc.safety_approved_at).toLocaleString() : "-"}${sc.safety_approval_comment ? `（${sc.safety_approval_comment}）` : ""}`,
                              color: "red",
                            } : {
                              dot: <SafetyCertificateOutlined />,
                              children: "审批结果",
                              color: "gray",
                            },
                          ].filter(Boolean) as any}
                        />
                      )}

                      {/* Approval Actions for manager/admin */}
                      {sc.safety_approval_status === "submitted" && canApprove('special_characteristic') && (
                        <Space>
                          <Button type="primary" onClick={handleSafetyApprove} loading={approvalLoading}>
                            批准
                          </Button>
                          <Button danger onClick={handleSafetyReject} loading={approvalLoading}>
                            驳回
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

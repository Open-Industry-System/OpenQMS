import { useState, useEffect, useCallback } from "react";
import {
  Card, Button, Tag, Space, Form, Input, Select, DatePicker, App,
  Tabs, Table, Modal, Popconfirm, Row, Col, Statistic, Descriptions,
  Upload, Typography,
} from "antd";
import {
  ArrowLeftOutlined, PlayCircleOutlined, CheckCircleOutlined, StopOutlined,
  PlusOutlined, DeleteOutlined, LinkOutlined, CheckOutlined, UploadOutlined,
  MinusCircleOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";
import type { AuditPlan, AuditFinding, User } from "../../types";
import {
  getAuditPlan, startAuditPlan, completeAuditPlan, cancelAuditPlan,
  listAuditFindings, createAuditFinding, updateAuditFinding,
  createCAPAFromFinding, transitionFinding, confirmCustomerFinding,
  confirmCustomerAudit,
} from "../../api/audit";
import { listUsers } from "../../api/auth";
import dayjs from "dayjs";

const { Option } = Select;
const { Text } = Typography;

const statusLabel: Record<string, string> = {
  planned: "已计划", in_progress: "进行中", completed: "已完成", cancelled: "已取消",
};
const statusColor: Record<string, string> = {
  planned: "blue", in_progress: "processing", completed: "success", cancelled: "default",
};
const findingStatusLabel: Record<string, string> = {
  open: "已开立", in_progress: "整改中", closed: "已关闭",
};
const findingStatusColor: Record<string, string> = {
  open: "error", in_progress: "processing", closed: "success",
};
const findingTypeLabel: Record<string, string> = {
  major_nc: "严重不符合", minor_nc: "一般不符合", ofi: "改进机会", observation: "观察项",
};
const auditModeLabel: Record<string, string> = { on_site: "现场", remote: "远程" };

export default function CustomerAuditDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const { canEdit, canApprove } = usePermission();

  const [plan, setPlan] = useState<AuditPlan | null>(null);
  const [findings, setFindings] = useState<AuditFinding[]>([]);
  const [loading, setLoading] = useState(false);
  const [findingModalOpen, setFindingModalOpen] = useState(false);
  const [editingFinding, setEditingFinding] = useState<AuditFinding | null>(null);
  const [confirmModalOpen, setConfirmModalOpen] = useState(false);
  const [confirmFindingId, setConfirmFindingId] = useState<string | null>(null);
  const [confirmAttachments, setConfirmAttachments] = useState<{ file_name: string; file_url: string }[]>([]);
  const [planConfirmModalOpen, setPlanConfirmModalOpen] = useState(false);
  const [users, setUsers] = useState<User[]>([]);
  const [findingForm] = Form.useForm();
  const [confirmForm] = Form.useForm();
  const [planConfirmForm] = Form.useForm();

  const fetchPlan = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [p, f] = await Promise.all([
        getAuditPlan(id),
        listAuditFindings({ audit_id: id, page_size: 1000 }),
      ]);
      setPlan(p);
      setFindings(f.items);
    } catch {
      message.error("加载失败");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { fetchPlan(); }, [fetchPlan]);
  useEffect(() => { listUsers().then(setUsers).catch(() => {}); }, []);

  const handlePlanAction = async (action: string) => {
    if (!id) return;
    try {
      if (action === "start") await startAuditPlan(id);
      else if (action === "complete") await completeAuditPlan(id);
      else if (action === "cancel") await cancelAuditPlan(id);
      message.success("操作成功");
      fetchPlan();
    } catch (e: unknown) {
      message.error((e as Error).message || "操作失败");
    }
  };

  const handleCreateFinding = async () => {
    try {
      const values = await findingForm.validateFields();
      if (editingFinding) {
        await updateAuditFinding(editingFinding.finding_id, values);
        message.success("更新成功");
      } else {
        await createAuditFinding({ ...values, audit_id: id });
        message.success("创建成功");
      }
      setFindingModalOpen(false);
      findingForm.resetFields();
      setEditingFinding(null);
      fetchPlan();
    } catch (e: unknown) {
      if (e && typeof e === "object" && "errorFields" in e) return;
      message.error((e as Error).message || "操作失败");
    }
  };

  const handleTransition = async (findingId: string, action: "start_progress" | "close") => {
    try {
      await transitionFinding(findingId, { action });
      message.success("操作成功");
      fetchPlan();
    } catch (e: unknown) {
      message.error((e as Error).message || "操作失败");
    }
  };

  const handleCustomerConfirm = async () => {
    try {
      const values = await confirmForm.validateFields();
      const date = values.confirmation_date.format("YYYY-MM-DD");
      const attachments = confirmAttachments
        .filter((a) => a.file_name.trim() && a.file_url.trim())
        .map((a) => ({ file_name: a.file_name.trim(), file_url: a.file_url.trim() }));
      if (confirmFindingId) {
        await confirmCustomerFinding(confirmFindingId, {
          confirmation_date: date,
          attachments,
        });
      }
      message.success("确认成功");
      setConfirmModalOpen(false);
      confirmForm.resetFields();
      setConfirmFindingId(null);
      setConfirmAttachments([]);
      fetchPlan();
    } catch (e: unknown) {
      if (e && typeof e === "object" && "errorFields" in e) return;
      message.error((e as Error).message || "确认失败");
    }
  };

  const handlePlanConfirm = async () => {
    try {
      const values = await planConfirmForm.validateFields();
      if (!id) return;
      const date = values.confirmation_date.format("YYYY-MM-DD");
      const attachments = (values.attachments || [])
        .filter((a: { file_name?: string; file_url?: string }) => a.file_name?.trim() && a.file_url?.trim())
        .map((a: { file_name: string; file_url: string }) => ({ file_name: a.file_name.trim(), file_url: a.file_url.trim() }));
      await confirmCustomerAudit(id, { confirmation_date: date, attachments });
      message.success("审核确认成功");
      setPlanConfirmModalOpen(false);
      planConfirmForm.resetFields();
      fetchPlan();
    } catch (e: unknown) {
      if (e && typeof e === "object" && "errorFields" in e) return;
      message.error((e as Error).message || "确认失败");
    }
  };

  const openEditFinding = (f: AuditFinding) => {
    setEditingFinding(f);
    findingForm.setFieldsValue({
      clause_ref: f.clause_ref,
      finding_type: f.finding_type,
      description: f.description,
      root_cause: f.root_cause,
      correction: f.correction,
      corrective_action: f.corrective_action,
      due_date: f.due_date ? dayjs(f.due_date) : undefined,
    });
    setFindingModalOpen(true);
  };

  const findingColumns = [
    { title: "条款", dataIndex: "clause_ref", key: "clause_ref", width: 100, render: (v: string) => v || "-" },
    { title: "类型", dataIndex: "finding_type", key: "finding_type", width: 110,
      render: (v: string) => findingTypeLabel[v] || v },
    { title: "描述", dataIndex: "description", key: "description", ellipsis: true },
    { title: "根本原因", dataIndex: "root_cause", key: "root_cause", ellipsis: true, render: (v: string) => v || "-" },
    { title: "纠正措施", dataIndex: "corrective_action", key: "corrective_action", ellipsis: true, render: (v: string) => v || "-" },
    { title: "状态", dataIndex: "status", key: "status", width: 90,
      render: (v: string) => <Tag color={findingStatusColor[v]}>{findingStatusLabel[v]}</Tag> },
    { title: "客户确认", dataIndex: "customer_confirmed", key: "customer_confirmed", width: 90,
      render: (v: boolean) => v ? <Tag color="success">已确认</Tag> : <Tag color="warning">待确认</Tag> },
    { title: "CAPA", dataIndex: "capa_ref_id", key: "capa_ref_id", width: 80,
      render: (v: string) => v ? <Tag color="blue" style={{ cursor: "pointer" }} onClick={() => navigate(`/capa/${v}`)}>查看</Tag> : "-" },
    {
      title: "操作", key: "finding_actions", width: 280,
      render: (_: unknown, record: AuditFinding) => (
        <Space size="small">
          {canEdit('customer_audit') && <Button size="small" onClick={() => openEditFinding(record)}>编辑</Button>}
          {record.status === "open" && canEdit('customer_audit') && (
            <Button size="small" type="default" onClick={() => handleTransition(record.finding_id, "start_progress")}>开始整改</Button>
          )}
          {record.status === "in_progress" && canEdit('customer_audit') && (
            <Popconfirm title="确认关闭？需满足所有关闭条件" onConfirm={() => handleTransition(record.finding_id, "close")}>
              <Button size="small" type="primary">关闭</Button>
            </Popconfirm>
          )}
          {!record.customer_confirmed && canEdit('customer_audit') && (
            <Button size="small" icon={<CheckOutlined />}
              onClick={() => { setConfirmFindingId(record.finding_id); setConfirmAttachments([]); setConfirmModalOpen(true); }}>
              客户确认
            </Button>
          )}
          {!record.capa_ref_id && canEdit('customer_audit') && record.finding_type === "major_nc" && (
            <Popconfirm title="是否创建 CAPA？" onConfirm={async () => {
              try { await createCAPAFromFinding(record.finding_id); message.success("CAPA 已创建"); fetchPlan(); }
              catch (e: unknown) { message.error((e as Error).message || "创建失败"); }
            }}>
              <Button size="small" icon={<LinkOutlined />}>CAPA</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  if (!plan) return null;

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/customer-audits")}>返回列表</Button>
      </div>

      <Card loading={loading}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
          <h3 style={{ margin: 0 }}>{plan.plan_no} - {plan.customer_name}</h3>
          <Space>
            {plan.status === "planned" && canEdit('customer_audit') && (
              <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => handlePlanAction("start")}>开始审核</Button>
            )}
            {plan.status === "in_progress" && canApprove('customer_audit') && (
              <>
                <Button type="primary" icon={<CheckCircleOutlined />} onClick={() => handlePlanAction("complete")}>完成审核</Button>
                <Button danger icon={<StopOutlined />} onClick={() => handlePlanAction("cancel")}>取消</Button>
              </>
            )}
            <Tag color={statusColor[plan.status]} style={{ fontSize: 14, padding: "4px 12px" }}>
              {statusLabel[plan.status]}
            </Tag>
          </Space>
        </div>

        <Descriptions column={3} bordered size="small">
          <Descriptions.Item label="客户名称">{plan.customer_name}</Descriptions.Item>
          <Descriptions.Item label="客户类型">{plan.customer_type}</Descriptions.Item>
          <Descriptions.Item label="审核方式">{plan.audit_mode ? auditModeLabel[plan.audit_mode] : "-"}</Descriptions.Item>
          <Descriptions.Item label="审核范围" span={2}>{plan.audit_scope}</Descriptions.Item>
          <Descriptions.Item label="计划日期">{plan.planned_date}</Descriptions.Item>
          <Descriptions.Item label="审核准则" span={3}>{plan.audit_criteria}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card style={{ marginTop: 16 }}>
        <Tabs items={[
          {
            key: "findings",
            label: `发现项 (${findings.length})`,
            children: (
              <>
                <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
                  {canEdit('customer_audit') && (
                    <Button type="primary" icon={<PlusOutlined />}
                      onClick={() => { setEditingFinding(null); findingForm.resetFields(); setFindingModalOpen(true); }}>
                      新增发现项
                    </Button>
                  )}
                </div>
                <Table
                  rowKey="finding_id"
                  columns={findingColumns}
                  dataSource={findings}
                  pagination={false}
                  size="small"
                  scroll={{ x: 1200 }}
                />
              </>
            ),
          },
          {
            key: "confirmation",
            label: "确认凭证",
            children: (
              <div>
                <Row gutter={16}>
                  <Col span={8}>
                    <Statistic
                      title="已确认发现项"
                      value={findings.filter((f) => f.customer_confirmed).length}
                      suffix={`/ ${findings.length}`}
                      valueStyle={{ color: "#52c41a" }}
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="待确认发现项"
                      value={findings.filter((f) => !f.customer_confirmed && f.status !== "closed").length}
                      valueStyle={{ color: "#faad14" }}
                    />
                  </Col>
                  <Col span={8}>
                    <div style={{ marginTop: 32 }}>
                      {canEdit('customer_audit') && (
                        <Button type="primary" icon={<UploadOutlined />} onClick={() => setPlanConfirmModalOpen(true)}>
                          上传审核级确认函
                        </Button>
                      )}
                    </div>
                  </Col>
                </Row>
                {plan.customer_confirmation_doc && plan.customer_confirmation_doc.length > 0 && (
                  <div style={{ marginTop: 16 }}>
                    <Text strong>审核确认附件：</Text>
                    <ul>
                      {plan.customer_confirmation_doc.map((a, i) => (
                        <li key={i}>{a.file_name}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ),
          },
        ]} />
      </Card>

      {/* Create/Edit Finding Modal */}
      <Modal
        title={editingFinding ? "编辑发现项" : "新增发现项"}
        open={findingModalOpen}
        onOk={handleCreateFinding}
        onCancel={() => { setFindingModalOpen(false); findingForm.resetFields(); setEditingFinding(null); }}
        width={640}
      >
        <Form form={findingForm} layout="vertical">
          <Form.Item name="finding_type" label="发现类型" rules={[{ required: true }]}>
            <Select>
              <Option value="major_nc">严重不符合</Option>
              <Option value="minor_nc">一般不符合</Option>
              <Option value="ofi">改进机会</Option>
              <Option value="observation">观察项</Option>
            </Select>
          </Form.Item>
          <Form.Item name="clause_ref" label="条款号">
            <Input placeholder="如 8.5.1" />
          </Form.Item>
          <Form.Item name="description" label="不符合描述" rules={[{ required: true }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="root_cause" label="根本原因">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="correction" label="纠正">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="corrective_action" label="纠正措施">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="due_date" label="截止日期">
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Customer Confirm Modal */}
      <Modal
        title="客户确认整改完成"
        open={confirmModalOpen}
        onOk={handleCustomerConfirm}
        onCancel={() => { setConfirmModalOpen(false); confirmForm.resetFields(); setConfirmFindingId(null); setConfirmAttachments([]); }}
      >
        <Form form={confirmForm} layout="vertical">
          <Form.Item name="confirmation_date" label="确认日期" rules={[{ required: true }]}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <div style={{ marginBottom: 8 }}>
            <Text strong>确认附件</Text>
            {confirmAttachments.map((a, i) => (
              <div key={i} style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <Input
                  placeholder="文件名称"
                  value={a.file_name}
                  onChange={(e) => {
                    const next = [...confirmAttachments];
                    next[i].file_name = e.target.value;
                    setConfirmAttachments(next);
                  }}
                />
                <Input
                  placeholder="文件链接"
                  value={a.file_url}
                  onChange={(e) => {
                    const next = [...confirmAttachments];
                    next[i].file_url = e.target.value;
                    setConfirmAttachments(next);
                  }}
                />
                <Button
                  icon={<MinusCircleOutlined />}
                  danger
                  onClick={() => setConfirmAttachments(confirmAttachments.filter((_, idx) => idx !== i))}
                />
              </div>
            ))}
            <Button
              type="dashed"
              icon={<PlusOutlined />}
              style={{ marginTop: 8, width: "100%" }}
              onClick={() => setConfirmAttachments([...confirmAttachments, { file_name: "", file_url: "" }])}
            >
              添加附件
            </Button>
          </div>
        </Form>
      </Modal>

      {/* Plan Confirm Modal */}
      <Modal
        title="上传审核级确认函"
        open={planConfirmModalOpen}
        onOk={handlePlanConfirm}
        onCancel={() => { setPlanConfirmModalOpen(false); planConfirmForm.resetFields(); }}
      >
        <Form form={planConfirmForm} layout="vertical">
          <Form.Item name="confirmation_date" label="确认日期" rules={[{ required: true }]} initialValue={dayjs()}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.List name="attachments">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <div key={key} style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                    <Form.Item {...restField} name={[name, "file_name"]} rules={[{ required: true }]} style={{ flex: 1, marginBottom: 0 }}>
                      <Input placeholder="文件名称" />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, "file_url"]} rules={[{ required: true }]} style={{ flex: 1, marginBottom: 0 }}>
                      <Input placeholder="文件链接" />
                    </Form.Item>
                    <Button icon={<MinusCircleOutlined />} danger onClick={() => remove(name)} />
                  </div>
                ))}
                <Button type="dashed" icon={<PlusOutlined />} style={{ width: "100%" }} onClick={() => add()}>
                  添加附件
                </Button>
              </>
            )}
          </Form.List>
        </Form>
      </Modal>
    </div>
  );
}

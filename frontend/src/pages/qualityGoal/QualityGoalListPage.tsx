import { useState, useEffect, useCallback } from "react";
import {
  Card,
  Table,
  Button,
  Tag,
  Space,
  Modal,
  Form,
  Input,
  Select,
  App,
  Tabs,
  Row,
  Col,
  Statistic,
  Popconfirm,
  Tooltip,
} from "antd";
import {
  PlusOutlined,
  CheckOutlined,
  CloseOutlined,
  SendOutlined,
  RollbackOutlined,
  InboxOutlined,
  EditOutlined,
  DeleteOutlined,
} from "@ant-design/icons";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";
import { useProductLineStore } from "../../store/productLineStore";
import type { QualityGoal } from "../../types";
import {
  listQualityGoals,
  createQualityGoal,
  updateQualityGoal,
  deleteQualityGoal,
  submitQualityGoal,
  withdrawQualityGoal,
  approveQualityGoal,
  rejectQualityGoal,
  archiveQualityGoal,
  updateActualValue,
  getQualityGoalStats,
} from "../../api/qualityGoal";
import { listUsers } from "../../api/auth";
import type { User } from "../../types";

const { Option } = Select;

const LEVEL_MAP: Record<number, { label: string; color: string; icon: string }> = {
  1: { label: "公司级", color: "blue", icon: "🏢" },
  2: { label: "产品线级", color: "green", icon: "🏭" },
  3: { label: "过程级", color: "orange", icon: "🔧" },
};

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft: { label: "草稿", color: "default" },
  pending: { label: "待审批", color: "gold" },
  active: { label: "生效中", color: "success" },
  archived: { label: "已停用", color: "default" },
};

function parseTargetValue(value: string): { operator: string; threshold: number } {
  const v = value.trim();
  if (v.startsWith("≤")) return { operator: "<=", threshold: parseFloat(v.slice(1).replace("%", "")) };
  if (v.startsWith("≥")) return { operator: ">=", threshold: parseFloat(v.slice(1).replace("%", "")) };
  if (v.startsWith("<=")) return { operator: "<=", threshold: parseFloat(v.slice(2).replace("%", "")) };
  if (v.startsWith(">=")) return { operator: ">=", threshold: parseFloat(v.slice(2).replace("%", "")) };
  return { operator: "<=", threshold: parseFloat(v.replace("%", "")) };
}

function checkAchievement(target: string, actual: string | null): "achieved" | "not_achieved" | "pending" {
  if (!actual) return "pending";
  const { operator, threshold } = parseTargetValue(target);
  const actualNum = parseFloat(actual.replace("%", ""));
  if (isNaN(actualNum) || isNaN(threshold)) return "pending";
  if (operator === "<=") return actualNum <= threshold ? "achieved" : "not_achieved";
  if (operator === ">=") return actualNum >= threshold ? "achieved" : "not_achieved";
  return "pending";
}

function getProgressPercent(target: string, actual: string | null): number {
  if (!actual) return 0;
  const { operator, threshold } = parseTargetValue(target);
  const actualNum = parseFloat(actual.replace("%", ""));
  if (isNaN(actualNum) || isNaN(threshold) || threshold === 0) return 0;
  if (operator === ">=") return Math.min((actualNum / threshold) * 100, 100);
  if (operator === "<=") return Math.min((actualNum / threshold) * 100, 100);
  return 0;
}

export default function QualityGoalListPage() {
  const { message } = App.useApp();
  const user = useAuthStore((s) => s.user);
  const { canEdit, canApprove } = usePermission();
  const productLine = useProductLineStore((s) => s.selected);

  const [goals, setGoals] = useState<QualityGoal[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [activeTab, setActiveTab] = useState("all");
  const [modalOpen, setModalOpen] = useState(false);
  const [editingGoal, setEditingGoal] = useState<QualityGoal | null>(null);
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [rejectingGoalId, setRejectingGoalId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [users, setUsers] = useState<User[]>([]);
  const [parentGoals, setParentGoals] = useState<QualityGoal[]>([]);
  const [stats, setStats] = useState({ total: 0, active: 0, pending: 0, achieved: 0 });
  const [form] = Form.useForm();

  const loadParentGoals = useCallback(async (targetLevel: number) => {
    if (targetLevel <= 1) {
      setParentGoals([]);
      return;
    }
    try {
      const resp = await listQualityGoals({
        level: targetLevel - 1,
        page_size: 1000,
      });
      setParentGoals(resp.items);
    } catch {
      setParentGoals([]);
    }
  }, []);

  const fetchGoals = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page, page_size: pageSize };
      if (productLine) params.product_line = productLine;
      if (activeTab === "pending") params.status = "pending";
      else if (activeTab === "draft") params.status = "draft";
      const [resp, s] = await Promise.all([
        listQualityGoals(params),
        getQualityGoalStats(),
      ]);
      let items = resp.items;
      if (activeTab === "my") {
        items = items.filter((g) => g.owner_id === user?.user_id);
      }
      setGoals(items);
      setTotal(resp.total);
      setStats(s);
    } catch {
      message.error("加载数据失败");
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, activeTab, user?.user_id, productLine]);

  useEffect(() => {
    fetchGoals();
  }, [fetchGoals]);

  useEffect(() => {
    listUsers().then(setUsers).catch(() => {});
  }, []);

  const handleCreate = () => {
    setEditingGoal(null);
    form.resetFields();
    loadParentGoals(1);
    setModalOpen(true);
  };

  const handleEdit = (goal: QualityGoal) => {
    setEditingGoal(goal);
    form.setFieldsValue({
      parent_id: goal.parent_id,
      level: goal.level,
      product_line_code: goal.product_line_code,
      name: goal.name,
      target_value: goal.target_value,
      unit: goal.unit,
      period: goal.period,
      owner_id: goal.owner_id,
      description: goal.description,
    });
    loadParentGoals(goal.level);
    setModalOpen(true);
  };

  const handleSubmitForm = async (values: Record<string, unknown>) => {
    try {
      if (editingGoal) {
        await updateQualityGoal(editingGoal.goal_id, {
          name: values.name as string,
          target_value: values.target_value as string,
          unit: values.unit as string,
          period: values.period as string,
          owner_id: values.owner_id as string,
          description: values.description as string | null,
        });
        message.success("更新成功");
      } else {
        await createQualityGoal({
          parent_id: (values.parent_id as string) || null,
          level: values.level as number,
          product_line_code: (values.product_line_code as string) || null,
          name: values.name as string,
          target_value: values.target_value as string,
          unit: values.unit as string,
          period: values.period as string,
          owner_id: values.owner_id as string,
          description: (values.description as string) || null,
        });
        message.success("创建成功");
      }
      setModalOpen(false);
      fetchGoals();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "操作失败");
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteQualityGoal(id);
      message.success("删除成功");
      fetchGoals();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "删除失败");
    }
  };

  const handleSubmitForApproval = async (id: string) => {
    try {
      await submitQualityGoal(id);
      message.success("已提交审批");
      fetchGoals();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "提交失败");
    }
  };

  const handleWithdraw = async (id: string) => {
    try {
      await withdrawQualityGoal(id);
      message.success("已撤回");
      fetchGoals();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "撤回失败");
    }
  };

  const handleApprove = async (id: string) => {
    try {
      await approveQualityGoal(id);
      message.success("审批通过");
      fetchGoals();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "审批失败");
    }
  };

  const handleReject = async () => {
    if (!rejectingGoalId || !rejectReason.trim()) return;
    try {
      await rejectQualityGoal(rejectingGoalId, rejectReason);
      message.success("已驳回");
      setRejectModalOpen(false);
      setRejectReason("");
      setRejectingGoalId(null);
      fetchGoals();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "驳回失败");
    }
  };

  const handleArchive = async (id: string) => {
    try {
      await archiveQualityGoal(id);
      message.success("已停用");
      fetchGoals();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "停用失败");
    }
  };

  const handleUpdateActual = async (id: string, value: string) => {
    try {
      await updateActualValue(id, value);
      message.success("实际值已更新");
      fetchGoals();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "更新失败");
    }
  };

  const activeCount = stats.active;
  const pendingCount = stats.pending;
  const achievementRate = stats.active > 0 ? Math.round((stats.achieved / stats.active) * 100) : 0;

  const columns = [
    {
      title: "指标名称",
      dataIndex: "name",
      render: (_: string, record: QualityGoal) => (
        <div>
          <Tag color={LEVEL_MAP[record.level]?.color}>
            {LEVEL_MAP[record.level]?.icon} {LEVEL_MAP[record.level]?.label}
          </Tag>
          <div style={{ marginTop: 4, fontWeight: 500 }}>{record.name}</div>
          {record.product_line_code && (
            <div style={{ fontSize: 12, color: "#888" }}>{record.product_line_code}</div>
          )}
        </div>
      ),
    },
    {
      title: "进度与达成",
      render: (_: unknown, record: QualityGoal) => {
        const achievement = checkAchievement(record.target_value, record.actual_value);
        const percent = getProgressPercent(record.target_value, record.actual_value);
        return (
          <div>
            <div style={{ fontSize: 12, color: "#666" }}>
              目标: {record.target_value} | 实际: {record.actual_value || "—"}
            </div>
            {record.actual_value && (
              <div style={{ marginTop: 4 }}>
                <div
                  style={{
                    width: "100%",
                    height: 6,
                    background: "#f0f0f0",
                    borderRadius: 3,
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      width: `${percent}%`,
                      height: "100%",
                      background:
                        achievement === "achieved"
                          ? "#52c41a"
                          : achievement === "not_achieved"
                          ? "#ff4d4f"
                          : "#bfbfbf",
                      borderRadius: 3,
                    }}
                  />
                </div>
              </div>
            )}
            <div style={{ marginTop: 4 }}>
              {achievement === "achieved" && <Tag color="success">✅ 已达成</Tag>}
              {achievement === "not_achieved" && <Tag color="error">🔴 未达成</Tag>}
              {achievement === "pending" && <Tag>⏳ 待录入</Tag>}
            </div>
          </div>
        );
      },
    },
    {
      title: "周期",
      dataIndex: "period",
      width: 80,
    },
    {
      title: "责任人",
      dataIndex: "owner_id",
      width: 120,
      render: (ownerId: string) => {
        const u = users.find((x) => x.user_id === ownerId);
        return u?.display_name || u?.username || ownerId.slice(0, 8);
      },
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (status: string) => {
        const cfg = STATUS_MAP[status];
        return <Tag color={cfg?.color}>{cfg?.label}</Tag>;
      },
    },
    {
      title: "操作",
      width: 240,
      render: (_: unknown, record: QualityGoal) => {
        const isOwner = record.owner_id === user?.user_id;
        return (
          <Space size="small" wrap>
            {record.status === "draft" && canEdit('quality_goal') && (
              <>
                <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
                  编辑
                </Button>
                <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.goal_id)}>
                  <Button size="small" danger icon={<DeleteOutlined />}>
                    删除
                  </Button>
                </Popconfirm>
                <Button size="small" type="primary" icon={<SendOutlined />} onClick={() => handleSubmitForApproval(record.goal_id)}>
                  提交
                </Button>
              </>
            )}
            {record.status === "pending" && (
              <>
                {canEdit('quality_goal') && isOwner && (
                  <Button size="small" icon={<RollbackOutlined />} onClick={() => handleWithdraw(record.goal_id)}>
                    撤回
                  </Button>
                )}
                {canApprove('quality_goal') && (
                  <>
                    <Button size="small" type="primary" icon={<CheckOutlined />} onClick={() => handleApprove(record.goal_id)}>
                      通过
                    </Button>
                    <Button
                      size="small"
                      danger
                      icon={<CloseOutlined />}
                      onClick={() => {
                        setRejectingGoalId(record.goal_id);
                        setRejectModalOpen(true);
                      }}
                    >
                      驳回
                    </Button>
                  </>
                )}
              </>
            )}
            {record.status === "active" && (
              <>
                {canEdit('quality_goal') && (
                  <Tooltip title="更新实际值">
                    <Button
                      size="small"
                      icon={<EditOutlined />}
                      onClick={() => {
                        const value = prompt("请输入实际值:", record.actual_value || "");
                        if (value !== null) handleUpdateActual(record.goal_id, value);
                      }}
                    >
                      更新值
                    </Button>
                  </Tooltip>
                )}
                {canApprove('quality_goal') && (
                  <Popconfirm title="确认停用？" onConfirm={() => handleArchive(record.goal_id)}>
                    <Button size="small" icon={<InboxOutlined />}>
                      停用
                    </Button>
                  </Popconfirm>
                )}
              </>
            )}
          </Space>
        );
      },
    },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title="目标总数" value={total} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="生效中" value={activeCount} valueStyle={{ color: "#52c41a" }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="待审批" value={pendingCount} valueStyle={{ color: "#faad14" }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="达成率"
              value={`${achievementRate}%`}
              valueStyle={{ color: achievementRate >= 80 ? "#52c41a" : "#ff4d4f" }}
            />
          </Card>
        </Col>
      </Row>

      <Card
        title="质量目标列表"
        extra={
          canEdit('quality_goal') && (
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
              新建目标
            </Button>
          )
        }
      >
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            { label: "全部", key: "all" },
            ...(canApprove('quality_goal') ? [{ label: "待我审批", key: "pending" }] : []),
            { label: "我的目标", key: "my" },
            ...(canEdit('quality_goal') ? [{ label: "草稿", key: "draft" }] : []),
          ]}
        />
        <Table
          rowKey="goal_id"
          columns={columns}
          dataSource={goals}
          loading={loading}
          pagination={{
            current: page,
            pageSize: pageSize,
            total: total,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps || 20);
            },
          }}
        />
      </Card>

      <Modal
        title={editingGoal ? "编辑质量目标" : "新建质量目标"}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleSubmitForm}>
          <Form.Item name="level" label="层级" rules={[{ required: true }]}>
            <Select
              placeholder="选择层级"
              disabled={!!editingGoal}
              onChange={(value) => loadParentGoals(value as number)}
            >
              <Option value={1}>🏢 公司级</Option>
              <Option value={2}>🏭 产品线级</Option>
              <Option value={3}>🔧 过程级</Option>
            </Select>
          </Form.Item>
          <Form.Item name="parent_id" label="父目标">
            <Select placeholder="选择父目标（公司级无需选择）" allowClear disabled={!!editingGoal}>
              {parentGoals.map((g) => (
                <Option key={g.goal_id} value={g.goal_id}>
                  {g.name}
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="product_line_code" label="产品线">
            <Input placeholder="如 DC-DC-100" />
          </Form.Item>
          <Form.Item name="name" label="指标名称" rules={[{ required: true }]}>
            <Input placeholder="如 客户投诉率" />
          </Form.Item>
          <Form.Item name="target_value" label="目标值" rules={[{ required: true }]}>
            <Input placeholder="如 ≤500 或 ≥90%" />
          </Form.Item>
          <Form.Item name="unit" label="单位" rules={[{ required: true }]}>
            <Input placeholder="如 PPM、%" />
          </Form.Item>
          <Form.Item name="period" label="周期" rules={[{ required: true }]}>
            <Select placeholder="选择周期">
              <Option value="月度">月度</Option>
              <Option value="季度">季度</Option>
              <Option value="年度">年度</Option>
            </Select>
          </Form.Item>
          <Form.Item name="owner_id" label="责任人" rules={[{ required: true }]}>
            <Select placeholder="选择责任人">
              {users.map((u) => (
                <Option key={u.user_id} value={u.user_id}>
                  {u.display_name || u.username}
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="description" label="说明">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="驳回理由"
        open={rejectModalOpen}
        onCancel={() => {
          setRejectModalOpen(false);
          setRejectReason("");
          setRejectingGoalId(null);
        }}
        onOk={handleReject}
      >
        <Input.TextArea
          rows={4}
          placeholder="请输入驳回理由"
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
        />
      </Modal>
    </div>
  );
}

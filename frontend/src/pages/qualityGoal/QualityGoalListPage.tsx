import { useState, useEffect, useCallback } from "react";
import {
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
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";
import { useProductLineStore } from "../../store/productLineStore";
import type { QualityGoal } from "../../types";
import { PageShell, DataCard, StatusBadge } from "../../components/design";
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
import { useLevelMap, useStatusMap, useStatusColor, useAchievementMap, usePeriodOptions } from "./useOptions";

const { Option } = Select;

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
  const { t } = useTranslation("qualityGoal");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const user = useAuthStore((s) => s.user);
  const { canEdit, canApprove } = usePermission();
  const productLine = useProductLineStore((s) => s.selected);
  const LEVEL_MAP = useLevelMap();
  const STATUS_MAP = useStatusMap();
  const STATUS_COLOR = useStatusColor();
  const ACHIEVEMENT_MAP = useAchievementMap();
  const PERIOD_OPTIONS = usePeriodOptions();

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
      message.error(t("messages.loadFailed", "加载数据失败"));
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
        message.success(t("messages.updateSuccess", "更新成功"));
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
        message.success(t("messages.createSuccess", "创建成功"));
      }
      setModalOpen(false);
      fetchGoals();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed", "操作失败"));
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteQualityGoal(id);
      message.success(t("messages.deleteSuccess", "删除成功"));
      fetchGoals();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || t("messages.deleteFailed", "删除失败"));
    }
  };

  const handleSubmitForApproval = async (id: string) => {
    try {
      await submitQualityGoal(id);
      message.success(t("messages.submitSuccess", "已提交审批"));
      fetchGoals();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed", "提交失败"));
    }
  };

  const handleWithdraw = async (id: string) => {
    try {
      await withdrawQualityGoal(id);
      message.success(t("messages.withdrawSuccess", "已撤回"));
      fetchGoals();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed", "撤回失败"));
    }
  };

  const handleApprove = async (id: string) => {
    try {
      await approveQualityGoal(id);
      message.success(t("messages.approveSuccess", "审批通过"));
      fetchGoals();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed", "审批失败"));
    }
  };

  const handleReject = async () => {
    if (!rejectingGoalId || !rejectReason.trim()) return;
    try {
      await rejectQualityGoal(rejectingGoalId, rejectReason);
      message.success(t("messages.rejectSuccess", "已驳回"));
      setRejectModalOpen(false);
      setRejectReason("");
      setRejectingGoalId(null);
      fetchGoals();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed", "驳回失败"));
    }
  };

  const handleArchive = async (id: string) => {
    try {
      await archiveQualityGoal(id);
      message.success(t("messages.archiveSuccess", "已停用"));
      fetchGoals();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed", "停用失败"));
    }
  };

  const handleUpdateActual = async (id: string, value: string) => {
    try {
      await updateActualValue(id, value);
      message.success(t("messages.actualValueUpdated", "实际值已更新"));
      fetchGoals();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed", "更新失败"));
    }
  };

  const activeCount = stats.active;
  const pendingCount = stats.pending;
  const achievementRate = stats.active > 0 ? Math.round((stats.achieved / stats.active) * 100) : 0;

  const columns = [
    {
      title: t("table.name", "指标名称"),
      dataIndex: "name",
      render: (_: string, record: QualityGoal) => (
        <div>
          <Tag style={{ background: "var(--qf-bg-elevated)", color: "var(--qf-text-secondary)", borderColor: "var(--qf-border)" }}>
            {LEVEL_MAP[record.level]?.icon} {LEVEL_MAP[record.level]?.label}
          </Tag>
          <div style={{ marginTop: 4, fontWeight: 500, color: "var(--qf-text-primary)" }}>{record.name}</div>
          {record.product_line_code && (
            <div style={{ fontSize: 12, color: "var(--qf-text-tertiary)", fontFamily: "var(--qf-font-mono)" }}>{record.product_line_code}</div>
          )}
        </div>
      ),
    },
    {
      title: t("table.progress", "进度与达成"),
      render: (_: unknown, record: QualityGoal) => {
        const achievement = checkAchievement(record.target_value, record.actual_value);
        const percent = getProgressPercent(record.target_value, record.actual_value);
        return (
          <div>
            <div style={{ fontSize: 12, color: "var(--qf-text-secondary)" }}>
              {t("table.target", "目标")}: {record.target_value} | {t("table.actual", "实际")}: {record.actual_value || "—"}
            </div>
            {record.actual_value && (
              <div style={{ marginTop: 4 }}>
                <div
                  style={{
                    width: "100%",
                    height: 6,
                    background: "var(--qf-bg-hover)",
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
                          ? "var(--qf-green)"
                          : achievement === "not_achieved"
                          ? "var(--qf-red)"
                          : "var(--qf-text-tertiary)",
                      borderRadius: 3,
                    }}
                  />
                </div>
              </div>
            )}
            <div style={{ marginTop: 4 }}>
              {achievement === "achieved" && <StatusBadge status={ACHIEVEMENT_MAP.achieved.color}>{ACHIEVEMENT_MAP.achieved.label}</StatusBadge>}
              {achievement === "not_achieved" && <StatusBadge status={ACHIEVEMENT_MAP.not_achieved.color}>{ACHIEVEMENT_MAP.not_achieved.label}</StatusBadge>}
              {achievement === "pending" && <StatusBadge status={ACHIEVEMENT_MAP.pending.color}>{ACHIEVEMENT_MAP.pending.label}</StatusBadge>}
            </div>
          </div>
        );
      },
    },
    {
      title: t("table.period", "周期"),
      dataIndex: "period",
      width: 80,
    },
    {
      title: t("table.owner", "责任人"),
      dataIndex: "owner_id",
      width: 120,
      render: (ownerId: string) => {
        const u = users.find((x) => x.user_id === ownerId);
        return u?.display_name || u?.username || ownerId.slice(0, 8);
      },
    },
    {
      title: t("table.status", "状态"),
      dataIndex: "status",
      width: 100,
      render: (status: string) => {
        const cfg = STATUS_MAP[status];
        return <StatusBadge status={STATUS_COLOR[status] || "default"}>{cfg}</StatusBadge>;
      },
    },
    {
      title: tc("table.operations", "操作"),
      width: 240,
      render: (_: unknown, record: QualityGoal) => {
        const isOwner = record.owner_id === user?.user_id;
        return (
          <Space size="small" wrap>
            {record.status === "draft" && canEdit('quality_goal') && (
              <>
                <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
                  {tc("actions.edit", "编辑")}
                </Button>
                <Popconfirm title={tc("messages.confirmDelete", "确认删除？")} onConfirm={() => handleDelete(record.goal_id)}>
                  <Button size="small" danger icon={<DeleteOutlined />}>
                    {tc("actions.delete", "删除")}
                  </Button>
                </Popconfirm>
                <Button size="small" type="primary" icon={<SendOutlined />} onClick={() => handleSubmitForApproval(record.goal_id)}>
                  {tc("actions.submit", "提交")}
                </Button>
              </>
            )}
            {record.status === "pending" && (
              <>
                {canEdit('quality_goal') && isOwner && (
                  <Button size="small" icon={<RollbackOutlined />} onClick={() => handleWithdraw(record.goal_id)}>
                    {t("actions.withdraw", "撤回")}
                  </Button>
                )}
                {canApprove('quality_goal') && (
                  <>
                    <Button size="small" type="primary" icon={<CheckOutlined />} onClick={() => handleApprove(record.goal_id)}>
                      {tc("actions.approve", "通过")}
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
                      {tc("actions.reject", "驳回")}
                    </Button>
                  </>
                )}
              </>
            )}
            {record.status === "active" && (
              <>
                {canEdit('quality_goal') && (
                  <Tooltip title={t("actions.updateValue", "更新实际值")}>
                    <Button
                      size="small"
                      icon={<EditOutlined />}
                      onClick={() => {
                        const value = prompt(t("prompt.actualValue", "请输入实际值:"), record.actual_value || "");
                        if (value !== null) handleUpdateActual(record.goal_id, value);
                      }}
                    >
                      {t("actions.updateValue", "更新值")}
                    </Button>
                  </Tooltip>
                )}
                {canApprove('quality_goal') && (
                  <Popconfirm title={tc("messages.confirmDelete", "确认停用？")} onConfirm={() => handleArchive(record.goal_id)}>
                    <Button size="small" icon={<InboxOutlined />}>
                      {t("actions.archive", "停用")}
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
    <PageShell
      title={t("pageTitle.list", "质量目标")}
      subtitle={t("pageTitle.list", "QMS 质量目标管理 · 目标设定 · 审批 · 达成跟踪")}
      actions={
        canEdit('quality_goal') ? (
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            {t("actions.newGoal", "新建目标")}
          </Button>
        ) : null
      }
    >
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <DataCard title={t("stats.totalGoals", "目标总数")} noPadding>
            <Statistic
              value={total}
              valueStyle={{ fontFamily: "var(--qf-font-mono)", color: "var(--qf-text-primary)" }}
            />
          </DataCard>
        </Col>
        <Col span={6}>
          <DataCard title={t("stats.active", "生效中")} noPadding>
            <Statistic
              value={activeCount}
              valueStyle={{ fontFamily: "var(--qf-font-mono)", color: "var(--qf-green)" }}
            />
          </DataCard>
        </Col>
        <Col span={6}>
          <DataCard title={t("stats.pendingApproval", "待审批")} noPadding>
            <Statistic
              value={pendingCount}
              valueStyle={{ fontFamily: "var(--qf-font-mono)", color: "var(--qf-amber)" }}
            />
          </DataCard>
        </Col>
        <Col span={6}>
          <DataCard title={t("stats.achievementRate", "达成率")} noPadding>
            <Statistic
              value={`${achievementRate}%`}
              valueStyle={{
                fontFamily: "var(--qf-font-mono)",
                color: achievementRate >= 80 ? "var(--qf-green)" : "var(--qf-red)",
              }}
            />
          </DataCard>
        </Col>
      </Row>

      <DataCard title={t("table.name", "质量目标列表")}>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            { label: t("tabs.all", "全部"), key: "all" },
            ...(canApprove('quality_goal') ? [{ label: t("tabs.pendingMe", "待我审批"), key: "pending" }] : []),
            { label: t("tabs.my", "我的目标"), key: "my" },
            ...(canEdit('quality_goal') ? [{ label: t("tabs.draft", "草稿"), key: "draft" }] : []),
          ]}
        />
        <Table
          className="qf-table"
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
      </DataCard>

      <Modal
        title={editingGoal ? t("modal.editGoal", "编辑质量目标") : t("modal.newGoal", "新建质量目标")}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleSubmitForm}>
          <Form.Item name="level" label={t("form.level", "层级")} rules={[{ required: true, message: t("validation.levelRequired", "请选择层级") }]}>
            <Select
              placeholder={t("placeholder.selectLevel", "选择层级")}
              disabled={!!editingGoal}
              onChange={(value) => loadParentGoals(value as number)}
            >
              {Object.entries(LEVEL_MAP).map(([key, val]) => (
                <Option key={key} value={Number(key)}>
                  {val.icon} {val.label}
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="parent_id" label={t("form.parentGoal", "父目标")}>
            <Select placeholder={t("placeholder.parentGoal", "选择父目标（公司级无需选择）")} allowClear disabled={!!editingGoal}>
              {parentGoals.map((g) => (
                <Option key={g.goal_id} value={g.goal_id}>
                  {g.name}
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="product_line_code" label={t("form.productLine", "产品线")}>
            <Input placeholder={t("placeholder.productLine", "如 DC-DC-100")} />
          </Form.Item>
          <Form.Item name="name" label={t("form.name", "指标名称")} rules={[{ required: true, message: t("validation.nameRequired", "请输入指标名称") }]}>
            <Input placeholder={t("placeholder.name", "如 客户投诉率")} />
          </Form.Item>
          <Form.Item name="target_value" label={t("form.targetValue", "目标值")} rules={[{ required: true, message: t("validation.targetValueRequired", "请输入目标值") }]}>
            <Input placeholder={t("placeholder.targetValue", "如 ≤500 或 ≥90%")} />
          </Form.Item>
          <Form.Item name="unit" label={t("form.unit", "单位")} rules={[{ required: true, message: t("validation.unitRequired", "请输入单位") }]}>
            <Input placeholder={t("placeholder.unit", "如 PPM、%")} />
          </Form.Item>
          <Form.Item name="period" label={t("form.period", "周期")} rules={[{ required: true, message: t("validation.periodRequired", "请选择周期") }]}>
            <Select placeholder={t("placeholder.selectPeriod", "选择周期")}>
              {PERIOD_OPTIONS.map((o) => (
                <Option key={o.value} value={o.value}>{o.label}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="owner_id" label={t("form.owner", "责任人")} rules={[{ required: true, message: t("validation.ownerRequired", "请选择责任人") }]}>
            <Select placeholder={t("placeholder.selectOwner", "选择责任人")}>
              {users.map((u) => (
                <Option key={u.user_id} value={u.user_id}>
                  {u.display_name || u.username}
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="description" label={t("form.description", "说明")}>
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t("modal.rejectReason", "驳回理由")}
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
          placeholder={t("placeholder.rejectReason", "请输入驳回理由")}
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
        />
      </Modal>
    </PageShell>
  );
}
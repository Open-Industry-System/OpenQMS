import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Button, Space, Tag, Typography, Input, Table, Card, Row, Col,
  App, Spin, Select, Alert, Tooltip, Tabs, Modal,
} from "antd";
import {
  SaveOutlined, ArrowLeftOutlined, PlusOutlined, DeleteOutlined,
  ImportOutlined, CheckCircleOutlined, ExclamationCircleOutlined,
  SyncOutlined, HistoryOutlined,
} from "@ant-design/icons";
import {
  getControlPlan, createControlPlan, updateControlPlan,
  checkStaleItems, approveControlPlan,
} from "../../api/controlPlan";
import type { ControlPlan, ControlPlanItem } from "../../types";
import type { CPSyncStatusItem } from "../../types/specialCharacteristic";
import { useAuthStore } from "../../store/authStore";
import { getCPSyncStatus, syncToCP } from "../../api/specialCharacteristic";
import ImportFromFMEAModal from "../../components/control-plan/ImportFromFMEAModal";
import VersionHistoryTab from "../../components/version/VersionHistoryTab";
import CreateVersionModal from "../../components/version/CreateVersionModal";
import RollbackConfirmModal from "../../components/version/RollbackConfirmModal";
import VersionCompareView from "../../components/version/VersionCompareView";
import SyncPreviewDrawer from "../../components/version/SyncPreviewDrawer";

const { Title, Text } = Typography;

const phaseOptions = [
  { value: "sample", label: "样件" },
  { value: "trial", label: "试生产" },
  { value: "production", label: "生产" },
];

const phaseLabels: Record<string, string> = {
  sample: "样件",
  trial: "试生产",
  production: "生产",
};

const statusLabels: Record<string, string> = {
  draft: "草稿",
  approved: "已批准",
};

const specialClassOptions = [
  { value: "", label: "-" },
  { value: "CC", label: "CC" },
  { value: "SC", label: "SC" },
];

function createBlankItem(sortOrder: number): ControlPlanItem {
  return {
    item_id: `temp-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    step_no: "",
    process_name: "",
    equipment: "",
    characteristic_no: "",
    product_characteristic: "",
    process_characteristic: "",
    special_class: "",
    specification_tolerance: "",
    evaluation_method: "",
    sample_size: "",
    sample_frequency: "",
    control_method: "",
    reaction_plan: "",
    source_fmea_node_id: null,
    sort_order: sortOrder,
  };
}

export default function ControlPlanEditorPage() {
  const { message } = App.useApp();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isNew = id === "new";

  const [cp, setCp] = useState<ControlPlan | null>(null);
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [staleAlert, setStaleAlert] = useState<{ visible: boolean; stepNos: string[] }>({
    visible: false,
    stepNos: [],
  });
  const [syncStatus, setSyncStatus] = useState<CPSyncStatusItem[]>([]);
  const [outerTab, setOuterTab] = useState("editor");
  const [createVersionOpen, setCreateVersionOpen] = useState(false);
  const [rollbackTarget, setRollbackTarget] = useState<{ major: number; minor: number } | null>(null);
  const [compareState, setCompareState] = useState<{ major1: number; minor1: number; major2: number; minor2: number } | null>(null);
  const [syncDrawerOpen, setSyncDrawerOpen] = useState(false);

  const user = useAuthStore((s) => s.user);
  const isApproved = cp?.status === "approved";
  const canEdit = user?.role !== "viewer" && !isApproved;
  const isAdminOrManager = user?.role === "admin" || user?.role === "manager";

  // Form state
  const [title, setTitle] = useState("");
  const [documentNo, setDocumentNo] = useState("");
  const [phase, setPhase] = useState("sample");
  const [partNo, setPartNo] = useState("");
  const [partName, setPartName] = useState("");
  const [contactInfo, setContactInfo] = useState("");
  const [coreGroup, setCoreGroup] = useState("");
  const [orgFactory, setOrgFactory] = useState("");
  const [drawingRev, setDrawingRev] = useState("");
  const [items, setItems] = useState<ControlPlanItem[]>([]);

  useEffect(() => {
    if (isNew) {
      setLoading(false);
      return;
    }
    if (!id) return;
    setLoading(true);
    getControlPlan(id)
      .then((doc) => {
        setCp(doc);
        setTitle(doc.title);
        setDocumentNo(doc.document_no);
        setPhase(doc.phase || "sample");
        setPartNo(doc.part_no || "");
        setPartName(doc.part_name || "");
        setContactInfo(doc.contact_info || "");
        setCoreGroup(doc.core_group || "");
        setOrgFactory(doc.org_factory || "");
        setDrawingRev(doc.drawing_rev || "");
        setItems(doc.items || []);
        if (id) {
          getCPSyncStatus(id).then((res) => setSyncStatus(res.items)).catch(() => {});
        }
      })
      .catch(() => {
        message.error("加载控制计划失败");
      })
      .finally(() => setLoading(false));
  }, [id, isNew]);

  const updateItem = useCallback((index: number, field: keyof ControlPlanItem, value: string) => {
    setItems((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], [field]: value };
      return next;
    });
  }, []);

  const addItem = useCallback(() => {
    setItems((prev) => [...prev, createBlankItem(prev.length)]);
  }, []);

  const removeItem = useCallback((index: number) => {
    setItems((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const handleSave = async () => {
    if (!title.trim()) {
      message.warning("请输入标题");
      return;
    }
    if (!documentNo.trim()) {
      message.warning("请输入文档编号");
      return;
    }

    setSaving(true);
    try {
      if (isNew) {
        const created = await createControlPlan({
          title: title.trim(),
          document_no: documentNo.trim(),
          phase,
          part_no: partNo.trim() || undefined,
          part_name: partName.trim() || undefined,
          contact_info: contactInfo.trim() || undefined,
          core_group: coreGroup.trim() || undefined,
          org_factory: orgFactory.trim() || undefined,
          drawing_rev: drawingRev.trim() || undefined,
        });
        // Save items separately via update
        if (items.length > 0) {
          await updateControlPlan(created.cp_id, { items });
        }
        message.success("创建成功");
        navigate(`/control-plans/${created.cp_id}`);
      } else if (id) {
        await updateControlPlan(id, {
          title: title.trim(),
          phase,
          part_no: partNo.trim() || undefined,
          part_name: partName.trim() || undefined,
          contact_info: contactInfo.trim() || undefined,
          core_group: coreGroup.trim() || undefined,
          org_factory: orgFactory.trim() || undefined,
          drawing_rev: drawingRev.trim() || undefined,
          items,
        });
        message.success("保存成功");
        // Refresh
        const refreshed = await getControlPlan(id);
        setCp(refreshed);
      }
    } catch (e: any) {
      message.error(e.response?.data?.detail || (isNew ? "创建失败" : "保存失败"));
    } finally {
      setSaving(false);
    }
  };

  const handleCheckStale = async () => {
    if (!id || isNew) return;
    try {
      const result = await checkStaleItems(id);
      if (result.stale_items.length > 0) {
        const stepNos = result.stale_items.map((s) => s.step_no).filter(Boolean);
        setStaleAlert({ visible: true, stepNos });
      } else {
        message.success("未检测到 PFMEA 变更");
        setStaleAlert({ visible: false, stepNos: [] });
      }
    } catch {
      message.error("检查失败");
    }
  };

  const handleApprove = async () => {
    if (!id || isNew) return;
    try {
      const updated = await approveControlPlan(id);
      setCp(updated);
      message.success("批准成功");
    } catch (e: any) {
      message.error(e.response?.data?.detail || "批准失败");
    }
  };

  const handleImportSuccess = async () => {
    if (!id || isNew) return;
    try {
      const refreshed = await getControlPlan(id);
      setCp(refreshed);
      setItems(refreshed.items || []);
      message.success("导入成功");
    } catch {
      message.error("刷新数据失败");
    }
  };

  const columns = [
    {
      title: "零件/过程编号",
      dataIndex: "step_no",
      key: "step_no",
      width: 120,
      render: (_: string, __: ControlPlanItem, index: number) => (
        <Input
          value={items[index]?.step_no || ""}
          onChange={(e) => updateItem(index, "step_no", e.target.value)}
          disabled={!canEdit}
          size="small"
        />
      ),
    },
    {
      title: "过程名称/操作描述",
      dataIndex: "process_name",
      key: "process_name",
      width: 160,
      render: (_: string, __: ControlPlanItem, index: number) => (
        <Input
          value={items[index]?.process_name || ""}
          onChange={(e) => updateItem(index, "process_name", e.target.value)}
          disabled={!canEdit}
          size="small"
        />
      ),
    },
    {
      title: "设备/工装/夹具",
      dataIndex: "equipment",
      key: "equipment",
      width: 140,
      render: (_: string, __: ControlPlanItem, index: number) => (
        <Input
          value={items[index]?.equipment || ""}
          onChange={(e) => updateItem(index, "equipment", e.target.value)}
          disabled={!canEdit}
          size="small"
        />
      ),
    },
    {
      title: "特性",
      children: [
        {
          title: "特性编号",
          dataIndex: "characteristic_no",
          key: "characteristic_no",
          width: 100,
          render: (_: string, __: ControlPlanItem, index: number) => (
            <Input
              value={items[index]?.characteristic_no || ""}
              onChange={(e) => updateItem(index, "characteristic_no", e.target.value)}
              disabled={!canEdit}
              size="small"
            />
          ),
        },
        {
          title: "产品特性",
          dataIndex: "product_characteristic",
          key: "product_characteristic",
          width: 140,
          render: (_: string, __: ControlPlanItem, index: number) => (
            <Input
              value={items[index]?.product_characteristic || ""}
              onChange={(e) => updateItem(index, "product_characteristic", e.target.value)}
              disabled={!canEdit}
              size="small"
            />
          ),
        },
        {
          title: "过程特性",
          dataIndex: "process_characteristic",
          key: "process_characteristic",
          width: 140,
          render: (_: string, __: ControlPlanItem, index: number) => (
            <Input
              value={items[index]?.process_characteristic || ""}
              onChange={(e) => updateItem(index, "process_characteristic", e.target.value)}
              disabled={!canEdit}
              size="small"
            />
          ),
        },
      ],
    },
    {
      title: "特殊特性分类",
      dataIndex: "special_class",
      key: "special_class",
      width: 130,
      render: (_: string, record: ControlPlanItem, index: number) => {
        const syncItem = syncStatus.find((s) => s.item_id === record.item_id);
        const outOfSync = syncItem?.is_out_of_sync;
        return (
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <Select
              value={items[index]?.special_class || ""}
              onChange={(value) => updateItem(index, "special_class", value)}
              options={specialClassOptions}
              disabled={!canEdit}
              size="small"
              style={{ width: 80 }}
            />
            {outOfSync && (
              <Tooltip title="节点特性已变更，建议同步">
                <Tag color="warning">!</Tag>
              </Tooltip>
            )}
          </div>
        );
      },
    },
    {
      title: "产品/过程/规格/公差",
      dataIndex: "specification_tolerance",
      key: "specification_tolerance",
      width: 160,
      render: (_: string, __: ControlPlanItem, index: number) => (
        <Input
          value={items[index]?.specification_tolerance || ""}
          onChange={(e) => updateItem(index, "specification_tolerance", e.target.value)}
          disabled={!canEdit}
          size="small"
        />
      ),
    },
    {
      title: "方法",
      children: [
        {
          title: "评价/测量技术",
          dataIndex: "evaluation_method",
          key: "evaluation_method",
          width: 140,
          render: (_: string, __: ControlPlanItem, index: number) => (
            <Input
              value={items[index]?.evaluation_method || ""}
              onChange={(e) => updateItem(index, "evaluation_method", e.target.value)}
              disabled={!canEdit}
              size="small"
            />
          ),
        },
      ],
    },
    {
      title: "样本",
      children: [
        {
          title: "样本大小",
          dataIndex: "sample_size",
          key: "sample_size",
          width: 100,
          render: (_: string, __: ControlPlanItem, index: number) => (
            <Input
              value={items[index]?.sample_size || ""}
              onChange={(e) => updateItem(index, "sample_size", e.target.value)}
              disabled={!canEdit}
              size="small"
            />
          ),
        },
        {
          title: "样本频次",
          dataIndex: "sample_frequency",
          key: "sample_frequency",
          width: 100,
          render: (_: string, __: ControlPlanItem, index: number) => (
            <Input
              value={items[index]?.sample_frequency || ""}
              onChange={(e) => updateItem(index, "sample_frequency", e.target.value)}
              disabled={!canEdit}
              size="small"
            />
          ),
        },
      ],
    },
    {
      title: "控制方法",
      dataIndex: "control_method",
      key: "control_method",
      width: 140,
      render: (_: string, __: ControlPlanItem, index: number) => (
        <Input
          value={items[index]?.control_method || ""}
          onChange={(e) => updateItem(index, "control_method", e.target.value)}
          disabled={!canEdit}
          size="small"
        />
      ),
    },
    {
      title: "反应计划",
      dataIndex: "reaction_plan",
      key: "reaction_plan",
      width: 140,
      render: (_: string, __: ControlPlanItem, index: number) => (
        <Input
          value={items[index]?.reaction_plan || ""}
          onChange={(e) => updateItem(index, "reaction_plan", e.target.value)}
          disabled={!canEdit}
          size="small"
        />
      ),
    },
    {
      title: "操作",
      key: "actions",
      width: 80,
      fixed: "right" as const,
      render: (_: unknown, __: ControlPlanItem, index: number) => (
        canEdit ? (
          <Button
            type="link"
            danger
            size="small"
            icon={<DeleteOutlined />}
            onClick={() => removeItem(index)}
          >
            删除
          </Button>
        ) : null
      ),
    },
  ];

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: 64 }}>
        <Spin size="large" />
      </div>
    );
  }

  const currentStatus = cp?.status || "draft";

  return (
    <div>
      {/* Top bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/control-plans")}>
            返回
          </Button>
          <Title level={4} style={{ margin: 0 }}>
            {isNew ? "新建控制计划" : title || "控制计划详情"}
          </Title>
        </Space>
        <Space>
          <Text>
            状态：
            <Tag color={currentStatus === "approved" ? "green" : "blue"}>
              {statusLabels[currentStatus] || currentStatus}
            </Tag>
          </Text>
        </Space>
      </div>

      {/* Stale alert */}
      {staleAlert.visible && (
        <Alert
          type="warning"
          showIcon
          icon={<ExclamationCircleOutlined />}
          closable
          onClose={() => setStaleAlert({ visible: false, stepNos: [] })}
          message={`关联的 PFMEA 已发生变更，以下行可能已过期：${staleAlert.stepNos.join(", ")}，建议重新导入或手动核对。`}
          style={{ marginBottom: 16 }}
        />
      )}

      {/* Sync pending banner */}
      {cp?.sync_pending && (
        <Alert
          message="关联的 FMEA 已更新（当前 CP 基于较旧版本），建议同步更新"
          type="warning"
          showIcon
          action={
            <Button size="small" icon={<SyncOutlined />} onClick={() => setSyncDrawerOpen(true)}>
              立即同步
            </Button>
          }
          style={{ marginBottom: 16 }}
        />
      )}

      <Tabs activeKey={outerTab} onChange={setOuterTab}>
        <Tabs.TabPane tab="编辑器" key="editor">

      {/* Action buttons */}
      <Space style={{ marginBottom: 16 }}>
        <Button
          type="primary"
          icon={<SaveOutlined />}
          loading={saving}
          onClick={handleSave}
          disabled={!canEdit}
        >
          保存
        </Button>
        {!isNew && canEdit && (
          <Button icon={<ImportOutlined />} onClick={() => setImportOpen(true)}>
            从 PFMEA 导入
          </Button>
        )}
        {!isNew && (
          <Button icon={<ExclamationCircleOutlined />} onClick={handleCheckStale}>
            检查 PFMEA 变更
          </Button>
        )}
        {!isNew && canEdit && syncStatus.some((s) => s.is_out_of_sync) && (
          <Button
            icon={<SyncOutlined />}
            onClick={async () => {
              try {
                if (!id) return;
                await syncToCP(id);
                message.success("同步成功");
                getCPSyncStatus(id).then((res) => setSyncStatus(res.items)).catch(() => {});
              } catch {
                message.error("同步失败");
              }
            }}
          >
            同步特殊特性
          </Button>
        )}
        {!isNew && isAdminOrManager && currentStatus !== "approved" && (
          <Button icon={<CheckCircleOutlined />} onClick={handleApprove}>
            批准
          </Button>
        )}
      </Space>

      {/* Header info card */}
      <Card title="基本信息" style={{ marginBottom: 16 }}>
        <Row gutter={24}>
          <Col span={12}>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">标题</Text>
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                disabled={!canEdit}
                placeholder="控制计划标题"
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">编号</Text>
              <Input
                value={documentNo}
                onChange={(e) => setDocumentNo(e.target.value)}
                disabled={!isNew || !canEdit}
                placeholder="如 CP-2026-001"
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">零件编号</Text>
              <Input
                value={partNo}
                onChange={(e) => setPartNo(e.target.value)}
                disabled={!canEdit}
                placeholder="零件编号"
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">零件名称</Text>
              <Input
                value={partName}
                onChange={(e) => setPartName(e.target.value)}
                disabled={!canEdit}
                placeholder="零件名称"
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">联系人</Text>
              <Input
                value={contactInfo}
                onChange={(e) => setContactInfo(e.target.value)}
                disabled={!canEdit}
                placeholder="联系人信息"
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">核心小组</Text>
              <Input
                value={coreGroup}
                onChange={(e) => setCoreGroup(e.target.value)}
                disabled={!canEdit}
                placeholder="核心小组成员"
              />
            </div>
          </Col>
          <Col span={12}>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">组织/工厂</Text>
              <Input
                value={orgFactory}
                onChange={(e) => setOrgFactory(e.target.value)}
                disabled={!canEdit}
                placeholder="组织/工厂"
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">图纸版本</Text>
              <Input
                value={drawingRev}
                onChange={(e) => setDrawingRev(e.target.value)}
                disabled={!canEdit}
                placeholder="图纸版本"
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">阶段</Text>
              <Select
                value={phase}
                onChange={(value) => setPhase(value)}
                options={phaseOptions}
                disabled={!canEdit}
                style={{ width: "100%" }}
                placeholder="选择阶段"
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">关联 PFMEA</Text>
              <Input
                value={cp?.fmea_ref_id || "未关联"}
                disabled
              />
            </div>
          </Col>
        </Row>
      </Card>

      {/* Items table */}
      <Card title="控制计划内容">
        <Table
          columns={columns}
          dataSource={items}
          rowKey="item_id"
          pagination={false}
          scroll={{ x: 1600 }}
          size="small"
          bordered
          footer={() =>
            canEdit ? (
              <Button type="dashed" icon={<PlusOutlined />} onClick={addItem} block>
                新增行
              </Button>
            ) : null
          }
        />
      </Card>

      {/* Import modal */}
      {!isNew && id && (
        <ImportFromFMEAModal
          cpId={id}
          open={importOpen}
          onClose={() => setImportOpen(false)}
          onSuccess={handleImportSuccess}
        />
      )}
        </Tabs.TabPane>
        <Tabs.TabPane tab={<span><HistoryOutlined /> 版本历史</span>} key="history">
          <VersionHistoryTab
            documentId={id!}
            documentType="cp"
            canCreate={user?.role !== "viewer"}
            canRollback={isAdminOrManager}
            isDraft={currentStatus === "draft"}
            onViewSnapshot={() => {}}
            onCompare={(major1, minor1, major2, minor2) => setCompareState({ major1, minor1, major2, minor2 })}
            onRollback={(major, minor) => setRollbackTarget({ major, minor })}
            onCreateVersion={() => setCreateVersionOpen(true)}
          />
        </Tabs.TabPane>
      </Tabs>

      {!isNew && id && (
        <>
          <CreateVersionModal
            open={createVersionOpen}
            documentId={id}
            documentType="cp"
            onClose={() => setCreateVersionOpen(false)}
            onSuccess={() => setCreateVersionOpen(false)}
          />
          <RollbackConfirmModal
            open={!!rollbackTarget}
            targetVersion={rollbackTarget}
            documentId={id}
            documentType="cp"
            onClose={() => setRollbackTarget(null)}
            onSuccess={() => setRollbackTarget(null)}
          />
          {compareState && (
            <Modal
              open={!!compareState}
              title="版本对比"
              width={900}
              footer={null}
              onCancel={() => setCompareState(null)}
            >
              <VersionCompareView
                documentId={id}
                documentType="cp"
                major1={compareState.major1}
                minor1={compareState.minor1}
                major2={compareState.major2}
                minor2={compareState.minor2}
              />
            </Modal>
          )}
          <SyncPreviewDrawer
            open={syncDrawerOpen}
            cpId={id}
            onClose={() => setSyncDrawerOpen(false)}
            onSuccess={async () => {
              setSyncDrawerOpen(false);
              if (!id) return;
              try {
                const refreshed = await getControlPlan(id);
                setCp(refreshed);
              } catch { /* silent */ }
            }}
          />
        </>
      )}
    </div>
  );
}

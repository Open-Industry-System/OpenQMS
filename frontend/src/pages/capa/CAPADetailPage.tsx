import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Button, Space, Tag, Typography, Steps, Card, Form, Input,
  Select, App, Spin, Empty, Row, Col, Table, Divider, Modal,
} from "antd";
import { ArrowLeftOutlined, ArrowRightOutlined, LinkOutlined, PlusOutlined, DeleteOutlined } from "@ant-design/icons";
import { getCAPA, updateCAPA, advanceCAPA, linkFMEA } from "../../api/capa";
import { listFMEAs } from "../../api/fmea";
import RelatedFMEALink from "../../components/cross-links/RelatedFMEALink";
import D7RecPanel, { type D7UnconfirmedItem } from "../../components/capa/D7RecPanel";
import type { CAPAReport, FMEADocument } from "../../types";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";


const { Title, Text } = Typography;
const { TextArea } = Input;

const stepItems = [
  { title: "D1 团队组建" }, { title: "D2 问题描述" },
  { title: "D3 临时措施" }, { title: "D4 根因分析" },
  { title: "D5 永久措施" }, { title: "D6 实施验证" },
  { title: "D7 预防复发" }, { title: "D8 关闭" },
];

const stepIndex: Record<string, number> = {
  D1_TEAM: 0, D2_DESCRIPTION: 1, D3_INTERIM: 2, D4_ROOT_CAUSE: 3,
  D5_CORRECTION: 4, D6_VERIFICATION: 5, D7_PREVENTION: 6, D8_CLOSURE: 7, ARCHIVED: 8,
};

export default function CAPADetailPage() {
  const { message } = App.useApp();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [capa, setCapa] = useState<CAPAReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [fmeas, setFmeas] = useState<FMEADocument[]>([]);
  const [linkModal, setLinkModal] = useState(false);

  // User Role Controls
  const user = useAuthStore((s) => s.user);
  const { canEdit, canApprove } = usePermission();

  // Local Form Buffers (for input debouncing/onBlur saves)
  const [localData, setLocalData] = useState<Record<string, any>>({});
  
  // D1 Team Adding UI State
  const [newMemberName, setNewMemberName] = useState("");
  const [newMemberRole, setNewMemberRole] = useState("质量工程师");

  // D7 soft gate state
  const [allD7Confirmed, setAllD7Confirmed] = useState(true);
  const [d7UnconfirmedItems, setD7UnconfirmedItems] = useState<D7UnconfirmedItem[]>([]);
  const [d7SkipDialogOpen, setD7SkipDialogOpen] = useState(false);
  const [d7SkipReasons, setD7SkipReasons] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!id) return;
    getCAPA(id).then(setCapa).finally(() => setLoading(false));
    listFMEAs({ page_size: 100 }).then((res) => setFmeas(res.items));
  }, [id]);

  useEffect(() => {
    if (capa) {
      setLocalData({
        d1_team: capa.d1_team || [],
        d2_description: capa.d2_description || "",
        d3_interim: capa.d3_interim || "",
        d4_root_cause: capa.d4_root_cause || "",
        d5_correction: capa.d5_correction || "",
        d6_verification: capa.d6_verification || "",
        d7_prevention: capa.d7_prevention || "",
        d8_closure: capa.d8_closure || "",
      });
    }
  }, [capa]);

  const currentStep = capa ? (stepIndex[capa.status] ?? 0) : 0;

  const handleUpdate = async (field: string, value: unknown) => {
    if (!id || !canEdit('capa')) return;
    
    // Check if value actually changed to prevent redundant network hits
    if (capa && JSON.stringify(capa[field as keyof CAPAReport]) === JSON.stringify(value)) {
      return;
    }
    
    setSaving(true);
    try {
      const updated = await updateCAPA(id, { [field]: value });
      setCapa(updated);
    } catch { message.error("保存失败"); }
    setSaving(false);
  };

  const handleAdvance = async () => {
    if (!id) return;

    // D7 soft gate: check for unconfirmed recommendations
    if (capa?.status === "D7_PREVENTION" && !allD7Confirmed) {
      setD7SkipDialogOpen(true);
      return;
    }

    try {
      const updated = await advanceCAPA(id);
      setCapa(updated);
      message.success("已推进到下一步");
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err?.response?.data?.detail || "推进失败");
    }
  };

  const handleD7SkipConfirm = async () => {
    if (!id) return;
    setD7SkipDialogOpen(false);

    const globalReason = (d7SkipReasons["__global__"] || "").trim();
    const skipReasonsList = d7UnconfirmedItems.map((item) => ({
      fmea_id: item.fmea_id,
      node_id: item.failure_mode_node_id,
      reason: globalReason || "未填写理由",
    }));

    try {
      const updated = await advanceCAPA(id, {
        d7_skip_reasons: skipReasonsList.length > 0 ? skipReasonsList : undefined,
      });
      setCapa(updated);
      message.success("已推进到下一步");
      setD7SkipReasons({});
      setD7UnconfirmedItems([]);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err?.response?.data?.detail || "推进失败");
    }
  };

  const handleLinkFMEA = async (fmeaId: string) => {
    if (!id) return;
    try {
      const updated = await linkFMEA(id, fmeaId);
      setCapa(updated);
      setLinkModal(false);
      message.success("已关联 FMEA");
    } catch { message.error("关联失败"); }
  };

  if (loading) return <Spin size="large" style={{ display: "block", margin: "100px auto" }} />;
  if (!capa) return <Empty description="8D 报告未找到" />;

  return (
    <>
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
          <Space>
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/capa")}>返回</Button>
            <Title level={4} style={{ margin: 0 }}>{capa.title}</Title>
            <Tag color="blue">{capa.document_no}</Tag>
            <Tag color="red">{capa.severity}</Tag>
          </Space>
          <Space>
            {capa.fmea_ref_id && (
              <Tag icon={<LinkOutlined />} color="green">已关联 FMEA</Tag>
            )}
            <RelatedFMEALink
              fmeaRefId={capa.fmea_ref_id ?? null}
              fmeaNodeId={capa.fmea_node_id ?? null}
            />
            {canEdit('capa') && (
              <Button icon={<LinkOutlined />} onClick={() => setLinkModal(true)}>
                {capa.fmea_ref_id ? "更换FMEA关联" : "关联FMEA"}
              </Button>
            )}
            {capa.status !== "ARCHIVED" && capa.status !== "D8_CLOSURE" && (!["D7_PREVENTION", "D8_CLOSURE"].includes(capa.status) || canApprove('capa')) && canEdit('capa') && (
              <Button type="primary" icon={<ArrowRightOutlined />} onClick={handleAdvance}>
                推进下一步
              </Button>
            )}
          </Space>
        </div>

        <Steps current={currentStep} items={stepItems} style={{ marginBottom: 24 }} />

        <Row gutter={16}>
          <Col span={16}>
            <Card title="当前步骤详情">
            {capa.status === "D1_TEAM" && (
              <div>
                <Table
                  dataSource={localData.d1_team || []}
                  rowKey="name"
                  size="small"
                  pagination={false}
                  columns={[
                    { title: "成员姓名", dataIndex: "name", key: "name" },
                    { title: "项目职责", dataIndex: "role", key: "role" },
                    {
                      title: "操作",
                      key: "action",
                      width: 80,
                      render: (_, record: any) => (
                        <Button
                          type="text"
                          danger
                          disabled={!canEdit('capa')}
                          icon={<DeleteOutlined />}
                          onClick={() => {
                            const filtered = (localData.d1_team || []).filter(
                              (m: any) => m.name !== record.name
                            );
                            handleUpdate("d1_team", filtered);
                          }}
                        />
                      ),
                    },
                  ]}
                />
                {canEdit('capa') && (
                  <div style={{ marginTop: 16, display: "flex", gap: 8 }}>
                    <Input
                      placeholder="成员姓名"
                      value={newMemberName}
                      onChange={(e) => setNewMemberName(e.target.value)}
                      style={{ width: 150 }}
                    />
                    <Select
                      value={newMemberRole}
                      onChange={(val) => setNewMemberRole(val)}
                      style={{ width: 150 }}
                      options={[
                        { value: "质量工程师", label: "质量工程师" },
                        { value: "工艺工程师", label: "工艺工程师" },
                        { value: "研发工程师", label: "研发工程师" },
                        { value: "项目经理", label: "项目经理" },
                        { value: "生产主管", label: "生产主管" },
                      ]}
                    />
                    <Button
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={() => {
                        if (!newMemberName.trim()) {
                          message.warning("请输入姓名");
                          return;
                        }
                        const exists = (localData.d1_team || []).some(
                          (m: any) => m.name === newMemberName.trim()
                        );
                        if (exists) {
                          message.warning("成员已存在");
                          return;
                        }
                        const newTeam = [
                          ...(localData.d1_team || []),
                          { name: newMemberName.trim(), role: newMemberRole },
                        ];
                        handleUpdate("d1_team", newTeam);
                        setNewMemberName("");
                      }}
                    >
                      添加成员
                    </Button>
                  </div>
                )}
              </div>
            )}

            {capa.status === "D2_DESCRIPTION" && (
              <Form layout="vertical">
                <Form.Item label="5W2H 问题描述">
                  <TextArea
                    rows={6}
                    disabled={!canEdit('capa')}
                    value={localData.d2_description || ""}
                    onChange={(e) => setLocalData({ ...localData, d2_description: e.target.value })}
                    onBlur={() => handleUpdate("d2_description", localData.d2_description)}
                    placeholder="What / Who / When / Where / Why / How / How much"
                  />
                </Form.Item>
              </Form>
            )}

            {capa.status === "D3_INTERIM" && (
              <Form layout="vertical">
                <Form.Item label="临时遏制措施">
                  <TextArea
                    rows={4}
                    disabled={!canEdit('capa')}
                    value={localData.d3_interim || ""}
                    onChange={(e) => setLocalData({ ...localData, d3_interim: e.target.value })}
                    onBlur={() => handleUpdate("d3_interim", localData.d3_interim)}
                  />
                </Form.Item>
              </Form>
            )}

            {capa.status === "D4_ROOT_CAUSE" && (
              <Form layout="vertical">
                <Form.Item label="根因分析 (5Why / 鱼骨图)">
                  <TextArea
                    rows={6}
                    disabled={!canEdit('capa')}
                    value={localData.d4_root_cause || ""}
                    onChange={(e) => setLocalData({ ...localData, d4_root_cause: e.target.value })}
                    onBlur={() => handleUpdate("d4_root_cause", localData.d4_root_cause)}
                  />
                </Form.Item>
              </Form>
            )}

            {capa.status === "D5_CORRECTION" && (
              <Form layout="vertical">
                <Form.Item label="永久纠正措施">
                  <TextArea
                    rows={4}
                    disabled={!canEdit('capa')}
                    value={localData.d5_correction || ""}
                    onChange={(e) => setLocalData({ ...localData, d5_correction: e.target.value })}
                    onBlur={() => handleUpdate("d5_correction", localData.d5_correction)}
                  />
                </Form.Item>
              </Form>
            )}

            {capa.status === "D6_VERIFICATION" && (
              <Form layout="vertical">
                <Form.Item label="效果验证">
                  <TextArea
                    rows={4}
                    disabled={!canEdit('capa')}
                    value={localData.d6_verification || ""}
                    onChange={(e) => setLocalData({ ...localData, d6_verification: e.target.value })}
                    onBlur={() => handleUpdate("d6_verification", localData.d6_verification)}
                  />
                </Form.Item>
              </Form>
            )}

            {capa.status === "D7_PREVENTION" && (
              <>
                <Form layout="vertical">
                  <Form.Item label="预防复发措施">
                    <TextArea
                      rows={4}
                      disabled={!canEdit('capa')}
                      value={localData.d7_prevention || ""}
                      onChange={(e) => setLocalData({ ...localData, d7_prevention: e.target.value })}
                      onBlur={() => handleUpdate("d7_prevention", localData.d7_prevention)}
                    />
                  </Form.Item>
                </Form>
                <Divider />
                <D7RecPanel
                  capaId={id!}
                  d5Correction={localData.d5_correction}
                  onConfirmationChange={(allConfirmed, unconfirmed) => {
                    setAllD7Confirmed(allConfirmed);
                    setD7UnconfirmedItems(unconfirmed);
                  }}
                />
              </>
            )}

            {capa.status === "D8_CLOSURE" && (
              <Form layout="vertical">
                <Form.Item label="关闭确认">
                  <TextArea
                    rows={4}
                    disabled={!canEdit('capa')}
                    value={localData.d8_closure || ""}
                    onChange={(e) => setLocalData({ ...localData, d8_closure: e.target.value })}
                    onBlur={() => handleUpdate("d8_closure", localData.d8_closure)}
                  />
                </Form.Item>
              </Form>
            )}

            {capa.status === "ARCHIVED" && <Empty description="报告已归档" />}
          </Card>
        </Col>

        <Col span={8}>
          <Card title="报告信息" size="small">
            <p><Text strong>编号:</Text> {capa.document_no}</p>
            <p><Text strong>严重等级:</Text> <Tag color="red">{capa.severity}</Tag></p>
            <p><Text strong>期限:</Text> {capa.due_date || "未设定"}</p>
            <p><Text strong>关联 FMEA:</Text> {capa.fmea_ref_id || "未关联"}</p>
            <p><Text strong>创建时间:</Text> {new Date(capa.created_at).toLocaleString("zh-CN")}</p>
          </Card>

          {linkModal && canEdit('capa') && (
            <Card title="选择关联的 FMEA" size="small" style={{ marginTop: 16 }}>
              <Select
                showSearch
                style={{ width: "100%" }}
                placeholder="搜索 FMEA 文档"
                filterOption={(input, option) =>
                  (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
                }
                options={fmeas.map((f) => ({
                  value: f.fmea_id,
                  label: `${f.document_no} - ${f.title}`,
                }))}
                onChange={(val) => handleLinkFMEA(val)}
              />
              <Button style={{ marginTop: 8 }} onClick={() => setLinkModal(false)}>取消</Button>
            </Card>
          )}
        </Col>
      </Row>
      </div>

      <Modal
        title="⚠️ 以下 FMEA 节点尚未确认"
        open={d7SkipDialogOpen}
        onOk={handleD7SkipConfirm}
        onCancel={() => setD7SkipDialogOpen(false)}
        okText="确认跳过并推进"
        cancelText="取消"
        width={600}
      >
        <p>以下推荐的 FMEA 节点尚未标记为"已更新"或"无需更新"：</p>
        <ul>
          {d7UnconfirmedItems.map((item) => (
            <li key={item.failure_mode_node_id}>
              {item.failure_mode_name}
              {item.failure_cause_node_id && ` (原因: ${item.failure_cause_node_id})`}
            </li>
          ))}
        </ul>
        <p>如需跳过，请填写理由（可选）：</p>
        <Input.TextArea
          rows={3}
          placeholder="跳过理由（可选）"
          value={d7SkipReasons["__global__"] || ""}
          onChange={(e) =>
            setD7SkipReasons({ ...d7SkipReasons, __global__: e.target.value })
          }
        />
      </Modal>
    </>
  );
}

import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Button, Space, Tag, Typography, Steps, Card, Form, Input,
  Select, App, Spin, Empty, Row, Col, Table, Divider,
} from "antd";
import { ArrowLeftOutlined, ArrowRightOutlined, LinkOutlined, PlusOutlined, DeleteOutlined } from "@ant-design/icons";
import { getCAPA, updateCAPA, advanceCAPA, linkFMEA } from "../../api/capa";
import { listFMEAs } from "../../api/fmea";
import RelatedFMEALink from "../../components/cross-links/RelatedFMEALink";
import type { CAPAReport, FMEADocument } from "../../types";
import { useAuthStore } from "../../store/authStore";


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
  const isViewer = user?.role === "viewer";
  const isAdminOrManager = user?.role === "admin" || user?.role === "manager";

  // Local Form Buffers (for input debouncing/onBlur saves)
  const [localData, setLocalData] = useState<Record<string, any>>({});
  
  // D1 Team Adding UI State
  const [newMemberName, setNewMemberName] = useState("");
  const [newMemberRole, setNewMemberRole] = useState("质量工程师");

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
    if (!id || isViewer) return;
    
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
    try {
      const updated = await advanceCAPA(id);
      setCapa(updated);
      message.success("已推进到下一步");
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
          {!isViewer && (
            <Button icon={<LinkOutlined />} onClick={() => setLinkModal(true)}>
              {capa.fmea_ref_id ? "更换FMEA关联" : "关联FMEA"}
            </Button>
          )}
          {capa.status !== "ARCHIVED" && capa.status !== "D8_CLOSURE" && (!["D7_PREVENTION", "D8_CLOSURE"].includes(capa.status) || isAdminOrManager) && !isViewer && (
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
                          disabled={isViewer}
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
                {!isViewer && (
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
                    disabled={isViewer}
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
                    disabled={isViewer}
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
                    disabled={isViewer}
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
                    disabled={isViewer}
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
                    disabled={isViewer}
                    value={localData.d6_verification || ""}
                    onChange={(e) => setLocalData({ ...localData, d6_verification: e.target.value })}
                    onBlur={() => handleUpdate("d6_verification", localData.d6_verification)}
                  />
                </Form.Item>
              </Form>
            )}

            {capa.status === "D7_PREVENTION" && (
              <Form layout="vertical">
                <Form.Item label="预防复发措施">
                  <TextArea
                    rows={4}
                    disabled={isViewer}
                    value={localData.d7_prevention || ""}
                    onChange={(e) => setLocalData({ ...localData, d7_prevention: e.target.value })}
                    onBlur={() => handleUpdate("d7_prevention", localData.d7_prevention)}
                  />
                </Form.Item>
              </Form>
            )}

            {capa.status === "D8_CLOSURE" && (
              <Form layout="vertical">
                <Form.Item label="关闭确认">
                  <TextArea
                    rows={4}
                    disabled={isViewer}
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

          {linkModal && !isViewer && (
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
  );
}

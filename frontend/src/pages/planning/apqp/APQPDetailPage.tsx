import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Card, Tag, Button, Space, Descriptions, Input, Modal, message, Spin, Row, Col, Steps, Timeline } from "antd";
import { EditOutlined } from "@ant-design/icons";
import { getAPQPProject, updateAPQPProject, transitionAPQPProject } from "../../../api/apqp";
import type { APQPProject, APQPProjectUpdate } from "../../../types";
import { useAuthStore } from "../../../store/authStore";

const PHASE_NAMES: Record<number, string> = {
  1: "策划与定义",
  2: "产品设计与开发",
  3: "过程设计与开发",
  4: "产品与过程确认",
  5: "量产启动与反馈",
};

const PROJECT_STATUS_LABELS: Record<string, string> = {
  active: "进行中",
  completed: "已完成",
  cancelled: "已取消",
};

const PROJECT_STATUS_COLORS: Record<string, string> = {
  active: "processing",
  completed: "success",
  cancelled: "default",
};

export default function APQPDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const [project, setProject] = useState<APQPProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [editOpen, setEditOpen] = useState(false);
  const [editForm, setEditForm] = useState<Record<string, string>>({});
  const [gateComment, setGateComment] = useState("");

  const isAdmin = user?.role === "admin";
  const isManager = user?.role === "admin" || user?.role === "manager";
  const isEngineer = user?.role === "admin" || user?.role === "manager" || user?.role === "quality_engineer";

  const load = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await getAPQPProject(id);
      setProject(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [id]);

  const handleTransition = async (action: string, comments?: string) => {
    if (!id) return;
    await transitionAPQPProject(id, { action: action as "submit_gate" | "approve_gate" | "reject_gate" | "cancel", comments });
    message.success("操作成功");
    setGateComment("");
    load();
  };

  const handleEdit = async () => {
    if (!id) return;
    const nullableFields = ["dfmea_id", "pfmea_id", "control_plan_id", "ppap_submission_id", "customer_name", "description"];
    const payload: APQPProjectUpdate = {};
    for (const [k, v] of Object.entries(editForm)) {
      (payload as Record<string, string | null>)[k] = nullableFields.includes(k) ? (v || null) : v;
    }
    await updateAPQPProject(id, payload);
    message.success("更新成功");
    setEditOpen(false);
    load();
  };

  if (loading || !project) {
    return <div style={{ textAlign: "center", padding: 100 }}><Spin size="large" /></div>;
  }

  const stepItems = [1, 2, 3, 4, 5].map((phase) => {
    const completedAt = (project as unknown as Record<string, string | null>)[`phase_${phase}_completed_at`];
    let status: "wait" | "process" | "finish" | "error" = "wait";
    let description = "";

    if (completedAt) {
      status = "finish";
      description = completedAt.slice(0, 10);
    } else if (project.current_phase === phase) {
      status = project.phase_status === "pending_approval" ? "error" : "process";
      description = project.phase_status === "pending_approval" ? "待审批" : "进行中";
    }

    return {
      title: `Phase ${phase}`,
      subTitle: PHASE_NAMES[phase],
      status,
      description,
    };
  });

  const actionButtons = (): ReactNode[] => {
    if (project.project_status !== "active") return [];
    const btns: ReactNode[] = [];
    if (project.phase_status === "in_progress" && isEngineer) {
      btns.push(
        <Button key="submit" type="primary" onClick={() => handleTransition("submit_gate")}>
          提交审批
        </Button>
      );
    }
    if (project.phase_status === "pending_approval") {
      if (isManager) {
        btns.push(
          <Button key="approve" type="primary" onClick={() => handleTransition("approve_gate", gateComment)}>
            审批通过
          </Button>
        );
        btns.push(
          <Button key="reject" danger onClick={() => handleTransition("reject_gate", gateComment)}>
            驳回
          </Button>
        );
      }
    }
    if (isAdmin && project.project_status === "active") {
      btns.push(
        <Button key="cancel" danger onClick={() => handleTransition("cancel")}>
          取消项目
        </Button>
      );
    }
    return btns;
  };

  return (
    <div>
      {/* Header */}
      <Card style={{ marginBottom: 16 }}>
        <Row justify="space-between" align="middle">
          <Col>
            <Space>
              <span style={{ fontSize: 20, fontWeight: 600 }}>{project.project_code}</span>
              <span style={{ fontSize: 16 }}>{project.project_name}</span>
              <Tag color={PROJECT_STATUS_COLORS[project.project_status]}>
                {PROJECT_STATUS_LABELS[project.project_status]}
              </Tag>
            </Space>
          </Col>
          <Col>
            <Space>
              {isEngineer && project.project_status === "active" && (
                <Button icon={<EditOutlined />} onClick={() => {
                  setEditForm({
                    project_name: project.project_name,
                    product_name: project.product_name,
                    customer_name: project.customer_name || "",
                    description: project.description || "",
                    dfmea_id: project.dfmea_id || "",
                    pfmea_id: project.pfmea_id || "",
                    control_plan_id: project.control_plan_id || "",
                    ppap_submission_id: project.ppap_submission_id || "",
                  });
                  setEditOpen(true);
                }}>
                  编辑
                </Button>
              )}
            </Space>
          </Col>
        </Row>
      </Card>

      {/* Project Info */}
      <Card title="项目信息" style={{ marginBottom: 16 }}>
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="项目编号">{project.project_code}</Descriptions.Item>
          <Descriptions.Item label="项目名称">{project.project_name}</Descriptions.Item>
          <Descriptions.Item label="产品">{project.product_name}</Descriptions.Item>
          <Descriptions.Item label="产品线">{project.product_line_code}</Descriptions.Item>
          <Descriptions.Item label="客户">{project.customer_name || "-"}</Descriptions.Item>
          <Descriptions.Item label="目标SOP">{project.target_sop_date || "-"}</Descriptions.Item>
          <Descriptions.Item label="创建人">{project.created_by_name}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{project.created_at ? new Date(project.created_at).toLocaleString() : "-"}</Descriptions.Item>
          <Descriptions.Item label="描述" span={2}>{project.description || "-"}</Descriptions.Item>
        </Descriptions>
      </Card>

      {/* Phase Progress */}
      <Card title="阶段进度" style={{ marginBottom: 16 }}>
        <Steps items={stepItems} current={project.current_phase - 1} status={project.phase_status === "pending_approval" ? "error" : undefined} />
      </Card>

      {/* Current Phase Actions */}
      {project.project_status === "active" && (
        <Card title="阶段操作" style={{ marginBottom: 16 }}>
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="当前阶段">
              <Tag color="blue">Phase {project.current_phase} — {PHASE_NAMES[project.current_phase]}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="阶段状态">
              {project.phase_status === "pending_approval" ? <Tag color="orange">待审批</Tag> : <Tag color="blue">进行中</Tag>}
            </Descriptions.Item>
          </Descriptions>
          <div style={{ marginTop: 12 }}>
            <Input.TextArea
              rows={3}
              value={gateComment}
              onChange={(e) => setGateComment(e.target.value)}
              placeholder="门控审批意见（可选）"
              style={{ marginBottom: 8 }}
            />
            <Space>{actionButtons()}</Space>
          </div>
        </Card>
      )}

      {/* Cross-module Links */}
      <Card title="关联交付物" style={{ marginBottom: 16 }}>
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label="DFMEA（Phase 2）">
            {project.dfmea_id ? (
              <Space>
                <span>{project.dfmea_document_no || project.dfmea_id}</span>
                <Button size="small" type="link" onClick={() => navigate(`/fmea/${project.dfmea_id}`)}>查看</Button>
              </Space>
            ) : <span style={{ color: "#999" }}>未关联</span>}
          </Descriptions.Item>
          <Descriptions.Item label="PFMEA（Phase 3）">
            {project.pfmea_id ? (
              <Space>
                <span>{project.pfmea_document_no || project.pfmea_id}</span>
                <Button size="small" type="link" onClick={() => navigate(`/fmea/${project.pfmea_id}`)}>查看</Button>
              </Space>
            ) : <span style={{ color: "#999" }}>未关联</span>}
          </Descriptions.Item>
          <Descriptions.Item label="控制计划（Phase 3）">
            {project.control_plan_id ? (
              <Space>
                <span>{project.control_plan_document_no || project.control_plan_id}</span>
                <Button size="small" type="link" onClick={() => navigate(`/control-plans/${project.control_plan_id}`)}>查看</Button>
              </Space>
            ) : <span style={{ color: "#999" }}>未关联</span>}
          </Descriptions.Item>
          <Descriptions.Item label="PPAP（Phase 4）">
            {project.ppap_submission_id ? (
              <Space>
                <span>{project.ppap_submission_part_no} — {project.ppap_submission_part_name}</span>
              </Space>
            ) : <span style={{ color: "#999" }}>未关联</span>}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* Phase Timeline */}
      <Card title="阶段时间线" style={{ marginBottom: 16 }}>
        <Timeline
          items={[1, 2, 3, 4, 5].map((phase) => {
            const completedAt = (project as unknown as Record<string, string | null>)[`phase_${phase}_completed_at`];
            return {
              color: completedAt ? "green" : project.current_phase === phase ? "blue" : "gray",
              children: (
                <div>
                  <strong>Phase {phase} — {PHASE_NAMES[phase]}</strong>
                  <div style={{ color: "#999", fontSize: 12 }}>{completedAt || "未完成"}</div>
                </div>
              ),
            };
          })}
        />
      </Card>

      {/* Gate History */}
      {project.gate_history && project.gate_history.length > 0 && (
        <Card title="门控审批记录">
          <Timeline
            items={project.gate_history.map((entry) => ({
              color: entry.action === "approve" ? "green" : entry.action === "reject" ? "red" : "blue",
              children: (
                <div>
                  <strong>
                    Phase {entry.phase} — {entry.action === "approve" ? "审批通过" : entry.action === "reject" ? "驳回" : "提交审批"}
                  </strong>
                  <span style={{ marginLeft: 8, color: "#999", fontSize: 12 }}>
                    by {entry.user_name} · {entry.timestamp ? new Date(entry.timestamp).toLocaleString() : ""}
                  </span>
                  {entry.comments && (
                    <div style={{ color: "#666", fontSize: 13, marginTop: 4 }}>
                      {entry.comments}
                    </div>
                  )}
                </div>
              ),
            }))}
          />
        </Card>
      )}

      {/* Edit Modal */}
      <Modal
        title="编辑项目"
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={handleEdit}
        width={640}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div>
            <label>项目名称</label>
            <Input value={editForm.project_name} onChange={(e) => setEditForm({ ...editForm, project_name: e.target.value })} />
          </div>
          <div>
            <label>产品名称</label>
            <Input value={editForm.product_name} onChange={(e) => setEditForm({ ...editForm, product_name: e.target.value })} />
          </div>
          <div>
            <label>客户名称</label>
            <Input value={editForm.customer_name} onChange={(e) => setEditForm({ ...editForm, customer_name: e.target.value })} />
          </div>
          <div>
            <label>描述</label>
            <Input.TextArea rows={3} value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} />
          </div>
          <div>
            <label>DFMEA ID</label>
            <Input value={editForm.dfmea_id} onChange={(e) => setEditForm({ ...editForm, dfmea_id: e.target.value })} />
          </div>
          <div>
            <label>PFMEA ID</label>
            <Input value={editForm.pfmea_id} onChange={(e) => setEditForm({ ...editForm, pfmea_id: e.target.value })} />
          </div>
          <div>
            <label>控制计划 ID</label>
            <Input value={editForm.control_plan_id} onChange={(e) => setEditForm({ ...editForm, control_plan_id: e.target.value })} />
          </div>
          <div>
            <label>PPAP ID</label>
            <Input value={editForm.ppap_submission_id} onChange={(e) => setEditForm({ ...editForm, ppap_submission_id: e.target.value })} />
          </div>
        </div>
      </Modal>
    </div>
  );
}

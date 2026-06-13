import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Card, Tag, Button, Space, Descriptions, Modal, Input, Select, message, Spin, Row, Col, Table } from "antd";
import { getPPAP, updatePPAPElement, transitionPPAP, deletePPAP } from "../../../api/ppap";
import { STATUS_COLORS, STATUS_LABELS, LEVEL_LABELS } from "./PPAPListPage";
import type { PPAPSubmission, PPAPElement } from "../../../types";

const ELEMENT_STATUS_COLORS: Record<string, string> = {
  pending: "default",
  in_review: "processing",
  approved: "success",
  not_applicable: "default",
};

const ELEMENT_STATUS_LABELS: Record<string, string> = {
  pending: "待审查",
  in_review: "审查中",
  approved: "已批准",
  not_applicable: "不适用",
};

export default function PPAPDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [ppap, setPpap] = useState<PPAPSubmission | null>(null);
  const [loading, setLoading] = useState(true);
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [editElementOpen, setEditElementOpen] = useState(false);
  const [editingElement, setEditingElement] = useState<PPAPElement | null>(null);
  const [editStatus, setEditStatus] = useState<string>("pending");
  const [editNotes, setEditNotes] = useState("");
  const [editFileUrl, setEditFileUrl] = useState("");

  const load = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await getPPAP(id);
      setPpap(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const doTransition = async (action: string, extra?: Record<string, string>) => {
    if (!id) return;
    await transitionPPAP(id, { action: action as "submit" | "approve" | "reject" | "resubmit", ...extra });
    message.success("状态更新成功");
    load();
  };

  const handleReject = async () => {
    if (!rejectReason.trim()) { message.warning("请输入驳回原因"); return; }
    await doTransition("reject", { rejection_reason: rejectReason });
    setRejectModalOpen(false);
    setRejectReason("");
  };

  const handleEditElement = (el: PPAPElement) => {
    setEditingElement(el);
    setEditStatus(el.status);
    setEditNotes(el.notes || "");
    setEditFileUrl(el.file_url || "");
    setEditElementOpen(true);
  };

  const handleSaveElement = async () => {
    if (!editingElement || !id) return;
    await updatePPAPElement(id, editingElement.element_id, {
      status: editStatus as "pending" | "in_review" | "approved" | "not_applicable",
      notes: editNotes === "" ? null : editNotes,
      file_url: editFileUrl === "" ? null : editFileUrl,
    });
    message.success("元素已更新");
    setEditElementOpen(false);
    load();
  };

  const handleDelete = async () => {
    if (!id) return;
    Modal.confirm({
      title: "确认删除",
      content: "确定要删除此 PPAP 提交吗？此操作不可撤销。",
      onOk: async () => {
        await deletePPAP(id);
        message.success("PPAP 已删除");
        navigate("/ppap");
      },
    });
  };

  if (loading || !ppap) {
    return <div style={{ textAlign: "center", padding: 100 }}><Spin size="large" /></div>;
  }

  const actionButtons = () => {
    const btns: ReactNode[] = [];
    if (ppap.status === "draft") {
      btns.push(<Button key="submit" type="primary" onClick={() => doTransition("submit")}>提交审查</Button>);
      btns.push(<Button key="delete" danger onClick={handleDelete}>删除</Button>);
    }
    if (ppap.status === "under_review") {
      btns.push(<Button key="approve" type="primary" onClick={() => doTransition("approve")}>批准</Button>);
      btns.push(<Button key="reject" danger onClick={() => setRejectModalOpen(true)}>驳回</Button>);
    }
    if (ppap.status === "rejected") {
      btns.push(<Button key="resubmit" type="primary" onClick={() => doTransition("resubmit")}>重新提交</Button>);
    }
    return btns;
  };

  const elementColumns = [
    { title: "序号", dataIndex: "element_no", key: "element_no", width: 60 },
    { title: "元素名称", dataIndex: "element_name", key: "element_name" },
    {
      title: "是否必须",
      dataIndex: "required",
      key: "required",
      width: 80,
      render: (v: boolean) => v ? "✓" : <span style={{ color: "#ccc" }}>—</span>,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (s: string) => <Tag color={ELEMENT_STATUS_COLORS[s]}>{ELEMENT_STATUS_LABELS[s] || s}</Tag>,
    },
    { title: "审查人", dataIndex: "reviewed_by", key: "reviewed_by", width: 100, render: (v: string | null) => v || "-" },
    { title: "审查时间", dataIndex: "reviewed_at", key: "reviewed_at", width: 160, render: (v: string | null) => v ? v.split(".")[0].replace("T", " ") : "-" },
    { title: "文件", dataIndex: "file_url", key: "file_url", render: (v: string | null) => v ? <a href={v} target="_blank" rel="noopener noreferrer">查看</a> : "-" },
    { title: "备注", dataIndex: "notes", key: "notes", ellipsis: true },
    {
      title: "操作",
      key: "action",
      width: 80,
      render: (_: unknown, record: PPAPElement) => (
        <Button type="link" size="small" onClick={() => handleEditElement(record)}>编辑</Button>
      ),
    },
  ];

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <Row justify="space-between" align="middle">
          <Col>
            <Space>
              <span style={{ fontSize: 20, fontWeight: 600 }}>{ppap.ppap_no}</span>
              <Tag color={STATUS_COLORS[ppap.status]}>{STATUS_LABELS[ppap.status]}</Tag>
              <span style={{ color: "#999" }}>版本 {ppap.revision}</span>
            </Space>
          </Col>
          <Col>
            <Space>{actionButtons()}</Space>
          </Col>
        </Row>
      </Card>

      <Card title="PPAP 信息" style={{ marginBottom: 16 }}>
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="供应商">{ppap.supplier_name || ppap.supplier_id}</Descriptions.Item>
          <Descriptions.Item label="零件号">{ppap.part_no}</Descriptions.Item>
          <Descriptions.Item label="零件名称">{ppap.part_name}</Descriptions.Item>
          <Descriptions.Item label="提交等级">{LEVEL_LABELS[ppap.submission_level] || ppap.submission_level}</Descriptions.Item>
          <Descriptions.Item label="客户名称">{ppap.customer_name || "-"}</Descriptions.Item>
          <Descriptions.Item label="产品线">{ppap.product_line_code || "-"}</Descriptions.Item>
          <Descriptions.Item label="提交日期">{ppap.submission_date || "-"}</Descriptions.Item>
          <Descriptions.Item label="备注" span={2}>{ppap.notes || "-"}</Descriptions.Item>
        </Descriptions>
      </Card>

      {ppap.status === "rejected" && ppap.rejection_reason && (
        <Card title="驳回原因" style={{ marginBottom: 16, borderColor: "#ff4d4f" }}>
          <div style={{ color: "#ff4d4f", whiteSpace: "pre-wrap" }}>{ppap.rejection_reason}</div>
        </Card>
      )}

      <Card title="18 元素">
        <Table
          dataSource={ppap.elements}
          columns={elementColumns}
          rowKey="element_id"
          pagination={false}
          size="small"
          rowClassName={(record) => !record.required ? "ppap-row-optional" : ""}
        />
      </Card>

      {/* Reject Modal */}
      <Modal title="驳回 PPAP" open={rejectModalOpen} onCancel={() => setRejectModalOpen(false)} onOk={handleReject}>
        <Input.TextArea
          rows={4}
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
          placeholder="请输入驳回原因"
        />
      </Modal>

      {/* Edit Element Modal */}
      <Modal title={`编辑元素: ${editingElement?.element_name || ""}`} open={editElementOpen} onCancel={() => setEditElementOpen(false)} onOk={handleSaveElement}>
        <div style={{ marginBottom: 16 }}>
          <label>状态</label>
          <Select
            style={{ width: "100%" }}
            value={editStatus}
            onChange={setEditStatus}
            options={[
              { value: "pending", label: "待审查" },
              { value: "in_review", label: "审查中" },
              { value: "approved", label: "已批准" },
              { value: "not_applicable", label: "不适用" },
            ]}
          />
        </div>
        <div style={{ marginBottom: 16 }}>
          <label>文件路径</label>
          <Input value={editFileUrl} onChange={(e) => setEditFileUrl(e.target.value)} placeholder="文件路径或 URL（可选）" />
        </div>
        <div>
          <label>备注</label>
          <Input.TextArea rows={2} value={editNotes} onChange={(e) => setEditNotes(e.target.value)} placeholder="备注（可选）" />
        </div>
      </Modal>
    </div>
  );
}

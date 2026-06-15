import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Card, Tag, Button, Space, Descriptions, Modal, Input, Select, message, Spin, Row, Col, Table } from "antd";
import { useTranslation } from "react-i18next";
import { getPPAP, updatePPAPElement, transitionPPAP, deletePPAP } from "../../../api/ppap";
import { usePPAPLabels } from "./PPAPListPage";
import type { PPAPSubmission, PPAPElement } from "../../../types";

const ELEMENT_STATUS_COLORS: Record<string, string> = {
  pending: "default",
  in_review: "processing",
  approved: "success",
  not_applicable: "default",
};

function useElementLabels(t: (key: string) => string) {
  const elementStatusLabels: Record<string, string> = {
    pending: t("elementStatus.pending"),
    in_review: t("elementStatus.inReview"),
    approved: t("elementStatus.approved"),
    not_applicable: t("elementStatus.notApplicable"),
  };

  const elementStatusOptions = [
    { value: "pending", label: t("elementStatus.pending") },
    { value: "in_review", label: t("elementStatus.inReview") },
    { value: "approved", label: t("elementStatus.approved") },
    { value: "not_applicable", label: t("elementStatus.notApplicable") },
  ];

  return { elementStatusLabels, elementStatusOptions };
}

export default function PPAPDetailPage() {
  const { t } = useTranslation("ppap");
  const { t: tc } = useTranslation("common");
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

  const { statusColors, statusLabels, levelLabels } = usePPAPLabels(t);
  const { elementStatusLabels, elementStatusOptions } = useElementLabels(t);

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
    message.success(t("message.statusUpdated"));
    load();
  };

  const handleReject = async () => {
    if (!rejectReason.trim()) { message.warning(t("message.enterRejectReason")); return; }
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
    message.success(t("message.elementUpdated"));
    setEditElementOpen(false);
    load();
  };

  const handleDelete = async () => {
    if (!id) return;
    Modal.confirm({
      title: t("message.deleteConfirmTitle"),
      content: t("message.deleteConfirmContent"),
      onOk: async () => {
        await deletePPAP(id);
        message.success(t("message.deleted"));
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
      btns.push(<Button key="submit" type="primary" onClick={() => doTransition("submit")}>{t("action.submitForReview")}</Button>);
      btns.push(<Button key="delete" danger onClick={handleDelete}>{tc("actions.delete")}</Button>);
    }
    if (ppap.status === "under_review") {
      btns.push(<Button key="approve" type="primary" onClick={() => doTransition("approve")}>{t("action.approve")}</Button>);
      btns.push(<Button key="reject" danger onClick={() => setRejectModalOpen(true)}>{t("action.reject")}</Button>);
    }
    if (ppap.status === "rejected") {
      btns.push(<Button key="resubmit" type="primary" onClick={() => doTransition("resubmit")}>{t("action.resubmit")}</Button>);
    }
    return btns;
  };

  const elementColumns = [
    { title: t("elementColumn.no"), dataIndex: "element_no", key: "element_no", width: 60 },
    { title: t("elementColumn.elementName"), dataIndex: "element_name", key: "element_name" },
    {
      title: t("elementColumn.required"),
      dataIndex: "required",
      key: "required",
      width: 80,
      render: (v: boolean) => v ? t("label.required") : <span style={{ color: "#ccc" }}>{t("label.notRequired")}</span>,
    },
    {
      title: t("elementColumn.status"),
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (s: string) => <Tag color={ELEMENT_STATUS_COLORS[s]}>{elementStatusLabels[s] || s}</Tag>,
    },
    { title: t("elementColumn.reviewer"), dataIndex: "reviewed_by", key: "reviewed_by", width: 100, render: (v: string | null) => v || "-" },
    { title: t("elementColumn.reviewTime"), dataIndex: "reviewed_at", key: "reviewed_at", width: 160, render: (v: string | null) => v ? v.split(".")[0].replace("T", " ") : "-" },
    { title: t("elementColumn.file"), dataIndex: "file_url", key: "file_url", render: (v: string | null) => v ? <a href={v} target="_blank" rel="noopener noreferrer">{tc("actions.view")}</a> : "-" },
    { title: t("elementColumn.notes"), dataIndex: "notes", key: "notes", ellipsis: true },
    {
      title: t("elementColumn.action"),
      key: "action",
      width: 80,
      render: (_: unknown, record: PPAPElement) => (
        <Button type="link" size="small" onClick={() => handleEditElement(record)}>{t("action.editElement")}</Button>
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
              <Tag color={statusColors[ppap.status]}>{statusLabels[ppap.status]}</Tag>
              <span style={{ color: "#999" }}>{t("label.version", { revision: ppap.revision })}</span>
            </Space>
          </Col>
          <Col>
            <Space>{actionButtons()}</Space>
          </Col>
        </Row>
      </Card>

      <Card title={t("label.ppapInfo")} style={{ marginBottom: 16 }}>
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label={t("column.supplier")}>{ppap.supplier_name || ppap.supplier_id}</Descriptions.Item>
          <Descriptions.Item label={t("column.partNo")}>{ppap.part_no}</Descriptions.Item>
          <Descriptions.Item label={t("column.partName")}>{ppap.part_name}</Descriptions.Item>
          <Descriptions.Item label={t("column.submissionLevel")}>{levelLabels[ppap.submission_level] || ppap.submission_level}</Descriptions.Item>
          <Descriptions.Item label={t("form.customerName")}>{ppap.customer_name || "-"}</Descriptions.Item>
          <Descriptions.Item label={t("form.productLine")}>{ppap.product_line_code || "-"}</Descriptions.Item>
          <Descriptions.Item label={t("label.submissionDate")}>{ppap.submission_date || "-"}</Descriptions.Item>
          <Descriptions.Item label={t("label.notes")} span={2}>{ppap.notes || "-"}</Descriptions.Item>
        </Descriptions>
      </Card>

      {ppap.status === "rejected" && ppap.rejection_reason && (
        <Card title={t("label.rejectionReason")} style={{ marginBottom: 16, borderColor: "#ff4d4f" }}>
          <div style={{ color: "#ff4d4f", whiteSpace: "pre-wrap" }}>{ppap.rejection_reason}</div>
        </Card>
      )}

      <Card title={t("label.elements")}>
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
      <Modal title={t("modal.rejectTitle")} open={rejectModalOpen} onCancel={() => setRejectModalOpen(false)} onOk={handleReject}>
        <Input.TextArea
          rows={4}
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
          placeholder={t("modal.rejectPlaceholder")}
        />
      </Modal>

      {/* Edit Element Modal */}
      <Modal title={t("modal.editElementTitle", { name: editingElement?.element_name || "" })} open={editElementOpen} onCancel={() => setEditElementOpen(false)} onOk={handleSaveElement}>
        <div style={{ marginBottom: 16 }}>
          <label>{t("elementColumn.status")}</label>
          <Select
            style={{ width: "100%" }}
            value={editStatus}
            onChange={setEditStatus}
            options={elementStatusOptions}
          />
        </div>
        <div style={{ marginBottom: 16 }}>
          <label>{t("label.filePath")}</label>
          <Input value={editFileUrl} onChange={(e) => setEditFileUrl(e.target.value)} placeholder={t("label.filePath")} />
        </div>
        <div>
          <label>{t("label.notes")}</label>
          <Input.TextArea rows={2} value={editNotes} onChange={(e) => setEditNotes(e.target.value)} placeholder={t("label.notes")} />
        </div>
      </Modal>
    </div>
  );
}

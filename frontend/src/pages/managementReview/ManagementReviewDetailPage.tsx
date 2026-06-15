import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Card, Descriptions, Button, Space, Tag, Collapse, Input, Table,
  Modal, Form, Select, DatePicker, message, Spin, Popconfirm,
} from "antd";
import {
  collectData, refreshData, backToDraft, startReview, closeReview,
  reopenReview, getManagementReview, updateManagementReview,
  listOutputs, createOutput, updateOutput, deleteOutput, verifyOutput,
} from "../../api/managementReview";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";
import { useTranslation } from "react-i18next";
import type { ManagementReview, ReviewOutput } from "../../types";
import ManagementReviewReportPanel from "./ManagementReviewReportPanel";
import {
  useReviewStatusMap,
  useReviewStatusColor,
  useCategoryLabels,
  useOutputStatusMap,
  useOutputStatusColor,
  useDataSources,
} from "./useOptions";

const { TextArea } = Input;

export default function ManagementReviewDetailPage() {
  const { t } = useTranslation("managementReview");
  const { t: tc } = useTranslation("common");
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const _user = useAuthStore((s) => s.user);
  const { canEdit, canApprove } = usePermission();

  const reviewStatusMap = useReviewStatusMap();
  const reviewStatusColor = useReviewStatusColor();
  const categoryLabels = useCategoryLabels();
  const outputStatusMap = useOutputStatusMap();
  const outputStatusColor = useOutputStatusColor();
  const { autoDataSources, manualTextSources, manualRichSources } = useDataSources();

  const [review, setReview] = useState<ManagementReview | null>(null);
  const [outputs, setOutputs] = useState<ReviewOutput[]>([]);
  const [loading, setLoading] = useState(true);
  const [outputModalOpen, setOutputModalOpen] = useState(false);
  const [verifyModalOpen, setVerifyModalOpen] = useState(false);
  const [activeOutput, setActiveOutput] = useState<ReviewOutput | null>(null);
  const [form] = Form.useForm();
  const [verifyForm] = Form.useForm();

  const fetchData = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [r, o] = await Promise.all([
        getManagementReview(id),
        listOutputs(id),
      ]);
      setReview(r);
      setOutputs(o);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (loading || !review) return <Spin style={{ display: "block", margin: "100px auto" }} />;

  const s = review.status;
  const isClosed = s === "closed";
  const manualInputs = (review.manual_inputs || {}) as Record<string, unknown>;

  const handleTransition = async (action: () => Promise<ManagementReview>) => {
    try {
      const updated = await action();
      setReview(updated);
      message.success(tc("messages.operationSuccess"));
    } catch (e: unknown) {
      message.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || tc("messages.operationFailed"));
    }
  };

  const handleSaveManualInput = async (key: string, value: any) => {
    if (!id) return;
    const inputs = { ...manualInputs, [key]: value };
    const updated = await updateManagementReview(id, { manual_inputs: inputs });
    setReview(updated);
  };

  const dataPackageItems: { key: string; label: React.ReactNode; children: React.ReactNode }[] = [];

  if (review.data_package) {
    for (const src of autoDataSources) {
      const data = review.data_package[src.key];
      dataPackageItems.push({
        key: src.key,
        label: src.title,
        children: data ? (
          <Descriptions column={2} size="small" bordered>
            {Object.entries(data as Record<string, unknown>).map(([k, v]) => (
              <Descriptions.Item key={k} label={k}>
                {typeof v === "object" ? JSON.stringify(v) : String(v ?? "-")}
              </Descriptions.Item>
            ))}
          </Descriptions>
        ) : <span style={{ color: "#999" }}>{t("dataSource.noData")}</span>,
      });
    }
  }

  for (const src of manualTextSources) {
    dataPackageItems.push({
      key: src.key,
      label: src.title,
      children: (
        <TextArea
          rows={3}
          defaultValue={String(manualInputs[src.key] || "")}
          disabled={isClosed || !canEdit('management_review')}
          onBlur={(e) => handleSaveManualInput(src.key, e.target.value)}
          placeholder={t("sectionEditor.placeholder")}
        />
      ),
    });
  }

  for (const src of manualRichSources) {
    const existing = manualInputs[src.key];
    const parsed = typeof existing === "string" ? JSON.parse(existing) : (typeof existing === "object" && existing !== null ? existing : {});
    const summary = (parsed as { summary?: string })?.summary || "";
    dataPackageItems.push({
      key: src.key,
      label: <>{src.title} <Tag color="orange">{t("dataSource.manualTag")}</Tag></>,
      children: (
        <Space direction="vertical" style={{ width: "100%" }}>
          <Tag color="blue">{t("dataSource.pendingModule")}</Tag>
          <TextArea
            rows={3}
            defaultValue={summary}
            disabled={isClosed || !canEdit('management_review')}
            onBlur={(e) => {
              const val = { ...parsed, summary: e.target.value };
              handleSaveManualInput(src.key, val);
            }}
            placeholder={t("sectionEditor.placeholder")}
          />
        </Space>
      ),
    });
  }

  const outputColumns = [
    {
      title: t("table.category"), dataIndex: "category", width: 120,
      render: (c: string) => categoryLabels[c] || c,
    },
    { title: t("table.description"), dataIndex: "description" },
    {
      title: t("table.dueDate"), dataIndex: "due_date", width: 120,
      render: (v: string | null) => v || "-",
    },
    {
      title: t("table.status"), dataIndex: "status", width: 100,
      render: (st: string) => {
        const info = outputStatusMap[st] ? { color: outputStatusColor[st], label: outputStatusMap[st] } : { color: "default", label: st };
        return <Tag color={info.color}>{info.label}</Tag>;
      },
    },
    {
      title: t("table.operations"), width: 200,
      render: (_: unknown, record: ReviewOutput) => (
        <Space>
          {!isClosed && record.status === "pending" && (
            <Button size="small" onClick={async () => {
              await updateOutput(id!, record.output_id, { status: "in_progress" });
              fetchData();
            }}>{t("actions.start")}</Button>
          )}
          {!isClosed && record.status === "in_progress" && (
            <Button size="small" type="primary" onClick={async () => {
              await updateOutput(id!, record.output_id, { status: "completed" });
              fetchData();
            }}>{t("actions.complete")}</Button>
          )}
          {record.status === "completed" && canApprove('management_review') && (
            <Button size="small" type="primary" onClick={() => {
              setActiveOutput(record);
              setVerifyModalOpen(true);
            }}>{t("actions.verify")}</Button>
          )}
          {!isClosed && (
            <Popconfirm title={t("confirm.deleteOutput")} onConfirm={async () => {
              await deleteOutput(id!, record.output_id);
              fetchData();
            }}>
              <Button size="small" danger>{tc("actions.delete")}</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <Card
        title={
          <Space>
            <span>{review.doc_no}</span>
            <Tag color={reviewStatusColor[s]}>{reviewStatusMap[s]}</Tag>
          </Space>
        }
        extra={
          <Space>
            {s === "draft" && !!canEdit('management_review') && (
              <Button type="primary" onClick={() => handleTransition(() => collectData(id!))}>{t("actions.collectData")}</Button>
            )}
            {s === "data_collected" && !!canEdit('management_review') && (
              <>
                <Button onClick={() => handleTransition(() => refreshData(id!))}>{t("actions.refreshData")}</Button>
                <Button onClick={() => handleTransition(() => backToDraft(id!))}>{t("actions.backToDraft")}</Button>
                <Button type="primary" onClick={() => handleTransition(() => startReview(id!))}>{t("actions.startReview")}</Button>
              </>
            )}
            {s === "in_review" && canApprove('management_review') && (
              <Button type="primary" onClick={() => handleTransition(() => closeReview(id!))}>{t("actions.closeReview")}</Button>
            )}
            {s === "closed" && canApprove('management_review') && (
              <Popconfirm title={t("confirm.reopenReview")} onConfirm={() => handleTransition(() => reopenReview(id!))}>
                <Button>{t("actions.reopenReview")}</Button>
              </Popconfirm>
            )}
            <Button onClick={() => navigate("/management-reviews")}>{tc("actions.back")}</Button>
          </Space>
        }
      >
        <Descriptions column={2}>
          <Descriptions.Item label={t("descriptions.title")}>{review.title}</Descriptions.Item>
          <Descriptions.Item label={t("descriptions.reviewDate")}>{review.review_date}</Descriptions.Item>
          <Descriptions.Item label={t("descriptions.actualDate")}>{review.actual_date || "-"}</Descriptions.Item>
          <Descriptions.Item label={t("descriptions.productLine")}>{review.product_line_code || t("descriptions.allPlants")}</Descriptions.Item>
          <Descriptions.Item label={t("descriptions.location")}>{review.location || "-"}</Descriptions.Item>
        </Descriptions>
      </Card>

      {(s === "data_collected" || s === "in_review" || s === "closed") && (
        <Card title={t("card.dataPackage")}>
          <Collapse items={dataPackageItems} />
        </Card>
      )}

      {(s === "in_review" || s === "closed") && (
        <Card title={t("card.meetingMinutes")}>
          <TextArea
            rows={6}
            defaultValue={review.meeting_minutes || ""}
            disabled={isClosed || !canEdit('management_review')}
            onBlur={async (e) => {
              if (!id) return;
              const updated = await updateManagementReview(id, { meeting_minutes: e.target.value });
              setReview(updated);
            }}
            placeholder={t("sectionEditor.placeholder")}
          />
        </Card>
      )}

      {(s === "in_review" || s === "closed") && (
        <Card
          title={t("card.outputs")}
          extra={!isClosed && !!canEdit('management_review') ? (
            <Button type="primary" onClick={() => setOutputModalOpen(true)}>{t("actions.addOutput")}</Button>
          ) : undefined}
        >
          <Table rowKey="output_id" columns={outputColumns} dataSource={outputs} pagination={false} size="small" />
        </Card>
      )}

      <ManagementReviewReportPanel review={review} onReviewChange={setReview} />

      <Modal
        title={t("modal.addOutput")}
        open={outputModalOpen}
        onCancel={() => setOutputModalOpen(false)}
        onOk={async () => {
          const values = await form.validateFields();
          await createOutput(id!, values);
          setOutputModalOpen(false);
          form.resetFields();
          fetchData();
        }}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="category" label={t("form.category")} rules={[{ required: true }]}>
            <Select>
              <Select.Option value="improvement_opportunity">{categoryLabels.improvement_opportunity}</Select.Option>
              <Select.Option value="system_change">{categoryLabels.system_change}</Select.Option>
              <Select.Option value="resource_need">{categoryLabels.resource_need}</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="description" label={t("form.description")} rules={[{ required: true }]}>
            <TextArea rows={3} />
          </Form.Item>
          <Form.Item name="due_date" label={t("form.dueDate")}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t("modal.effectVerification")}
        open={verifyModalOpen}
        onCancel={() => { setVerifyModalOpen(false); setActiveOutput(null); }}
        onOk={async () => {
          const values = await verifyForm.validateFields();
          if (activeOutput && id) {
            await verifyOutput(id, activeOutput.output_id, values.verification_notes);
            setVerifyModalOpen(false);
            setActiveOutput(null);
            verifyForm.resetFields();
            fetchData();
          }
        }}
      >
        <Form form={verifyForm} layout="vertical">
          <Form.Item name="verification_notes" label={t("form.verificationNotes")} rules={[{ required: true }]}>
            <TextArea rows={3} placeholder={t("sectionEditor.placeholder")} />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}

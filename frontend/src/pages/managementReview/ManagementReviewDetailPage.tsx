import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Descriptions, Button, Space, Tag, Collapse, Input, Table,
  Modal, Form, Select, DatePicker, message, Spin, Popconfirm,
} from "antd";
import { useTranslation } from "react-i18next";
import {
  collectData, refreshData, backToDraft, startReview, closeReview,
  reopenReview, getManagementReview, updateManagementReview,
  listOutputs, createOutput, updateOutput, deleteOutput, verifyOutput,
} from "../../api/managementReview";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";
import type { ManagementReview, ReviewOutput } from "../../types";
import { PageShell, DataCard, StatusBadge } from "../../components/design";
import ManagementReviewReportPanel from "./ManagementReviewReportPanel";
import { useReviewStatusMap, useReviewStatusColor, useOutputStatusMap, useOutputStatusColor, useCategoryLabels, useDataSources } from "./useOptions";

const { TextArea } = Input;

export default function ManagementReviewDetailPage() {
  const { t } = useTranslation("managementReview");
  const { t: tc } = useTranslation("common");
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const _user = useAuthStore((s) => s.user);
  const { canEdit, canApprove } = usePermission();
  const statusMap = useReviewStatusMap();
  const statusColor = useReviewStatusColor();
  const outputStatusMap = useOutputStatusMap();
  const outputStatusColor = useOutputStatusColor();
  const categoryLabels = useCategoryLabels();
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
      message.success(tc("messages.operationSuccess", "操作成功"));
    } catch (e: unknown) {
      message.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || tc("messages.operationFailed", "操作失败"));
    }
  };

  const handleSaveManualInput = async (key: string, value: any) => {
    if (!id) return;
    const inputs = { ...manualInputs, [key]: value };
    const updated = await updateManagementReview(id, { manual_inputs: inputs });
    setReview(updated);
  };

  // Data package collapse items
  const dataPackageItems: { key: string; label: React.ReactNode; children: React.ReactNode }[] = [];

  // Auto data sources
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
        ) : <span style={{ color: "#999" }}>{t("dataSource.noData", "暂无数据")}</span>,
      });
    }
  }

  // Manual text sources
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
          placeholder={tc("status.loading", "请输入...")}
        />
      ),
    });
  }

  // Manual rich sources (placeholder modules) — CRITICAL: parse existing, merge, save as object
  for (const src of manualRichSources) {
    const existing = manualInputs[src.key];
    const parsed = typeof existing === "string" ? JSON.parse(existing) : (typeof existing === "object" && existing !== null ? existing : {});
    const summary = (parsed as { summary?: string })?.summary || "";
    dataPackageItems.push({
      key: src.key,
      label: <>{src.title} <Tag color="orange">{t("dataSource.manualTag", "手动录入")}</Tag></>,
      children: (
        <Space direction="vertical" style={{ width: "100%" }}>
          <Tag color="blue">{t("dataSource.pendingModule", "待模块上线后自动切换")}</Tag>
          <TextArea
            rows={3}
            defaultValue={summary}
            disabled={isClosed || !canEdit('management_review')}
            onBlur={(e) => {
              const val = { ...parsed, summary: e.target.value };
              handleSaveManualInput(src.key, val);
            }}
            placeholder={t("dataSource.noData", "请输入汇总文字...")}
          />
        </Space>
      ),
    });
  }

  // Output table columns
  const outputColumns = [
    {
      title: t("table.category", "类别"), dataIndex: "category", width: 120,
      render: (c: string) => categoryLabels[c] || c,
    },
    { title: t("table.description", "描述"), dataIndex: "description" },
    {
      title: t("table.dueDate", "截止日期"), dataIndex: "due_date", width: 120,
      render: (v: string | null) => v || "-",
    },
    {
      title: t("table.status", "状态"), dataIndex: "status", width: 100,
      render: (st: string) => {
        return <StatusBadge status={outputStatusColor[st] || "default"}>{outputStatusMap[st] || st}</StatusBadge>;
      },
    },
    {
      title: tc("table.operations", "操作"), width: 200,
      render: (_: unknown, record: ReviewOutput) => (
        <Space>
          {!isClosed && record.status === "pending" && (
            <Button size="small" onClick={async () => {
              await updateOutput(id!, record.output_id, { status: "in_progress" });
              fetchData();
            }}>{t("actions.start", "开始")}</Button>
          )}
          {!isClosed && record.status === "in_progress" && (
            <Button size="small" type="primary" onClick={async () => {
              await updateOutput(id!, record.output_id, { status: "completed" });
              fetchData();
            }}>{t("actions.complete", "完成")}</Button>
          )}
          {record.status === "completed" && canApprove('management_review') && (
            <Button size="small" type="primary" onClick={() => {
              setActiveOutput(record);
              setVerifyModalOpen(true);
            }}>{t("actions.verify", "验证")}</Button>
          )}
          {!isClosed && (
            <Popconfirm title={t("confirm.deleteOutput", "确认删除?")} onConfirm={async () => {
              await deleteOutput(id!, record.output_id);
              fetchData();
            }}>
              <Button size="small" danger>{tc("actions.delete", "删除")}</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <PageShell
      title={t("pageTitle.detail", "管理评审详情")}
      actions={
        <Space>
          {s === "draft" && !!canEdit('management_review') && (
            <Button type="primary" onClick={() => handleTransition(() => collectData(id!))}>{t("actions.collectData", "汇总数据")}</Button>
          )}
          {s === "data_collected" && !!canEdit('management_review') && (
            <>
              <Button onClick={() => handleTransition(() => refreshData(id!))}>{t("actions.refreshData", "刷新数据")}</Button>
              <Button onClick={() => handleTransition(() => backToDraft(id!))}>{t("actions.backToDraft", "返回草稿")}</Button>
              <Button type="primary" onClick={() => handleTransition(() => startReview(id!))}>{t("actions.startReview", "开始评审")}</Button>
            </>
          )}
          {s === "in_review" && canApprove('management_review') && (
            <Button type="primary" onClick={() => handleTransition(() => closeReview(id!))}>{t("actions.closeReview", "关闭评审")}</Button>
          )}
          {s === "closed" && canApprove('management_review') && (
            <Popconfirm title={t("confirm.reopenReview", "确认重新打开?")} onConfirm={() => handleTransition(() => reopenReview(id!))}>
              <Button>{t("actions.reopenReview", "重新打开")}</Button>
            </Popconfirm>
          )}
          <Button onClick={() => navigate("/management-reviews")}>{tc("actions.back", "返回列表")}</Button>
        </Space>
      }
    >
      <Space direction="vertical" style={{ width: "100%" }} size="large">
        {/* Basic info */}
        <DataCard title={<Space><span>{review.doc_no}</span><StatusBadge status={statusColor[s] || "info"}>{statusMap[s]}</StatusBadge></Space>}>
          <Descriptions column={2}>
            <Descriptions.Item label={t("descriptions.title", "评审主题")}>{review.title}</Descriptions.Item>
            <Descriptions.Item label={t("descriptions.reviewDate", "评审日期")}>{review.review_date}</Descriptions.Item>
            <Descriptions.Item label={t("descriptions.actualDate", "实际日期")}>{review.actual_date || "-"}</Descriptions.Item>
            <Descriptions.Item label={t("descriptions.productLine", "产品线")}>{review.product_line_code || t("descriptions.allPlants", "全厂")}</Descriptions.Item>
            <Descriptions.Item label={t("descriptions.location", "地点")}>{review.location || "-"}</Descriptions.Item>
          </Descriptions>
        </DataCard>

        {/* Data package */}
        {(s === "data_collected" || s === "in_review" || s === "closed") && (
          <DataCard title={t("card.dataPackage", "评审输入数据包")}>
            <Collapse items={dataPackageItems} />
          </DataCard>
        )}

        {/* Meeting minutes */}
        {(s === "in_review" || s === "closed") && (
          <DataCard title={t("card.meetingMinutes", "会议纪要")}>
            <TextArea
              rows={6}
              defaultValue={review.meeting_minutes || ""}
              disabled={isClosed || !canEdit('management_review')}
              onBlur={async (e) => {
                if (!id) return;
                const updated = await updateManagementReview(id, { meeting_minutes: e.target.value });
                setReview(updated);
              }}
              placeholder={t("card.meetingMinutes", "请输入评审会议纪要...")}
            />
          </DataCard>
        )}

        {/* Outputs */}
        {(s === "in_review" || s === "closed") && (
          <DataCard
            title={t("card.outputs", "评审输出措施")}
            extra={!isClosed && !!canEdit('management_review') ? (
              <Button type="primary" onClick={() => setOutputModalOpen(true)}>{t("actions.addOutput", "添加措施")}</Button>
            ) : undefined}
          >
            <Table rowKey="output_id" columns={outputColumns} dataSource={outputs} pagination={false} size="small" className="qf-table" />
          </DataCard>
        )}

        {/* Management Review Report */}
        <ManagementReviewReportPanel review={review} onReviewChange={setReview} />

        {/* Add output modal */}
        <Modal
          title={t("modal.addOutput", "添加措施")}
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
            <Form.Item name="category" label={t("form.category", "类别")} rules={[{ required: true }]}>
              <Select>
                <Select.Option value="improvement_opportunity">{categoryLabels.improvement_opportunity}</Select.Option>
                <Select.Option value="system_change">{categoryLabels.system_change}</Select.Option>
                <Select.Option value="resource_need">{categoryLabels.resource_need}</Select.Option>
              </Select>
            </Form.Item>
            <Form.Item name="description" label={t("form.description", "描述")} rules={[{ required: true }]}>
              <TextArea rows={3} />
            </Form.Item>
            <Form.Item name="due_date" label={t("form.dueDate", "截止日期")}>
              <DatePicker style={{ width: "100%" }} />
            </Form.Item>
          </Form>
        </Modal>

        {/* Verify output modal */}
        <Modal
          title={t("modal.effectVerification", "效果验证")}
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
            <Form.Item name="verification_notes" label={t("form.verificationNotes", "验证结论")} rules={[{ required: true }]}>
              <TextArea rows={3} placeholder={t("form.verificationNotes", "请输入效果验证结论...")} />
            </Form.Item>
          </Form>
        </Modal>
      </Space>
    </PageShell>
  );
}
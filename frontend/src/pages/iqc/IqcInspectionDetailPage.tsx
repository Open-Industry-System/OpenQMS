import { useState, useEffect, useCallback, useMemo } from "react";
import {
  Card,
  Button,
  Tag,
  Space,
  Form,
  Input,
  Select,
  App,
  Table,
  Row,
  Col,
  Steps,
  InputNumber,
  Descriptions,
  Divider,
} from "antd";
import {
  ArrowLeftOutlined,
  PlayCircleOutlined,
  CheckCircleOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";
import type { IqcInspection } from "../../types";
import {
  getInspection,
  startInspection,
  updateInspectionItems,
  judgeInspection,
  closeInspection,
  triggerScar,
  requestReinspect,
  approveConcession,
} from "../../api/iqc";

const { Option } = Select;
const { TextArea } = Input;

function statusToStep(status: string): number {
  switch (status) {
    case "pending":
      return 0;
    case "inspecting":
      return 1;
    case "judged":
      return 2;
    case "closed":
      return 3;
    default:
      return 0;
  }
}

export default function IqcInspectionDetailPage() {
  const { t } = useTranslation("iqc");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const _user = useAuthStore((s) => s.user);
  const { canEdit, canApprove } = usePermission();

  const [inspection, setInspection] = useState<IqcInspection | null>(null);
  const [loading, setLoading] = useState(false);
  const [itemForm] = Form.useForm();
  const [judgeForm] = Form.useForm();

  const statusMap = useMemo<Record<string, { label: string; color: string }>>(
    () => ({
      pending: { label: t("status.inspection.pending"), color: "orange" },
      inspecting: { label: t("status.inspection.inspecting"), color: "blue" },
      judged: { label: t("status.inspection.judged"), color: "cyan" },
      closed: { label: t("status.inspection.closed"), color: "default" },
    }),
    [t]
  );

  const resultMap = useMemo<Record<string, { label: string; color: string }>>(
    () => ({
      pending: { label: t("status.result.pending"), color: "default" },
      accepted: { label: t("status.result.accepted"), color: "green" },
      rejected: { label: t("status.result.rejected"), color: "red" },
      concession: { label: t("status.result.concession"), color: "gold" },
    }),
    [t]
  );

  const fetchInspection = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await getInspection(id);
      setInspection(data);
    } catch {
      message.error(t("messages.loadInspectionFailed"));
    } finally {
      setLoading(false);
    }
  }, [id, message, t]);

  useEffect(() => {
    fetchInspection();
  }, [fetchInspection]);

  const handleStart = async () => {
    if (!id) return;
    try {
      await startInspection(id);
      message.success(t("messages.inspectionStarted"));
      fetchInspection();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed"));
    }
  };

  const handleUpdateItems = async (values: Record<string, unknown>) => {
    if (!id) return;
    try {
      await updateInspectionItems(id, values.items as Record<string, unknown>[]);
      message.success(t("messages.itemsUpdated"));
      fetchInspection();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed"));
    }
  };

  const handleJudge = async (values: Record<string, unknown>) => {
    if (!id) return;
    try {
      await judgeInspection(id, {
        inspection_result: values.inspection_result as string,
        defect_qty: (values.defect_qty as number) || 0,
        defect_description: (values.defect_description as string) || null,
        sample_qty: (values.sample_qty as number) || null,
      });
      message.success(t("messages.judgementSubmitted"));
      fetchInspection();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed"));
    }
  };

  const handleClose = async () => {
    if (!id) return;
    try {
      await closeInspection(id);
      message.success(t("messages.inspectionClosed"));
      fetchInspection();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed"));
    }
  };

  const handleTriggerScar = async () => {
    if (!id) return;
    try {
      const result = await triggerScar(id);
      message.success(t("messages.scarTriggered"));
      if (result.linked_scar_id) {
        navigate(`/scars/${result.linked_scar_id}`);
      } else {
        fetchInspection();
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed"));
    }
  };

  const handleReinspect = async () => {
    if (!id) return;
    try {
      await requestReinspect(id);
      message.success(t("messages.reinspectRequested"));
      fetchInspection();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed"));
    }
  };

  const handleConcession = async () => {
    if (!id) return;
    try {
      await approveConcession(id, t("status.result.concession"));
      message.success(t("messages.concessionApproved"));
      fetchInspection();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed"));
    }
  };

  const itemColumns = useMemo(
    () => [
      { title: t("table.sortOrder"), dataIndex: "sort_order", width: 60 },
      { title: t("table.category"), dataIndex: "category", width: 100 },
      { title: t("table.itemName"), dataIndex: "item_name", width: 200 },
      { title: t("table.inspectType"), dataIndex: "inspect_type", width: 100 },
      { title: t("table.specUpper"), dataIndex: "spec_upper", width: 100, render: (v: number | null) => v ?? "—" },
      { title: t("table.specLower"), dataIndex: "spec_lower", width: 100, render: (v: number | null) => v ?? "—" },
      { title: t("table.sampleSize"), dataIndex: "sample_size", width: 80, render: (v: number | null) => v ?? "—" },
      { title: t("table.acceptNo"), dataIndex: "accept_no", width: 60, render: (v: number | null) => v ?? "—" },
      { title: t("table.rejectNo"), dataIndex: "reject_no", width: 60, render: (v: number | null) => v ?? "—" },
      { title: t("table.defectQty"), dataIndex: "defect_qty", width: 80 },
      {
        title: t("table.result"),
        dataIndex: "result",
        width: 100,
        render: (result: string) => {
          const cfg = resultMap[result] || { label: result, color: "default" };
          return <Tag color={cfg.color}>{cfg.label}</Tag>;
        },
      },
      { title: t("table.remark"), dataIndex: "remark", ellipsis: true, render: (v: string | null) => v || "—" },
    ],
    [t, resultMap]
  );

  if (!inspection) {
    return <div>{tc("messages.loading")}</div>;
  }

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/iqc/inspections")}>
          {t("actions.backToList")}
        </Button>
        {inspection.status === "pending" && canEdit('iqc') && (
          <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleStart}>
            {t("actions.startInspection")}
          </Button>
        )}
        {inspection.status === "judged" && canEdit('iqc') && (
          <Button type="primary" onClick={handleClose}>
            {t("actions.closeInspection")}
          </Button>
        )}
        {inspection.status === "judged" && inspection.inspection_result === "rejected" && canEdit('iqc') && (
          <>
            <Button danger onClick={handleTriggerScar}>
              {t("actions.triggerScar")}
            </Button>
            <Button onClick={handleReinspect}>{t("actions.requestReinspect")}</Button>
            {canApprove('iqc') && (
              <Button onClick={handleConcession}>{t("actions.approveConcession")}</Button>
            )}
          </>
        )}
      </Space>

      <Card title={t("detail.inspectionInfo")} loading={loading}>
        <Steps current={statusToStep(inspection.status)} style={{ marginBottom: 24 }}>
          <Steps.Step title={t("steps.pending")} />
          <Steps.Step title={t("steps.inspecting")} />
          <Steps.Step title={t("steps.judged")} />
          <Steps.Step title={t("steps.closed")} />
        </Steps>

        <Descriptions bordered column={3}>
          <Descriptions.Item label={t("table.inspectionNo")}>{inspection.inspection_no}</Descriptions.Item>
          <Descriptions.Item label={t("table.partNo")}>{inspection.part_no || "—"}</Descriptions.Item>
          <Descriptions.Item label={t("table.partName")}>{inspection.part_name || "—"}</Descriptions.Item>
          <Descriptions.Item label={t("table.lotNo")}>{inspection.lot_no || "—"}</Descriptions.Item>
          <Descriptions.Item label={t("table.lotQty")}>{inspection.lot_qty || "—"}</Descriptions.Item>
          <Descriptions.Item label={t("table.sampleSize")}>{inspection.sample_qty || "—"}</Descriptions.Item>
          <Descriptions.Item label={t("table.inspectionMode")}>
            {inspection.inspection_mode === "quick" ? t("inspectionMode.quick") : t("inspectionMode.detailed")}
          </Descriptions.Item>
          <Descriptions.Item label={t("table.status")}>
            <Tag color={statusMap[inspection.status]?.color}>
              {statusMap[inspection.status]?.label}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t("table.inspectionResult")}>
            <Tag color={resultMap[inspection.inspection_result]?.color}>
              {resultMap[inspection.inspection_result]?.label}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t("descriptions.aqlLevel")}>{inspection.aql_level || "—"}</Descriptions.Item>
          <Descriptions.Item label={t("descriptions.inspectionLevel")}>{inspection.inspection_level || "—"}</Descriptions.Item>
          <Descriptions.Item label={t("descriptions.codeLetter")}>{inspection.code_letter || "—"}</Descriptions.Item>
          <Descriptions.Item label={t("descriptions.acceptNo")}>{inspection.accept_number ?? "—"}</Descriptions.Item>
          <Descriptions.Item label={t("descriptions.rejectNo")}>{inspection.reject_number ?? "—"}</Descriptions.Item>
          <Descriptions.Item label={t("table.defectQty")}>{inspection.defect_qty}</Descriptions.Item>
          <Descriptions.Item label={t("table.inspectionDate")}>{inspection.inspection_date || "—"}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Divider />

      {inspection.status === "inspecting" && canEdit('iqc') && (
        <Card title={t("detail.enterResults")}>
          <Form form={itemForm} onFinish={handleUpdateItems} layout="vertical">
            <Form.Item
              name="items"
              rules={[{ required: true, message: t("validation.enterResultJson") }]}
            >
              <TextArea
                rows={6}
                placeholder={t("placeholder.resultJson")}
              />
            </Form.Item>
            <Button type="primary" htmlType="submit">
              {t("form.submitResult")}
            </Button>
          </Form>
        </Card>
      )}

      {inspection.status === "inspecting" && canEdit('iqc') && (
        <Card title={t("detail.judgement")} style={{ marginTop: 16 }}>
          <Form form={judgeForm} onFinish={handleJudge} layout="vertical">
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item
                  name="inspection_result"
                  label={t("form.inspectionResult")}
                  rules={[{ required: true }]}
                >
                  <Select placeholder={t("placeholder.selectResult")}>
                    <Option value="accepted">{t("status.result.accepted")}</Option>
                    <Option value="rejected">{t("status.result.rejected")}</Option>
                  </Select>
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="defect_qty" label={t("form.defectQty")} initialValue={0}>
                  <InputNumber min={0} style={{ width: "100%" }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="sample_qty" label={t("form.sampleQty")}>
                  <InputNumber min={0} style={{ width: "100%" }} />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item name="defect_description" label={t("form.defectDescription")}>
              <TextArea rows={3} />
            </Form.Item>
            <Button type="primary" htmlType="submit" icon={<CheckCircleOutlined />}>
              {t("form.submitJudgement")}
            </Button>
          </Form>
        </Card>
      )}

      <Divider />

      <Card title={t("detail.inspectionItems")}>
        <Table
          rowKey="item_id"
          columns={itemColumns}
          dataSource={inspection.items || []}
          scroll={{ x: 1200 }}
          pagination={false}
        />
      </Card>
    </div>
  );
}

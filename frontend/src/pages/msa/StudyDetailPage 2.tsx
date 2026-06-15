import { useState, useEffect, useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  Card,
  Button,
  Tag,
  Space,
  Form,
  Input,
  Select,
  DatePicker,
  message,
  Tabs,
  Table,
  Row,
  Col,
  Spin,
  InputNumber,
  Descriptions,
} from "antd";
import {
  ArrowLeftOutlined,
  EditOutlined,
  SaveOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  CalculatorOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";
import type {
  GrrStudy,
  BiasStudy,
  LinearityStudy,
  StabilityStudy,
  AttributeStudy,
  GrrResult,
  BiasResult,
  LinearityResult,
  StabilityResult,
  AttributeResult,
  Gauge,
  MsaSpcCharacteristic,
} from "../../types";
import {
  getGrrStudy,
  createGrrStudy,
  updateGrrStudy,
  upsertGrrMeasurements,
  getGrrMeasurements,
  computeGrr,
  getGrrResult,
  completeGrrStudy,
  getBiasStudy,
  createBiasStudy,
  updateBiasStudy,
  upsertBiasMeasurements,
  getBiasMeasurements,
  computeBias,
  getBiasResult,
  completeBiasStudy,
  getLinearityStudy,
  createLinearityStudy,
  updateLinearityStudy,
  upsertLinearityMeasurements,
  getLinearityMeasurements,
  computeLinearity,
  getLinearityResult,
  completeLinearityStudy,
  getStabilityStudy,
  createStabilityStudy,
  updateStabilityStudy,
  upsertStabilityMeasurements,
  getStabilityMeasurements,
  computeStability,
  getStabilityResult,
  completeStabilityStudy,
  getAttributeStudy,
  createAttributeStudy,
  updateAttributeStudy,
  upsertAttributeMeasurements,
  getAttributeMeasurements,
  computeAttribute,
  getAttributeResult,
  completeAttributeStudy,
  listGauges,
  listSpcCharacteristics,
} from "../../api/msa";
import dayjs from "dayjs";

const { Option } = Select;

type StudyType = "grr" | "bias" | "linearity" | "stability" | "attribute";
type Study = GrrStudy | BiasStudy | LinearityStudy | StabilityStudy | AttributeStudy;
type Result = GrrResult | BiasResult | LinearityResult | StabilityResult | AttributeResult;

export default function StudyDetailPage() {
  const { t } = useTranslation("msa");
  const { t: tc } = useTranslation("common");
  const { type, id } = useParams<{ type: StudyType; id: string }>();
  const navigate = useNavigate();
  const { user: _user } = useAuthStore();

  const isNew = id === "new";
  const { canEdit } = usePermission();

  const [study, setStudy] = useState<Study | null>(null);
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [infoForm] = Form.useForm();
  const [editing, setEditing] = useState(isNew);

  const [gauges, setGauges] = useState<Gauge[]>([]);
  const [spcChars, setSpcChars] = useState<MsaSpcCharacteristic[]>([]);

  const [measurements, setMeasurements] = useState<Record<string, unknown>[]>([]);
  const [measLoading, setMeasLoading] = useState(false);
  const [measSaving, setMeasSaving] = useState(false);

  const [result, setResult] = useState<Result | null>(null);
  const [resultLoading, setResultLoading] = useState(false);
  const [completing, setCompleting] = useState(false);

  const studyType = type as StudyType;

  const statusLabel = (status: string) => t(`study.status.${status}`, { defaultValue: status });
  const statusColor = (status: string) => status === "draft" ? "default" : status === "ongoing" ? "processing" : "success";

  const loadGauges = useCallback(async () => {
    try {
      const resp = await listGauges({ page_size: 100 });
      setGauges(resp.items);
    } catch {
      // ignore
    }
  }, []);

  const loadSpcChars = useCallback(async () => {
    try {
      const data = await listSpcCharacteristics();
      setSpcChars(data);
    } catch {
      // ignore
    }
  }, []);

  const loadStudy = useCallback(async () => {
    if (!id || isNew) return;
    setLoading(true);
    try {
      let s: Study;
      switch (studyType) {
        case "grr":
          s = await getGrrStudy(id);
          break;
        case "bias":
          s = await getBiasStudy(id);
          break;
        case "linearity":
          s = await getLinearityStudy(id);
          break;
        case "stability":
          s = await getStabilityStudy(id);
          break;
        case "attribute":
          s = await getAttributeStudy(id);
          break;
        default:
          throw new Error("unknown type");
      }
      setStudy(s);
    } catch {
      message.error(t("study.detail.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [id, isNew, studyType, t]);

  const loadMeasurements = useCallback(async () => {
    if (!id || isNew) return;
    setMeasLoading(true);
    try {
      let data: Record<string, unknown>[] = [];
      switch (studyType) {
        case "grr":
          data = await getGrrMeasurements(id);
          break;
        case "bias":
          data = await getBiasMeasurements(id);
          break;
        case "linearity":
          data = await getLinearityMeasurements(id);
          break;
        case "stability":
          data = await getStabilityMeasurements(id);
          break;
        case "attribute":
          data = await getAttributeMeasurements(id);
          break;
      }
      setMeasurements(data);
    } catch {
      // ignore
    } finally {
      setMeasLoading(false);
    }
  }, [id, isNew, studyType]);

  const loadResult = useCallback(async () => {
    if (!id || isNew) return;
    setResultLoading(true);
    try {
      let r: Result | null = null;
      switch (studyType) {
        case "grr":
          r = await getGrrResult(id);
          break;
        case "bias":
          r = await getBiasResult(id);
          break;
        case "linearity":
          r = await getLinearityResult(id);
          break;
        case "stability":
          r = await getStabilityResult(id);
          break;
        case "attribute":
          r = await getAttributeResult(id);
          break;
      }
      setResult(r);
    } catch {
      setResult(null);
    } finally {
      setResultLoading(false);
    }
  }, [id, isNew, studyType]);

  useEffect(() => {
    loadGauges();
    loadSpcChars();
  }, [loadGauges, loadSpcChars]);

  useEffect(() => {
    if (!isNew) {
      loadStudy();
      loadMeasurements();
      loadResult();
    }
  }, [loadStudy, loadMeasurements, loadResult, isNew]);

  useEffect(() => {
    if (study && editing && !isNew) {
      const s = study as unknown as Record<string, unknown>;
      const base = {
        title: s.title as string,
        gauge_id: s.gauge_id as string | null,
        characteristic_name: s.characteristic_name as string,
        spc_characteristic_id: s.spc_characteristic_id as string | null,
        unit: s.unit as string | null,
        study_date: s.study_date ? dayjs(s.study_date as string) : null,
      };
      if (studyType === "grr") {
        const g = study as GrrStudy;
        infoForm.setFieldsValue({
          ...base,
          method: g.method,
          tolerance_upper: g.tolerance_upper,
          tolerance_lower: g.tolerance_lower,
          reference_value: g.reference_value,
          appraiser_count: g.appraiser_count,
          part_count: g.part_count,
          trial_count: g.trial_count,
        });
      } else if (studyType === "bias") {
        const b = study as BiasStudy;
        infoForm.setFieldsValue({
          ...base,
          reference_value: b.reference_value,
          sample_size: b.sample_size,
        });
      } else if (studyType === "linearity") {
        const l = study as LinearityStudy;
        infoForm.setFieldsValue({
          ...base,
          tolerance_upper: l.tolerance_upper,
          tolerance_lower: l.tolerance_lower,
          sample_size_per_reference: l.sample_size_per_reference,
        });
      } else if (studyType === "stability") {
        const s = study as StabilityStudy;
        infoForm.setFieldsValue({
          ...base,
          reference_value: s.reference_value,
          subgroup_size: s.subgroup_size,
        });
      } else if (studyType === "attribute") {
        const a = study as AttributeStudy;
        infoForm.setFieldsValue({
          ...base,
          method: a.method,
          sample_size: a.sample_size,
          known_standard_count: a.known_standard_count,
        });
      }
    }
  }, [study, editing, isNew, studyType, infoForm]);

  const handleSaveInfo = async () => {
    if (!id) return;
    try {
      const values = await infoForm.validateFields();
      setSaving(true);
      const payload: Record<string, unknown> = {
        ...values,
        study_date: values.study_date ? values.study_date.format("YYYY-MM-DD") : null,
      };
      let updated: Study;
      if (isNew) {
        switch (studyType) {
          case "grr":
            updated = await createGrrStudy(payload as Omit<GrrStudy, "study_id" | "study_no" | "status" | "accepted_by" | "created_by" | "created_at" | "updated_at">);
            break;
          case "bias":
            updated = await createBiasStudy(payload as Omit<BiasStudy, "study_id" | "study_no" | "status" | "accepted_by" | "created_by" | "created_at" | "updated_at">);
            break;
          case "linearity":
            updated = await createLinearityStudy(payload as Omit<LinearityStudy, "study_id" | "study_no" | "status" | "accepted_by" | "created_by" | "created_at" | "updated_at">);
            break;
          case "stability":
            updated = await createStabilityStudy(payload as Omit<StabilityStudy, "study_id" | "study_no" | "status" | "accepted_by" | "created_by" | "created_at" | "updated_at">);
            break;
          case "attribute":
            updated = await createAttributeStudy(payload as Omit<AttributeStudy, "study_id" | "study_no" | "status" | "accepted_by" | "created_by" | "created_at" | "updated_at">);
            break;
          default:
            throw new Error("unknown type");
        }
        message.success(t("study.detail.createSuccess"));
        navigate(`/msa/studies/${studyType}/${updated.study_id}`);
      } else {
        switch (studyType) {
          case "grr":
            updated = await updateGrrStudy(id, payload);
            break;
          case "bias":
            updated = await updateBiasStudy(id, payload);
            break;
          case "linearity":
            updated = await updateLinearityStudy(id, payload);
            break;
          case "stability":
            updated = await updateStabilityStudy(id, payload);
            break;
          case "attribute":
            updated = await updateAttributeStudy(id, payload);
            break;
          default:
            throw new Error("unknown type");
        }
        setStudy(updated);
        setEditing(false);
        message.success(t("study.detail.saveSuccess"));
      }
    } catch (err: unknown) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      const e = err as { response?: { data?: { detail?: string } } };
      message.error(e.response?.data?.detail || t("study.detail.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const handleSaveMeasurements = async () => {
    if (!id || isNew) return;
    setMeasSaving(true);
    try {
      switch (studyType) {
        case "grr":
          await upsertGrrMeasurements(
            id,
            measurements as { appraiser_name: string; part_no: string; trial_no: number; value: number }[]
          );
          break;
        case "bias":
          await upsertBiasMeasurements(
            id,
            measurements as { value: number; sequence_no: number }[]
          );
          break;
        case "linearity":
          await upsertLinearityMeasurements(
            id,
            measurements as { reference_value: number; measured_value: number; sequence_no: number }[]
          );
          break;
        case "stability":
          await upsertStabilityMeasurements(
            id,
            measurements as { measurement_date: string; sample_mean: number; sample_range: number; sequence_no: number }[]
          );
          break;
        case "attribute":
          await upsertAttributeMeasurements(
            id,
            measurements as { appraiser_name: string; part_no: string; known_standard: string; appraiser_decision: string; trial_no?: number }[]
          );
          break;
      }
      message.success(t("study.detail.measurementsSaved"));
      loadStudy();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || t("study.detail.saveFailed"));
    } finally {
      setMeasSaving(false);
    }
  };

  const handleCompute = async () => {
    if (!id || isNew) return;
    setResultLoading(true);
    try {
      let r: Result;
      switch (studyType) {
        case "grr":
          r = await computeGrr(id);
          break;
        case "bias":
          r = await computeBias(id);
          break;
        case "linearity":
          r = await computeLinearity(id);
          break;
        case "stability":
          r = await computeStability(id);
          break;
        case "attribute":
          r = await computeAttribute(id);
          break;
        default:
          throw new Error("unknown type");
      }
      setResult(r);
      message.success(t("study.detail.computeSuccess"));
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || t("study.detail.computeFailed"));
    } finally {
      setResultLoading(false);
    }
  };

  const handleComplete = async (accepted: boolean) => {
    if (!id || isNew) return;
    setCompleting(true);
    try {
      let updated: Study;
      switch (studyType) {
        case "grr":
          updated = await completeGrrStudy(id, accepted);
          break;
        case "bias":
          updated = await completeBiasStudy(id, accepted);
          break;
        case "linearity":
          updated = await completeLinearityStudy(id, accepted);
          break;
        case "stability":
          updated = await completeStabilityStudy(id, accepted);
          break;
        case "attribute":
          updated = await completeAttributeStudy(id, accepted);
          break;
        default:
          throw new Error("unknown type");
      }
      setStudy(updated);
      message.success(accepted ? t("study.detail.accepted") : t("study.detail.rejected"));
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || t("study.detail.operationFailed"));
    } finally {
      setCompleting(false);
    }
  };

  const typeLabel = useMemo(() => {
    return t(`study.type.${studyType}`, { defaultValue: studyType.toUpperCase() });
  }, [studyType, t]);

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  // ─── Create form ───
  if (isNew) {
    return (
      <div style={{ padding: 24 }}>
        <div style={{ marginBottom: 16, display: "flex", alignItems: "center", gap: 12 }}>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/msa/studies")}>
            {tc("actions.back")}
          </Button>
          <h2 style={{ margin: 0, fontSize: 20 }}>
            {t("study.detail.newTitle", { type: typeLabel })}
          </h2>
        </div>
        <Card>
          <Form form={infoForm} layout="vertical">
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item label={t("study.fields.title")} name="title" rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item label={t("study.fields.characteristic_name")} name="characteristic_name" rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item label={t("study.fields.gauge_id")} name="gauge_id">
                  <Select allowClear placeholder={t("study.placeholders.selectGauge")}>
                    {gauges.map((g) => (
                      <Option key={g.gauge_id} value={g.gauge_id}>
                        {g.gauge_no} - {g.name}
                      </Option>
                    ))}
                  </Select>
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item label={t("study.fields.spc_characteristic_id")} name="spc_characteristic_id">
                  <Select allowClear placeholder={t("study.placeholders.selectSpc")}>
                    {spcChars.map((c) => (
                      <Option key={c.ic_id} value={c.ic_id}>
                        {c.ic_code} - {c.characteristic_name}
                      </Option>
                    ))}
                  </Select>
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item label={t("study.fields.unit")} name="unit">
                  <Input placeholder={t("study.placeholders.unit")} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item label={t("study.fields.study_date")} name="study_date">
                  <DatePicker style={{ width: "100%" }} />
                </Form.Item>
              </Col>
            </Row>
            {studyType === "grr" && (
              <>
                <Row gutter={16}>
                  <Col span={8}>
                    <Form.Item label={t("study.fields.method")} name="method" initialValue="average_range">
                      <Select>
                        <Option value="average_range">{t("study.method.average_range")}</Option>
                        <Option value="anova">{t("study.method.anova")}</Option>
                      </Select>
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label={t("study.fields.appraiser_count")} name="appraiser_count" initialValue={3}>
                      <InputNumber min={2} max={5} style={{ width: "100%" }} />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label={t("study.fields.part_count")} name="part_count" initialValue={10}>
                      <InputNumber min={2} max={10} style={{ width: "100%" }} />
                    </Form.Item>
                  </Col>
                </Row>
                <Row gutter={16}>
                  <Col span={8}>
                    <Form.Item label={t("study.fields.trial_count")} name="trial_count" initialValue={3}>
                      <InputNumber min={2} max={3} style={{ width: "100%" }} />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label={t("study.fields.tolerance_upper")} name="tolerance_upper">
                      <InputNumber style={{ width: "100%" }} />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label={t("study.fields.tolerance_lower")} name="tolerance_lower">
                      <InputNumber style={{ width: "100%" }} />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item label={t("study.fields.reference_value")} name="reference_value">
                  <InputNumber style={{ width: "100%" }} />
                </Form.Item>
              </>
            )}
            {studyType === "bias" && (
              <Row gutter={16}>
                <Col span={8}>
                  <Form.Item label={t("study.fields.reference_value")} name="reference_value" rules={[{ required: true }]}>
                    <InputNumber style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label={t("study.fields.sample_size")} name="sample_size" initialValue={10}>
                    <InputNumber min={5} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
              </Row>
            )}
            {studyType === "linearity" && (
              <>
                <Row gutter={16}>
                  <Col span={8}>
                    <Form.Item label={t("study.fields.tolerance_upper")} name="tolerance_upper">
                      <InputNumber style={{ width: "100%" }} />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label={t("study.fields.tolerance_lower")} name="tolerance_lower">
                      <InputNumber style={{ width: "100%" }} />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label={t("study.fields.sample_size_per_reference")} name="sample_size_per_reference" initialValue={5}>
                      <InputNumber min={3} style={{ width: "100%" }} />
                    </Form.Item>
                  </Col>
                </Row>
              </>
            )}
            {studyType === "stability" && (
              <Row gutter={16}>
                <Col span={8}>
                  <Form.Item label={t("study.fields.reference_value")} name="reference_value">
                    <InputNumber style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label={t("study.fields.subgroup_size")} name="subgroup_size" initialValue={5}>
                    <InputNumber min={2} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
              </Row>
            )}
            {studyType === "attribute" && (
              <>
                <Row gutter={16}>
                  <Col span={8}>
                    <Form.Item label={t("study.fields.method")} name="method" initialValue="risk_analysis">
                      <Select>
                        <Option value="risk_analysis">{t("study.method.risk_analysis")}</Option>
                        <Option value="signal_detection">{t("study.method.signal_detection")}</Option>
                        <Option value="analytic">{t("study.method.analytic")}</Option>
                      </Select>
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label={t("study.fields.sample_size")} name="sample_size" initialValue={50}>
                      <InputNumber min={10} style={{ width: "100%" }} />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label={t("study.fields.known_standard_count")} name="known_standard_count">
                      <InputNumber style={{ width: "100%" }} />
                    </Form.Item>
                  </Col>
                </Row>
              </>
            )}
            <Form.Item>
              <Button type="primary" loading={saving} onClick={handleSaveInfo}>
                {t("study.detail.newTitle", { type: typeLabel })}
              </Button>
            </Form.Item>
          </Form>
        </Card>
      </div>
    );
  }

  if (!study) {
    return <div style={{ padding: 24 }}>{t("study.detail.notFound")}</div>;
  }

  const statusInfo = { label: statusLabel(study.status), color: statusColor(study.status) };

  // ─── Measurement editors ───

  const renderMeasurementsEditor = () => {
    const addRow = () => {
      const maxSeq = measurements.length > 0
        ? Math.max(...measurements.map((m) => (m.sequence_no as number) || 0))
        : 0;
      if (studyType === "grr") {
        setMeasurements([...measurements, { appraiser_name: "", part_no: "", trial_no: 1, value: 0 }]);
      } else if (studyType === "bias") {
        setMeasurements([...measurements, { value: 0, sequence_no: maxSeq + 1 }]);
      } else if (studyType === "linearity") {
        setMeasurements([...measurements, { reference_value: 0, measured_value: 0, sequence_no: maxSeq + 1 }]);
      } else if (studyType === "stability") {
        setMeasurements([...measurements, { measurement_date: dayjs().format("YYYY-MM-DD"), sample_mean: 0, sample_range: 0, sequence_no: maxSeq + 1 }]);
      } else if (studyType === "attribute") {
        setMeasurements([...measurements, { appraiser_name: "", part_no: "", known_standard: "", appraiser_decision: "", trial_no: 1 }]);
      }
    };

    const removeRow = (idx: number) => {
      setMeasurements(measurements.filter((_, i) => i !== idx));
    };

    const updateRow = (idx: number, field: string, value: unknown) => {
      const next = [...measurements];
      next[idx] = { ...next[idx], [field]: value };
      setMeasurements(next);
    };

    const commonColumns = [
      {
        title: tc("actions.delete"),
        render: (_: unknown, __: unknown, idx: number) => (
          <Button size="small" danger onClick={() => removeRow(idx)}>{tc("actions.delete")}</Button>
        ),
      },
    ];

    if (studyType === "grr") {
      return (
        <div>
          <Table
            dataSource={measurements.map((m, i) => ({ ...m, key: i }))}
            pagination={false}
            size="small"
            loading={measLoading}
            columns={[
              { title: t("study.measurementColumns.appraiser_name"), dataIndex: "appraiser_name", render: (_: unknown, __: unknown, idx: number) => (
                <Input value={measurements[idx].appraiser_name as string} onChange={(e) => updateRow(idx, "appraiser_name", e.target.value)} size="small" style={{ width: 100 }} />
              )},
              { title: t("study.measurementColumns.part_no"), dataIndex: "part_no", render: (_: unknown, __: unknown, idx: number) => (
                <Input value={measurements[idx].part_no as string} onChange={(e) => updateRow(idx, "part_no", e.target.value)} size="small" style={{ width: 100 }} />
              )},
              { title: t("study.measurementColumns.trial_no"), dataIndex: "trial_no", render: (_: unknown, __: unknown, idx: number) => (
                <InputNumber min={1} value={measurements[idx].trial_no as number} onChange={(v) => updateRow(idx, "trial_no", v)} size="small" style={{ width: 60 }} />
              )},
              { title: t("study.measurementColumns.value"), dataIndex: "value", render: (_: unknown, __: unknown, idx: number) => (
                <InputNumber value={measurements[idx].value as number} onChange={(v) => updateRow(idx, "value", v)} size="small" style={{ width: 100 }} />
              )},
              ...commonColumns,
            ]}
          />
          <Button style={{ marginTop: 12 }} onClick={addRow} size="small">{t("study.measurementColumns.addRow")}</Button>
        </div>
      );
    }

    if (studyType === "bias") {
      return (
        <div>
          <Table
            dataSource={measurements.map((m, i) => ({ ...m, key: i }))}
            pagination={false}
            size="small"
            loading={measLoading}
            columns={[
              { title: t("study.measurementColumns.sequence_no"), dataIndex: "sequence_no", render: (_: unknown, __: unknown, idx: number) => (
                <InputNumber min={1} value={measurements[idx].sequence_no as number} onChange={(v) => updateRow(idx, "sequence_no", v)} size="small" style={{ width: 60 }} />
              )},
              { title: t("study.measurementColumns.value"), dataIndex: "value", render: (_: unknown, __: unknown, idx: number) => (
                <InputNumber value={measurements[idx].value as number} onChange={(v) => updateRow(idx, "value", v)} size="small" style={{ width: 120 }} />
              )},
              ...commonColumns,
            ]}
          />
          <Button style={{ marginTop: 12 }} onClick={addRow} size="small">{t("study.measurementColumns.addRow")}</Button>
        </div>
      );
    }

    if (studyType === "linearity") {
      return (
        <div>
          <Table
            dataSource={measurements.map((m, i) => ({ ...m, key: i }))}
            pagination={false}
            size="small"
            loading={measLoading}
            columns={[
              { title: t("study.measurementColumns.sequence_no"), dataIndex: "sequence_no", render: (_: unknown, __: unknown, idx: number) => (
                <InputNumber min={1} value={measurements[idx].sequence_no as number} onChange={(v) => updateRow(idx, "sequence_no", v)} size="small" style={{ width: 60 }} />
              )},
              { title: t("study.measurementColumns.reference_value"), dataIndex: "reference_value", render: (_: unknown, __: unknown, idx: number) => (
                <InputNumber value={measurements[idx].reference_value as number} onChange={(v) => updateRow(idx, "reference_value", v)} size="small" style={{ width: 120 }} />
              )},
              { title: t("study.measurementColumns.value"), dataIndex: "measured_value", render: (_: unknown, __: unknown, idx: number) => (
                <InputNumber value={measurements[idx].measured_value as number} onChange={(v) => updateRow(idx, "measured_value", v)} size="small" style={{ width: 120 }} />
              )},
              ...commonColumns,
            ]}
          />
          <Button style={{ marginTop: 12 }} onClick={addRow} size="small">{t("study.measurementColumns.addRow")}</Button>
        </div>
      );
    }

    if (studyType === "stability") {
      return (
        <div>
          <Table
            dataSource={measurements.map((m, i) => ({ ...m, key: i }))}
            pagination={false}
            size="small"
            loading={measLoading}
            columns={[
              { title: t("study.measurementColumns.sequence_no"), dataIndex: "sequence_no", render: (_: unknown, __: unknown, idx: number) => (
                <InputNumber min={1} value={measurements[idx].sequence_no as number} onChange={(v) => updateRow(idx, "sequence_no", v)} size="small" style={{ width: 60 }} />
              )},
              { title: t("study.measurementColumns.measurement_date"), dataIndex: "measurement_date", render: (_: unknown, __: unknown, idx: number) => (
                <Input value={measurements[idx].measurement_date as string} onChange={(e) => updateRow(idx, "measurement_date", e.target.value)} size="small" style={{ width: 130 }} />
              )},
              { title: t("study.measurementColumns.sample_mean"), dataIndex: "sample_mean", render: (_: unknown, __: unknown, idx: number) => (
                <InputNumber value={measurements[idx].sample_mean as number} onChange={(v) => updateRow(idx, "sample_mean", v)} size="small" style={{ width: 100 }} />
              )},
              { title: t("study.measurementColumns.sample_range"), dataIndex: "sample_range", render: (_: unknown, __: unknown, idx: number) => (
                <InputNumber value={measurements[idx].sample_range as number} onChange={(v) => updateRow(idx, "sample_range", v)} size="small" style={{ width: 100 }} />
              )},
              ...commonColumns,
            ]}
          />
          <Button style={{ marginTop: 12 }} onClick={addRow} size="small">{t("study.measurementColumns.addRow")}</Button>
        </div>
      );
    }

    if (studyType === "attribute") {
      return (
        <div>
          <Table
            dataSource={measurements.map((m, i) => ({ ...m, key: i }))}
            pagination={false}
            size="small"
            loading={measLoading}
            columns={[
              { title: t("study.measurementColumns.appraiser_name"), dataIndex: "appraiser_name", render: (_: unknown, __: unknown, idx: number) => (
                <Input value={measurements[idx].appraiser_name as string} onChange={(e) => updateRow(idx, "appraiser_name", e.target.value)} size="small" style={{ width: 100 }} />
              )},
              { title: t("study.measurementColumns.part_no"), dataIndex: "part_no", render: (_: unknown, __: unknown, idx: number) => (
                <Input value={measurements[idx].part_no as string} onChange={(e) => updateRow(idx, "part_no", e.target.value)} size="small" style={{ width: 100 }} />
              )},
              { title: t("study.measurementColumns.known_standard"), dataIndex: "known_standard", render: (_: unknown, __: unknown, idx: number) => (
                <Select value={measurements[idx].known_standard as string} onChange={(v) => updateRow(idx, "known_standard", v)} size="small" style={{ width: 90 }}>
                  <Option value={t("study.dataValues.pass")}>{t("study.measurementColumns.pass")}</Option>
                  <Option value={t("study.dataValues.fail")}>{t("study.measurementColumns.fail")}</Option>
                </Select>
              )},
              { title: t("study.measurementColumns.appraiser_decision"), dataIndex: "appraiser_decision", render: (_: unknown, __: unknown, idx: number) => (
                <Select value={measurements[idx].appraiser_decision as string} onChange={(v) => updateRow(idx, "appraiser_decision", v)} size="small" style={{ width: 90 }}>
                  <Option value={t("study.dataValues.pass")}>{t("study.measurementColumns.pass")}</Option>
                  <Option value={t("study.dataValues.fail")}>{t("study.measurementColumns.fail")}</Option>
                </Select>
              )},
              { title: t("study.measurementColumns.trial_no"), dataIndex: "trial_no", render: (_: unknown, __: unknown, idx: number) => (
                <InputNumber min={1} value={measurements[idx].trial_no as number} onChange={(v) => updateRow(idx, "trial_no", v)} size="small" style={{ width: 60 }} />
              )},
              ...commonColumns,
            ]}
          />
          <Button style={{ marginTop: 12 }} onClick={addRow} size="small">{t("study.measurementColumns.addRow")}</Button>
        </div>
      );
    }

    return null;
  };

  // ─── Results display ───

  const renderResults = () => {
    if (!result) {
      return (
        <div style={{ textAlign: "center", padding: 60, color: "#999" }}>
          {t("study.notCalculated")}
        </div>
      );
    }

    if (studyType === "grr") {
      const r = result as GrrResult;
      return (
        <Descriptions bordered column={3}>
          <Descriptions.Item label={t("study.resultLabels.ev")}>{r.ev.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.av")}>{r.av.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.grr")}>{r.grr.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.pv")}>{r.pv.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.tv")}>{r.tv.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.ndc")}>{r.ndc.toFixed(1)}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.grr_percent_tol")}>{r.grr_percent_tol.toFixed(2)}%</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.grr_percent_tv")}>{r.grr_percent_tv.toFixed(2)}%</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.ev_percent")}>{r.ev_percent.toFixed(2)}%</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.av_percent")}>{r.av_percent.toFixed(2)}%</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.pv_percent")}>{r.pv_percent.toFixed(2)}%</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.conclusion")}>{r.conclusion}</Descriptions.Item>
        </Descriptions>
      );
    }

    if (studyType === "bias") {
      const r = result as BiasResult;
      return (
        <Descriptions bordered column={2}>
          <Descriptions.Item label={t("study.resultLabels.mean")}>{r.mean.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.bias")}>{r.bias.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.bias_percent")}>{r.bias_percent?.toFixed(2) ?? "—"}%</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.std_dev")}>{r.std_dev.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.t_statistic")}>{r.t_statistic.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.p_value")}>{r.p_value.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.confidence_interval")}>[{r.lower_ci?.toFixed(4) ?? "—"}, {r.upper_ci?.toFixed(4) ?? "—"}]</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.conclusion")}>{r.conclusion}</Descriptions.Item>
        </Descriptions>
      );
    }

    if (studyType === "linearity") {
      const r = result as LinearityResult;
      return (
        <Descriptions bordered column={2}>
          <Descriptions.Item label={t("study.resultLabels.slope")}>{r.slope.toFixed(6)}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.intercept")}>{r.intercept.toFixed(6)}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.r_squared")}>{r.r_squared.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.linearity")}>{r.linearity.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.linearity_percent")}>{r.linearity_percent?.toFixed(2) ?? "—"}%</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.bias_at_lower")}>{r.bias_at_lower?.toFixed(4) ?? "—"}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.bias_at_upper")}>{r.bias_at_upper?.toFixed(4) ?? "—"}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.conclusion")}>{r.conclusion}</Descriptions.Item>
        </Descriptions>
      );
    }

    if (studyType === "stability") {
      const r = result as StabilityResult;
      return (
        <Descriptions bordered column={2}>
          <Descriptions.Item label={t("study.resultLabels.ucl_mean")}>{r.ucl_mean.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.lcl_mean")}>{r.lcl_mean?.toFixed(4) ?? "—"}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.cl_mean")}>{r.cl_mean.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.ucl_range")}>{r.ucl_range.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.lcl_range")}>{r.lcl_range?.toFixed(4) ?? "—"}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.cl_range")}>{r.cl_range.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.cpk")}>{r.cpk?.toFixed(4) ?? "—"}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.conclusion")}>{r.conclusion}</Descriptions.Item>
        </Descriptions>
      );
    }

    if (studyType === "attribute") {
      const r = result as AttributeResult;
      return (
        <Descriptions bordered column={2}>
          <Descriptions.Item label={t("study.resultLabels.effectiveness")}>{r.effectiveness.toFixed(2)}%</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.miss_rate")}>{r.miss_rate.toFixed(2)}%</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.false_alarm_rate")}>{r.false_alarm_rate.toFixed(2)}%</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.kappa_within")}>{r.kappa_within?.toFixed(4) ?? "—"}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.kappa_vs_standard")}>{r.kappa_vs_standard?.toFixed(4) ?? "—"}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.kappa_between")}>{r.kappa_between?.toFixed(4) ?? "—"}</Descriptions.Item>
          <Descriptions.Item label={t("study.resultLabels.conclusion")}>{r.conclusion}</Descriptions.Item>
        </Descriptions>
      );
    }

    return null;
  };

  const tabItems = [
    {
      key: "info",
      label: t("study.tabs.info"),
      children: (
        <Card
          extra={
            canEdit('msa') && (
              <Space>
                {editing ? (
                  <>
                    <Button onClick={() => setEditing(false)}>{tc("actions.cancel")}</Button>
                    <Button type="primary" loading={saving} onClick={handleSaveInfo}>
                      {tc("actions.save")}
                    </Button>
                  </>
                ) : (
                  <Button icon={<EditOutlined />} onClick={() => setEditing(true)}>
                    {tc("actions.edit")}
                  </Button>
                )}
              </Space>
            )
          }
        >
          {editing ? (
            <Form form={infoForm} layout="vertical">
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item label={t("study.fields.title")} name="title" rules={[{ required: true }]}>
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label={t("study.fields.characteristic_name")} name="characteristic_name" rules={[{ required: true }]}>
                    <Input />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item label={t("study.fields.gauge_id")} name="gauge_id">
                    <Select allowClear>
                      {gauges.map((g) => (
                        <Option key={g.gauge_id} value={g.gauge_id}>
                          {g.gauge_no} - {g.name}
                        </Option>
                      ))}
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label={t("study.fields.spc_characteristic_id")} name="spc_characteristic_id">
                    <Select allowClear>
                      {spcChars.map((c) => (
                        <Option key={c.ic_id} value={c.ic_id}>
                          {c.ic_code} - {c.characteristic_name}
                        </Option>
                      ))}
                    </Select>
                  </Form.Item>
                </Col>
              </Row>
            </Form>
          ) : (
            <Descriptions bordered column={2}>
              <Descriptions.Item label={t("study.columns.studyNo")}>{study.study_no}</Descriptions.Item>
              <Descriptions.Item label={t("study.fields.title")}>{study.title}</Descriptions.Item>
              <Descriptions.Item label={t("study.fields.characteristic_name")}>{study.characteristic_name}</Descriptions.Item>
              <Descriptions.Item label={t("study.fields.gauge_id")}>
                {gauges.find((g) => g.gauge_id === study.gauge_id)?.name ?? "—"}
              </Descriptions.Item>
              <Descriptions.Item label={t("study.columns.status")}>
                <Tag color={statusInfo.color}>{statusInfo.label}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t("study.fields.study_date")}>
                {study.study_date ? dayjs(study.study_date).format("YYYY-MM-DD") : "—"}
              </Descriptions.Item>
              {studyType === "grr" && (
                <>
                  <Descriptions.Item label={t("study.fields.method")}>{(study as GrrStudy).method}</Descriptions.Item>
                  <Descriptions.Item label={t("study.measurementColumns.appraiser_name")}>
                    {(study as GrrStudy).appraiser_count} / {(study as GrrStudy).part_count} / {(study as GrrStudy).trial_count}
                  </Descriptions.Item>
                </>
              )}
              {studyType === "bias" && (
                <>
                  <Descriptions.Item label={t("study.fields.reference_value")}>{(study as BiasStudy).reference_value}</Descriptions.Item>
                  <Descriptions.Item label={t("study.fields.sample_size")}>{(study as BiasStudy).sample_size}</Descriptions.Item>
                </>
              )}
              {studyType === "linearity" && (
                <>
                  <Descriptions.Item label={t("study.fields.sample_size_per_reference")}>{(study as LinearityStudy).sample_size_per_reference}</Descriptions.Item>
                </>
              )}
              {studyType === "stability" && (
                <>
                  <Descriptions.Item label={t("study.fields.reference_value")}>{(study as StabilityStudy).reference_value}</Descriptions.Item>
                  <Descriptions.Item label={t("study.fields.subgroup_size")}>{(study as StabilityStudy).subgroup_size}</Descriptions.Item>
                </>
              )}
              {studyType === "attribute" && (
                <>
                  <Descriptions.Item label={t("study.fields.method")}>{(study as AttributeStudy).method}</Descriptions.Item>
                  <Descriptions.Item label={t("study.fields.sample_size")}>{(study as AttributeStudy).sample_size}</Descriptions.Item>
                </>
              )}
            </Descriptions>
          )}
        </Card>
      ),
    },
    {
      key: "measurements",
      label: t("study.tabs.measurements"),
      children: (
        <Card
          extra={
            canEdit('msa') && study.status !== "completed" && (
              <Space>
                <Button loading={measSaving} onClick={handleSaveMeasurements} icon={<SaveOutlined />}>
                  {t("study.actions.saveMeasurements")}
                </Button>
              </Space>
            )
          }
        >
          {renderMeasurementsEditor()}
        </Card>
      ),
    },
    {
      key: "results",
      label: t("study.tabs.results"),
      children: (
        <Card
          extra={
            canEdit('msa') && study.status !== "completed" && (
              <Space>
                <Button loading={resultLoading} onClick={handleCompute} icon={<CalculatorOutlined />} type="primary">
                  {t("study.actions.compute")}
                </Button>
                {result && (
                  <>
                    <Button loading={completing} onClick={() => handleComplete(true)} icon={<CheckCircleOutlined />}>
                      {t("study.actions.accept")}
                    </Button>
                    <Button loading={completing} onClick={() => handleComplete(false)} icon={<CloseCircleOutlined />} danger>
                      {t("study.actions.reject")}
                    </Button>
                  </>
                )}
              </Space>
            )
          }
        >
          {renderResults()}
        </Card>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 16, display: "flex", alignItems: "center", gap: 12 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/msa/studies")}>
          {tc("actions.back")}
        </Button>
        <h2 style={{ margin: 0, fontSize: 20 }}>{study.title}</h2>
        <Tag color={statusInfo.color}>{statusInfo.label}</Tag>
        <Tag>{typeLabel}</Tag>
      </div>
      <Tabs items={tabItems} />
    </div>
  );
}

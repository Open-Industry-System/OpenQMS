import { useState, useEffect, useCallback, useMemo } from "react";
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

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft: { label: "草稿", color: "default" },
  ongoing: { label: "进行中", color: "processing" },
  completed: { label: "已完成", color: "success" },
};

type StudyType = "grr" | "bias" | "linearity" | "stability" | "attribute";
type Study = GrrStudy | BiasStudy | LinearityStudy | StabilityStudy | AttributeStudy;
type Result = GrrResult | BiasResult | LinearityResult | StabilityResult | AttributeResult;

export default function StudyDetailPage() {
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
      message.error("加载研究信息失败");
    } finally {
      setLoading(false);
    }
  }, [id, isNew, studyType]);

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
        message.success("研究已创建");
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
        message.success("保存成功");
      }
    } catch (err: unknown) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      const e = err as { response?: { data?: { detail?: string } } };
      message.error(e.response?.data?.detail || "保存失败");
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
      message.success("测量数据已保存");
      loadStudy();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "保存失败");
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
      message.success("计算完成");
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "计算失败");
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
      message.success(accepted ? "研究已验收通过" : "研究已标记为不通过");
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "操作失败");
    } finally {
      setCompleting(false);
    }
  };

  const typeLabel = useMemo(() => {
    switch (studyType) {
      case "grr":
        return "GRR";
      case "bias":
        return "偏倚";
      case "linearity":
        return "线性";
      case "stability":
        return "稳定性";
      case "attribute":
        return "计数型";
    }
  }, [studyType]);

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
            返回
          </Button>
          <h2 style={{ margin: 0, fontSize: 20 }}>
            新建{typeLabel}研究
          </h2>
        </div>
        <Card>
          <Form form={infoForm} layout="vertical">
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item label="标题" name="title" rules={[{ required: true, message: "请输入标题" }]}>
                  <Input />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item label="特性名称" name="characteristic_name" rules={[{ required: true, message: "请输入特性名称" }]}>
                  <Input />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item label="关联量具" name="gauge_id">
                  <Select allowClear placeholder="选择量具">
                    {gauges.map((g) => (
                      <Option key={g.gauge_id} value={g.gauge_id}>
                        {g.gauge_no} - {g.name}
                      </Option>
                    ))}
                  </Select>
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item label="SPC特性" name="spc_characteristic_id">
                  <Select allowClear placeholder="选择SPC检验特性">
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
                <Form.Item label="单位" name="unit">
                  <Input placeholder="如: mm" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item label="研究日期" name="study_date">
                  <DatePicker style={{ width: "100%" }} />
                </Form.Item>
              </Col>
            </Row>
            {studyType === "grr" && (
              <>
                <Row gutter={16}>
                  <Col span={8}>
                    <Form.Item label="方法" name="method" initialValue="average_range">
                      <Select>
                        <Option value="average_range">平均极差法</Option>
                        <Option value="anova">方差分析法</Option>
                      </Select>
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="评价人数量" name="appraiser_count" initialValue={3}>
                      <InputNumber min={2} max={5} style={{ width: "100%" }} />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="零件数量" name="part_count" initialValue={10}>
                      <InputNumber min={2} max={10} style={{ width: "100%" }} />
                    </Form.Item>
                  </Col>
                </Row>
                <Row gutter={16}>
                  <Col span={8}>
                    <Form.Item label="试验次数" name="trial_count" initialValue={3}>
                      <InputNumber min={2} max={3} style={{ width: "100%" }} />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="公差上限" name="tolerance_upper">
                      <InputNumber style={{ width: "100%" }} />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="公差下限" name="tolerance_lower">
                      <InputNumber style={{ width: "100%" }} />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item label="基准值" name="reference_value">
                  <InputNumber style={{ width: "100%" }} />
                </Form.Item>
              </>
            )}
            {studyType === "bias" && (
              <Row gutter={16}>
                <Col span={8}>
                  <Form.Item label="基准值" name="reference_value" rules={[{ required: true }]}>
                    <InputNumber style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="样本量" name="sample_size" initialValue={10}>
                    <InputNumber min={5} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
              </Row>
            )}
            {studyType === "linearity" && (
              <>
                <Row gutter={16}>
                  <Col span={8}>
                    <Form.Item label="公差上限" name="tolerance_upper">
                      <InputNumber style={{ width: "100%" }} />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="公差下限" name="tolerance_lower">
                      <InputNumber style={{ width: "100%" }} />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="每基准样本量" name="sample_size_per_reference" initialValue={5}>
                      <InputNumber min={3} style={{ width: "100%" }} />
                    </Form.Item>
                  </Col>
                </Row>
              </>
            )}
            {studyType === "stability" && (
              <Row gutter={16}>
                <Col span={8}>
                  <Form.Item label="基准值" name="reference_value">
                    <InputNumber style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="子组大小" name="subgroup_size" initialValue={5}>
                    <InputNumber min={2} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
              </Row>
            )}
            {studyType === "attribute" && (
              <>
                <Row gutter={16}>
                  <Col span={8}>
                    <Form.Item label="方法" name="method" initialValue="risk_analysis">
                      <Select>
                        <Option value="risk_analysis">风险分析法</Option>
                        <Option value="signal_detection">信号探测法</Option>
                        <Option value="analytic">解析法</Option>
                      </Select>
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="样本量" name="sample_size" initialValue={50}>
                      <InputNumber min={10} style={{ width: "100%" }} />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="已知标准数量" name="known_standard_count">
                      <InputNumber style={{ width: "100%" }} />
                    </Form.Item>
                  </Col>
                </Row>
              </>
            )}
            <Form.Item>
              <Button type="primary" loading={saving} onClick={handleSaveInfo}>
                创建研究
              </Button>
            </Form.Item>
          </Form>
        </Card>
      </div>
    );
  }

  if (!study) {
    return <div style={{ padding: 24 }}>研究不存在</div>;
  }

  const statusInfo = STATUS_MAP[study.status] ?? { label: study.status, color: "default" };

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

    if (studyType === "grr") {
      return (
        <div>
          <Table
            dataSource={measurements.map((m, i) => ({ ...m, key: i }))}
            pagination={false}
            size="small"
            loading={measLoading}
            columns={[
              { title: "评价人", dataIndex: "appraiser_name", render: (_: unknown, __: unknown, idx: number) => (
                <Input value={measurements[idx].appraiser_name as string} onChange={(e) => updateRow(idx, "appraiser_name", e.target.value)} size="small" style={{ width: 100 }} />
              )},
              { title: "零件号", dataIndex: "part_no", render: (_: unknown, __: unknown, idx: number) => (
                <Input value={measurements[idx].part_no as string} onChange={(e) => updateRow(idx, "part_no", e.target.value)} size="small" style={{ width: 100 }} />
              )},
              { title: "试验", dataIndex: "trial_no", render: (_: unknown, __: unknown, idx: number) => (
                <InputNumber min={1} value={measurements[idx].trial_no as number} onChange={(v) => updateRow(idx, "trial_no", v)} size="small" style={{ width: 60 }} />
              )},
              { title: "测量值", dataIndex: "value", render: (_: unknown, __: unknown, idx: number) => (
                <InputNumber value={measurements[idx].value as number} onChange={(v) => updateRow(idx, "value", v)} size="small" style={{ width: 100 }} />
              )},
              { title: "操作", render: (_: unknown, __: unknown, idx: number) => (
                <Button size="small" danger onClick={() => removeRow(idx)}>删除</Button>
              )},
            ]}
          />
          <Button style={{ marginTop: 12 }} onClick={addRow} size="small">添加行</Button>
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
              { title: "序号", dataIndex: "sequence_no", render: (_: unknown, __: unknown, idx: number) => (
                <InputNumber min={1} value={measurements[idx].sequence_no as number} onChange={(v) => updateRow(idx, "sequence_no", v)} size="small" style={{ width: 60 }} />
              )},
              { title: "测量值", dataIndex: "value", render: (_: unknown, __: unknown, idx: number) => (
                <InputNumber value={measurements[idx].value as number} onChange={(v) => updateRow(idx, "value", v)} size="small" style={{ width: 120 }} />
              )},
              { title: "操作", render: (_: unknown, __: unknown, idx: number) => (
                <Button size="small" danger onClick={() => removeRow(idx)}>删除</Button>
              )},
            ]}
          />
          <Button style={{ marginTop: 12 }} onClick={addRow} size="small">添加行</Button>
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
              { title: "序号", dataIndex: "sequence_no", render: (_: unknown, __: unknown, idx: number) => (
                <InputNumber min={1} value={measurements[idx].sequence_no as number} onChange={(v) => updateRow(idx, "sequence_no", v)} size="small" style={{ width: 60 }} />
              )},
              { title: "基准值", dataIndex: "reference_value", render: (_: unknown, __: unknown, idx: number) => (
                <InputNumber value={measurements[idx].reference_value as number} onChange={(v) => updateRow(idx, "reference_value", v)} size="small" style={{ width: 120 }} />
              )},
              { title: "实测值", dataIndex: "measured_value", render: (_: unknown, __: unknown, idx: number) => (
                <InputNumber value={measurements[idx].measured_value as number} onChange={(v) => updateRow(idx, "measured_value", v)} size="small" style={{ width: 120 }} />
              )},
              { title: "操作", render: (_: unknown, __: unknown, idx: number) => (
                <Button size="small" danger onClick={() => removeRow(idx)}>删除</Button>
              )},
            ]}
          />
          <Button style={{ marginTop: 12 }} onClick={addRow} size="small">添加行</Button>
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
              { title: "序号", dataIndex: "sequence_no", render: (_: unknown, __: unknown, idx: number) => (
                <InputNumber min={1} value={measurements[idx].sequence_no as number} onChange={(v) => updateRow(idx, "sequence_no", v)} size="small" style={{ width: 60 }} />
              )},
              { title: "日期", dataIndex: "measurement_date", render: (_: unknown, __: unknown, idx: number) => (
                <Input value={measurements[idx].measurement_date as string} onChange={(e) => updateRow(idx, "measurement_date", e.target.value)} size="small" style={{ width: 130 }} />
              )},
              { title: "样本均值", dataIndex: "sample_mean", render: (_: unknown, __: unknown, idx: number) => (
                <InputNumber value={measurements[idx].sample_mean as number} onChange={(v) => updateRow(idx, "sample_mean", v)} size="small" style={{ width: 100 }} />
              )},
              { title: "样本极差", dataIndex: "sample_range", render: (_: unknown, __: unknown, idx: number) => (
                <InputNumber value={measurements[idx].sample_range as number} onChange={(v) => updateRow(idx, "sample_range", v)} size="small" style={{ width: 100 }} />
              )},
              { title: "操作", render: (_: unknown, __: unknown, idx: number) => (
                <Button size="small" danger onClick={() => removeRow(idx)}>删除</Button>
              )},
            ]}
          />
          <Button style={{ marginTop: 12 }} onClick={addRow} size="small">添加行</Button>
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
              { title: "评价人", dataIndex: "appraiser_name", render: (_: unknown, __: unknown, idx: number) => (
                <Input value={measurements[idx].appraiser_name as string} onChange={(e) => updateRow(idx, "appraiser_name", e.target.value)} size="small" style={{ width: 100 }} />
              )},
              { title: "零件号", dataIndex: "part_no", render: (_: unknown, __: unknown, idx: number) => (
                <Input value={measurements[idx].part_no as string} onChange={(e) => updateRow(idx, "part_no", e.target.value)} size="small" style={{ width: 100 }} />
              )},
              { title: "已知标准", dataIndex: "known_standard", render: (_: unknown, __: unknown, idx: number) => (
                <Select value={measurements[idx].known_standard as string} onChange={(v) => updateRow(idx, "known_standard", v)} size="small" style={{ width: 90 }}>
                  <Option value="合格">合格</Option>
                  <Option value="不合格">不合格</Option>
                </Select>
              )},
              { title: "评价决策", dataIndex: "appraiser_decision", render: (_: unknown, __: unknown, idx: number) => (
                <Select value={measurements[idx].appraiser_decision as string} onChange={(v) => updateRow(idx, "appraiser_decision", v)} size="small" style={{ width: 90 }}>
                  <Option value="合格">合格</Option>
                  <Option value="不合格">不合格</Option>
                </Select>
              )},
              { title: "试验", dataIndex: "trial_no", render: (_: unknown, __: unknown, idx: number) => (
                <InputNumber min={1} value={measurements[idx].trial_no as number} onChange={(v) => updateRow(idx, "trial_no", v)} size="small" style={{ width: 60 }} />
              )},
              { title: "操作", render: (_: unknown, __: unknown, idx: number) => (
                <Button size="small" danger onClick={() => removeRow(idx)}>删除</Button>
              )},
            ]}
          />
          <Button style={{ marginTop: 12 }} onClick={addRow} size="small">添加行</Button>
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
          尚未计算结果，请先录入测量数据并点击计算
        </div>
      );
    }

    if (studyType === "grr") {
      const r = result as GrrResult;
      return (
        <Descriptions bordered column={3}>
          <Descriptions.Item label="重复性 EV">{r.ev.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label="再现性 AV">{r.av.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label="GRR">{r.grr.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label="零件变差 PV">{r.pv.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label="总变差 TV">{r.tv.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label="可区分的类别数 NDC">{r.ndc.toFixed(1)}</Descriptions.Item>
          <Descriptions.Item label="GRR%公差">{r.grr_percent_tol.toFixed(2)}%</Descriptions.Item>
          <Descriptions.Item label="GRR%TV">{r.grr_percent_tv.toFixed(2)}%</Descriptions.Item>
          <Descriptions.Item label="EV%">{r.ev_percent.toFixed(2)}%</Descriptions.Item>
          <Descriptions.Item label="AV%">{r.av_percent.toFixed(2)}%</Descriptions.Item>
          <Descriptions.Item label="PV%">{r.pv_percent.toFixed(2)}%</Descriptions.Item>
          <Descriptions.Item label="结论">{r.conclusion}</Descriptions.Item>
        </Descriptions>
      );
    }

    if (studyType === "bias") {
      const r = result as BiasResult;
      return (
        <Descriptions bordered column={2}>
          <Descriptions.Item label="均值">{r.mean.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label="偏倚">{r.bias.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label="偏倚%">{r.bias_percent?.toFixed(2) ?? "—"}%</Descriptions.Item>
          <Descriptions.Item label="标准差">{r.std_dev.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label="t统计量">{r.t_statistic.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label="p值">{r.p_value.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label="置信区间">[{r.lower_ci?.toFixed(4) ?? "—"}, {r.upper_ci?.toFixed(4) ?? "—"}]</Descriptions.Item>
          <Descriptions.Item label="结论">{r.conclusion}</Descriptions.Item>
        </Descriptions>
      );
    }

    if (studyType === "linearity") {
      const r = result as LinearityResult;
      return (
        <Descriptions bordered column={2}>
          <Descriptions.Item label="斜率">{r.slope.toFixed(6)}</Descriptions.Item>
          <Descriptions.Item label="截距">{r.intercept.toFixed(6)}</Descriptions.Item>
          <Descriptions.Item label="R²">{r.r_squared.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label="线性度">{r.linearity.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label="线性度%">{r.linearity_percent?.toFixed(2) ?? "—"}%</Descriptions.Item>
          <Descriptions.Item label="下限偏倚">{r.bias_at_lower?.toFixed(4) ?? "—"}</Descriptions.Item>
          <Descriptions.Item label="上限偏倚">{r.bias_at_upper?.toFixed(4) ?? "—"}</Descriptions.Item>
          <Descriptions.Item label="结论">{r.conclusion}</Descriptions.Item>
        </Descriptions>
      );
    }

    if (studyType === "stability") {
      const r = result as StabilityResult;
      return (
        <Descriptions bordered column={2}>
          <Descriptions.Item label="均值 UCL">{r.ucl_mean.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label="均值 LCL">{r.lcl_mean?.toFixed(4) ?? "—"}</Descriptions.Item>
          <Descriptions.Item label="均值 CL">{r.cl_mean.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label="极差 UCL">{r.ucl_range.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label="极差 LCL">{r.lcl_range?.toFixed(4) ?? "—"}</Descriptions.Item>
          <Descriptions.Item label="极差 CL">{r.cl_range.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label="Cpk">{r.cpk?.toFixed(4) ?? "—"}</Descriptions.Item>
          <Descriptions.Item label="结论">{r.conclusion}</Descriptions.Item>
        </Descriptions>
      );
    }

    if (studyType === "attribute") {
      const r = result as AttributeResult;
      return (
        <Descriptions bordered column={2}>
          <Descriptions.Item label="有效性">{r.effectiveness.toFixed(2)}%</Descriptions.Item>
          <Descriptions.Item label="漏判率">{r.miss_rate.toFixed(2)}%</Descriptions.Item>
          <Descriptions.Item label="误判率">{r.false_alarm_rate.toFixed(2)}%</Descriptions.Item>
          <Descriptions.Item label="Kappa(内部)">{r.kappa_within?.toFixed(4) ?? "—"}</Descriptions.Item>
          <Descriptions.Item label="Kappa(与标准)">{r.kappa_vs_standard?.toFixed(4) ?? "—"}</Descriptions.Item>
          <Descriptions.Item label="Kappa(评价人间)">{r.kappa_between?.toFixed(4) ?? "—"}</Descriptions.Item>
          <Descriptions.Item label="结论">{r.conclusion}</Descriptions.Item>
        </Descriptions>
      );
    }

    return null;
  };

  const tabItems = [
    {
      key: "info",
      label: "基本信息",
      children: (
        <Card
          extra={
            canEdit('msa') && (
              <Space>
                {editing ? (
                  <>
                    <Button onClick={() => setEditing(false)}>取消</Button>
                    <Button type="primary" loading={saving} onClick={handleSaveInfo}>
                      保存
                    </Button>
                  </>
                ) : (
                  <Button icon={<EditOutlined />} onClick={() => setEditing(true)}>
                    编辑
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
                  <Form.Item label="标题" name="title" rules={[{ required: true }]}>
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="特性名称" name="characteristic_name" rules={[{ required: true }]}>
                    <Input />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item label="关联量具" name="gauge_id">
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
                  <Form.Item label="SPC特性" name="spc_characteristic_id">
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
              <Descriptions.Item label="研究编号">{study.study_no}</Descriptions.Item>
              <Descriptions.Item label="标题">{study.title}</Descriptions.Item>
              <Descriptions.Item label="特性名称">{study.characteristic_name}</Descriptions.Item>
              <Descriptions.Item label="关联量具">
                {gauges.find((g) => g.gauge_id === study.gauge_id)?.name ?? "—"}
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusInfo.color}>{statusInfo.label}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="研究日期">
                {study.study_date ? dayjs(study.study_date).format("YYYY-MM-DD") : "—"}
              </Descriptions.Item>
              {studyType === "grr" && (
                <>
                  <Descriptions.Item label="方法">{(study as GrrStudy).method}</Descriptions.Item>
                  <Descriptions.Item label="评价人/零件/试验">
                    {(study as GrrStudy).appraiser_count} / {(study as GrrStudy).part_count} / {(study as GrrStudy).trial_count}
                  </Descriptions.Item>
                </>
              )}
              {studyType === "bias" && (
                <>
                  <Descriptions.Item label="基准值">{(study as BiasStudy).reference_value}</Descriptions.Item>
                  <Descriptions.Item label="样本量">{(study as BiasStudy).sample_size}</Descriptions.Item>
                </>
              )}
              {studyType === "linearity" && (
                <>
                  <Descriptions.Item label="每基准样本量">{(study as LinearityStudy).sample_size_per_reference}</Descriptions.Item>
                </>
              )}
              {studyType === "stability" && (
                <>
                  <Descriptions.Item label="子组大小">{(study as StabilityStudy).subgroup_size}</Descriptions.Item>
                </>
              )}
              {studyType === "attribute" && (
                <>
                  <Descriptions.Item label="方法">{(study as AttributeStudy).method}</Descriptions.Item>
                  <Descriptions.Item label="样本量">{(study as AttributeStudy).sample_size}</Descriptions.Item>
                </>
              )}
            </Descriptions>
          )}
        </Card>
      ),
    },
    {
      key: "measurements",
      label: "测量数据",
      children: (
        <Card
          extra={
            canEdit('msa') && study.status !== "completed" && (
              <Space>
                <Button loading={measSaving} onClick={handleSaveMeasurements} icon={<SaveOutlined />}>
                  保存数据
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
      label: "分析结果",
      children: (
        <Card
          extra={
            canEdit('msa') && study.status !== "completed" && (
              <Space>
                <Button loading={resultLoading} onClick={handleCompute} icon={<CalculatorOutlined />} type="primary">
                  计算结果
                </Button>
                {result && (
                  <>
                    <Button loading={completing} onClick={() => handleComplete(true)} icon={<CheckCircleOutlined />}>
                      验收通过
                    </Button>
                    <Button loading={completing} onClick={() => handleComplete(false)} icon={<CloseCircleOutlined />} danger>
                      不通过
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
          返回
        </Button>
        <h2 style={{ margin: 0, fontSize: 20 }}>{study.title}</h2>
        <Tag color={statusInfo.color}>{statusInfo.label}</Tag>
        <Tag>{typeLabel}</Tag>
      </div>
      <Tabs items={tabItems} />
    </div>
  );
}

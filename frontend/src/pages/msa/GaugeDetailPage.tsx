import { useState, useEffect, useCallback } from "react";
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
  Modal,
  Row,
  Col,
  Typography,
  Spin,
} from "antd";
import {
  ArrowLeftOutlined,
  PlusOutlined,
  EditOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";
import type { Gauge, GaugeCalibration } from "../../types";
import {
  getGauge,
  updateGauge,
  listCalibrations,
  createCalibration,
} from "../../api/msa";
import dayjs from "dayjs";

const { Option } = Select;
const { Text } = Typography;

export default function GaugeDetailPage() {
  const { t } = useTranslation("msa");
  const { t: tc } = useTranslation("common");
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user: _user } = useAuthStore();

  const { canEdit } = usePermission();

  const [gauge, setGauge] = useState<Gauge | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [infoForm] = Form.useForm();

  const [cals, setCals] = useState<GaugeCalibration[]>([]);
  const [calsLoading, setCalsLoading] = useState(false);
  const [calModalOpen, setCalModalOpen] = useState(false);
  const [calForm] = Form.useForm();
  const [calSaving, setCalSaving] = useState(false);

  const statusLabel = (status: string) => t(`gauge.status.${status}`, { defaultValue: status });

  const loadGauge = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const g = await getGauge(id);
      setGauge(g);
    } catch {
      message.error(t("gauge.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [id, t]);

  const loadCals = useCallback(async () => {
    if (!id) return;
    setCalsLoading(true);
    try {
      const data = await listCalibrations(id);
      setCals(data);
    } catch {
      message.error(t("gauge.calibration.loadFailed"));
    } finally {
      setCalsLoading(false);
    }
  }, [id, t]);

  useEffect(() => {
    Promise.all([loadGauge(), loadCals()]);
  }, [loadGauge, loadCals]);

  useEffect(() => {
    if (gauge && editing) {
      infoForm.setFieldsValue({
        gauge_no: gauge.gauge_no,
        name: gauge.name,
        model: gauge.model,
        manufacturer: gauge.manufacturer,
        resolution: gauge.resolution,
        measuring_range: gauge.measuring_range,
        department: gauge.department,
        location: gauge.location,
        status: gauge.status,
        calibration_cycle_days: gauge.calibration_cycle_days,
        next_calibration_date: gauge.next_calibration_date ? dayjs(gauge.next_calibration_date) : null,
      });
    }
  }, [gauge, editing, infoForm]);

  const handleSaveInfo = async () => {
    if (!id) return;
    try {
      const values = await infoForm.validateFields();
      setSaving(true);
      const payload = {
        ...values,
        next_calibration_date: values.next_calibration_date
          ? values.next_calibration_date.format("YYYY-MM-DD")
          : null,
        resolution: values.resolution ? Number(values.resolution) : null,
        calibration_cycle_days: values.calibration_cycle_days ? Number(values.calibration_cycle_days) : null,
      };
      const updated = await updateGauge(id, payload);
      setGauge(updated);
      setEditing(false);
      message.success(t("gauge.saveSuccess"));
    } catch (err: unknown) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(t("gauge.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const handleCancelEdit = () => {
    setEditing(false);
    infoForm.resetFields();
  };

  const handleCalSave = async () => {
    if (!id) return;
    try {
      const values = await calForm.validateFields();
      setCalSaving(true);
      await createCalibration(id, {
        ...values,
        calibration_date: values.calibration_date.format("YYYY-MM-DD"),
        next_calibration_date: values.next_calibration_date
          ? values.next_calibration_date.format("YYYY-MM-DD")
          : null,
      });
      message.success(t("gauge.calibration.addSuccess"));
      setCalModalOpen(false);
      calForm.resetFields();
      await loadCals();
      await loadGauge();
    } catch (err: unknown) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(t("gauge.saveFailed"));
    } finally {
      setCalSaving(false);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!gauge) {
    return <div style={{ padding: 24 }}>{t("gauge.notFound")}</div>;
  }

  const statusInfo = {
    label: statusLabel(gauge.status),
    color: gauge.status === "active" ? "green" : gauge.status === "inactive" ? "default" : gauge.status === "calibrating" ? "blue" : "red",
  };

  const calColumns = [
    {
      title: t("gauge.calibration.date"),
      dataIndex: "calibration_date",
      render: (v: string) => dayjs(v).format("YYYY-MM-DD"),
    },
    {
      title: t("gauge.calibration.result"),
      dataIndex: "result",
      render: (v: string) => (
        <Tag color={v === "pass" ? "green" : "red"}>{v === "pass" ? t("gauge.calibration.pass") : t("gauge.calibration.fail")}</Tag>
      ),
    },
    { title: t("gauge.calibration.certificate_no"), dataIndex: "certificate_no", render: (v: string | null) => v || "—" },
    { title: t("gauge.calibration.calibrated_by"), dataIndex: "calibrated_by", render: (v: string | null) => v || "—" },
    { title: t("gauge.calibration.notes"), dataIndex: "notes", render: (v: string | null) => v || "—" },
    {
      title: t("gauge.calibration.next_date"),
      dataIndex: "next_calibration_date",
      render: (v: string | null) => (v ? dayjs(v).format("YYYY-MM-DD") : "—"),
    },
  ];

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
                    <Button onClick={handleCancelEdit}>{tc("actions.cancel")}</Button>
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
                  <Form.Item label={t("gauge.fields.gauge_no")} name="gauge_no" rules={[{ required: true }]}>
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label={t("gauge.fields.name")} name="name" rules={[{ required: true }]}>
                    <Input />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item label={t("gauge.fields.model")} name="model">
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label={t("gauge.fields.manufacturer")} name="manufacturer">
                    <Input />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16}>
                <Col span={8}>
                  <Form.Item label={t("gauge.fields.resolution")} name="resolution">
                    <Input type="number" />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label={t("gauge.fields.measuring_range")} name="measuring_range">
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label={t("gauge.fields.calibration_cycle_days")} name="calibration_cycle_days">
                    <Input type="number" />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item label={t("gauge.fields.department")} name="department">
                    <Select allowClear>
                      <Option value="IQC">{t("gauge.department.IQC")}</Option>
                      <Option value="PQC">{t("gauge.department.PQC")}</Option>
                      <Option value="OQC">{t("gauge.department.OQC")}</Option>
                      <Option value={t("gauge.department.labValue")}>{t("gauge.department.lab")}</Option>
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label={t("gauge.fields.location")} name="location">
                    <Input />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item label={t("gauge.fields.status")} name="status">
                    <Select>
                      <Option value="active">{t("gauge.status.active")}</Option>
                      <Option value="inactive">{t("gauge.status.inactive")}</Option>
                      <Option value="calibrating">{t("gauge.status.calibrating")}</Option>
                      <Option value="scrapped">{t("gauge.status.scrapped")}</Option>
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label={t("gauge.fields.next_calibration_date")} name="next_calibration_date">
                    <DatePicker style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
              </Row>
            </Form>
          ) : (
            <Row gutter={[16, 8]}>
              <Col span={12}>
                <Text type="secondary">{t("gauge.fields.gauge_no")}</Text>
                <div>{gauge.gauge_no}</div>
              </Col>
              <Col span={12}>
                <Text type="secondary">{t("gauge.fields.name")}</Text>
                <div>{gauge.name}</div>
              </Col>
              <Col span={12}>
                <Text type="secondary">{t("gauge.fields.model")}</Text>
                <div>{gauge.model ?? "—"}</div>
              </Col>
              <Col span={12}>
                <Text type="secondary">{t("gauge.fields.manufacturer")}</Text>
                <div>{gauge.manufacturer ?? "—"}</div>
              </Col>
              <Col span={8}>
                <Text type="secondary">{t("gauge.fields.resolution")}</Text>
                <div>{gauge.resolution ?? "—"}</div>
              </Col>
              <Col span={8}>
                <Text type="secondary">{t("gauge.fields.measuring_range")}</Text>
                <div>{gauge.measuring_range ?? "—"}</div>
              </Col>
              <Col span={8}>
                <Text type="secondary">{t("gauge.fields.calibration_cycle_days")}</Text>
                <div>{gauge.calibration_cycle_days ? `${gauge.calibration_cycle_days}${t("gauge.columns.days", { days: gauge.calibration_cycle_days })}` : "—"}</div>
              </Col>
              <Col span={12}>
                <Text type="secondary">{t("gauge.fields.department")}</Text>
                <div>{gauge.department ?? "—"}</div>
              </Col>
              <Col span={12}>
                <Text type="secondary">{t("gauge.fields.location")}</Text>
                <div>{gauge.location ?? "—"}</div>
              </Col>
              <Col span={12}>
                <Text type="secondary">{t("gauge.fields.status")}</Text>
                <div>
                  <Tag color={statusInfo.color}>{statusInfo.label}</Tag>
                </div>
              </Col>
              <Col span={12}>
                <Text type="secondary">{t("gauge.fields.next_calibration_date")}</Text>
                <div>{gauge.next_calibration_date ?? "—"}</div>
              </Col>
              <Col span={12}>
                <Text type="secondary">{t("gauge.createdAt")}</Text>
                <div>{dayjs(gauge.created_at).format("YYYY-MM-DD HH:mm")}</div>
              </Col>
            </Row>
          )}
        </Card>
      ),
    },
    {
      key: "calibrations",
      label: t("gauge.calibration.title"),
      children: (
        <Card
          extra={
            canEdit('msa') && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCalModalOpen(true)}>
                {t("gauge.calibration.add")}
              </Button>
            )
          }
        >
          <Table
            loading={calsLoading}
            dataSource={cals}
            rowKey="calibration_id"
            columns={calColumns}
            pagination={false}
            size="middle"
          />
        </Card>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 16, display: "flex", alignItems: "center", gap: 12 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/msa/gauges")}>
          {tc("actions.back")}
        </Button>
        <h2 style={{ margin: 0, fontSize: 20 }}>{gauge.name}</h2>
        <Tag color={statusInfo.color}>{statusInfo.label}</Tag>
      </div>

      <Tabs items={tabItems} />

      <Modal
        title={t("gauge.calibration.add")}
        open={calModalOpen}
        onCancel={() => {
          setCalModalOpen(false);
          calForm.resetFields();
        }}
        onOk={handleCalSave}
        confirmLoading={calSaving}
        okText={tc("actions.save")}
        cancelText={tc("actions.cancel")}
        destroyOnHidden
      >
        <Form form={calForm} layout="vertical">
          <Form.Item
            label={t("gauge.calibration.date")}
            name="calibration_date"
            rules={[{ required: true }]}
          >
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item
            label={t("gauge.calibration.result")}
            name="result"
            rules={[{ required: true }]}
            initialValue="pass"
          >
            <Select>
              <Option value="pass">{t("gauge.calibration.pass")}</Option>
              <Option value="fail">{t("gauge.calibration.fail")}</Option>
            </Select>
          </Form.Item>
          <Form.Item label={t("gauge.calibration.certificate_no")} name="certificate_no">
            <Input />
          </Form.Item>
          <Form.Item label={t("gauge.calibration.calibrated_by")} name="calibrated_by">
            <Input />
          </Form.Item>
          <Form.Item label={t("gauge.calibration.notes")} name="notes">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item label={t("gauge.calibration.next_date")} name="next_calibration_date">
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

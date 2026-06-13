import { useState, useEffect, useCallback } from "react";
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

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  active: { label: "在用", color: "green" },
  inactive: { label: "闲置", color: "default" },
  calibrating: { label: "校准中", color: "blue" },
  scrapped: { label: "报废", color: "red" },
};

export default function GaugeDetailPage() {
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

  const loadGauge = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const g = await getGauge(id);
      setGauge(g);
    } catch {
      message.error("加载量具信息失败");
    } finally {
      setLoading(false);
    }
  }, [id]);

  const loadCals = useCallback(async () => {
    if (!id) return;
    setCalsLoading(true);
    try {
      const data = await listCalibrations(id);
      setCals(data);
    } catch {
      message.error("加载校准记录失败");
    } finally {
      setCalsLoading(false);
    }
  }, [id]);

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
      message.success("保存成功");
    } catch (err: unknown) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error("保存失败");
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
      message.success("校准记录已添加");
      setCalModalOpen(false);
      calForm.resetFields();
      await loadCals();
      await loadGauge();
    } catch (err: unknown) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error("保存失败");
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
    return <div style={{ padding: 24 }}>量具不存在</div>;
  }

  const statusInfo = STATUS_MAP[gauge.status] ?? { label: gauge.status, color: "default" };

  const calColumns = [
    {
      title: "校准日期",
      dataIndex: "calibration_date",
      render: (v: string) => dayjs(v).format("YYYY-MM-DD"),
    },
    {
      title: "结果",
      dataIndex: "result",
      render: (v: string) => (
        <Tag color={v === "pass" ? "green" : "red"}>{v === "pass" ? "合格" : "不合格"}</Tag>
      ),
    },
    { title: "证书编号", dataIndex: "certificate_no", render: (v: string | null) => v || "—" },
    { title: "校准人", dataIndex: "calibrated_by", render: (v: string | null) => v || "—" },
    { title: "备注", dataIndex: "notes", render: (v: string | null) => v || "—" },
    {
      title: "下次校准",
      dataIndex: "next_calibration_date",
      render: (v: string | null) => (v ? dayjs(v).format("YYYY-MM-DD") : "—"),
    },
  ];

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
                    <Button onClick={handleCancelEdit}>取消</Button>
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
                  <Form.Item label="量具编号" name="gauge_no" rules={[{ required: true }]}>
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="名称" name="name" rules={[{ required: true }]}>
                    <Input />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item label="型号" name="model">
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="制造商" name="manufacturer">
                    <Input />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16}>
                <Col span={8}>
                  <Form.Item label="分辨力" name="resolution">
                    <Input type="number" />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="测量范围" name="measuring_range">
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="校准周期（天）" name="calibration_cycle_days">
                    <Input type="number" />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item label="部门" name="department">
                    <Select allowClear>
                      <Option value="IQC">IQC</Option>
                      <Option value="PQC">PQC</Option>
                      <Option value="OQC">OQC</Option>
                      <Option value="实验室">实验室</Option>
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="存放位置" name="location">
                    <Input />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item label="状态" name="status">
                    <Select>
                      <Option value="active">在用</Option>
                      <Option value="inactive">闲置</Option>
                      <Option value="calibrating">校准中</Option>
                      <Option value="scrapped">报废</Option>
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="下次校准日期" name="next_calibration_date">
                    <DatePicker style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
              </Row>
            </Form>
          ) : (
            <Row gutter={[16, 8]}>
              <Col span={12}>
                <Text type="secondary">量具编号</Text>
                <div>{gauge.gauge_no}</div>
              </Col>
              <Col span={12}>
                <Text type="secondary">名称</Text>
                <div>{gauge.name}</div>
              </Col>
              <Col span={12}>
                <Text type="secondary">型号</Text>
                <div>{gauge.model ?? "—"}</div>
              </Col>
              <Col span={12}>
                <Text type="secondary">制造商</Text>
                <div>{gauge.manufacturer ?? "—"}</div>
              </Col>
              <Col span={8}>
                <Text type="secondary">分辨力</Text>
                <div>{gauge.resolution ?? "—"}</div>
              </Col>
              <Col span={8}>
                <Text type="secondary">测量范围</Text>
                <div>{gauge.measuring_range ?? "—"}</div>
              </Col>
              <Col span={8}>
                <Text type="secondary">校准周期</Text>
                <div>{gauge.calibration_cycle_days ? `${gauge.calibration_cycle_days}天` : "—"}</div>
              </Col>
              <Col span={12}>
                <Text type="secondary">部门</Text>
                <div>{gauge.department ?? "—"}</div>
              </Col>
              <Col span={12}>
                <Text type="secondary">存放位置</Text>
                <div>{gauge.location ?? "—"}</div>
              </Col>
              <Col span={12}>
                <Text type="secondary">状态</Text>
                <div>
                  <Tag color={statusInfo.color}>{statusInfo.label}</Tag>
                </div>
              </Col>
              <Col span={12}>
                <Text type="secondary">下次校准</Text>
                <div>{gauge.next_calibration_date ?? "—"}</div>
              </Col>
              <Col span={12}>
                <Text type="secondary">创建时间</Text>
                <div>{dayjs(gauge.created_at).format("YYYY-MM-DD HH:mm")}</div>
              </Col>
            </Row>
          )}
        </Card>
      ),
    },
    {
      key: "calibrations",
      label: "校准记录",
      children: (
        <Card
          extra={
            canEdit('msa') && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCalModalOpen(true)}>
                添加记录
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
          返回
        </Button>
        <h2 style={{ margin: 0, fontSize: 20 }}>{gauge.name}</h2>
        <Tag color={statusInfo.color}>{statusInfo.label}</Tag>
      </div>

      <Tabs items={tabItems} />

      <Modal
        title="添加校准记录"
        open={calModalOpen}
        onCancel={() => {
          setCalModalOpen(false);
          calForm.resetFields();
        }}
        onOk={handleCalSave}
        confirmLoading={calSaving}
        okText="保存"
        cancelText="取消"
        destroyOnHidden
      >
        <Form form={calForm} layout="vertical">
          <Form.Item
            label="校准日期"
            name="calibration_date"
            rules={[{ required: true, message: "请选择日期" }]}
          >
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item
            label="结果"
            name="result"
            rules={[{ required: true, message: "请选择结果" }]}
            initialValue="pass"
          >
            <Select>
              <Option value="pass">合格</Option>
              <Option value="fail">不合格</Option>
            </Select>
          </Form.Item>
          <Form.Item label="证书编号" name="certificate_no">
            <Input />
          </Form.Item>
          <Form.Item label="校准人" name="calibrated_by">
            <Input />
          </Form.Item>
          <Form.Item label="备注" name="notes">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item label="下次校准日期" name="next_calibration_date">
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

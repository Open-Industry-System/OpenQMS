import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import {
  Card,
  Table,
  Button,
  Tag,
  Space,
  Input,
  Select,
  message,
  Row,
  Col,
  Statistic,
  Modal,
  Form,
  DatePicker,
  Drawer,
} from "antd";
import {
  PlusOutlined,
  ReloadOutlined,
  EyeOutlined,
  EditOutlined,
  DeleteOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { usePermission } from "../../hooks/usePermission";
import type { Gauge } from "../../types";
import { listGauges, getExpiringGauges, createGauge, deleteGauge } from "../../api/msa";
import dayjs from "dayjs";

const { Option } = Select;

export default function GaugeListPage() {
  const { t } = useTranslation("msa");
  const { t: tc } = useTranslation("common");
  const navigate = useNavigate();
  const { canEdit } = usePermission();

  const [gauges, setGauges] = useState<Gauge[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const [filterSearch, setFilterSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<string | undefined>();
  const [filterDepartment, setFilterDepartment] = useState<string | undefined>();

  const [expiryDrawerOpen, setExpiryDrawerOpen] = useState(false);
  const [expiryGauges, setExpiryGauges] = useState<Gauge[]>([]);
  const [expiryLoading, setExpiryLoading] = useState(false);

  const [modalOpen, setModalOpen] = useState(false);
  const [modalForm] = Form.useForm();
  const [saving, setSaving] = useState(false);

  const fetchGauges = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page, page_size: pageSize };
      if (filterSearch) params.search = filterSearch;
      if (filterStatus) params.status = filterStatus;
      if (filterDepartment) params.department = filterDepartment;
      const resp = await listGauges(params);
      setGauges(resp.items);
      setTotal(resp.total);
    } catch {
      message.error(t("gauge.listLoadFailed"));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, filterSearch, filterStatus, filterDepartment, t]);

  useEffect(() => {
    fetchGauges();
  }, [fetchGauges]);

  const handleOpenExpiryDrawer = async () => {
    setExpiryDrawerOpen(true);
    setExpiryLoading(true);
    try {
      const resp = await getExpiringGauges(30);
      setExpiryGauges(resp.items);
    } catch {
      message.error(t("gauge.expiryLoadFailed"));
    } finally {
      setExpiryLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteGauge(id);
      message.success(t("gauge.deleteSuccess"));
      fetchGauges();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || t("gauge.deleteFailed"));
    }
  };

  const handleCreate = async () => {
    try {
      const values = await modalForm.validateFields();
      setSaving(true);
      await createGauge({
        ...values,
        next_calibration_date: values.next_calibration_date
          ? values.next_calibration_date.format("YYYY-MM-DD")
          : null,
      });
      message.success(t("gauge.createSuccess"));
      setModalOpen(false);
      modalForm.resetFields();
      fetchGauges();
    } catch (err: unknown) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(t("gauge.createFailed"));
    } finally {
      setSaving(false);
    }
  };

  const activeCount = gauges.filter((g) => g.status === "active").length;
  const expiringCount = gauges.filter((g) => {
    if (!g.next_calibration_date) return false;
    const days = dayjs(g.next_calibration_date).diff(dayjs(), "day");
    return days <= 30 && days >= 0;
  }).length;

  const columns = [
    {
      title: t("gauge.columns.gaugeNo"),
      dataIndex: "gauge_no",
      width: 160,
      render: (no: string) => <span style={{ fontFamily: "monospace" }}>{no}</span>,
    },
    { title: t("gauge.columns.name"), dataIndex: "name", width: 180 },
    { title: t("gauge.columns.model"), dataIndex: "model", render: (v: string | null) => v || "—" },
    { title: t("gauge.columns.department"), dataIndex: "department", width: 120, render: (v: string | null) => v || "—" },
    {
      title: t("gauge.columns.status"),
      dataIndex: "status",
      width: 100,
      render: (status: string) => {
        const label = t(`gauge.status.${status}`, { defaultValue: status });
        const color = status === "active" ? "green" : status === "inactive" ? "default" : status === "calibrating" ? "blue" : "red";
        return <Tag color={color}>{label}</Tag>;
      },
    },
    {
      title: t("gauge.columns.nextCalibration"),
      dataIndex: "next_calibration_date",
      width: 120,
      render: (v: string | null) => {
        if (!v) return "—";
        const days = dayjs(v).diff(dayjs(), "day");
        const isExpiringSoon = days <= 30;
        return (
          <span style={isExpiringSoon ? { color: "#ff4d4f", fontWeight: 500 } : {}}>
            {dayjs(v).format("YYYY-MM-DD")}
            {isExpiringSoon && days >= 0 && <span style={{ marginLeft: 4, fontSize: 12 }}>({t("gauge.columns.days", { days })})</span>}
            {days < 0 && <span style={{ marginLeft: 4, fontSize: 12 }}>({t("gauge.expired")})</span>}
          </span>
        );
      },
    },
    {
      title: tc("table.operations"),
      width: 200,
      render: (_: unknown, record: Gauge) => (
        <Space size="small">
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/msa/gauges/${record.gauge_id}`)}
          >
            {tc("actions.view")}
          </Button>
          {canEdit('msa') && (
            <>
              <Button
                size="small"
                icon={<EditOutlined />}
                onClick={() => navigate(`/msa/gauges/${record.gauge_id}`)}
              >
                {tc("actions.edit")}
              </Button>
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
                onClick={() => handleDelete(record.gauge_id)}
              >
                {tc("actions.delete")}
              </Button>
            </>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title={t("gauge.total")} value={total} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title={t("gauge.active")} value={activeCount} valueStyle={{ color: "#52c41a" }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title={t("gauge.inactiveOrOther")} value={total - activeCount} />
          </Card>
        </Col>
        <Col span={6}>
          <Card style={{ cursor: "pointer" }} onClick={handleOpenExpiryDrawer} hoverable>
            <Statistic
              title={t("gauge.expiring30Days")}
              value={expiringCount}
              valueStyle={expiringCount > 0 ? { color: "#ff4d4f" } : undefined}
            />
          </Card>
        </Col>
      </Row>

      <Card
        title={t("gauge.title")}
        extra={
          <Space>
            {canEdit('msa') && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
                {t("gauge.new")}
              </Button>
            )}
            <Button icon={<ReloadOutlined />} onClick={fetchGauges}>
              {tc("actions.refresh")}
            </Button>
          </Space>
        }
      >
        <Space style={{ marginBottom: 16 }} wrap>
          <Input
            placeholder={t("gauge.searchPlaceholder")}
            allowClear
            style={{ width: 220 }}
            value={filterSearch}
            onChange={(e) => setFilterSearch(e.target.value)}
            onPressEnter={() => setPage(1)}
          />
          <Select
            placeholder={t("gauge.columns.status")}
            allowClear
            style={{ width: 140 }}
            value={filterStatus}
            onChange={(v) => {
              setFilterStatus(v || undefined);
              setPage(1);
            }}
          >
            <Option value="active">{t("gauge.status.active")}</Option>
            <Option value="inactive">{t("gauge.status.inactive")}</Option>
            <Option value="calibrating">{t("gauge.status.calibrating")}</Option>
            <Option value="scrapped">{t("gauge.status.scrapped")}</Option>
          </Select>
          <Select
            placeholder={t("gauge.columns.department")}
            allowClear
            style={{ width: 140 }}
            value={filterDepartment}
            onChange={(v) => {
              setFilterDepartment(v || undefined);
              setPage(1);
            }}
          >
            <Option value="IQC">{t("gauge.department.IQC")}</Option>
            <Option value="PQC">{t("gauge.department.PQC")}</Option>
            <Option value="OQC">{t("gauge.department.OQC")}</Option>
            <Option value={t("gauge.department.labValue")}>{t("gauge.department.lab")}</Option>
          </Select>
          <Button type="primary" onClick={() => setPage(1)}>
            {tc("actions.search")}
          </Button>
        </Space>

        <Table
          rowKey="gauge_id"
          columns={columns}
          dataSource={gauges}
          loading={loading}
          pagination={{
            current: page,
            pageSize: pageSize,
            total: total,
            showSizeChanger: true,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps || 20);
            },
          }}
        />
      </Card>

      <Drawer
        title={t("gauge.expiryDrawerTitle")}
        open={expiryDrawerOpen}
        onClose={() => setExpiryDrawerOpen(false)}
        width={640}
      >
        <Table
          rowKey="gauge_id"
          dataSource={expiryGauges}
          loading={expiryLoading}
          pagination={false}
          columns={[
            { title: t("gauge.columns.gaugeNo"), dataIndex: "gauge_no", width: 140 },
            { title: t("gauge.columns.name"), dataIndex: "name" },
            {
              title: t("gauge.columns.expiryDate"),
              dataIndex: "next_calibration_date",
              render: (v: string) => dayjs(v).format("YYYY-MM-DD"),
            },
            {
              title: t("gauge.columns.remainingDays"),
              render: (_: unknown, record: Gauge) => {
                const days = dayjs(record.next_calibration_date).diff(dayjs(), "day");
                return (
                  <span style={{ color: days <= 7 ? "#ff4d4f" : undefined, fontWeight: days <= 7 ? 600 : undefined }}>
                    {t("gauge.columns.days", { days })}
                  </span>
                );
              },
            },
          ]}
        />
      </Drawer>

      <Modal
        title={t("gauge.new")}
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false);
          modalForm.resetFields();
        }}
        onOk={handleCreate}
        confirmLoading={saving}
        okText={tc("actions.save")}
        cancelText={tc("actions.cancel")}
        destroyOnHidden
      >
        <Form form={modalForm} layout="vertical">
          <Form.Item label={t("gauge.fields.gauge_no")} name="gauge_no" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item label={t("gauge.fields.name")} name="name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item label={t("gauge.fields.model")} name="model">
            <Input />
          </Form.Item>
          <Form.Item label={t("gauge.fields.manufacturer")} name="manufacturer">
            <Input />
          </Form.Item>
          <Form.Item label={t("gauge.fields.resolution")} name="resolution">
            <Input type="number" />
          </Form.Item>
          <Form.Item label={t("gauge.fields.measuring_range")} name="measuring_range">
            <Input placeholder="0-150mm" />
          </Form.Item>
          <Form.Item label={t("gauge.fields.department")} name="department">
            <Select allowClear placeholder={t("gauge.columns.department")}>
              <Option value="IQC">{t("gauge.department.IQC")}</Option>
              <Option value="PQC">{t("gauge.department.PQC")}</Option>
              <Option value="OQC">{t("gauge.department.OQC")}</Option>
              <Option value={t("gauge.department.labValue")}>{t("gauge.department.lab")}</Option>
            </Select>
          </Form.Item>
          <Form.Item label={t("gauge.fields.location")} name="location">
            <Input />
          </Form.Item>
          <Form.Item label={t("gauge.fields.calibration_cycle_days")} name="calibration_cycle_days">
            <Input type="number" />
          </Form.Item>
          <Form.Item label={t("gauge.fields.next_calibration_date")} name="next_calibration_date">
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

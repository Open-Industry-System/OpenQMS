import React, { useState, useEffect } from "react";
import { Table, Button, Modal, Form, Input, Select, Switch, message, Popconfirm } from "antd";
import { useTranslation } from "react-i18next";
import type { NotificationChannel } from "../../../types";
import { riskAlertApi } from "../../../api/supplierRisk";
import { StatusBadge } from "../../../components/design";

const ChannelConfigTable: React.FC = () => {
  const { t } = useTranslation("supplierRisk");
  const { t: tc } = useTranslation("common");
  const [data, setData] = useState<NotificationChannel[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  const TYPE_LABELS: Record<string, string> = {
    email: t("channel.types.email"),
    webhook: t("channel.types.webhook"),
  };

  const MIN_RISK_LEVEL_LABELS: Record<string, string> = {
    high: t("channel.minRiskLevels.high"),
    critical: t("channel.minRiskLevels.critical"),
  };

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await riskAlertApi.listChannels();
      setData(res.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const createChannel = async (values: Record<string, unknown>) => {
    try {
      await riskAlertApi.createChannel(values);
      message.success(t("channel.messages.created"));
      setModalOpen(false);
      form.resetFields();
      fetchData();
    } catch {
      message.error(t("channel.messages.createFailed"));
    }
  };

  const toggleEnabled = async (record: NotificationChannel, enabled: boolean) => {
    try {
      await riskAlertApi.updateChannel(record.channel_id, { enabled });
      fetchData();
    } catch {
      message.error(t("channel.messages.updateFailed"));
    }
  };

  const deleteChannel = async (id: string) => {
    try {
      await riskAlertApi.deleteChannel(id);
      message.success(t("channel.messages.deleted"));
      fetchData();
    } catch {
      message.error(t("channel.messages.deleteFailed"));
    }
  };

  const columns = [
    {
      title: t("channel.columns.type"),
      dataIndex: "channel_type",
      render: (v: string) => (
        <StatusBadge status={v}>{TYPE_LABELS[v] || v}</StatusBadge>
      ),
    },
    {
      title: t("channel.columns.minRiskLevel"),
      dataIndex: "min_risk_level",
      render: (v: string) => MIN_RISK_LEVEL_LABELS[v] || v,
    },
    {
      title: t("channel.columns.enabled"),
      dataIndex: "enabled",
      render: (v: boolean, record: NotificationChannel) => (
        <Switch checked={v} onChange={(val) => toggleEnabled(record, val)} />
      ),
    },
    {
      title: tc("table.operations"),
      render: (_: unknown, record: NotificationChannel) => (
        <Popconfirm
          title={tc("messages.confirmDelete")}
          onConfirm={() => deleteChannel(record.channel_id)}
        >
          <Button size="small" danger>
            {tc("actions.delete")}
          </Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <>
      <Button
        type="primary"
        onClick={() => setModalOpen(true)}
        style={{ marginBottom: 16 }}
      >
        {t("channel.add")}
      </Button>
      <Table
        rowKey="channel_id"
        columns={columns}
        dataSource={data}
        loading={loading}
        className="qf-table"
      />
      <Modal
        title={t("channel.addTitle")}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
      >
        <Form form={form} onFinish={createChannel} layout="vertical">
          <Form.Item
            name="channel_type"
            label={t("channel.form.type")}
            rules={[{ required: true }]}
          >
            <Select
              options={[
                { value: "email", label: TYPE_LABELS.email },
                { value: "webhook", label: TYPE_LABELS.webhook },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="min_risk_level"
            label={t("channel.form.minRiskLevel")}
            initialValue="high"
          >
            <Select
              options={[
                { value: "high", label: MIN_RISK_LEVEL_LABELS.high },
                { value: "critical", label: MIN_RISK_LEVEL_LABELS.critical },
              ]}
            />
          </Form.Item>
          <Form.Item
            noStyle
            shouldUpdate={(prev, cur) => prev.channel_type !== cur.channel_type}
          >
            {({ getFieldValue }) =>
              getFieldValue("channel_type") === "email" ? (
                <Form.Item
                  name={["config", "addresses"]}
                  label={t("channel.form.emailAddresses")}
                  rules={[{ required: true }]}
                >
                  <Input placeholder={t("channel.placeholders.emailAddresses")} />
                </Form.Item>
              ) : getFieldValue("channel_type") === "webhook" ? (
                <>
                  <Form.Item
                    name={["config", "url"]}
                    label={t("channel.form.webhookUrl")}
                    rules={[{ required: true }]}
                  >
                    <Input placeholder={t("channel.placeholders.webhookUrl")} />
                  </Form.Item>
                  <Form.Item
                    name={["config", "secret"]}
                    label={t("channel.form.secret")}
                    rules={[{ required: true }]}
                  >
                    <Input.Password />
                  </Form.Item>
                </>
              ) : null
            }
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default ChannelConfigTable;

import React, { useState, useEffect } from "react";
import { Table, Button, Modal, Form, Input, Select, Switch, message, Popconfirm, Tag } from "antd";
import type { NotificationChannel } from "../../../types";
import { riskAlertApi } from "../../../api/supplierRisk";

const ChannelConfigTable: React.FC = () => {
  const [data, setData] = useState<NotificationChannel[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

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
      message.success("已创建");
      setModalOpen(false);
      form.resetFields();
      fetchData();
    } catch {
      message.error("创建失败");
    }
  };

  const toggleEnabled = async (record: NotificationChannel, enabled: boolean) => {
    try {
      await riskAlertApi.updateChannel(record.channel_id, { enabled });
      fetchData();
    } catch {
      message.error("更新失败");
    }
  };

  const deleteChannel = async (id: string) => {
    try {
      await riskAlertApi.deleteChannel(id);
      message.success("已删除");
      fetchData();
    } catch {
      message.error("删除失败");
    }
  };

  const columns = [
    {
      title: "类型",
      dataIndex: "channel_type",
      render: (v: string) => (
        <Tag color={v === "email" ? "blue" : "green"}>
          {v === "email" ? "邮件" : "Webhook"}
        </Tag>
      ),
    },
    {
      title: "最低风险等级",
      dataIndex: "min_risk_level",
      render: (v: string) => ({ high: "高", critical: "极高" }[v] || v),
    },
    {
      title: "启用",
      dataIndex: "enabled",
      render: (v: boolean, record: NotificationChannel) => (
        <Switch checked={v} onChange={(val) => toggleEnabled(record, val)} />
      ),
    },
    {
      title: "操作",
      render: (_: unknown, record: NotificationChannel) => (
        <Popconfirm
          title="确定删除?"
          onConfirm={() => deleteChannel(record.channel_id)}
        >
          <Button size="small" danger>
            删除
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
        添加渠道
      </Button>
      <Table
        rowKey="channel_id"
        columns={columns}
        dataSource={data}
        loading={loading}
      />
      <Modal
        title="添加通知渠道"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
      >
        <Form form={form} onFinish={createChannel} layout="vertical">
          <Form.Item
            name="channel_type"
            label="类型"
            rules={[{ required: true }]}
          >
            <Select
              options={[
                { value: "email", label: "邮件" },
                { value: "webhook", label: "Webhook" },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="min_risk_level"
            label="最低风险等级"
            initialValue="high"
          >
            <Select
              options={[
                { value: "high", label: "高" },
                { value: "critical", label: "极高" },
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
                  label="邮件地址（逗号分隔）"
                  rules={[{ required: true }]}
                >
                  <Input placeholder="a@b.com,c@d.com" />
                </Form.Item>
              ) : getFieldValue("channel_type") === "webhook" ? (
                <>
                  <Form.Item
                    name={["config", "url"]}
                    label="Webhook URL"
                    rules={[{ required: true }]}
                  >
                    <Input placeholder="https://hooks.example.com/..." />
                  </Form.Item>
                  <Form.Item
                    name={["config", "secret"]}
                    label="签名密钥"
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

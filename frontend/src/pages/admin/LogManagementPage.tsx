import { useState, useCallback, useEffect } from "react";
import { Tabs, Form, Input, Select, DatePicker, Table, Tag, App, Button } from "antd";
import { useTranslation } from "react-i18next";
import type { Dayjs } from "dayjs";
import { PageShell } from "../../components/design";
import { listAuditLogs, listLoginLogs, listSystemLogs } from "../../api/logs";
import type { PaginatedResponse, AuditLogItem, LoginLogItem, SystemLogItem } from "../../types";

function rangeParams(range: [Dayjs | null, Dayjs | null] | null): Record<string, string> {
  if (!range || !range[0] || !range[1]) return {};
  return { start: range[0].toISOString(), end: range[1].toISOString() };
}

function AuditTab() {
  const { t } = useTranslation("logs");
  const { message } = App.useApp();
  const [data, setData] = useState<PaginatedResponse<AuditLogItem>>({ items: [], total: 0, page: 1, page_size: 20 });
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async (page: number, page_size: number, values: Record<string, unknown>) => {
    setLoading(true);
    try {
      const { range, ...rest } = values;
      setData(await listAuditLogs({ page, page_size, ...rest, ...rangeParams(range as never) }));
    } catch { message.error("error"); }
    finally { setLoading(false); }
  }, [message]);

  const onSearch = async () => {
    const v = await form.validateFields();
    await load(1, 20, v);
  };

  useEffect(() => { load(1, 20, form.getFieldsValue()); }, [load, form]);

  return (
    <>
      <Form form={form} layout="inline" style={{ marginBottom: 16 }}>
        <Form.Item name="table_name"><Input placeholder={t("filters.table_name")} allowClear /></Form.Item>
        <Form.Item name="action"><Input placeholder={t("filters.action")} allowClear /></Form.Item>
        <Form.Item name="operated_by"><Input placeholder={t("filters.operated_by")} allowClear /></Form.Item>
        <Form.Item name="range"><DatePicker.RangePicker showTime /></Form.Item>
        <Form.Item><Button type="primary" onClick={onSearch}>查询</Button></Form.Item>
      </Form>
      <Table
        rowKey="log_id" loading={loading} dataSource={data.items}
        pagination={{
          current: data.page, pageSize: data.page_size, total: data.total,
          onChange: (p, ps) => load(p, ps, form.getFieldsValue()),
        }}
        columns={[
          { title: t("columns.operated_at"), dataIndex: "operated_at" },
          { title: t("columns.table_name"), dataIndex: "table_name" },
          { title: t("columns.action"), dataIndex: "action" },
          { title: t("columns.operated_by"), dataIndex: "operated_by" },
          { title: t("columns.ip"), dataIndex: "ip_address" },
        ]}
        expandable={{
          expandedRowRender: (r: AuditLogItem) => (
            <pre style={{ margin: 0 }}>{JSON.stringify({
              [t("expand.oldValues")]: r.old_values,
              [t("expand.newValues")]: r.new_values,
              [t("expand.changedFields")]: r.changed_fields,
            }, null, 2)}</pre>
          ),
        }}
      />
    </>
  );
}

function LoginTab() {
  const { t } = useTranslation("logs");
  const { message } = App.useApp();
  const [data, setData] = useState<PaginatedResponse<LoginLogItem>>({ items: [], total: 0, page: 1, page_size: 20 });
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async (page: number, page_size: number, values: Record<string, unknown>) => {
    setLoading(true);
    try {
      const { range, success, ...rest } = values;
      const successVal = success === "all" || success == null ? undefined : success === "true";
      setData(await listLoginLogs({ page, page_size, ...rest, success: successVal, ...rangeParams(range as never) }));
    } catch { message.error("error"); }
    finally { setLoading(false); }
  }, [message]);

  const onSearch = async () => {
    const v = await form.validateFields();
    await load(1, 20, v);
  };

  useEffect(() => { load(1, 20, form.getFieldsValue()); }, [load, form]);

  return (
    <>
      <Form form={form} layout="inline" style={{ marginBottom: 16 }}>
        <Form.Item name="username"><Input placeholder={t("filters.username")} allowClear /></Form.Item>
        <Form.Item name="success" initialValue="all">
          <Select style={{ width: 120 }} options={[
            { value: "all", label: t("filters.all") },
            { value: "true", label: t("filters.success") },
            { value: "false", label: t("filters.fail") },
          ]} />
        </Form.Item>
        <Form.Item name="range"><DatePicker.RangePicker showTime /></Form.Item>
        <Form.Item><Button type="primary" onClick={onSearch}>查询</Button></Form.Item>
      </Form>
      <Table
        rowKey="log_id" loading={loading} dataSource={data.items}
        pagination={{
          current: data.page, pageSize: data.page_size, total: data.total,
          onChange: (p, ps) => load(p, ps, form.getFieldsValue()),
        }}
        columns={[
          { title: t("columns.occurred_at"), dataIndex: "occurred_at" },
          { title: t("columns.username"), dataIndex: "username" },
          {
            title: t("columns.result"), dataIndex: "success",
            render: (v: boolean) => <Tag color={v ? "green" : "red"}>{v ? t("filters.success") : t("filters.fail")}</Tag>,
          },
          { title: t("columns.ip"), dataIndex: "ip_address" },
          { title: t("columns.failure_reason"), dataIndex: "failure_reason" },
        ]}
      />
    </>
  );
}

function SystemTab() {
  const { t } = useTranslation("logs");
  const { message } = App.useApp();
  const [data, setData] = useState<PaginatedResponse<SystemLogItem>>({ items: [], total: 0, page: 1, page_size: 20 });
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async (page: number, page_size: number, values: Record<string, unknown>) => {
    setLoading(true);
    try {
      const { range, ...rest } = values;
      setData(await listSystemLogs({ page, page_size, ...rest, ...rangeParams(range as never) }));
    } catch { message.error("error"); }
    finally { setLoading(false); }
  }, [message]);

  const onSearch = async () => {
    const v = await form.validateFields();
    await load(1, 20, v);
  };

  useEffect(() => { load(1, 20, form.getFieldsValue()); }, [load, form]);

  const levelColor: Record<string, string> = { WARNING: "orange", ERROR: "red", CRITICAL: "magenta" };

  return (
    <>
      <Form form={form} layout="inline" style={{ marginBottom: 16 }}>
        <Form.Item name="level">
          <Select allowClear style={{ width: 140 }} placeholder={t("filters.level")} options={[
            { value: "WARNING", label: "WARNING" },
            { value: "ERROR", label: "ERROR" },
            { value: "CRITICAL", label: "CRITICAL" },
          ]} />
        </Form.Item>
        <Form.Item name="logger_name"><Input placeholder={t("filters.logger_name")} allowClear /></Form.Item>
        <Form.Item name="range"><DatePicker.RangePicker showTime /></Form.Item>
        <Form.Item><Button type="primary" onClick={onSearch}>查询</Button></Form.Item>
      </Form>
      <Table
        rowKey="log_id" loading={loading} dataSource={data.items}
        pagination={{
          current: data.page, pageSize: data.page_size, total: data.total,
          onChange: (p, ps) => load(p, ps, form.getFieldsValue()),
        }}
        columns={[
          { title: t("columns.occurred_at"), dataIndex: "occurred_at" },
          {
            title: t("columns.level"), dataIndex: "level",
            render: (v: string) => <Tag color={levelColor[v] || "default"}>{v}</Tag>,
          },
          { title: t("columns.logger_name"), dataIndex: "logger_name" },
          { title: t("columns.message"), dataIndex: "message", ellipsis: true },
        ]}
        expandable={{
          expandedRowRender: (r: SystemLogItem) => <pre style={{ margin: 0 }}>{r.traceback || r.message}</pre>,
        }}
      />
    </>
  );
}

export default function LogManagementPage() {
  const { t } = useTranslation("logs");
  return (
    <PageShell title={t("title")}>
      <Tabs items={[
        { key: "audit", label: t("tabs.audit"), children: <AuditTab /> },
        { key: "login", label: t("tabs.login"), children: <LoginTab /> },
        { key: "system", label: t("tabs.system"), children: <SystemTab /> },
      ]} />
    </PageShell>
  );
}

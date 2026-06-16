import { useState, useEffect } from "react";
import { Form, Input, InputNumber, Button, Card, App, Select, Space, Alert, Modal, Tag, Descriptions } from "antd";
import { useTranslation } from "react-i18next";
import { SaveOutlined, ReloadOutlined, ApiOutlined, CheckCircleTwoTone, CloseCircleTwoTone } from "@ant-design/icons";
import { getAIConfig, updateAIConfig, testAIConfig, type AIConfig, type AIConfigTestResult } from "../../api/aiConfig";
import { PageShell } from "../../components/design";

const { Option } = Select;

export default function AIConfigPage() {
  const { t } = useTranslation("aiConfig");
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<AIConfigTestResult | null>(null);
  const [testModalOpen, setTestModalOpen] = useState(false);

  const loadConfig = async () => {
    setLoading(true);
    try {
      const config = await getAIConfig();
      form.setFieldsValue(config);
    } catch (error) {
      message.error(t("messages.loadFailed"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadConfig();
  }, []);

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      await updateAIConfig(values as AIConfig);
      message.success(t("messages.saveSuccess"));
      await loadConfig();
    } catch (error: any) {
      if (error.errorFields) {
        message.error(t("messages.validationFailed"));
      } else {
        message.error(t("messages.saveFailed"));
      }
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    try {
      const values = await form.validateFields();
      setTesting(true);
      const result = await testAIConfig(values as AIConfig);
      setTestResult(result);
      setTestModalOpen(true);
    } catch (error: any) {
      if (error.errorFields) {
        message.error(t("messages.validationFailed"));
      } else {
        message.error(t("messages.testFailed"));
      }
    } finally {
      setTesting(false);
    }
  };

  const renderTestRow = (label: string, result: { ok: boolean; latency_ms: number | null; detail: string | null } | undefined) => {
    if (!result) return null;
    return (
      <Descriptions.Item label={label}>
        <Space>
          {result.ok ? (
            <CheckCircleTwoTone twoToneColor="#52c41a" />
          ) : (
            <CloseCircleTwoTone twoToneColor="#ff4d4f" />
          )}
          <Tag color={result.ok ? "success" : "error"}>{result.ok ? "成功" : "失败"}</Tag>
          {result.latency_ms !== null && result.latency_ms !== undefined && (
            <span style={{ color: "var(--qf-text-secondary)", fontFamily: "var(--qf-font-mono)" }}>
              {result.latency_ms} ms
            </span>
          )}
          {result.detail && <span style={{ color: "var(--qf-text-secondary)" }}>{result.detail}</span>}
        </Space>
      </Descriptions.Item>
    );
  };

  return (
    <PageShell
      title={t("title")}
      subtitle={t("subtitle")}
    >
      <Alert
        message={t("notice.title")}
        description={t("notice.description")}
        type="info"
        showIcon
        style={{ marginBottom: 24 }}
      />

      <Form form={form} layout="vertical" disabled={loading}>
        <Card title={t("sections.llm")} style={{ marginBottom: 24 }}>
          <Form.Item
            name="llm_provider"
            label={t("fields.llm_provider.label")}
            tooltip={t("fields.llm_provider.tooltip")}
          >
            <Select placeholder={t("fields.llm_provider.placeholder")} allowClear>
              <Option value="">None (规则引擎模式)</Option>
              <Option value="claude">Claude (Anthropic)</Option>
              <Option value="openai">OpenAI</Option>
              <Option value="local">Local (Ollama / vLLM)</Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="llm_api_key"
            label={t("fields.llm_api_key.label")}
            tooltip={t("fields.llm_api_key.tooltip")}
          >
            <Input.Password placeholder={t("fields.llm_api_key.placeholder")} autoComplete="new-password" />
          </Form.Item>

          <Form.Item
            name="llm_model"
            label={t("fields.llm_model.label")}
            tooltip={t("fields.llm_model.tooltip")}
          >
            <Input placeholder={t("fields.llm_model.placeholder")} />
          </Form.Item>

          <Form.Item
            name="llm_base_url"
            label={t("fields.llm_base_url.label")}
            tooltip={t("fields.llm_base_url.tooltip")}
          >
            <Input placeholder={t("fields.llm_base_url.placeholder")} />
          </Form.Item>

          <Space style={{ width: "100%" }} size="large">
            <Form.Item name="llm_timeout" label={t("fields.llm_timeout.label")}>
              <InputNumber min={1} max={120} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="capa_draft_llm_timeout" label={t("fields.capa_draft_llm_timeout.label")}>
              <InputNumber min={1} max={120} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="report_llm_timeout" label={t("fields.report_llm_timeout.label")}>
              <InputNumber min={1} max={120} style={{ width: 140 }} />
            </Form.Item>
            <span style={{ color: "var(--qf-text-secondary)", fontSize: 12, alignSelf: "flex-end", marginBottom: 24 }}>
              秒
            </span>
          </Space>
        </Card>

        <Card title={t("sections.embedding")} style={{ marginBottom: 24 }}>
          <Form.Item
            name="embedding_provider"
            label={t("fields.embedding_provider.label")}
            tooltip={t("fields.embedding_provider.tooltip")}
          >
            <Select placeholder={t("fields.embedding_provider.placeholder")} allowClear>
              <Option value="">跟随 LLM Provider</Option>
              <Option value="openai">OpenAI</Option>
              <Option value="ollama">Ollama</Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="embedding_model"
            label={t("fields.embedding_model.label")}
            tooltip={t("fields.embedding_model.tooltip")}
          >
            <Input placeholder={t("fields.embedding_model.placeholder")} />
          </Form.Item>

          <Form.Item
            name="embedding_base_url"
            label={t("fields.embedding_base_url.label")}
            tooltip={t("fields.embedding_base_url.tooltip")}
          >
            <Input placeholder={t("fields.embedding_base_url.placeholder")} />
          </Form.Item>

          <Form.Item
            name="embedding_dimensions"
            label={t("fields.embedding_dimensions.label")}
            tooltip={t("fields.embedding_dimensions.tooltip")}
          >
            <InputNumber min={1} max={4096} style={{ width: 180 }} />
          </Form.Item>
        </Card>

        <Card title={t("sections.search")}>
          <Space style={{ width: "100%" }}>
            <Form.Item
              name="search_vector_weight"
              label={t("fields.search_vector_weight.label")}
              tooltip={t("fields.search_vector_weight.tooltip")}
            >
              <InputNumber min={0} max={1} step={0.1} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item
              name="search_fulltext_weight"
              label={t("fields.search_fulltext_weight.label")}
              tooltip={t("fields.search_fulltext_weight.tooltip")}
            >
              <InputNumber min={0} max={1} step={0.1} style={{ width: 140 }} />
            </Form.Item>
          </Space>
        </Card>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 12, marginTop: 24 }}>
          <Button icon={<ReloadOutlined />} onClick={loadConfig} disabled={loading}>
            {t("actions.reload")}
          </Button>
          <Button icon={<ApiOutlined />} onClick={handleTest} loading={testing} disabled={loading}>
            {t("actions.test")}
          </Button>
          <Button type="primary" icon={<SaveOutlined />} onClick={handleSave} loading={saving}>
            {t("actions.save")}
          </Button>
        </div>
      </Form>

      <Modal
        title={t("testResult.title")}
        open={testModalOpen}
        onCancel={() => setTestModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setTestModalOpen(false)}>
            {t("testResult.close")}
          </Button>,
        ]}
      >
        {testResult && (
          <Descriptions column={1} size="small" bordered>
            {renderTestRow(t("sections.llm"), testResult.llm)}
            {renderTestRow(t("sections.embedding"), testResult.embedding)}
          </Descriptions>
        )}
        <Alert
          type="info"
          message={t("testResult.hint")}
          style={{ marginTop: 16 }}
          showIcon
        />
      </Modal>
    </PageShell>
  );
}

import { useMemo, useState } from "react";
import { Alert, Button, List, Space, Tag, Typography } from "antd";
import { useTranslation } from "react-i18next";
import type { WidgetProps } from "./types";
import { interpretQualityTrend } from "../../../api/dashboard";
import { useProductLineStore } from "../../../store/productLineStore";
import type { QualityTrendRiskLevel } from "./types";

const riskColor: Record<string, string> = {
  high: "red",
  medium: "orange",
  low: "green",
  insufficient_data: "default",
};

export default function QualityTrendAIWidget({ data, loading, error, onRetry }: WidgetProps) {
  const { t } = useTranslation("dashboard");
  const summary = data.quality_trend?.summary;
  const productLine = useProductLineStore((s) => s.selected);
  const [busy, setBusy] = useState(false);
  const [interpretation, setInterpretation] = useState<any>(null);
  const [aiError, setAiError] = useState<string | null>(null);

  const isStale = useMemo(() => {
    if (!summary?.evidence_hash || !interpretation?.evidence_hash) return false;
    const evidenceMismatch = summary.evidence_hash !== interpretation.evidence_hash;
    const scopeMismatch = summary.scope_hash && interpretation.scope_hash && summary.scope_hash !== interpretation.scope_hash;
    return evidenceMismatch || Boolean(scopeMismatch);
  }, [summary?.evidence_hash, summary?.scope_hash, interpretation?.evidence_hash, interpretation?.scope_hash]);

  const handleInterpret = async () => {
    if (!summary?.ai_available) return;
    setBusy(true);
    setAiError(null);
    try {
      const result = await interpretQualityTrend({ product_line: productLine || undefined });
      setInterpretation(result);
    } catch {
      setAiError(t("qualityTrend.aiError"));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <div>{t("kpi.loading")}</div>;
  if (error) return <div>{t("kpi.loadFailed")} <Button size="small" onClick={onRetry}>{t("riskList.retry")}</Button></div>;
  if (!summary) return <div>{t("qualityTrend.noTrendData")}</div>;

  const riskLevel: QualityTrendRiskLevel = summary.risk_level ?? "insufficient_data";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <Space>
        <Tag color={riskColor[riskLevel] ?? "default"}>{riskLevel}</Tag>
        <Typography.Text strong>{summary.headline}</Typography.Text>
      </Space>

      {summary.metadata?.omitted_modules && summary.metadata.omitted_modules.length > 0 && (
        <Alert
          type="info"
          showIcon
          message={t("qualityTrend.omittedModules", { modules: summary.metadata.omitted_modules.join(", ") })}
        />
      )}

      <List
        size="small"
        header={<div>{t("qualityTrend.keyEvidence")}</div>}
        dataSource={summary.evidence ?? []}
        renderItem={(item) => (
          <List.Item>
            {t("qualityTrend.evidenceFormat", { label: item.label, value: item.value, trend: item.trend })}
          </List.Item>
        )}
      />

      <List
        size="small"
        header={<div>{t("qualityTrend.suggestedActions")}</div>}
        dataSource={summary.actions ?? []}
        renderItem={(item) => (
          <List.Item>
            {t("qualityTrend.actionFormat", { priority: item.priority, text: item.text })}
          </List.Item>
        )}
      />

      <Space>
        <Button type="primary" loading={busy} disabled={!summary.ai_available} onClick={handleInterpret}>
          {t("qualityTrend.aiInterpret")}
        </Button>
        {!summary.ai_available && <Typography.Text type="secondary">{t("qualityTrend.aiUnavailable")}</Typography.Text>}
      </Space>

      {isStale && (
        <Alert
          type="warning"
          showIcon
          message={t("qualityTrend.dataUpdated")}
        />
      )}

      {aiError && <Alert type="error" showIcon message={aiError} />}

      {interpretation && (
        <div style={{ marginTop: 8 }}>
          <Typography.Paragraph>{interpretation.summary}</Typography.Paragraph>
          <Typography.Text type="secondary">
            {t("qualityTrend.confidenceFormat", {
              confidence: interpretation.confidence,
              cached: interpretation.cached ? t("qualityTrend.yes") : t("qualityTrend.no"),
            })}
          </Typography.Text>
        </div>
      )}
    </div>
  );
}

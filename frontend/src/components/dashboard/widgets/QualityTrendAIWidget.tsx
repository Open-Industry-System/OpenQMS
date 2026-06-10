import { useMemo, useState } from "react";
import { Alert, Button, List, Space, Tag, Typography } from "antd";
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
      setAiError("AI 解读暂不可用，请稍后重试");
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <div>加载中...</div>;
  if (error) return <div>加载失败 <Button size="small" onClick={onRetry}>重试</Button></div>;
  if (!summary) return <div>暂无趋势数据</div>;

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
          message={`当前视图缺少模块权限，已忽略：${summary.metadata.omitted_modules.join(", ")}`}
        />
      )}

      <List
        size="small"
        header={<div>关键证据</div>}
        dataSource={summary.evidence ?? []}
        renderItem={(item) => (
          <List.Item>
            {item.label}: {item.value}（趋势：{item.trend}）
          </List.Item>
        )}
      />

      <List
        size="small"
        header={<div>建议动作</div>}
        dataSource={summary.actions ?? []}
        renderItem={(item) => (
          <List.Item>
            [{item.priority}] {item.text}
          </List.Item>
        )}
      />

      <Space>
        <Button type="primary" loading={busy} disabled={!summary.ai_available} onClick={handleInterpret}>
          AI 深度解读
        </Button>
        {!summary.ai_available && <Typography.Text type="secondary">未配置 LLM 或数据不足时不可用</Typography.Text>}
      </Space>

      {isStale && (
        <Alert
          type="warning"
          showIcon
          message="数据已更新，点击重新生成 AI 解读"
        />
      )}

      {aiError && <Alert type="error" showIcon message={aiError} />}

      {interpretation && (
        <div style={{ marginTop: 8 }}>
          <Typography.Paragraph>{interpretation.summary}</Typography.Paragraph>
          <Typography.Text type="secondary">置信度：{interpretation.confidence}，缓存：{interpretation.cached ? "是" : "否"}</Typography.Text>
        </div>
      )}
    </div>
  );
}

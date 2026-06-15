import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Card, List, Tag, Button, Space, Typography } from "antd";
import { BulbOutlined } from "@ant-design/icons";
import { useDfmeaRules } from "../../utils/dfmeaRules";

const { Text } = Typography;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface InlineRecommendationsProps {
  trigger: "function" | "failureMode" | "risk" | null;
  functionDesc?: string;
  failureMode?: string;
  s?: number;
  o?: number;
  d?: number;
  onApplySuggestion?: (suggestion: string, field: string) => void;
}

type RecommendationType =
  | "failureModeSuggestion"
  | "failureEffectSuggestion"
  | "failureCauseSuggestion"
  | "apAnalysis"
  | "preventionSuggestion"
  | "detectionSuggestion";

interface RecommendationItem {
  key: string;
  type: RecommendationType;
  content: string;
  applyField: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function InlineRecommendations({
  trigger,
  functionDesc,
  failureMode,
  s,
  o,
  d,
  onApplySuggestion,
}: InlineRecommendationsProps) {
  const { t } = useTranslation("dfmea");
  const { generateFailureModes, suggestFailureChain, analyzeRisk, suggestMeasures } = useDfmeaRules();

  const recommendations = useMemo<RecommendationItem[]>(() => {
    if (!trigger) return [];

    if (trigger === "function" && functionDesc) {
      const modes = generateFailureModes(functionDesc);
      return modes.map((mode, i) => ({
        key: `fm-${i}`,
        type: "failureModeSuggestion" as const,
        content: mode,
        applyField: "failureMode",
      }));
    }

    if (trigger === "failureMode" && failureMode) {
      const chain = suggestFailureChain(failureMode);
      const items: RecommendationItem[] = [];
      chain.effects.forEach((effect, i) => {
        items.push({
          key: `fe-${i}`,
          type: "failureEffectSuggestion",
          content: effect,
          applyField: "effect",
        });
      });
      chain.causes.forEach((cause, i) => {
        items.push({
          key: `fc-${i}`,
          type: "failureCauseSuggestion",
          content: cause,
          applyField: "cause",
        });
      });
      return items;
    }

    if (trigger === "risk" && s !== undefined && o !== undefined && d !== undefined) {
      const result = analyzeRisk(s, o, d);
      const items: RecommendationItem[] = [];

      // AP analysis item
      if (result.ap) {
        items.push({
          key: "ap-analysis",
          type: "apAnalysis",
          content: `RPN=${result.rpn}  AP=${result.ap}  ${result.hint}`,
          applyField: "",
        });
      }

      // Prevention and detection suggestions
      if (result.ap && failureMode) {
        const measures = suggestMeasures(
          failureMode,
          result.ap as "H" | "M" | "L"
        );
        measures.prevention.forEach((pm, i) => {
          items.push({
            key: `pm-${i}`,
            type: "preventionSuggestion",
            content: pm,
            applyField: "prevention",
          });
        });
        measures.detection.forEach((dm, i) => {
          items.push({
            key: `dm-${i}`,
            type: "detectionSuggestion",
            content: dm,
            applyField: "detection",
          });
        });
      }

      return items;
    }

    return [];
  }, [trigger, functionDesc, failureMode, s, o, d, generateFailureModes, suggestFailureChain, analyzeRisk, suggestMeasures]);

  if (recommendations.length === 0) return null;

  const tagColors: Record<RecommendationType, string> = {
    failureModeSuggestion: "blue",
    failureEffectSuggestion: "orange",
    failureCauseSuggestion: "purple",
    apAnalysis: "red",
    preventionSuggestion: "green",
    detectionSuggestion: "cyan",
  };

  return (
    <Card
      title={
        <Space>
          <BulbOutlined style={{ color: "#faad14" }} />
          <span>{t("inlineRecommendations.title")}</span>
        </Space>
      }
      size="small"
      style={{ marginTop: 16, background: "#fffbe6" }}
    >
      <List
        size="small"
        dataSource={recommendations}
        renderItem={(item) => (
          <List.Item
            extra={
              item.type !== "apAnalysis" && onApplySuggestion ? (
                <Button
                  size="small"
                  type="link"
                  onClick={() => onApplySuggestion(item.content, item.applyField)}
                >
                  {t("inlineRecommendations.apply")}
                </Button>
              ) : null
            }
          >
            <Space>
              <Tag color={tagColors[item.type]}>{t(`inlineRecommendations.types.${item.type}`)}</Tag>
              <Text>{item.content}</Text>
            </Space>
          </List.Item>
        )}
      />
    </Card>
  );
}

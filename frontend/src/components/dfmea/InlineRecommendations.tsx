import { useMemo } from "react";
import { Card, List, Tag, Button, Space, Typography } from "antd";
import { BulbOutlined } from "@ant-design/icons";
import {
  generateFailureModes,
  suggestFailureChain,
  analyzeRisk,
  suggestMeasures,
} from "../../utils/dfmeaRules";

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

interface RecommendationItem {
  key: string;
  type:
    | "失效模式建议"
    | "失效影响建议"
    | "失效原因建议"
    | "AP分析"
    | "预防措施建议"
    | "探测措施建议";
  content: string;
  applyField: string;
}

// ---------------------------------------------------------------------------
// Tag colour map
// ---------------------------------------------------------------------------

const TAG_COLORS: Record<RecommendationItem["type"], string> = {
  "失效模式建议": "blue",
  "失效影响建议": "orange",
  "失效原因建议": "purple",
  "AP分析": "red",
  "预防措施建议": "green",
  "探测措施建议": "cyan",
};

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
  const recommendations = useMemo<RecommendationItem[]>(() => {
    if (!trigger) return [];

    if (trigger === "function" && functionDesc) {
      const modes = generateFailureModes(functionDesc);
      return modes.map((mode, i) => ({
        key: `fm-${i}`,
        type: "失效模式建议" as const,
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
          type: "失效影响建议",
          content: effect,
          applyField: "effect",
        });
      });
      chain.causes.forEach((cause, i) => {
        items.push({
          key: `fc-${i}`,
          type: "失效原因建议",
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
          type: "AP分析",
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
            type: "预防措施建议",
            content: pm,
            applyField: "prevention",
          });
        });
        measures.detection.forEach((dm, i) => {
          items.push({
            key: `dm-${i}`,
            type: "探测措施建议",
            content: dm,
            applyField: "detection",
          });
        });
      }

      return items;
    }

    return [];
  }, [trigger, functionDesc, failureMode, s, o, d]);

  if (recommendations.length === 0) return null;

  return (
    <Card
      title={
        <Space>
          <BulbOutlined style={{ color: "#faad14" }} />
          <span>智能推荐</span>
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
              item.type !== "AP分析" && onApplySuggestion ? (
                <Button
                  size="small"
                  type="link"
                  onClick={() => onApplySuggestion(item.content, item.applyField)}
                >
                  采用
                </Button>
              ) : null
            }
          >
            <Space>
              <Tag color={TAG_COLORS[item.type]}>{item.type}</Tag>
              <Text>{item.content}</Text>
            </Space>
          </List.Item>
        )}
      />
    </Card>
  );
}

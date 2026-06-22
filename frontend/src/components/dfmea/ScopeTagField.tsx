import { useState, useRef } from "react";
import { Select, Button, Tag, Spin, message } from "antd";
import { StarOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { getRecommendations, type Suggestion } from "../../api/recommendation";
import { parseScopeTokens, stringifyScopeTokens } from "../../utils/wizardScopeTokens";

export type ScopeTriggerType = "dfmea_tool" | "dfmea_trend";

interface ScopeTagFieldProps {
  /** 「、」分隔的存盘 string */
  value: string;
  /** 回写「、」分隔 string */
  onChange: (v: string) => void;
  /** 预设清单（从 i18n 取，调用处 `as string[]`） */
  presets: string[];
  triggerType: ScopeTriggerType;
  fmeaId: string;
  /** AI 请求上下文：{ fmea_title, product_line_code, task, team } */
  context: Record<string, unknown>;
}

export default function ScopeTagField({
  value,
  onChange,
  presets,
  triggerType,
  fmeaId,
  context,
}: ScopeTagFieldProps) {
  const { t } = useTranslation("dfmea");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiSuggestions, setAiSuggestions] = useState<string[]>([]);

  // 用 ref 持有最新 value：异步 AI 回调过滤「已选」时取最新值，
  // 避免请求返回前用户改动选择造成的 stale tokenSet。
  const valueRef = useRef(value);
  valueRef.current = value;

  const tokens = parseScopeTokens(value);
  const tokenSet = new Set(tokens);

  const emit = (next: string[]) => onChange(stringifyScopeTokens(next));

  const addPreset = (preset: string) => {
    if (tokenSet.has(preset)) return;
    emit([...tokens, preset]);
  };

  const addAiSuggestion = (name: string) => {
    if (tokenSet.has(name)) return;
    emit([...tokens, name]);
  };

  const handleAiClick = async () => {
    setAiLoading(true);
    try {
      const res = await getRecommendations(fmeaId, {
        trigger_type: triggerType,
        context,
        scope: "current_product_line",
        include_graph: false,
      });
      const names = res.suggestions.map((s: Suggestion) => s.name).filter(Boolean);
      // 用 valueRef 取最新已选集合，避免请求返回前用户改动造成的 stale tokenSet
      const current = new Set(parseScopeTokens(valueRef.current));
      const fresh = Array.from(new Set(names.filter((n) => !current.has(n))));
      setAiSuggestions(fresh);
      if (fresh.length === 0) {
        message.warning(t("wizard.scope.aiRecommendEmpty"));
      }
    } catch {
      setAiSuggestions([]);
      message.warning(t("wizard.scope.aiRecommendFailed"));
    } finally {
      setAiLoading(false);
    }
  };

  return (
    <div>
      <Select
        mode="tags"
        style={{ width: "100%" }}
        tokenSeparators={[",", "、", ";", "，", "；"]}
        value={tokens}
        onChange={(next) => emit(next as string[])}
      />
      <div style={{ marginTop: 6, display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
        {presets
          .filter((p) => !tokenSet.has(p))
          .map((p) => (
            <Tag key={p} style={{ cursor: "pointer" }} onClick={() => addPreset(p)}>
              + {p}
            </Tag>
          ))}
        <Button
          size="small"
          type="dashed"
          data-testid="scope-ai-btn"
          icon={aiLoading ? <Spin size="small" /> : <StarOutlined />}
          onClick={handleAiClick}
          disabled={aiLoading}
        >
          {aiLoading ? t("wizard.scope.aiRecommendLoading") : t("wizard.scope.aiRecommend")}
        </Button>
        {aiSuggestions.map((name) => (
          <Tag
            key={name}
            color="purple"
            style={{ cursor: "pointer" }}
            onClick={() => addAiSuggestion(name)}
          >
            <StarOutlined /> {name}
          </Tag>
        ))}
      </div>
    </div>
  );
}

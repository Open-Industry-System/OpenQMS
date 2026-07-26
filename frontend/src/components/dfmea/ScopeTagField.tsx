import { useState, useRef } from "react";
import { Select, Button, Tag, Spin, Radio, message } from "antd";
import { GlobalOutlined, StarOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { getRecommendations, type Suggestion } from "../../api/recommendation";
import { parseScopeTokens, stringifyScopeTokens } from "../../utils/wizardScopeTokens";

type RecommendScope = "global" | "current_product_type" | "current_product_line";

export type ScopeTriggerType = "dfmea_tool" | "dfmea_trend" | "pfmea_tool" | "pfmea_trend";

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
  /** 采纳 AI 建议（带推荐元数据）时回调，用于 ADOPT_RECOMMENDATION 审计；手工/预设不触发 */
  onAdopt?: (s: Suggestion) => void;
}

export default function ScopeTagField({
  value,
  onChange,
  presets,
  triggerType,
  fmeaId,
  context,
  onAdopt,
}: ScopeTagFieldProps) {
  const { t } = useTranslation("dfmea");
  const [aiLoading, setAiLoading] = useState(false);
  // 保留完整 Suggestion（含 recommendation_id/source），采纳时才能回报审计元数据
  const [aiSuggestions, setAiSuggestions] = useState<Suggestion[]>([]);
  // 推荐 scope：与 SmartSuggestionDropdown 一致默认「同类产品」，让向导范围标签也用上同类历史召回。
  const [scope, setScope] = useState<RecommendScope>("current_product_type");

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

  const addAiSuggestion = (s: Suggestion) => {
    if (tokenSet.has(s.name)) return;
    emit([...tokens, s.name]);
    onAdopt?.(s);
  };

  const handleAiClick = async () => {
    setAiLoading(true);
    try {
      const res = await getRecommendations(fmeaId, {
        trigger_type: triggerType,
        context,
        scope,
        include_graph: true,
      });
      // 用 valueRef 取最新已选集合，避免请求返回前用户改动造成的 stale tokenSet
      const current = new Set(parseScopeTokens(valueRef.current));
      // name-based dedupe（first occurrence wins）：同名建议只留一条，
      // 否则渲染 key={s.name} 会撞 key，且同一可见 tag 只需一条。
      const seen = new Set<string>();
      const deduped = res.suggestions.filter((s: Suggestion) => {
        if (!s.name || current.has(s.name) || seen.has(s.name)) return false;
        seen.add(s.name);
        return true;
      });
      setAiSuggestions(deduped);
      if (deduped.length === 0) {
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
      <div style={{ marginTop: 6 }}>
        <Radio.Group
          value={scope}
          onChange={(e) => setScope(e.target.value as RecommendScope)}
          size="small"
          className="qf-radio-group"
        >
          <Radio.Button value="global"><GlobalOutlined /> {t("smartSuggestion.global")}</Radio.Button>
          <Radio.Button value="current_product_type">{t("smartSuggestion.currentProductType")}</Radio.Button>
          <Radio.Button value="current_product_line">{t("smartSuggestion.currentProductLine")}</Radio.Button>
        </Radio.Group>
      </div>
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
          data-e2e="fmea-recommend"
          icon={aiLoading ? <Spin size="small" /> : <StarOutlined />}
          onClick={handleAiClick}
          disabled={aiLoading}
        >
          {aiLoading ? t("wizard.scope.aiRecommendLoading") : t("wizard.scope.aiRecommend")}
        </Button>
        {aiSuggestions.map((s) => (
          <Tag
            key={s.name}
            color="purple"
            style={{ cursor: "pointer" }}
            onClick={() => addAiSuggestion(s)}
          >
            <StarOutlined /> {s.name}
          </Tag>
        ))}
      </div>
    </div>
  );
}

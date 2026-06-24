import { useState, useEffect, useRef, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Input, Dropdown, Tag, Spin, Button, Typography, Radio } from "antd";
import { BulbOutlined, StarOutlined, SettingOutlined, GlobalOutlined, CloseOutlined } from "@ant-design/icons";
import axios from "axios";
import { getRecommendations, type Suggestion, type RecommendResponse } from "../../api/recommendation";
import { usePermission } from "../../hooks/usePermission";
import type { ModuleKey } from "../../hooks/usePermission";

const { Text } = Typography;

interface SmartSuggestionDropdownProps {
  triggerType: "failure_mode" | "failure_effect" | "failure_cause" | "measure" | "optimization";
  context: Record<string, unknown>;
  fmeaId: string;
  onSelect: (suggestion: Suggestion) => void;
  disabled?: boolean;
  value?: string;
  onChange?: (value: string) => void;
  scope?: "global" | "current_product_type" | "current_product_line";
}

// Module-scope helpers (defined once, not re-created each render) so the
// suggestion subtree doesn't remount on every keystroke.
const SourceTag = ({ item, t }: { item: Suggestion; t: TFunc }) => {
  if (item.source === "graph" && item.source_document_no) {
    const href = `/fmea/${item.source_fmea_id}?tab=graph&highlightNode=${item.source_node_id}`;
    return (
      <span style={{ fontSize: 11, color: "#52c41a" }}>
        {t("smartSuggestion.from")}{" "}
        <a href={href} target="_blank" rel="noopener" style={{ color: "#52c41a", textDecoration: "underline" }}>{item.source_document_no}</a>
        {item.source_product_line_code && ` · ${item.source_product_line_code}`}
        {item.source_product_line_name && `（${item.source_product_line_name}）`}
        {item.similarity_score !== undefined && ` · ${t("smartSuggestion.similarity", { score: (item.similarity_score * 100).toFixed(0) })}`}
      </span>
    );
  }
  if (item.source === "rule") {
    return <span style={{ fontSize: 11, color: "#1890ff" }}>{t("smartSuggestion.ruleEngine")}</span>;
  }
  if (item.source === "llm") {
    return <span style={{ fontSize: 11, color: "#722ed1" }}>{t("smartSuggestion.aiGenerated")}</span>;
  }
  return null;
};

const confidenceLabel = (c: number, t: TFunc) => {
  if (c >= 0.7) return <Tag color="green">{t("smartSuggestion.confidence.high")}</Tag>;
  if (c >= 0.4) return <Tag color="orange">{t("smartSuggestion.confidence.medium")}</Tag>;
  return <Tag color="default">{t("smartSuggestion.confidence.low")}</Tag>;
};

const sourceIcon = (s: string) =>
  s === "llm" ? <StarOutlined style={{ color: "#722ed1" }} /> : <SettingOutlined style={{ color: "#1890ff" }} />;

const scopeLabel = (s: "global" | "current_product_type" | "current_product_line", t: TFunc) => {
  if (s === "global") return t("smartSuggestion.scopeGlobal");
  if (s === "current_product_type") return t("smartSuggestion.scopeProductType");
  return t("smartSuggestion.scopeLocal");
};

type TFunc = (key: string, opts?: Record<string, unknown>) => string;

export default function SmartSuggestionDropdown({
  triggerType,
  context,
  fmeaId,
  onSelect,
  disabled = false,
  value,
  onChange,
  scope: externalScope,
}: SmartSuggestionDropdownProps) {
  const { t } = useTranslation("dfmea");
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [llmAvailable, setLlmAvailable] = useState(true);
  const [fallback, setFallback] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const abortRef = useRef<AbortController>();
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [scope, setScope] = useState<"global" | "current_product_type" | "current_product_line">(externalScope || "global");
  const [effectiveScope, setEffectiveScope] = useState<"global" | "current_product_type" | "current_product_line">("global");

  const { canView } = usePermission();
  const hasKgPermission = canView("knowledge_graph" as ModuleKey);

  const fetchSuggestions = useCallback(
    async (inputValue: string) => {
      if (!inputValue || inputValue.length < 2 || !fmeaId) {
        setSuggestions([]);
        setOpen(false);
        return;
      }

      abortRef.current?.abort();
      abortRef.current = new AbortController();

      setLoading(true);
      setError(null);
      try {
        const res: RecommendResponse = await getRecommendations(
          fmeaId,
          {
            trigger_type: triggerType,
            context: { ...context, input_text: inputValue },
            scope,
            include_graph: true,
          },
          abortRef.current.signal
        );
        setSuggestions(res.suggestions.slice(0, 5));
        setLlmAvailable(res.llm_available);
        setFallback(res.source === "rule_fallback");
        setEffectiveScope(res.effective_scope);
        setOpen(res.suggestions.length > 0);
        setSelectedIndex(-1);
      } catch (e: unknown) {
        if (axios.isCancel(e)) return; // ignore superseded requests
        const err = e as { response?: { status?: number }; message?: string };
        if (err?.response?.status === 429) {
          setError(t("smartSuggestion.tooFrequent"));
        } else if (err?.response?.status === 403) {
          setError(t("smartSuggestion.noPermission"));
        } else {
          setError(t("smartSuggestion.serviceUnavailable"));
        }
        setSuggestions([]);
        setOpen(true);  // show error in dropdown
      } finally {
        setLoading(false);
      }
    },
    [fmeaId, triggerType, context, scope, t]
  );

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const val = e.target.value;
    onChange?.(val);
    setError(null);

    clearTimeout(debounceRef.current);
    if (val.length >= 2) {
      debounceRef.current = setTimeout(() => fetchSuggestions(val), 500);
    } else {
      setSuggestions([]);
      setOpen(false);
    }
  };

  const handleSelect = (suggestion: Suggestion) => {
    onSelect(suggestion);
    onChange?.(suggestion.name);
    setOpen(false);
    setSuggestions([]);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!open || suggestions.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => Math.min(prev + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => Math.max(prev - 1, 0));
    } else if (e.key === "Enter") {
      // TextArea inserts a newline on Enter by default; suppress it while the
      // suggestion dropdown is open so Enter confirms a selection, not a line break.
      e.preventDefault();
      if (selectedIndex >= 0) handleSelect(suggestions[selectedIndex]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  useEffect(() => {
    return () => {
      clearTimeout(debounceRef.current);
      abortRef.current?.abort();
    };
  }, []);

  const dropdownContent = (
    <div
      style={{
        width: 360,
        // Cap height to the viewport so antd's autoAdjustOverflow can always
        // fit the popup (it opens upward when below has no room). Without this,
        // a tall popup flipped upward has its top clipped above the viewport
        // and the page can't scroll to it. Overflow scrolls inside the popup.
        maxHeight: "calc(100vh - 80px)",
        overflowY: "auto",
        background: "var(--qf-bg-panel)",
        border: "1px solid var(--qf-border-strong)",
        borderRadius: "var(--qf-radius-md)",
        boxShadow: "var(--qf-shadow-md)",
        color: "var(--qf-text-primary)",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "flex-end",
          padding: "2px 4px",
          borderBottom: "1px solid var(--qf-border)",
        }}
      >
        <Button
          type="text"
          size="small"
          icon={<CloseOutlined />}
          onMouseDown={(e) => e.preventDefault()}
          onClick={(e) => { e.stopPropagation(); setOpen(false); }}
          aria-label={t("smartSuggestion.close")}
          title={t("smartSuggestion.close")}
        />
      </div>
      {error && (
        <div
          style={{
            padding: "6px 12px",
            fontSize: 12,
            color: "var(--qf-red)",
            background: "var(--qf-red-dim)",
            borderBottom: "1px solid var(--qf-border)",
          }}
        >
          {error}
        </div>
      )}
      {fallback && (
        <div
          style={{
            padding: "6px 12px",
            fontSize: 12,
            color: "var(--qf-amber)",
            background: "var(--qf-amber-dim)",
            borderBottom: "1px solid var(--qf-border)",
          }}
        >
          {t("smartSuggestion.aiUnavailable")}
        </div>
      )}
      {!llmAvailable && (
        <Text
          type="secondary"
          style={{ display: "block", padding: "4px 12px", fontSize: 12, color: "var(--qf-text-secondary)" }}
        >
          {t("smartSuggestion.ruleOnlyMode")}
        </Text>
      )}
      <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--qf-border)" }}>
        <Radio.Group
          value={scope}
          onChange={(e) => setScope(e.target.value)}
          disabled={!hasKgPermission}
          size="small"
          className="qf-radio-group"
        >
          <Radio.Button value="global"><GlobalOutlined /> {t("smartSuggestion.global")}</Radio.Button>
          <Radio.Button value="current_product_line">{t("smartSuggestion.currentProductLine")}</Radio.Button>
        </Radio.Group>
        {!hasKgPermission && (
          <Text type="secondary" style={{ fontSize: 11, marginLeft: 8, color: "var(--qf-text-tertiary)" }}>
            {t("smartSuggestion.noGlobalPermission")}
          </Text>
        )}
        {effectiveScope !== scope && (
          <Text type="warning" style={{ fontSize: 11, marginLeft: 8, color: "var(--qf-amber)" }}>
            {t("smartSuggestion.actualScope", { scope: scopeLabel(effectiveScope, t) })}
          </Text>
        )}
      </div>
      <div
        style={{
          maxHeight: 240,
          overflowY: "auto",
        }}
      >
        {suggestions.map((s, i) => (
          <div
            key={`${s.source}-${s.name}-${i}`}
            onClick={() => handleSelect(s)}
            style={{
              padding: "8px 12px",
              cursor: "pointer",
              background: i === selectedIndex ? "var(--qf-bg-hover)" : "transparent",
              borderBottom: i < suggestions.length - 1 ? "1px solid var(--qf-divider)" : "none",
              transition: "background var(--qf-transition-fast)",
            }}
            onMouseEnter={(e) => { if (i !== selectedIndex) e.currentTarget.style.background = "var(--qf-bg-hover)"; }}
            onMouseLeave={(e) => { if (i !== selectedIndex) e.currentTarget.style.background = "transparent"; }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {sourceIcon(s.source)}
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, color: "var(--qf-text-primary)" }}>{s.name}</div>
                {s.explanation && (
                  <Text type="secondary" style={{ fontSize: 11, color: "var(--qf-text-secondary)" }}>
                    {s.explanation}
                  </Text>
                )}
                <div><SourceTag item={s} t={t} /></div>
              </div>
              {confidenceLabel(s.confidence, t)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <Dropdown
      open={open && !disabled}
      popupRender={() => dropdownContent}
      trigger={[]}
      placement="bottomLeft"
    >
      <div style={{ position: "relative" }}>
        <Input.TextArea
          value={value}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={() => suggestions.length > 0 && setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 200)}
          disabled={disabled}
          autoSize={{ minRows: 1, maxRows: 6 }}
          style={{ width: "100%", resize: "none", padding: "4px 28px 4px 11px" }}
        />
        {/* Suffix indicator (Input.TextArea has no suffix prop) — pinned to
            bottom-right so long content wraps and the row grows to fit it. */}
        <span
          style={{
            position: "absolute",
            right: 8,
            bottom: 4,
            pointerEvents: "none",
            lineHeight: 1,
            color: "#faad14",
          }}
        >
          {loading ? <Spin size="small" /> : <BulbOutlined />}
        </span>
      </div>
    </Dropdown>
  );
}

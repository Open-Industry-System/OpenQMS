import { useState, useEffect, useRef, useCallback } from "react";
import { Input, Dropdown, Tag, Spin, Alert, Typography } from "antd";
import { BulbOutlined, StarOutlined, SettingOutlined } from "@ant-design/icons";
import { getRecommendations, type Suggestion, type RecommendResponse } from "../../api/recommendation";

const { Text } = Typography;

interface SmartSuggestionDropdownProps {
  triggerType: "failure_mode" | "failure_effect" | "failure_cause" | "measure" | "optimization";
  context: Record<string, unknown>;
  fmeaId: string;
  onSelect: (suggestion: Suggestion) => void;
  disabled?: boolean;
  value?: string;
  onChange?: (value: string) => void;
}

export default function SmartSuggestionDropdown({
  triggerType,
  context,
  fmeaId,
  onSelect,
  disabled = false,
  value,
  onChange,
}: SmartSuggestionDropdownProps) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [llmAvailable, setLlmAvailable] = useState(true);
  const [fallback, setFallback] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const abortRef = useRef<AbortController>();
  const [selectedIndex, setSelectedIndex] = useState(-1);

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
      try {
        const res: RecommendResponse = await getRecommendations(
          fmeaId,
          { trigger_type: triggerType, context: { ...context, [contextKey(triggerType)]: inputValue } },
          abortRef.current.signal
        );
        setSuggestions(res.suggestions.slice(0, 5));
        setLlmAvailable(res.llm_available);
        setFallback(res.source === "rule_fallback");
        setOpen(res.suggestions.length > 0);
        setSelectedIndex(-1);
      } catch {
        // Silently ignore aborted requests
      } finally {
        setLoading(false);
      }
    },
    [fmeaId, triggerType, context]
  );

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    onChange?.(val);

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
    } else if (e.key === "Enter" && selectedIndex >= 0) {
      e.preventDefault();
      handleSelect(suggestions[selectedIndex]);
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

  const confidenceLabel = (c: number) => {
    if (c >= 0.7) return <Tag color="green">高</Tag>;
    if (c >= 0.4) return <Tag color="orange">中</Tag>;
    return <Tag color="default">低</Tag>;
  };

  const sourceIcon = (s: string) =>
    s === "llm" ? <StarOutlined style={{ color: "#722ed1" }} /> : <SettingOutlined style={{ color: "#1890ff" }} />;

  const dropdownContent = (
    <div style={{ width: 320, background: "#fff", borderRadius: 4, boxShadow: "0 2px 8px rgba(0,0,0,0.15)" }}>
      {fallback && (
        <Alert
          type="warning"
          message="AI 建议暂不可用，已使用规则引擎"
          banner
          style={{ fontSize: 12 }}
        />
      )}
      {!llmAvailable && (
        <Text type="secondary" style={{ display: "block", padding: "4px 12px", fontSize: 12 }}>
          仅规则引擎模式
        </Text>
      )}
      {suggestions.map((s, i) => (
        <div
          key={i}
          onClick={() => handleSelect(s)}
          style={{
            padding: "8px 12px",
            cursor: "pointer",
            background: i === selectedIndex ? "#f0f0f0" : "transparent",
            borderBottom: i < suggestions.length - 1 ? "1px solid #f0f0f0" : "none",
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          {sourceIcon(s.source)}
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13 }}>{s.name}</div>
            {s.explanation && (
              <Text type="secondary" style={{ fontSize: 11 }}>
                {s.explanation}
              </Text>
            )}
          </div>
          {confidenceLabel(s.confidence)}
        </div>
      ))}
    </div>
  );

  return (
    <Dropdown
      open={open && !disabled}
      dropdownRender={() => dropdownContent}
      trigger={[]}
      placement="bottomLeft"
    >
      <div style={{ position: "relative" }}>
        <Input
          value={value}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={() => suggestions.length > 0 && setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 200)}
          disabled={disabled}
          suffix={loading ? <Spin size="small" /> : <BulbOutlined style={{ color: "#faad14" }} />}
          style={{ width: "100%" }}
        />
      </div>
    </Dropdown>
  );
}

function contextKey(triggerType: string): string {
  const map: Record<string, string> = {
    failure_mode: "function_description",
    failure_effect: "failure_mode",
    failure_cause: "failure_mode",
    measure: "failure_mode",
    optimization: "failure_mode",
  };
  return map[triggerType] || "function_description";
}

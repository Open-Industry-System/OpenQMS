import { useState, useEffect } from "react";
import { Dropdown, Spin } from "antd";
import { OpenAIOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import type { DraftFormat } from "../../types";

const STORAGE_KEY = "openqms_ai_draft_preference";

function loadFormat(): DraftFormat {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed.format === "structured" || parsed.format === "paragraph") return parsed.format;
    }
  } catch { /* localStorage unavailable or invalid JSON */ }
  return "structured";
}

function saveFormat(fmt: DraftFormat) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ format: fmt })); } catch { /* ignore */ }
}

interface AIDraftButtonProps {
  loading: boolean;
  tempUnavailable: boolean;
  error?: string | null;
  onGenerate: (format: DraftFormat) => void;
}

export default function AIDraftButton({
  loading,
  tempUnavailable,
  error,
  onGenerate,
}: AIDraftButtonProps) {
  const { t } = useTranslation("capa");
  const [format, setFormat] = useState<DraftFormat>(loadFormat);

  useEffect(() => {
    saveFormat(format);
  }, [format]);

  const items = [
    {
      key: "structured",
      label: t("draft.formats.structured"),
      onClick: () => setFormat("structured"),
    },
    {
      key: "paragraph",
      label: t("draft.formats.paragraph"),
      onClick: () => setFormat("paragraph"),
    },
  ];

  return (
    <Dropdown.Button
      type="text"
      size="small"
      icon={loading ? <Spin size="small" /> : <OpenAIOutlined />}
      loading={loading}
      disabled={loading || tempUnavailable}
      danger={!!error}
      onClick={() => onGenerate(format)}
      menu={{ items }}
      title={error || undefined}
    >
      {loading ? t("draft.drafting") : t("draft.button")}
    </Dropdown.Button>
  );
}

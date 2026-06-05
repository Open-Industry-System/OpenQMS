import { useState } from "react";
import { Button, Dropdown, Spin } from "antd";
import { OpenAIOutlined } from "@ant-design/icons";
import type { DraftFormat } from "../../types";

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
  const [format, setFormat] = useState<DraftFormat>("structured");

  const items = [
    {
      key: "structured",
      label: "结构化",
      onClick: () => setFormat("structured"),
    },
    {
      key: "paragraph",
      label: "段落",
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
      {loading ? "草拟中..." : "AI草拟"}
    </Dropdown.Button>
  );
}

import { Input } from "antd";
import type { ManagementReviewReportSection } from "../../types";

const { TextArea } = Input;

interface Props {
  section: ManagementReviewReportSection;
  readOnly: boolean;
  onChange: (section: ManagementReviewReportSection) => void;
}

export default function ReportSectionEditor({ section, readOnly, onChange }: Props) {
  return (
    <div>
      {section.source === "data_package" && (
        <div style={{ marginBottom: 12, whiteSpace: "pre-wrap", color: "#666", fontSize: 13 }}>
          {section.base_text}
        </div>
      )}
      {section.ai_analysis && (
        <div style={{ marginBottom: 12, color: "#333" }}>
          <strong>AI 分析：</strong>
          <div>{section.ai_analysis}</div>
        </div>
      )}
      <TextArea
        rows={4}
        value={section.manual_text}
        disabled={readOnly}
        onChange={(e) => onChange({ ...section, manual_text: e.target.value })}
        placeholder="在此输入人工编辑内容，导出时优先使用..."
      />
    </div>
  );
}

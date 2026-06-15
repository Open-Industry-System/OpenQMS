import { Input } from "antd";
import { useTranslation } from "react-i18next";
import type { ManagementReviewReportSection } from "../../types";

const { TextArea } = Input;

interface Props {
  section: ManagementReviewReportSection;
  readOnly: boolean;
  onChange: (section: ManagementReviewReportSection) => void;
}

export default function ReportSectionEditor({ section, readOnly, onChange }: Props) {
  const { t } = useTranslation("managementReview");

  return (
    <div>
      {section.source === "data_package" && (
        <div style={{ marginBottom: 12, whiteSpace: "pre-wrap", color: "#666", fontSize: 13 }}>
          {section.base_text}
        </div>
      )}
      {section.ai_analysis && (
        <div style={{ marginBottom: 12, color: "#333" }}>
          <strong>{t("sectionEditor.aiAnalysis")}</strong>
          <div>{section.ai_analysis}</div>
        </div>
      )}
      {section.findings.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <strong>{t("sectionEditor.keyFindings")}</strong>
          <ul style={{ margin: "4px 0", paddingLeft: 20 }}>
            {section.findings.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </div>
      )}
      {section.recommendations.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <strong>{t("sectionEditor.recommendations")}</strong>
          <ul style={{ margin: "4px 0", paddingLeft: 20 }}>
            {section.recommendations.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}
      <TextArea
        rows={4}
        value={section.manual_text}
        disabled={readOnly}
        onChange={(e) => onChange({ ...section, manual_text: e.target.value })}
        placeholder={t("sectionEditor.placeholder")}
      />
    </div>
  );
}

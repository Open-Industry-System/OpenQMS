import { useState } from "react";
import { Tag, Space, Button } from "antd";
import { useTranslation } from "react-i18next";
import type { SupplierRiskInputProjection } from "../../types";

interface Props {
  input: SupplierRiskInputProjection;
  canEdit: boolean;
  onConfirm: (confirmed: boolean) => void | Promise<void>;
}

const LEVEL_COLOR: Record<string, string> = {
  low: "default",
  medium: "orange",
  high: "red",
  critical: "red",
};

export default function SupplierRiskInputCard({ input, canEdit, onConfirm }: Props) {
  const { t } = useTranslation("capa");
  const [submitting, setSubmitting] = useState(false);

  if (!input) return null;

  const showButtons =
    canEdit && input.status === "processed" && input.repeat_confirmed === null;

  let prompt = "";
  if (input.repeat_confirmed === null) {
    if (input.repeat_detection_status === "matched") {
      prompt = t("riskInput.matched", {
        nos: (input.matched_capa_nos || []).join(", "),
      });
    } else if (input.repeat_detection_status === "not_matched") {
      prompt = t("riskInput.notMatched");
    } else {
      prompt = t("riskInput.unavailable");
    }
  }

  const handleConfirm = async (confirmed: boolean) => {
    if (submitting) return;
    setSubmitting(true);
    try {
      await onConfirm(confirmed);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div data-e2e="supplier-risk-input-card">
      <Space wrap size={4} style={{ marginBottom: 8 }}>
        {input.evaluated_risk_level && (
          <Tag color={LEVEL_COLOR[input.evaluated_risk_level] || "default"}>
            {input.evaluated_risk_level}
          </Tag>
        )}
        {input.status !== "processed" && (
          <Tag data-e2e="supplier-risk-input-status">
            {t(`riskInput.status.${input.status}`)}
          </Tag>
        )}
      </Space>
      {input.repeat_confirmed === null ? (
        <div>
          <p data-e2e="supplier-risk-input-prompt" style={{ marginBottom: showButtons ? 8 : 0 }}>
            {prompt}
          </p>
          {showButtons && (
            <Space>
              <Button
                data-e2e="supplier-risk-confirm-yes"
                type="primary"
                danger
                loading={submitting}
                onClick={() => handleConfirm(true)}
              >
                {t("riskInput.confirmYes")}
              </Button>
              <Button
                data-e2e="supplier-risk-confirm-no"
                loading={submitting}
                onClick={() => handleConfirm(false)}
              >
                {t("riskInput.confirmNo")}
              </Button>
            </Space>
          )}
        </div>
      ) : (
        <p data-e2e="supplier-risk-input-confirmed" style={{ marginBottom: 0 }}>
          {input.repeat_confirmed
            ? t("riskInput.confirmedRecurrence")
            : t("riskInput.confirmedNoRecurrence")}
        </p>
      )}
    </div>
  );
}

export { SupplierRiskInputCard };

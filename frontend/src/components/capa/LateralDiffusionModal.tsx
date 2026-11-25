import { useState } from "react";
import { Modal, Tag, Input, Button, Typography, Space } from "antd";
import { useTranslation } from "react-i18next";
import type { LateralDiffusionProjection } from "../../types";

export interface LateralDiffusionModalProps {
  open: boolean;
  projection: LateralDiffusionProjection | null;
  onDecide: (decision: "notify" | "skip", skipReason?: string) => void;
  loading?: boolean;
}

export function LateralDiffusionModal({
  open,
  projection,
  onDecide,
  loading,
}: LateralDiffusionModalProps) {
  const { t } = useTranslation("capa");
  const [skipReason, setSkipReason] = useState("");

  if (!projection) return null;

  return (
    <Modal
      open={open}
      title={t("lateral.title")}
      footer={null}
      closable={false}
      maskClosable={false}
      data-e2e="lateral-diffusion-modal"
      destroyOnClose
    >
      <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
        {t(
          "lateral.hint",
        )}
      </Typography.Paragraph>
      {projection.similar_products.map((sp) => (
        <div
          key={sp.product_type_code}
          data-e2e={`lateral-hit-${sp.product_type_code}`}
          style={{
            marginBottom: 12,
            padding: 8,
            border: "1px solid var(--qf-border, #f0f0f0)",
            borderRadius: 6,
          }}
        >
          <Typography.Text strong>
            {sp.product_type_name || sp.product_type_code}
          </Typography.Text>
          <div style={{ marginTop: 4 }}>
            {(sp.hit_criteria || []).map((c) => (
              <Tag key={c}>{c}</Tag>
            ))}
          </div>
          {sp.suggestion_direction && (
            <Typography.Paragraph style={{ marginTop: 8, marginBottom: 0 }}>
              {sp.suggestion_direction}
            </Typography.Paragraph>
          )}
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {(sp.product_lines || []).map((pl) => pl.code).join(", ")}
          </Typography.Text>
        </div>
      ))}
      <Input.TextArea
        data-e2e="lateral-skip-reason"
        value={skipReason}
        onChange={(e) => setSkipReason(e.target.value)}
        placeholder={t("lateral.skipReason")}
        rows={2}
        style={{ marginBottom: 12 }}
      />
      <Space>
        <Button
          type="primary"
          data-e2e="lateral-decide-notify"
          loading={loading}
          onClick={() => onDecide("notify")}
        >
          {t("lateral.notify")}
        </Button>
        <Button
          data-e2e="lateral-decide-skip"
          disabled={!skipReason.trim()}
          loading={loading}
          onClick={() => onDecide("skip", skipReason.trim())}
        >
          {t("lateral.skip")}
        </Button>
      </Space>
    </Modal>
  );
}

export default LateralDiffusionModal;

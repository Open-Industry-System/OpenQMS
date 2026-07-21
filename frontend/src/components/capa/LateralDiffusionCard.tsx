import { Button, Card, Space, Tag, Typography } from "antd";
import { useTranslation } from "react-i18next";
import type { LateralDiffusionProjection } from "../../types";

export interface LateralDiffusionCardProps {
  projection: LateralDiffusionProjection;
  canEdit?: boolean;
  onRerun?: () => void | Promise<void>;
  rerunLoading?: boolean;
}

export function LateralDiffusionCard({
  projection,
  canEdit,
  onRerun,
  rerunLoading,
}: LateralDiffusionCardProps) {
  const { t } = useTranslation("capa");
  const undecided =
    projection.status === "done" &&
    (projection.similar_products?.length || 0) > 0 &&
    projection.decision == null;

  return (
    <Card
      size="small"
      title={t("lateral.title", "横向扩散预警")}
      data-e2e="lateral-diffusion-card"
      style={{ marginTop: 16 }}
      extra={
        canEdit && undecided && onRerun ? (
          <Button size="small" loading={rerunLoading} onClick={() => onRerun()}>
            {t("lateral.rerun", "重新检查")}
          </Button>
        ) : null
      }
    >
      <Space wrap size={4} style={{ marginBottom: 8 }}>
        <Tag data-e2e="lateral-status">{projection.status}</Tag>
        {projection.decision && (
          <Tag color={projection.decision === "notified" ? "green" : "default"}>
            {projection.decision}
          </Tag>
        )}
        {projection.truncated && <Tag color="orange">{t("lateral.truncated", "已截断")}</Tag>}
      </Space>

      {projection.status === "empty" ? (
        <Typography.Text type="secondary">
          {t("lateral.empty", "未命中类似产品")}
        </Typography.Text>
      ) : (
        <>
          <Typography.Paragraph style={{ marginBottom: 8 }}>
            {t("lateral.hitCount", "命中类型 {{n}} 个", {
              n: projection.similar_products?.length || 0,
            })}
          </Typography.Paragraph>
          {(projection.similar_products || []).map((sp) => (
            <div key={sp.product_type_code} style={{ marginBottom: 6 }}>
              <Typography.Text strong>{sp.product_type_code}</Typography.Text>{" "}
              {(sp.hit_criteria || []).map((c) => (
                <Tag key={c}>{c}</Tag>
              ))}
            </div>
          ))}
        </>
      )}

      {(projection.notifications || []).length > 0 && (
        <div style={{ marginTop: 12 }} data-e2e="lateral-notifications">
          <Typography.Text type="secondary">
            {t("lateral.notifications", "通知记录")}
          </Typography.Text>
          {(projection.notifications || []).map((n) => (
            <div key={n.notification_id} style={{ fontSize: 12 }}>
              {n.product_type_code} · {n.recipient_label} · {n.decision}/{n.status}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export default LateralDiffusionCard;

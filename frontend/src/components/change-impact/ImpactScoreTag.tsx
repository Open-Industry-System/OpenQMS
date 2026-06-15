import { Tag } from "antd";
import { useTranslation } from "react-i18next";

interface ImpactScoreTagProps {
  score: number;
}

export default function ImpactScoreTag({ score }: ImpactScoreTagProps) {
  const { t } = useTranslation("changeImpact");
  let color: string;
  let label: string;

  if (score >= 7) {
    color = "red";
    label = t("affectedNode.score.high");
  } else if (score >= 4) {
    color = "orange";
    label = t("affectedNode.score.medium");
  } else {
    color = "green";
    label = t("affectedNode.score.low");
  }

  return (
    <Tag color={color}>
      {label} ({score})
    </Tag>
  );
}

import { Tag } from "antd";

interface ImpactScoreTagProps {
  score: number;
}

export default function ImpactScoreTag({ score }: ImpactScoreTagProps) {
  let color: string;
  let label: string;

  if (score >= 7) {
    color = "red";
    label = "高";
  } else if (score >= 4) {
    color = "orange";
    label = "中";
  } else {
    color = "green";
    label = "低";
  }

  return (
    <Tag color={color}>
      {label} ({score})
    </Tag>
  );
}

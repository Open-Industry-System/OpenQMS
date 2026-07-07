import { Steps, Tag, Badge, Space, Typography } from "antd";
import { useTranslation } from "react-i18next";
import type { StageRun } from "../../types";

interface RecommendationDAGProps {
  stages?: StageRun[];
}

const { Text } = Typography;
const { Step } = Steps;

const statusToAnt = (status: StageRun["status"]) => {
  switch (status) {
    case "done":
      return "finish";
    case "error":
      return "error";
    case "running":
      return "process";
    case "skipped":
    case "pending":
    default:
      return "wait";
  }
};

export default function RecommendationDAG({ stages }: RecommendationDAGProps) {
  const { t } = useTranslation("capa");

  if (!stages || stages.length === 0) return null;

  const sorted = [...stages].sort((a, b) => a.index - b.index);

  return (
    <Steps direction="vertical" size="small">
      {sorted.map((stage) => {
        const title = t(`dag.stageNames.${stage.index}`, { defaultValue: stage.name });
        return (
          <Step
            key={stage.index}
            status={statusToAnt(stage.status)}
            title={title}
            description={
              <Space size={4} wrap>
                <Tag>{stage.source}</Tag>
                <Badge count={stage.hit_count} showZero />
                <Text type="secondary">{stage.summary}</Text>
              </Space>
            }
            data-e2e={`rec-dag-stage-${stage.index}`}
            data-status={stage.status}
          />
        );
      })}
    </Steps>
  );
}

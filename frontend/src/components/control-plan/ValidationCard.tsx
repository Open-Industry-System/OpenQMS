import { Card, Tag, Button, Space, Typography } from "antd";
import {
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
  UndoOutlined,
} from "@ant-design/icons";
import type { ValidationResult } from "../../types/cpValidation";

const { Text } = Typography;

const severityConfig = {
  error: { color: "red", icon: <CloseCircleOutlined />, label: "错误" },
  warning: { color: "orange", icon: <ExclamationCircleOutlined />, label: "警告" },
  info: { color: "blue", icon: <InfoCircleOutlined />, label: "提示" },
};

interface Props {
  result: ValidationResult;
  onReject: (findingId: string) => void;
  onResolve: (findingId: string) => void;
  onReopen: (findingId: string) => void;
  loading?: boolean;
}

export default function ValidationCard({ result, onReject, onResolve, onReopen, loading }: Props) {
  const config = severityConfig[result.severity] || severityConfig.info;

  return (
    <Card
      size="small"
      style={{ marginBottom: 8, borderLeft: `3px solid ${config.color}` }}
      styles={{ body: { padding: 12 } }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
        <span style={{ color: config.color, fontSize: 16, marginTop: 2 }}>{config.icon}</span>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <Text strong>{result.title}</Text>
            <Tag color={config.color}>{config.label}</Tag>
          </div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {result.description}
          </Text>
          {result.suggestion && (
            <div style={{ marginTop: 4, padding: 6, background: "#f6ffed", borderRadius: 4 }}>
              <Text type="success" style={{ fontSize: 12 }}>
                建议: {result.suggestion}
              </Text>
            </div>
          )}
          <div style={{ marginTop: 8, display: "flex", justifyContent: "flex-end" }}>
            {result.status === "open" && (
              <Space size="small">
                <Button size="small" onClick={() => onResolve(result.finding_id)} loading={loading}>
                  标记已解决
                </Button>
                <Button size="small" danger onClick={() => onReject(result.finding_id)} loading={loading}>
                  忽略
                </Button>
              </Space>
            )}
            {result.status === "rejected" && (
              <Button size="small" icon={<UndoOutlined />} onClick={() => onReopen(result.finding_id)} loading={loading}>
                恢复
              </Button>
            )}
            {result.status === "resolved" && (
              <Tag color="green">已解决</Tag>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}

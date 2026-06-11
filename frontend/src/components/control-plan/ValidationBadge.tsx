import { Badge, Tooltip } from "antd";

interface Props {
  errorCount: number;
  warningCount: number;
  total: number;
}

export default function ValidationBadge({ errorCount, warningCount, total }: Props) {
  if (total === 0) {
    return <Tooltip title="未校验"><Badge status="default" /></Tooltip>;
  }
  if (errorCount > 0) {
    return <Tooltip title={`${errorCount} 个错误待处理`}><Badge status="error" /></Tooltip>;
  }
  if (warningCount > 0) {
    return <Tooltip title={`${warningCount} 个警告`}><Badge status="warning" /></Tooltip>;
  }
  return <Tooltip title="全部通过"><Badge status="success" /></Tooltip>;
}

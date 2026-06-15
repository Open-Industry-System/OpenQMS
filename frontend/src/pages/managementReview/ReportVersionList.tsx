import { List } from "antd";
import { StatusBadge } from "../../components/design";
import { formatDateTime } from "../../utils/dateTime";
import type { ReviewReportVersion } from "../../types";

interface Props {
  versions: ReviewReportVersion[];
  selectedId?: string;
  onSelect: (version: ReviewReportVersion) => void;
}

export default function ReportVersionList({ versions, selectedId, onSelect }: Props) {
  return (
    <List
      size="small"
      dataSource={versions}
      renderItem={(v) => (
        <List.Item
          style={{ cursor: "pointer", background: selectedId === v.report_id ? "#e6f7ff" : undefined }}
          onClick={() => onSelect(v)}
        >
          <StatusBadge status="success">{`v${v.version_no}`}</StatusBadge>
          <span style={{ fontSize: 12 }}>
            {v.finalized_at ? formatDateTime(v.finalized_at) : "-"}
          </span>
        </List.Item>
      )}
    />
  );
}
import { List, Tag } from "antd";
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
          <Tag color="green">v{v.version_no}</Tag>
          <span style={{ fontSize: 12 }}>
            {v.finalized_at ? new Date(v.finalized_at).toLocaleDateString() : "-"}
          </span>
        </List.Item>
      )}
    />
  );
}

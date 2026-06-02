import { Table } from "antd";
import type { ChangeImpactAnalysis } from "../../api/changeImpact";
import ImpactScoreTag from "./ImpactScoreTag";

interface ChangeHistoryTableProps {
  data: ChangeImpactAnalysis[];
  loading?: boolean;
  onSelect?: (record: ChangeImpactAnalysis) => void;
}

export default function ChangeHistoryTable({
  data,
  loading,
  onSelect,
}: ChangeHistoryTableProps) {
  return (
    <Table
      rowKey="id"
      loading={loading}
      dataSource={data}
      onRow={(record) => ({
        onClick: () => onSelect?.(record),
        style: { cursor: onSelect ? "pointer" : "default" },
      })}
      columns={[
        {
          title: "时间",
          dataIndex: "created_at",
          key: "created_at",
          render: (value: string) => new Date(value).toLocaleString("zh-CN"),
        },
        {
          title: "节点名",
          dataIndex: "node_name",
          key: "node_name",
        },
        {
          title: "变更类型",
          dataIndex: "change_type",
          key: "change_type",
          render: (value: string) =>
            value === "attribute" ? "属性" : "结构",
        },
        {
          title: "影响评分",
          dataIndex: "impact_score",
          key: "impact_score",
          render: (value: number) => <ImpactScoreTag score={value} />,
        },
        {
          title: "受影响节点数",
          key: "affected_count",
          render: (_: unknown, record: ChangeImpactAnalysis) =>
            record.impact_result?.summary?.total_affected ?? 0,
        },
      ]}
    />
  );
}

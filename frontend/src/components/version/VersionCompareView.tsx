import { useEffect, useState, useMemo } from "react";
import { Radio, Spin, Empty, Tag, Card, Descriptions, Typography } from "antd";
import type {
  FMEACompareResponse,
  CPCompareResponse,
  GraphNode,
  ModifiedNode,
  CPItemDiff,
  DiffSummary,
} from "../../types";

const { Text } = Typography;

interface VersionCompareViewProps {
  documentId: string;
  documentType: "fmea" | "cp";
  major1: number;
  minor1: number;
  major2: number;
  minor2: number;
}

type FilterKey = "all" | "added" | "deleted" | "modified";

function FMEADiffSection({
  diff,
  filter,
}: {
  diff: FMEACompareResponse["diff"];
  filter: FilterKey;
}) {
  const filteredAdded =
    filter === "all" || filter === "added" ? diff.added_nodes : [];
  const filteredDeleted =
    filter === "all" || filter === "deleted" ? diff.deleted_nodes : [];
  const filteredModified =
    filter === "all" || filter === "modified" ? diff.modified_nodes : [];

  return (
    <div>
      {filteredAdded.map((node) => (
        <NodeCard key={node.id} node={node} diffType="added" />
      ))}
      {filteredDeleted.map((node) => (
        <NodeCard key={node.id} node={node} diffType="deleted" />
      ))}
      {filteredModified.map((node) => (
        <ModifiedNodeCard key={node.node_id} node={node} />
      ))}
      {filteredAdded.length + filteredDeleted.length + filteredModified.length === 0 && (
        <Empty description="无匹配变更" />
      )}
    </div>
  );
}

function NodeCard({
  node,
  diffType,
}: {
  node: GraphNode;
  diffType: "added" | "deleted";
}) {
  const bg =
    diffType === "added"
      ? "#f6ffed"
      : "#fff2f0";
  const border =
    diffType === "added"
      ? "#b7eb8f"
      : "#ffccc7";
  const label = diffType === "added" ? "新增" : "删除";
  const tagColor = diffType === "added" ? "green" : "red";

  return (
    <Card
      size="small"
      style={{ marginBottom: 8, background: bg, borderColor: border }}
    >
      <SpaceInline>
        <Tag color={tagColor}>{label}</Tag>
        <Text strong>{node.name}</Text>
        {node.type && <Tag>{node.type}</Tag>}
      </SpaceInline>
      <div style={{ marginTop: 4, fontSize: 12, color: "#666" }}>
        S={node.severity} O={node.occurrence} D={node.detection}
        {node.ap && ` AP=${node.ap}`}
      </div>
    </Card>
  );
}

function ModifiedNodeCard({ node }: { node: ModifiedNode }) {
  return (
    <Card
      size="small"
      style={{ marginBottom: 8, background: "#fffbe6", borderColor: "#ffe58f" }}
    >
      <SpaceInline>
        <Tag color="orange">修改</Tag>
        <Text strong>{node.node_name}</Text>
        {node.impact_chain.length > 0 && (
          <>
            {node.impact_chain.map((item) => (
              <Tag key={item} color="blue">
                {item}
              </Tag>
            ))}
          </>
        )}
      </SpaceInline>
      <div style={{ marginTop: 8 }}>
        {node.changes.map((c, idx) => (
          <div key={idx} style={{ fontSize: 13, marginBottom: 2 }}>
            <Text type="secondary">{c.field}: </Text>
            <Text delete>{c.old_value}</Text>
            <Text type="secondary"> → </Text>
            <Text keyboard>{c.new_value}</Text>
          </div>
        ))}
      </div>
    </Card>
  );
}

function CPDiffSection({
  diff,
  filter,
}: {
  diff: CPCompareResponse["diff"];
  filter: FilterKey;
}) {
  const filteredAdded =
    filter === "all" || filter === "added" ? diff.added_items : [];
  const filteredDeleted =
    filter === "all" || filter === "deleted" ? diff.deleted_items : [];
  const filteredModified =
    filter === "all" || filter === "modified" ? diff.modified_items : [];

  return (
    <div>
      {filteredAdded.map((item) => (
        <CPItemCard
          key={item.item_id}
          stepNo={item.step_no}
          name={item.process_name}
          diffType="added"
        />
      ))}
      {filteredDeleted.map((item) => (
        <CPItemCard
          key={item.item_id}
          stepNo={item.step_no}
          name={item.process_name}
          diffType="deleted"
        />
      ))}
      {filteredModified.map((item) => (
        <CPModifiedCard key={item.item_id} item={item} />
      ))}
      {filteredAdded.length + filteredDeleted.length + filteredModified.length === 0 && (
        <Empty description="无匹配变更" />
      )}
    </div>
  );
}

function CPItemCard({
  stepNo,
  name,
  diffType,
}: {
  stepNo: string;
  name: string;
  diffType: "added" | "deleted";
}) {
  const bg = diffType === "added" ? "#f6ffed" : "#fff2f0";
  const border = diffType === "added" ? "#b7eb8f" : "#ffccc7";
  const label = diffType === "added" ? "新增" : "删除";
  const tagColor = diffType === "added" ? "green" : "red";

  return (
    <Card
      size="small"
      style={{ marginBottom: 8, background: bg, borderColor: border }}
    >
      <SpaceInline>
        <Tag color={tagColor}>{label}</Tag>
        <Text strong>{stepNo}</Text>
        <Text>{name}</Text>
      </SpaceInline>
    </Card>
  );
}

function CPModifiedCard({ item }: { item: CPItemDiff }) {
  return (
    <Card
      size="small"
      style={{ marginBottom: 8, background: "#fffbe6", borderColor: "#ffe58f" }}
    >
      <SpaceInline>
        <Tag color="orange">修改</Tag>
        <Text strong>{item.step_no}</Text>
      </SpaceInline>
      {item.changes && (
        <div style={{ marginTop: 8 }}>
          {item.changes.map((c, idx) => (
            <div key={idx} style={{ fontSize: 13, marginBottom: 2 }}>
              <Text type="secondary">{c.field}: </Text>
              <Text delete>{c.old_value}</Text>
              <Text type="secondary"> → </Text>
              <Text keyboard>{c.new_value}</Text>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function SpaceInline({ children }: { children: React.ReactNode }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      {children}
    </span>
  );
}

export default function VersionCompareView({
  documentId,
  documentType,
  major1,
  minor1,
  major2,
  minor2,
}: VersionCompareViewProps) {
  const [loading, setLoading] = useState(true);
  const [fmeaDiff, setFmeaDiff] = useState<FMEACompareResponse | null>(null);
  const [cpDiff, setCpDiff] = useState<CPCompareResponse | null>(null);
  const [filter, setFilter] = useState<FilterKey>("all");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      try {
        if (documentType === "fmea") {
          const { compareFMEAVersions } = await import("../../api/version");
          const resp = await compareFMEAVersions(
            documentId,
            major1,
            minor1,
            major2,
            minor2
          );
          if (!cancelled) setFmeaDiff(resp);
        } else {
          const { compareCPVersions } = await import("../../api/version");
          const resp = await compareCPVersions(
            documentId,
            major1,
            minor1,
            major2,
            minor2
          );
          if (!cancelled) setCpDiff(resp);
        }
      } catch {
        // error handled silently, diff stays null
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [documentId, documentType, major1, minor1, major2, minor2]);

  const summary: DiffSummary | null = useMemo(() => {
    if (fmeaDiff) return fmeaDiff.summary;
    if (cpDiff) return cpDiff.summary;
    return null;
  }, [fmeaDiff, cpDiff]);

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 40 }}>
        <Spin />
      </div>
    );
  }

  if (!fmeaDiff && !cpDiff) {
    return <Empty description="无法加载对比数据" />;
  }

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
        }}
      >
        <Descriptions size="small" column={1}>
          <Descriptions.Item label="版本对比">
            v{major1}.{minor1} → v{major2}.{minor2}
          </Descriptions.Item>
        </Descriptions>
        {summary && (
          <Radio.Group
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            optionType="button"
            buttonStyle="solid"
            size="small"
          >
            <Radio.Button value="all">
              全部 ({summary.added_count + summary.deleted_count + summary.modified_count})
            </Radio.Button>
            <Radio.Button value="added">
              新增 ({summary.added_count})
            </Radio.Button>
            <Radio.Button value="deleted">
              删除 ({summary.deleted_count})
            </Radio.Button>
            <Radio.Button value="modified">
              修改 ({summary.modified_count})
            </Radio.Button>
          </Radio.Group>
        )}
      </div>

      {fmeaDiff && <FMEADiffSection diff={fmeaDiff.diff} filter={filter} />}
      {cpDiff && <CPDiffSection diff={cpDiff.diff} filter={filter} />}
    </div>
  );
}
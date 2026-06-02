import { Modal, Alert, Button, List, Tag } from "antd";
import type { ConflictInfo } from "../../types/collaboration";
import type { GraphDiff } from "../../utils/graphDiff";

interface ConflictResolutionModalProps {
  visible: boolean;
  conflictInfo: ConflictInfo | null;
  diff: GraphDiff | null;
  onRefresh: () => void;
  onForceSave: () => void;
}

export default function ConflictResolutionModal({
  visible,
  conflictInfo,
  diff,
  onRefresh,
  onForceSave,
}: ConflictResolutionModalProps) {
  return (
    <Modal
      title="保存冲突"
      open={visible}
      closable={false}
      footer={null}
      width={600}
    >
      <Alert
        type="warning"
        message="文档已被他人修改"
        description={
          conflictInfo?.saved_by
            ? `${conflictInfo.saved_by} 保存了更改`
            : "文档在您编辑期间已被其他用户保存"
        }
        style={{ marginBottom: 16 }}
      />

      {diff && (
        <div style={{ marginBottom: 16 }}>
          <p style={{ fontWeight: 600, marginBottom: 8 }}>
            对方修改了 {diff.nodeChanges.length} 处内容
            {diff.conflictingFields.length > 0 && (
              <Tag color="red" style={{ marginLeft: 8 }}>
                {diff.conflictingFields.length} 处冲突
              </Tag>
            )}
          </p>
          <List
            size="small"
            dataSource={diff.nodeChanges.slice(0, 10)}
            renderItem={(change) => (
              <List.Item>
                {change.type === "added" && (
                  <span>
                    新增 <Tag>{change.nodeType}</Tag> {change.name}
                  </span>
                )}
                {change.type === "removed" && (
                  <span style={{ color: "#cf1322" }}>
                    删除 <Tag>{change.nodeType}</Tag> {change.name}
                  </span>
                )}
                {change.type === "modified" && (
                  <span>
                    修改 <Tag>{change.nodeType}</Tag> {change.name} 的{" "}
                    <Tag color="blue">{change.field}</Tag>
                    {diff.conflictingFields.some(
                      (c) => c.node_id === change.node_id && c.field === change.field
                    ) && (
                      <Tag color="red" style={{ marginLeft: 4 }}>
                        冲突
                      </Tag>
                    )}
                  </span>
                )}
              </List.Item>
            )}
          />
          {diff.nodeChanges.length > 10 && (
            <p style={{ color: "#8c8c8c", fontSize: 12 }}>
              还有 {diff.nodeChanges.length - 10} 处修改...
            </p>
          )}
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <Button onClick={onRefresh}>放弃我的更改，刷新页面</Button>
        <Button type="primary" danger onClick={onForceSave}>
          强制保存（覆盖对方更改）
        </Button>
      </div>
    </Modal>
  );
}

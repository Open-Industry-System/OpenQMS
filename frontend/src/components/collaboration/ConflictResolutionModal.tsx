import { Modal, Alert, Button, List, Tag } from "antd";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation("collaboration");
  return (
    <Modal
      title={t("conflict.title")}
      open={visible}
      closable={false}
      footer={null}
      width={600}
    >
      <Alert
        type="warning"
        message={t("conflict.documentChanged")}
        description={
          conflictInfo?.saved_by
            ? t("conflict.changedBy", { user: conflictInfo.saved_by })
            : t("conflict.changedByOther")
        }
        style={{ marginBottom: 16 }}
      />

      {diff && (
        <div style={{ marginBottom: 16 }}>
          <p style={{ fontWeight: 600, marginBottom: 8 }}>
            {t("conflict.changesCount", { count: diff.nodeChanges.length })}
            {diff.conflictingFields.length > 0 && (
              <Tag color="red" style={{ marginLeft: 8 }}>
                {t("conflict.conflictsCount", { count: diff.conflictingFields.length })}
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
                    {t("conflict.added", { type: change.nodeType, name: change.name })}
                  </span>
                )}
                {change.type === "removed" && (
                  <span style={{ color: "#cf1322" }}>
                    {t("conflict.removed", { type: change.nodeType, name: change.name })}
                  </span>
                )}
                {change.type === "modified" && (
                  <span>
                    {t("conflict.modified", { type: change.nodeType, name: change.name, field: change.field })}
                    {diff.conflictingFields.some(
                      (c) => c.node_id === change.node_id && c.field === change.field
                    ) && (
                      <Tag color="red" style={{ marginLeft: 4 }}>
                        {t("conflict.conflictTag")}
                      </Tag>
                    )}
                  </span>
                )}
              </List.Item>
            )}
          />
          {diff.nodeChanges.length > 10 && (
            <p style={{ color: "#8c8c8c", fontSize: 12 }}>
              {t("conflict.moreChanges", { count: diff.nodeChanges.length - 10 })}
            </p>
          )}
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <Button onClick={onRefresh}>{t("conflict.refresh")}</Button>
        <Button type="primary" danger onClick={onForceSave}>
          {t("conflict.forceSave")}
        </Button>
      </div>
    </Modal>
  );
}

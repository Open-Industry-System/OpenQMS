import { useEffect, useState, useCallback } from "react";
import { Button, Switch, Tag, Timeline, Space, Spin, Empty } from "antd";
import {
  EyeOutlined,
  SwapOutlined,
  RollbackOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import type { FMEAVersion, CPVersion } from "../../types";

type VersionItem = FMEAVersion | CPVersion;

interface VersionHistoryTabProps {
  documentId: string;
  documentType: "fmea" | "cp";
  canCreate: boolean;
  canRollback: boolean;
  isDraft: boolean;
  onViewSnapshot: (major: number, minor: number) => void;
  onCompare: (major1: number, minor1: number, major2: number, minor2: number) => void;
  onRollback: (major: number, minor: number) => void;
  onCreateVersion: () => void;
}

const CHANGE_TYPE_CONFIG: Record<
  string,
  { label: string; color: string }
> = {
  submit: { label: "提交审批", color: "blue" },
  approve: { label: "审批通过", color: "green" },
  manual: { label: "手动创建", color: "default" },
  rollback: { label: "版本回退", color: "orange" },
  fmea_sync: { label: "FMEA同步", color: "purple" },
};

export default function VersionHistoryTab({
  documentId,
  documentType,
  canCreate,
  canRollback,
  onViewSnapshot,
  onCompare,
  onRollback,
  onCreateVersion,
}: VersionHistoryTabProps) {
  const [versions, setVersions] = useState<VersionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [majorOnly, setMajorOnly] = useState(true);

  const fetchVersions = useCallback(async () => {
    setLoading(true);
    try {
      if (documentType === "fmea") {
        const { listFMEAVersions } = await import("../../api/version");
        const resp = await listFMEAVersions(documentId, {
          major_only: majorOnly,
          page_size: 100,
        });
        setVersions(resp.items);
      } else {
        const { listCPVersions } = await import("../../api/version");
        const resp = await listCPVersions(documentId, {
          major_only: majorOnly,
          page_size: 100,
        });
        setVersions(resp.items);
      }
    } catch {
      setVersions([]);
    } finally {
      setLoading(false);
    }
  }, [documentId, documentType, majorOnly]);

  useEffect(() => {
    fetchVersions();
  }, [fetchVersions]);

  const formatTime = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 40 }}>
        <Spin />
      </div>
    );
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
        <Space>
          <span style={{ color: "#666" }}>仅主版本</span>
          <Switch
            checked={majorOnly}
            onChange={setMajorOnly}
            size="small"
          />
        </Space>
        {canCreate && (
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={onCreateVersion}
          >
            创建版本
          </Button>
        )}
      </div>

      {versions.length === 0 ? (
        <Empty description="暂无版本记录" />
      ) : (
        <Timeline
          items={versions.map((v, idx) => {
            const cfg = CHANGE_TYPE_CONFIG[v.change_type] || {
              label: v.change_type,
              color: "default",
            };
            const nextVersion = idx < versions.length - 1 ? versions[idx + 1] : null;

            return {
              color: cfg.color === "default" ? "gray" : cfg.color,
              children: (
                <div
                  key={`${v.major}.${v.minor}`}
                  style={{ paddingBottom: 8 }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <Space>
                      <strong>v{v.major}.{v.minor}</strong>
                      <Tag color={cfg.color}>{cfg.label}</Tag>
                      <span style={{ color: "#999", fontSize: 12 }}>
                        {formatTime(v.changed_at)}
                      </span>
                    </Space>
                    <Space size={4}>
                      <Button
                        size="small"
                        icon={<EyeOutlined />}
                        onClick={() => onViewSnapshot(v.major, v.minor)}
                      >
                        查看
                      </Button>
                      {nextVersion && (
                        <Button
                          size="small"
                          icon={<SwapOutlined />}
                          onClick={() =>
                            onCompare(
                              v.major,
                              v.minor,
                              nextVersion.major,
                              nextVersion.minor
                            )
                          }
                        >
                          对比
                        </Button>
                      )}
                      {canRollback && idx > 0 && (
                        <Button
                          size="small"
                          danger
                          icon={<RollbackOutlined />}
                          onClick={() => onRollback(v.major, v.minor)}
                        >
                          回退
                        </Button>
                      )}
                    </Space>
                  </div>
                  {v.change_summary && (
                    <div style={{ color: "#666", fontSize: 13, marginTop: 4 }}>
                      {v.change_summary}
                    </div>
                  )}
                </div>
              ),
            };
          })}
        />
      )}
    </div>
  );
}

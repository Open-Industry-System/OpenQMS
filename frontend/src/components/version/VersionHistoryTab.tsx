import { useEffect, useState, useCallback } from "react";
import { Button, Switch, Tag, Timeline, Space, Spin, Empty } from "antd";
import {
  EyeOutlined,
  SwapOutlined,
  RollbackOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
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

export default function VersionHistoryTab({
  documentId,
  documentType,
  canCreate,
  canRollback,
  isDraft,
  onViewSnapshot,
  onCompare,
  onRollback,
  onCreateVersion,
}: VersionHistoryTabProps) {
  const { t } = useTranslation("version");
  const [versions, setVersions] = useState<VersionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [majorOnly, setMajorOnly] = useState(true);

  const getChangeTypeConfig = (changeType: string): { label: string; color: string } => {
    switch (changeType) {
      case "submit":
        return { label: t("history.changeTypes.submit"), color: "blue" };
      case "approve":
        return { label: t("history.changeTypes.approve"), color: "green" };
      case "manual":
        return { label: t("history.changeTypes.manual"), color: "default" };
      case "rollback":
        return { label: t("history.changeTypes.rollback"), color: "orange" };
      case "fmea_sync":
        return { label: t("history.changeTypes.fmea_sync"), color: "purple" };
      default:
        return { label: changeType, color: "default" };
    }
  };

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
    return d.toLocaleString(undefined, {
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
          <span style={{ color: "#666" }}>{t("history.majorOnly")}</span>
          <Switch
            checked={majorOnly}
            onChange={setMajorOnly}
            size="small"
          />
        </Space>
        {canCreate && isDraft && (
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={onCreateVersion}
          >
            {t("history.createVersion")}
          </Button>
        )}
      </div>

      {versions.length === 0 ? (
        <Empty description={t("history.noRecords")} />
      ) : (
        <Timeline
          items={versions.map((v, idx) => {
            const cfg = getChangeTypeConfig(v.change_type);
            const nextVersion = idx < versions.length - 1 ? versions[idx + 1] : null;

            return {
              color: cfg.color === "default" ? "gray" : cfg.color,
              children: (
                <div
                  key={`${v.major_no}.${v.minor_no}`}
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
                      <strong>v{v.major_no}.{v.minor_no}</strong>
                      <Tag color={cfg.color}>{cfg.label}</Tag>
                      <span style={{ color: "#999", fontSize: 12 }}>
                        {formatTime(v.created_at)}
                      </span>
                    </Space>
                    <Space size={4}>
                      <Button
                        size="small"
                        icon={<EyeOutlined />}
                        onClick={() => onViewSnapshot(v.major_no, v.minor_no)}
                      >
                        {t("history.view")}
                      </Button>
                      {nextVersion && (
                        <Button
                          size="small"
                          icon={<SwapOutlined />}
                          onClick={() =>
                            onCompare(
                              v.major_no,
                              v.minor_no,
                              nextVersion.major_no,
                              nextVersion.minor_no
                            )
                          }
                        >
                          {t("history.compare")}
                        </Button>
                      )}
                      {canRollback && idx > 0 && (
                        <Button
                          size="small"
                          danger
                          icon={<RollbackOutlined />}
                          onClick={() => onRollback(v.major_no, v.minor_no)}
                        >
                          {t("history.rollback")}
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

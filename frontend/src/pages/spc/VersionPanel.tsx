import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Drawer, List, Tag, Button, message, Badge } from "antd";
import { HistoryOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import type { ControlLimitSnapshot } from "../../types/spc";
import { getSnapshots, activateSnapshot } from "../../api/spc";

interface VersionPanelProps {
  icId: string;
  onActivated: () => void;
}

const VersionPanel: React.FC<VersionPanelProps> = ({ icId, onActivated }) => {
  const { t } = useTranslation("spc");
  const [open, setOpen] = useState(false);
  const [snapshots, setSnapshots] = useState<ControlLimitSnapshot[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchSnapshots = async () => {
    setLoading(true);
    try {
      const data = await getSnapshots(icId);
      setSnapshots(data);
    } catch {
      message.error(t("versionPanel.loadFailed"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) fetchSnapshots();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, icId]);

  const handleActivate = async (snapshotId: string) => {
    try {
      await activateSnapshot(icId, snapshotId);
      message.success(t("versionPanel.activateSuccess"));
      fetchSnapshots();
      onActivated();
    } catch {
      message.error(t("versionPanel.activateFailed"));
    }
  };

  return (
    <>
      <Button icon={<HistoryOutlined />} onClick={() => setOpen(true)}>
        {t("versionPanel.button")}
      </Button>
      <Drawer
        title={t("versionPanel.title")}
        open={open}
        onClose={() => setOpen(false)}
        width={400}
      >
        <List
          loading={loading}
          dataSource={snapshots}
          renderItem={(snap) => (
            <List.Item
              style={{ background: snap.is_active ? "#f0f5ff" : undefined, borderRadius: 4 }}
              actions={[
                snap.is_active ? (
                  <Tag color="blue">{t("versionPanel.current")}</Tag>
                ) : (
                  <Button size="small" onClick={() => handleActivate(snap.snapshot_id)}>
                    {t("versionPanel.activate")}
                  </Button>
                ),
              ]}
            >
              <List.Item.Meta
                title={
                  <span>
                    <Badge
                      count={`v${snap.version_no}`}
                      style={{ backgroundColor: snap.is_active ? "#1677ff" : "#8c8c8c" }}
                    />
                    <span style={{ marginLeft: 8 }}>
                      UCL: {snap.ucl} / LCL: {snap.lcl}
                    </span>
                  </span>
                }
                description={dayjs(snap.calculated_at).format("YYYY-MM-DD HH:mm")}
              />
            </List.Item>
          )}
          locale={{ emptyText: t("versionPanel.empty") }}
        />
      </Drawer>
    </>
  );
};

export default VersionPanel;

import React, { useEffect, useState } from "react";
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
  const [open, setOpen] = useState(false);
  const [snapshots, setSnapshots] = useState<ControlLimitSnapshot[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchSnapshots = async () => {
    setLoading(true);
    try {
      const data = await getSnapshots(icId);
      setSnapshots(data);
    } catch {
      message.error("加载版本列表失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) fetchSnapshots();
  }, [open, icId]);

  const handleActivate = async (snapshotId: string) => {
    try {
      await activateSnapshot(icId, snapshotId);
      message.success("已切换控制限版本");
      fetchSnapshots();
      onActivated();
    } catch {
      message.error("切换失败");
    }
  };

  return (
    <>
      <Button icon={<HistoryOutlined />} onClick={() => setOpen(true)}>
        版本管理
      </Button>
      <Drawer
        title="控制限版本"
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
                  <Tag color="blue">当前</Tag>
                ) : (
                  <Button size="small" onClick={() => handleActivate(snap.snapshot_id)}>
                    设为当前
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
          locale={{ emptyText: "暂无锁定的控制限版本" }}
        />
      </Drawer>
    </>
  );
};

export default VersionPanel;

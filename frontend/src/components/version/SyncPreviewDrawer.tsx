import { useEffect, useState } from "react";
import {
  Drawer,
  Alert,
  Table,
  Button,
  Space,
  Tag,
  message,
  Spin,
} from "antd";
import type { SyncPreviewItem, SyncPreviewResponse } from "../../types";

interface SyncPreviewDrawerProps {
  open: boolean;
  cpId: string;
  onClose: () => void;
  onSuccess: () => void;
}

const ACTION_CONFIG: Record<string, { label: string; color: string }> = {
  add: { label: "新增", color: "green" },
  sync: { label: "更新", color: "blue" },
  delete: { label: "删除", color: "red" },
};

export default function SyncPreviewDrawer({
  open,
  cpId,
  onClose,
  onSuccess,
}: SyncPreviewDrawerProps) {
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<SyncPreviewResponse | null>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    if (!open) return;

    let cancelled = false;

    async function load() {
      setLoading(true);
      try {
        const { getSyncPreview } = await import("../../api/version");
        const resp = await getSyncPreview(cpId);
        if (!cancelled) {
          setPreview(resp);
          // Default: select all non-delete items
          const selectableKeys = resp.items
            .filter((item) => item.action !== "delete")
            .map((item) => item.item_id);
          setSelectedRowKeys(selectableKeys);
        }
      } catch {
        if (!cancelled) {
          message.error("无法加载同步预览");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [open, cpId]);

  const handleSync = async () => {
    if (!selectedRowKeys.length) {
      message.warning("请至少选择一项进行同步");
      return;
    }

    setSyncing(true);
    try {
      const { applySyncFromFMEA } = await import("../../api/version");
      await applySyncFromFMEA(cpId, selectedRowKeys as string[]);
      message.success("同步成功");
      onSuccess();
      onClose();
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : "同步失败";
      message.error(errorMessage);
    } finally {
      setSyncing(false);
    }
  };

  const formatDictValue = (val: Record<string, string | null> | null) => {
    if (!val) return <span style={{ color: "#999" }}>无</span>;
    const entries = Object.entries(val).filter(([, v]) => v);
    if (!entries.length) return <span style={{ color: "#999" }}>无</span>;
    return (
      <div style={{ fontSize: 12, lineHeight: 1.6 }}>
        {entries.map(([k, v]) => (
          <div key={k}>{k}: {v}</div>
        ))}
      </div>
    );
  };

  const columns = [
    {
      title: "操作",
      dataIndex: "action",
      key: "action",
      width: 80,
      render: (action: string) => {
        const cfg = ACTION_CONFIG[action] || { label: action, color: "default" };
        return <Tag color={cfg.color}>{cfg.label}</Tag>;
      },
    },
    {
      title: "工序号",
      dataIndex: "step_no",
      key: "step_no",
      width: 100,
    },
    {
      title: "当前值",
      dataIndex: "current_value",
      key: "current_value",
      width: 180,
      render: formatDictValue,
    },
    {
      title: "FMEA新值",
      dataIndex: "fmea_new_value",
      key: "fmea_new_value",
      width: 180,
      render: formatDictValue,
    },
    {
      title: "合并值",
      dataIndex: "merged_value",
      key: "merged_value",
      width: 180,
      render: formatDictValue,
    },
  ];

  return (
    <Drawer
      open={open}
      title="FMEA 同步预览"
      width={960}
      onClose={onClose}
      footer={
        <Space style={{ width: "100%", justifyContent: "flex-end" }}>
          <Button onClick={onClose}>取消</Button>
          <Button
            type="primary"
            onClick={handleSync}
            loading={syncing}
            disabled={!preview || selectedRowKeys.length === 0}
          >
            确认同步
          </Button>
        </Space>
      }
    >
      {loading ? (
        <div style={{ textAlign: "center", padding: 40 }}>
          <Spin />
        </div>
      ) : preview ? (
        <div>
          <Alert
            message="同步来源"
            description={
              <div>
                <p>
                  FMEA版本: <strong>{preview.fmea_version}</strong>
                </p>
                <p style={{ marginTop: 4 }}>
                  新增: <Tag color="green">{preview.summary.add_count}</Tag>
                  更新: <Tag color="blue">{preview.summary.update_count}</Tag>
                  删除: <Tag color="red">{preview.summary.delete_count}</Tag>
                </p>
              </div>
            }
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />
          <Table
            dataSource={preview.items}
            columns={columns}
            rowKey="item_id"
            size="small"
            pagination={false}
            rowSelection={{
              selectedRowKeys,
              onChange: setSelectedRowKeys,
              getCheckboxProps: (record: SyncPreviewItem) => ({
                disabled: record.action === "delete",
              }),
            }}
          />
        </div>
      ) : (
        <div style={{ textAlign: "center", padding: 40 }}>
          无法加载预览
        </div>
      )}
    </Drawer>
  );
}
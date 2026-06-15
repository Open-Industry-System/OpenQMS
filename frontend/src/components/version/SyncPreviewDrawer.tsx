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
import { useTranslation } from "react-i18next";
import type { SyncPreviewItem, SyncPreviewResponse } from "../../types";

interface SyncPreviewDrawerProps {
  open: boolean;
  cpId: string;
  onClose: () => void;
  onSuccess: () => void;
}

export default function SyncPreviewDrawer({
  open,
  cpId,
  onClose,
  onSuccess,
}: SyncPreviewDrawerProps) {
  const { t } = useTranslation("version");
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<SyncPreviewResponse | null>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [syncing, setSyncing] = useState(false);

  const getActionConfig = (action: string) => {
    switch (action) {
      case "add":
        return { label: t("syncPreview.actions.add"), color: "green" };
      case "sync":
        return { label: t("syncPreview.actions.sync"), color: "blue" };
      case "delete":
        return { label: t("syncPreview.actions.delete"), color: "red" };
      default:
        return { label: action, color: "default" };
    }
  };

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
          const selectableKeys = resp.items
            .filter((item) => item.action !== "delete")
            .map((item) => item.item_id);
          setSelectedRowKeys(selectableKeys);
        }
      } catch {
        if (!cancelled) {
          message.error(t("syncPreview.loadFailed"));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [open, cpId, t]);

  const handleSync = async () => {
    if (!selectedRowKeys.length) {
      message.warning(t("syncPreview.selectAtLeastOne"));
      return;
    }

    setSyncing(true);
    try {
      const { applySyncFromFMEA } = await import("../../api/version");
      await applySyncFromFMEA(cpId, selectedRowKeys as string[]);
      message.success(t("syncPreview.syncSuccess"));
      onSuccess();
      onClose();
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : t("syncPreview.syncFailed");
      message.error(errorMessage);
    } finally {
      setSyncing(false);
    }
  };

  const formatDictValue = (val: Record<string, string | null> | null) => {
    if (!val) return <span style={{ color: "#999" }}>{t("syncPreview.none")}</span>;
    const entries = Object.entries(val).filter(([, v]) => v);
    if (!entries.length) return <span style={{ color: "#999" }}>{t("syncPreview.none")}</span>;
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
      title: t("syncPreview.columns.action"),
      dataIndex: "action",
      key: "action",
      width: 80,
      render: (action: string) => {
        const cfg = getActionConfig(action);
        return <Tag color={cfg.color}>{cfg.label}</Tag>;
      },
    },
    {
      title: t("syncPreview.columns.stepNo"),
      dataIndex: "step_no",
      key: "step_no",
      width: 100,
    },
    {
      title: t("syncPreview.columns.currentValue"),
      dataIndex: "current_value",
      key: "current_value",
      width: 180,
      render: formatDictValue,
    },
    {
      title: t("syncPreview.columns.fmeaNewValue"),
      dataIndex: "fmea_new_value",
      key: "fmea_new_value",
      width: 180,
      render: formatDictValue,
    },
    {
      title: t("syncPreview.columns.mergedValue"),
      dataIndex: "merged_value",
      key: "merged_value",
      width: 180,
      render: formatDictValue,
    },
  ];

  return (
    <Drawer
      open={open}
      title={t("syncPreview.title")}
      width={960}
      onClose={onClose}
      footer={
        <Space style={{ width: "100%", justifyContent: "flex-end" }}>
          <Button onClick={onClose}>{t("syncPreview.cancel")}</Button>
          <Button
            type="primary"
            onClick={handleSync}
            loading={syncing}
            disabled={!preview || selectedRowKeys.length === 0}
          >
            {t("syncPreview.confirmSync")}
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
            message={t("syncPreview.source")}
            description={
              <div>
                <p>
                  {t("syncPreview.fmeaVersion", { version: preview.fmea_version })}
                </p>
                <p style={{ marginTop: 4 }}>
                  {t("syncPreview.addCount", { count: preview.summary.add_count })}
                  {t("syncPreview.updateCount", { count: preview.summary.update_count })}
                  {t("syncPreview.deleteCount", { count: preview.summary.delete_count })}
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
          {t("syncPreview.loadPreviewFailed")}
        </div>
      )}
    </Drawer>
  );
}

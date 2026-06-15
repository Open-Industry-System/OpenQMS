import React, { useState } from "react";
import { Drawer, Button, Space, Input, message, Descriptions } from "antd";
import { useTranslation } from "react-i18next";
import type { SupplierRiskAlert } from "../../../types";
import { riskAlertApi } from "../../../api/supplierRisk";

interface Props {
  alert: SupplierRiskAlert | null;
  open: boolean;
  onClose: () => void;
}

const HandleAlertDrawer: React.FC<Props> = ({ alert, open, onClose }) => {
  const { t } = useTranslation("supplierRisk");
  const { t: tc } = useTranslation("common");
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);

  if (!alert) return null;

  const handle = async (action: string) => {
    if (action === "ignore" && !note.trim()) {
      message.warning(t("handleDrawer.messages.ignoreReasonRequired"));
      return;
    }
    setLoading(true);
    try {
      await riskAlertApi.handle(alert.alert_id, { action, note: note || undefined });
      message.success(t("handleDrawer.messages.operationSuccess"));
      onClose();
    } catch {
      message.error(t("handleDrawer.messages.operationFailed"));
    } finally {
      setLoading(false);
    }
  };

  const createScar = async () => {
    setLoading(true);
    try {
      await riskAlertApi.createScar(alert.alert_id);
      message.success(t("handleDrawer.messages.scarCreated"));
      onClose();
    } catch {
      message.error(t("handleDrawer.messages.createFailed"));
    } finally {
      setLoading(false);
    }
  };

  const createCapa = async () => {
    setLoading(true);
    try {
      await riskAlertApi.createCapa(alert.alert_id);
      message.success(t("handleDrawer.messages.capaCreated"));
      onClose();
    } catch {
      message.error(t("handleDrawer.messages.createFailed"));
    } finally {
      setLoading(false);
    }
  };

  const RISK_COLORS: Record<string, string> = {
    low: "#52c41a",
    medium: "#faad14",
    high: "#fa8c16",
    critical: "#f5222d",
  };

  return (
    <Drawer title={t("handleDrawer.title", { supplier_name: alert.supplier_name })} open={open} onClose={onClose} width={420}>
      <Space direction="vertical" style={{ width: "100%" }} size="middle">
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label={t("handleDrawer.labels.riskLevel")}>
            <span style={{ color: RISK_COLORS[alert.risk_level], fontWeight: 600 }}>
              {alert.risk_level}
            </span>
          </Descriptions.Item>
          <Descriptions.Item label={t("handleDrawer.labels.totalScore")}>{alert.risk_score}</Descriptions.Item>
          <Descriptions.Item label={t("handleDrawer.labels.qualityScore")}>{alert.quality_score}</Descriptions.Item>
          <Descriptions.Item label={t("handleDrawer.labels.deliveryScore")}>{alert.delivery_score}</Descriptions.Item>
          <Descriptions.Item label={t("handleDrawer.labels.complianceScore")}>{alert.compliance_score}</Descriptions.Item>
          <Descriptions.Item label={t("handleDrawer.labels.currentStatus")}>{alert.status}</Descriptions.Item>
        </Descriptions>

        <Input.TextArea
          placeholder={t("handleDrawer.notePlaceholder")}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={3}
        />

        <Space wrap>
          <Button onClick={() => handle("acknowledge")} loading={loading}>
            {t("handleDrawer.actions.acknowledge")}
          </Button>
          <Button onClick={() => handle("ignore")} loading={loading}>
            {t("handleDrawer.actions.ignore")}
          </Button>
          <Button onClick={() => handle("close")} loading={loading}>
            {tc("actions.close")}
          </Button>
        </Space>

        <Space wrap>
          <Button type="primary" onClick={createScar} loading={loading}>
            {t("handleDrawer.actions.createScar")}
          </Button>
          <Button type="primary" onClick={createCapa} loading={loading}>
            {t("handleDrawer.actions.createCapa")}
          </Button>
        </Space>
      </Space>
    </Drawer>
  );
};

export default HandleAlertDrawer;

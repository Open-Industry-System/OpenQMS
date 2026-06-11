import React, { useState } from "react";
import { Drawer, Button, Space, Input, message, Descriptions } from "antd";
import type { SupplierRiskAlert } from "../../../types";
import { riskAlertApi } from "../../../api/supplierRisk";

interface Props {
  alert: SupplierRiskAlert | null;
  open: boolean;
  onClose: () => void;
}

const HandleAlertDrawer: React.FC<Props> = ({ alert, open, onClose }) => {
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);

  if (!alert) return null;

  const handle = async (action: string) => {
    if (action === "ignore" && !note.trim()) {
      message.warning("忽略预警需填写理由");
      return;
    }
    setLoading(true);
    try {
      await riskAlertApi.handle(alert.alert_id, { action, note: note || undefined });
      message.success("操作成功");
      onClose();
    } catch {
      message.error("操作失败");
    } finally {
      setLoading(false);
    }
  };

  const createScar = async () => {
    setLoading(true);
    try {
      await riskAlertApi.createScar(alert.alert_id);
      message.success("SCAR 已创建");
      onClose();
    } catch {
      message.error("创建失败");
    } finally {
      setLoading(false);
    }
  };

  const createCapa = async () => {
    setLoading(true);
    try {
      await riskAlertApi.createCapa(alert.alert_id);
      message.success("CAPA 已创建");
      onClose();
    } catch {
      message.error("创建失败");
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
    <Drawer title={`预警处置 — ${alert.supplier_name}`} open={open} onClose={onClose} width={420}>
      <Space direction="vertical" style={{ width: "100%" }} size="middle">
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label="风险等级">
            <span style={{ color: RISK_COLORS[alert.risk_level], fontWeight: 600 }}>
              {alert.risk_level}
            </span>
          </Descriptions.Item>
          <Descriptions.Item label="综合风险分">{alert.risk_score}</Descriptions.Item>
          <Descriptions.Item label="质量分">{alert.quality_score}</Descriptions.Item>
          <Descriptions.Item label="交付分">{alert.delivery_score}</Descriptions.Item>
          <Descriptions.Item label="合规分">{alert.compliance_score}</Descriptions.Item>
          <Descriptions.Item label="当前状态">{alert.status}</Descriptions.Item>
        </Descriptions>

        <Input.TextArea
          placeholder="处置备注（忽略时必填理由）"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={3}
        />

        <Space wrap>
          <Button onClick={() => handle("acknowledge")} loading={loading}>
            确认
          </Button>
          <Button onClick={() => handle("ignore")} loading={loading}>
            忽略
          </Button>
          <Button onClick={() => handle("close")} loading={loading}>
            关闭
          </Button>
        </Space>

        <Space wrap>
          <Button type="primary" onClick={createScar} loading={loading}>
            创建 SCAR
          </Button>
          <Button type="primary" onClick={createCapa} loading={loading}>
            创建 CAPA
          </Button>
        </Space>
      </Space>
    </Drawer>
  );
};

export default HandleAlertDrawer;

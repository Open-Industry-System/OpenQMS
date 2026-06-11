import React, { useState, useEffect } from "react";
import { Row, Col, Card, Statistic, Button, Space } from "antd";
import { WarningOutlined, AlertOutlined, ReloadOutlined } from "@ant-design/icons";
import { message } from "antd";
import RiskMatrixChart from "./components/RiskMatrixChart";
import AlertTable from "./components/AlertTable";
import { riskAlertApi } from "../../api/supplierRisk";
import { useProductLineStore } from "../../store/productLineStore";
import type { RiskDashboard } from "../../types";

const SupplierRiskPage: React.FC = () => {
  const [dashboard, setDashboard] = useState<RiskDashboard | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const selected = useProductLineStore((s) => s.selected);

  const fetchDashboard = async () => {
    try {
      const res = await riskAlertApi.dashboard(selected ? { product_line_code: selected } : undefined);
      setDashboard(res.data);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    fetchDashboard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  const evaluateAll = async () => {
    setEvaluating(true);
    try {
      await riskAlertApi.evaluateAll();
      message.success("全量评估完成");
      fetchDashboard();
    } catch {
      message.error("评估失败");
    } finally {
      setEvaluating(false);
    }
  };

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<ReloadOutlined />} loading={evaluating} onClick={evaluateAll}>
          立即评估全部
        </Button>
      </Space>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="高风险供应商"
              value={dashboard?.high_risk_count ?? 0}
              prefix={<WarningOutlined />}
              valueStyle={{ color: "#fa8c16" }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="极高风险"
              value={dashboard?.critical_risk_count ?? 0}
              prefix={<AlertOutlined />}
              valueStyle={{ color: "#f5222d" }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="开放预警" value={dashboard?.open_alert_count ?? 0} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="平均风险分" value={dashboard?.avg_risk_score ?? 0} precision={1} />
          </Card>
        </Col>
      </Row>

      <Card title="风险矩阵（质量 vs 交付）" style={{ marginBottom: 24 }}>
        {dashboard && dashboard.supplier_risk_points.length > 0 ? (
          <RiskMatrixChart data={dashboard.supplier_risk_points} />
        ) : (
          <div style={{ textAlign: "center", padding: 48, color: "#999" }}>暂无数据</div>
        )}
      </Card>

      <Card title="预警列表">
        <AlertTable productLineCode={selected} onRefresh={fetchDashboard} />
      </Card>
    </div>
  );
};

export default SupplierRiskPage;

import React, { useState, useEffect } from "react";
import { Table, Switch, InputNumber, message } from "antd";
import { useTranslation } from "react-i18next";
import type { SupplierRiskConfig } from "../../../types";
import { riskAlertApi } from "../../../api/supplierRisk";
import { StatusBadge } from "../../../components/design";

const RuleConfigTable: React.FC = () => {
  const { t } = useTranslation("supplierRisk");
  const [data, setData] = useState<SupplierRiskConfig[]>([]);
  const [loading, setLoading] = useState(false);

  const CATEGORY_LABELS: Record<string, string> = {
    quality: t("ruleConfig.categories.quality"),
    delivery: t("ruleConfig.categories.delivery"),
    compliance: t("ruleConfig.categories.compliance"),
  };

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await riskAlertApi.listConfigs();
      setData(res.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const toggleEnabled = async (record: SupplierRiskConfig, enabled: boolean) => {
    try {
      await riskAlertApi.updateConfig(record.config_id, { enabled });
      message.success(t("ruleConfig.messages.updateSuccess"));
      fetchData();
    } catch {
      message.error(t("ruleConfig.messages.updateFailed"));
    }
  };

  const updateWeight = async (record: SupplierRiskConfig, weight: number) => {
    try {
      await riskAlertApi.updateConfig(record.config_id, { weight });
      message.success(t("ruleConfig.messages.weightUpdated"));
    } catch {
      message.error(t("ruleConfig.messages.updateFailed"));
    }
  };

  const columns = [
    { title: t("ruleConfig.columns.rule"), dataIndex: "rule_id", width: 80 },
    {
      title: t("ruleConfig.columns.category"),
      dataIndex: "category",
      width: 100,
      render: (v: string) => (
        <StatusBadge status={v}>{CATEGORY_LABELS[v] || v}</StatusBadge>
      ),
    },
    {
      title: t("ruleConfig.columns.enabled"),
      dataIndex: "enabled",
      width: 80,
      render: (v: boolean, record: SupplierRiskConfig) => (
        <Switch checked={v} onChange={(val) => toggleEnabled(record, val)} />
      ),
    },
    {
      title: t("ruleConfig.columns.weight"),
      dataIndex: "weight",
      width: 100,
      render: (v: number, record: SupplierRiskConfig) => (
        <InputNumber
          min={0}
          max={100}
          value={v}
          onChange={(val) => val !== null && updateWeight(record, val)}
          size="small"
          style={{ width: 70 }}
        />
      ),
    },
    {
      title: t("ruleConfig.columns.threshold"),
      dataIndex: "thresholds",
      render: (v: Record<string, unknown>) => (
        <span style={{ fontSize: 12 }}>{JSON.stringify(v)}</span>
      ),
    },
  ];

  return (
    <Table
      rowKey="config_id"
      columns={columns}
      dataSource={data}
      loading={loading}
      pagination={false}
      size="small"
      className="qf-table"
    />
  );
};

export default RuleConfigTable;

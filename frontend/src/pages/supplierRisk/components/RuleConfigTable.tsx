import React, { useState, useEffect } from "react";
import { Table, Switch, InputNumber, message, Tag } from "antd";
import type { SupplierRiskConfig } from "../../../types";
import { riskAlertApi } from "../../../api/supplierRisk";

const CATEGORY_LABELS: Record<string, string> = {
  quality: "质量",
  delivery: "交付",
  compliance: "合规",
};

const CATEGORY_COLORS: Record<string, string> = {
  quality: "blue",
  delivery: "green",
  compliance: "purple",
};

const RuleConfigTable: React.FC = () => {
  const [data, setData] = useState<SupplierRiskConfig[]>([]);
  const [loading, setLoading] = useState(false);

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
      message.success("已更新");
      fetchData();
    } catch {
      message.error("更新失败");
    }
  };

  const updateWeight = async (record: SupplierRiskConfig, weight: number) => {
    try {
      await riskAlertApi.updateConfig(record.config_id, { weight });
      message.success("权重已更新");
    } catch {
      message.error("更新失败");
    }
  };

  const columns = [
    { title: "规则", dataIndex: "rule_id", width: 80 },
    {
      title: "类别",
      dataIndex: "category",
      width: 100,
      render: (v: string) => (
        <Tag color={CATEGORY_COLORS[v]}>{CATEGORY_LABELS[v] || v}</Tag>
      ),
    },
    {
      title: "启用",
      dataIndex: "enabled",
      width: 80,
      render: (v: boolean, record: SupplierRiskConfig) => (
        <Switch checked={v} onChange={(val) => toggleEnabled(record, val)} />
      ),
    },
    {
      title: "权重",
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
      title: "阈值",
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
    />
  );
};

export default RuleConfigTable;

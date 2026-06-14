import React, { useState, useEffect } from "react";
import { Table, Button, Space, Select } from "antd";
import type { SupplierRiskAlert } from "../../../types";
import { riskAlertApi } from "../../../api/supplierRisk";
import HandleAlertDrawer from "./HandleAlertDrawer";
import { StatusBadge } from "../../../components/design";

const STATUS_LABELS: Record<string, string> = {
  open: "开放",
  acknowledged: "已确认",
  action_taken: "已处置",
  ignored: "已忽略",
  closed: "已关闭",
};

const RISK_LABELS: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "极高",
};

interface Props {
  productLineCode?: string | null;
  onRefresh?: () => void;
}

const AlertTable: React.FC<Props> = ({ productLineCode, onRefresh }) => {
  const [data, setData] = useState<SupplierRiskAlert[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [riskFilter, setRiskFilter] = useState<string | undefined>(undefined);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [selectedAlert, setSelectedAlert] = useState<SupplierRiskAlert | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await riskAlertApi.list({
        page,
        page_size: 20,
        product_line_code: productLineCode ?? undefined,
        risk_level: riskFilter,
        status: statusFilter,
      });
      setData(res.data.items);
      setTotal(res.data.total);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, productLineCode, riskFilter, statusFilter]);

  const columns = [
    { title: "供应商编号", dataIndex: "supplier_no" },
    { title: "供应商名称", dataIndex: "supplier_name" },
    {
      title: "风险等级",
      dataIndex: "risk_level",
      render: (v: string) => (
        <StatusBadge status={v}>{RISK_LABELS[v] || v}</StatusBadge>
      ),
    },
    { title: "风险分", dataIndex: "risk_score", sorter: true },
    { title: "状态", dataIndex: "status", render: (v: string) => <StatusBadge status={v}>{STATUS_LABELS[v] || v}</StatusBadge> },
    { title: "快照日期", dataIndex: "snapshot_date" },
    {
      title: "操作",
      render: (_: unknown, record: SupplierRiskAlert) => (
        <Button
          size="small"
          onClick={() => {
            setSelectedAlert(record);
            setDrawerOpen(true);
          }}
        >
          处置
        </Button>
      ),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Select
          allowClear
          placeholder="风险等级"
          style={{ width: 120 }}
          value={riskFilter}
          onChange={(v) => {
            setRiskFilter(v);
            setPage(1);
          }}
          options={[
            { value: "low", label: "低" },
            { value: "medium", label: "中" },
            { value: "high", label: "高" },
            { value: "critical", label: "极高" },
          ]}
        />
        <Select
          allowClear
          placeholder="状态"
          style={{ width: 120 }}
          value={statusFilter}
          onChange={(v) => {
            setStatusFilter(v);
            setPage(1);
          }}
          options={[
            { value: "open", label: "开放" },
            { value: "acknowledged", label: "已确认" },
            { value: "action_taken", label: "已处置" },
            { value: "ignored", label: "已忽略" },
            { value: "closed", label: "已关闭" },
          ]}
        />
      </Space>
      <Table
        rowKey="alert_id"
        columns={columns}
        dataSource={data}
        loading={loading}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: setPage,
          showTotal: (t) => `共 ${t} 条`,
        }}
        className="qf-table"
      />
      <HandleAlertDrawer
        alert={selectedAlert}
        open={drawerOpen}
        onClose={() => {
          setDrawerOpen(false);
          fetchData();
          onRefresh?.();
        }}
      />
    </>
  );
};

export default AlertTable;

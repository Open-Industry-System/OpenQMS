import React, { useState, useEffect } from "react";
import { Table, Button, Space, Select } from "antd";
import { useTranslation } from "react-i18next";
import type { SupplierRiskAlert } from "../../../types";
import { riskAlertApi } from "../../../api/supplierRisk";
import HandleAlertDrawer from "./HandleAlertDrawer";
import { StatusBadge } from "../../../components/design";

interface Props {
  productLineCode?: string | null;
  onRefresh?: () => void;
}

const AlertTable: React.FC<Props> = ({ productLineCode, onRefresh }) => {
  const { t } = useTranslation("supplierRisk");
  const { t: tc } = useTranslation("common");
  const [data, setData] = useState<SupplierRiskAlert[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [riskFilter, setRiskFilter] = useState<string | undefined>(undefined);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [selectedAlert, setSelectedAlert] = useState<SupplierRiskAlert | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const STATUS_LABELS: Record<string, string> = {
    open: t("alert.statuses.open"),
    acknowledged: t("alert.statuses.acknowledged"),
    action_taken: t("alert.statuses.action_taken"),
    ignored: t("alert.statuses.ignored"),
    closed: t("alert.statuses.closed"),
  };

  const RISK_LABELS: Record<string, string> = {
    low: t("alert.riskLevels.low"),
    medium: t("alert.riskLevels.medium"),
    high: t("alert.riskLevels.high"),
    critical: t("alert.riskLevels.critical"),
  };

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
    { title: t("alert.columns.supplierNo"), dataIndex: "supplier_no" },
    { title: t("alert.columns.supplierName"), dataIndex: "supplier_name" },
    {
      title: t("alert.columns.riskLevel"),
      dataIndex: "risk_level",
      render: (v: string) => (
        <StatusBadge status={v}>{RISK_LABELS[v] || v}</StatusBadge>
      ),
    },
    { title: t("alert.columns.riskScore"), dataIndex: "risk_score", sorter: true },
    { title: t("alert.columns.status"), dataIndex: "status", render: (v: string) => <StatusBadge status={v}>{STATUS_LABELS[v] || v}</StatusBadge> },
    { title: t("alert.columns.snapshotDate"), dataIndex: "snapshot_date" },
    {
      title: tc("table.operations"),
      render: (_: unknown, record: SupplierRiskAlert) => (
        <Button
          size="small"
          onClick={() => {
            setSelectedAlert(record);
            setDrawerOpen(true);
          }}
        >
          {t("alert.handle")}
        </Button>
      ),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Select
          allowClear
          placeholder={t("alert.placeholder.riskLevel")}
          style={{ width: 120 }}
          value={riskFilter}
          onChange={(v) => {
            setRiskFilter(v);
            setPage(1);
          }}
          options={[
            { value: "low", label: RISK_LABELS.low },
            { value: "medium", label: RISK_LABELS.medium },
            { value: "high", label: RISK_LABELS.high },
            { value: "critical", label: RISK_LABELS.critical },
          ]}
        />
        <Select
          allowClear
          placeholder={t("alert.placeholder.status")}
          style={{ width: 120 }}
          value={statusFilter}
          onChange={(v) => {
            setStatusFilter(v);
            setPage(1);
          }}
          options={[
            { value: "open", label: STATUS_LABELS.open },
            { value: "acknowledged", label: STATUS_LABELS.acknowledged },
            { value: "action_taken", label: STATUS_LABELS.action_taken },
            { value: "ignored", label: STATUS_LABELS.ignored },
            { value: "closed", label: STATUS_LABELS.closed },
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
          showTotal: (t) => tc("pagination.total", { total: t }),
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

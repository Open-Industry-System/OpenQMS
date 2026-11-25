import { useEffect, useState, useMemo } from "react";
import {
  Table, Select, App,
} from "antd";
import { useTranslation } from "react-i18next";
import { listScrapRecords } from "../../api/mes";
import { useProductLineStore } from "../../store/productLineStore";
import type { MESScrapRecord } from "../../types/mes";
import { PageShell, DataCard, StatusBadge } from "../../components/design";
import { formatDateTime } from "../../utils/dateTime";

const defectVariant: Record<string, string> = {
  scrap: "error",
  rework: "warning",
  reject: "error",
};

export default function MESScrapPage() {
  const { t } = useTranslation("mes");
  const { message } = App.useApp();
  const [data, setData] = useState<MESScrapRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [defectFilter, setDefectFilter] = useState<string>("");
  const productLine = useProductLineStore((s) => s.selected);

  const defectLabels = useMemo(() => ({
    scrap: t("scrap.defectType.scrap"),
    rework: t("scrap.defectType.rework"),
    reject: t("scrap.defectType.reject"),
  }), [t]);

  const defectFilterOptions = useMemo(() => [
    { value: "scrap", label: t("scrap.defectType.scrap") },
    { value: "rework", label: t("scrap.defectType.rework") },
    { value: "reject", label: t("scrap.defectType.reject") },
  ], [t]);

  const fetchData = (p: number = page, currentDefectType?: string, plCode?: string | null) => {
    setLoading(true);
    listScrapRecords(p, 20, plCode || undefined, currentDefectType || undefined)
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error(t("scrap.messages.loadFailed")))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData(1, defectFilter || undefined, productLine);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defectFilter, productLine]);

  const handleDefectChange = (value: string) => {
    setDefectFilter(value);
    setPage(1);
  };

  const columns = useMemo(() => [
    { title: t("scrap.columns.externalId"), dataIndex: "external_id", key: "external_id", width: 140 },
    {
      title: t("scrap.columns.defectType"),
      dataIndex: "defect_type",
      key: "defect_type",
      width: 100,
      render: (dt: string) => (
        <StatusBadge status={defectVariant[dt] || dt}>
          {defectLabels[dt as keyof typeof defectLabels] || dt}
        </StatusBadge>
      ),
    },
    {
      title: t("scrap.columns.defectCategory"),
      dataIndex: "defect_category",
      key: "defect_category",
      width: 120,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("scrap.columns.defectQty"),
      dataIndex: "defect_qty",
      key: "defect_qty",
      width: 100,
    },
    {
      title: t("scrap.columns.totalQty"),
      dataIndex: "total_qty",
      key: "total_qty",
      width: 100,
    },
    {
      title: t("scrap.columns.defectRate"),
      key: "defect_rate",
      width: 110,
      render: (_: unknown, record: MESScrapRecord) => {
        const rate = record.total_qty > 0
          ? ((record.defect_qty / record.total_qty) * 100).toFixed(2)
          : "0.00";
        return `${rate}%`;
      },
    },
    {
      title: t("scrap.columns.defectDescription"),
      dataIndex: "defect_description",
      key: "defect_description",
      ellipsis: true,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("scrap.columns.recordedAt"),
      dataIndex: "recorded_at",
      key: "recorded_at",
      width: 170,
      render: (v: string) => formatDateTime(v),
    },
  ], [t, defectLabels]);

  return (
    <PageShell
      title={t("scrap.title")}
      actions={
        <Select
          placeholder={t("scrap.filterPlaceholder")}
          allowClear
          style={{ width: 140 }}
          value={defectFilter || undefined}
          onChange={handleDefectChange}
          options={defectFilterOptions}
        />
      }
    >
      <DataCard title={t("scrap.title")}>
        <Table
          columns={columns}
          dataSource={data}
          rowKey="scrap_id"
          loading={loading}
          pagination={{
            current: page,
            total,
            pageSize: 20,
            onChange: (p) => {
              setPage(p);
              fetchData(p, defectFilter || undefined, productLine);
            },
          }}
          className="qf-table"
        />
      </DataCard>
    </PageShell>
  );
}
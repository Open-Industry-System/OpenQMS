import { useEffect, useState } from "react";
import { Row, Col, Table, Tag, DatePicker, Button, Spin } from "antd";
import { DownloadOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { Line, Pie } from "@ant-design/charts";
import { DataCard, StatusBadge } from "../../../components/design";
import { getQualityDashboard, exportQualityDashboard } from "../../../api/supplier";
import { useProductLineStore } from "../../../store/productLineStore";
import type { QualityDashboardResponse } from "../../../types";

const { RangePicker } = DatePicker;

export default function DashboardView() {
  const { t } = useTranslation("supplier");
  const { t: tc } = useTranslation("common");
  const [data, setData] = useState<QualityDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [dateRange, setDateRange] = useState<[string, string] | null>(null);
  const productLine = useProductLineStore((s) => s.selected);

  useEffect(() => {
    loadDashboard();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine, dateRange]);

  const loadDashboard = async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (dateRange) {
        params.start_date = dateRange[0];
        params.end_date = dateRange[1];
      }
      if (productLine) {
        params.product_line_code = productLine;
      }
      const result = await getQualityDashboard(params);
      setData(result);
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async () => {
    const params: Record<string, string> = {};
    if (dateRange) {
      params.start_date = dateRange[0];
      params.end_date = dateRange[1];
    }
    if (productLine) {
      params.product_line_code = productLine;
    }
    await exportQualityDashboard(params);
  };

  if (loading || !data) {
    return (
      <div style={{ textAlign: "center", padding: "100px 0" }}>
        <Spin size="large" />
      </div>
    );
  }

  const ppmTrendConfig = {
    data: data.ppm_trend,
    xField: "month",
    yField: "ppm",
    point: { size: 4 },
    smooth: true,
  };

  const gradeDistConfig = {
    data: [
      { type: "A", value: data.grade_distribution.A },
      { type: "B", value: data.grade_distribution.B },
      { type: "C", value: data.grade_distribution.C },
      { type: "D", value: data.grade_distribution.D },
    ],
    angleField: "value",
    colorField: "type",
    color: ["#52c41a", "#1677ff", "#faad14", "#ff4d4f"],
    label: { offset: "-30%" },
  };

  const rankingColumns = [
    { title: t("quality.column.rank"), width: 60, render: (_: unknown, __: unknown, idx: number) => idx + 1 },
    { title: t("list.column.supplierNo"), dataIndex: "supplier_no", key: "supplier_no" },
    { title: t("quality.column.supplierName"), dataIndex: "name", key: "name" },
    {
      title: t("quality.column.grade"),
      dataIndex: "grade",
      key: "grade",
      render: (grade: string) => {
        const colors: Record<string, string> = { A: "#52c41a", B: "#1677ff", C: "#faad14", D: "#ff4d4f" };
        return <Tag color={colors[grade]}>{grade}</Tag>;
      },
    },
    {
      title: "PPM",
      dataIndex: "ppm",
      key: "ppm",
      render: (ppm: number) => ppm.toLocaleString(undefined, { maximumFractionDigits: 0 }),
    },
    {
      title: t("quality.column.batchAcceptanceRate"),
      dataIndex: "batch_acceptance_rate",
      key: "batch_acceptance_rate",
      render: (rate: number) => `${(rate * 100).toFixed(1)}%`,
    },
    {
      title: t("quality.column.deliveryRate"),
      dataIndex: "delivery_rate",
      key: "delivery_rate",
      render: (rate: number) => `${(rate * 100).toFixed(1)}%`,
    },
    {
      title: t("quality.column.openScar"),
      dataIndex: "open_scar_count",
      key: "open_scar_count",
      render: (count: number) => <StatusBadge status={count > 0 ? "open" : "closed"}>{count}</StatusBadge>,
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between" }}>
        <RangePicker
          onChange={(dates) => {
            if (dates && dates[0] && dates[1]) {
              setDateRange([dates[0].format("YYYY-MM-DD"), dates[1].format("YYYY-MM-DD")]);
            } else {
              setDateRange(null);
            }
          }}
        />
        <Button icon={<DownloadOutlined />} onClick={handleExport}>
          {t("quality.exportReport")}
        </Button>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <DataCard title={null}>
            <div style={{ fontSize: 14, color: "#888" }}>{t("quality.kpi.totalSuppliers")}</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: "#1677ff" }}>
              {data.kpi.total_suppliers}
            </div>
          </DataCard>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <DataCard title={null}>
            <div style={{ fontSize: 14, color: "#888" }}>{t("quality.kpi.overallPpm")}</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: "#52c41a" }}>
              {data.kpi.overall_ppm.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </div>
          </DataCard>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <DataCard title={null}>
            <div style={{ fontSize: 14, color: "#888" }}>{t("quality.kpi.batchAcceptanceRate")}</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: "#52c41a" }}>
              {(data.kpi.batch_acceptance_rate * 100).toFixed(1)}%
            </div>
          </DataCard>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <DataCard title={null}>
            <div style={{ fontSize: 14, color: "#888" }}>{t("quality.kpi.openScar")}</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: "#faad14" }}>
              {data.kpi.open_scar_count}
            </div>
          </DataCard>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <DataCard title={t("quality.charts.ppmTrend")}>
            {data.ppm_trend.length > 0 ? (
              <Line {...ppmTrendConfig} />
            ) : (
              <div style={{ textAlign: "center", padding: "60px 0", color: "#888" }}>
                {tc("empty.data")}
              </div>
            )}
          </DataCard>
        </Col>
        <Col xs={24} lg={12}>
          <DataCard title={t("quality.charts.gradeDistribution")}>
            {Object.values(data.grade_distribution).some((v) => v > 0) ? (
              <Pie {...gradeDistConfig} />
            ) : (
              <div style={{ textAlign: "center", padding: "60px 0", color: "#888" }}>
                {tc("empty.data")}
              </div>
            )}
          </DataCard>
        </Col>
      </Row>

      <DataCard title={t("quality.rankingTitle")} style={{ marginTop: 16 }}>
        <Table
          className="qf-table"
          dataSource={data.ranking}
          columns={rankingColumns}
          rowKey="supplier_id"
          pagination={false}
          size="small"
        />
      </DataCard>
    </div>
  );
}

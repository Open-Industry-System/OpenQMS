import { useEffect, useState } from "react";
import { Row, Col, Card, Table, Tag, DatePicker, Button, Spin } from "antd";
import { DownloadOutlined } from "@ant-design/icons";
import { Line, Pie } from "@ant-design/charts";
import { getQualityDashboard, exportQualityDashboard } from "../../../api/supplier";
import { useProductLineStore } from "../../../store/productLineStore";
import type { QualityDashboardResponse } from "../../../types";

const { RangePicker } = DatePicker;

export default function DashboardView() {
  const [data, setData] = useState<QualityDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [dateRange, setDateRange] = useState<[string, string] | null>(null);
  const productLine = useProductLineStore((s) => s.selected);

  useEffect(() => {
    loadDashboard();
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
    { title: "排名", width: 60, render: (_: unknown, __: unknown, idx: number) => idx + 1 },
    { title: "供应商编号", dataIndex: "supplier_no", key: "supplier_no" },
    { title: "供应商名称", dataIndex: "name", key: "name" },
    {
      title: "评级",
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
      title: "批次合格率",
      dataIndex: "batch_acceptance_rate",
      key: "batch_acceptance_rate",
      render: (rate: number) => `${(rate * 100).toFixed(1)}%`,
    },
    {
      title: "交付准时率",
      dataIndex: "delivery_rate",
      key: "delivery_rate",
      render: (rate: number) => `${(rate * 100).toFixed(1)}%`,
    },
    {
      title: "未关闭SCAR",
      dataIndex: "open_scar_count",
      key: "open_scar_count",
      render: (count: number) => <Tag color={count > 0 ? "error" : "success"}>{count}</Tag>,
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
          导出报表
        </Button>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <div style={{ fontSize: 14, color: "#888" }}>供应商总数</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: "#1677ff" }}>
              {data.kpi.total_suppliers}
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <div style={{ fontSize: 14, color: "#888" }}>整体PPM</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: "#52c41a" }}>
              {data.kpi.overall_ppm.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <div style={{ fontSize: 14, color: "#888" }}>批次合格率</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: "#52c41a" }}>
              {(data.kpi.batch_acceptance_rate * 100).toFixed(1)}%
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <div style={{ fontSize: 14, color: "#888" }}>未关闭SCAR</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: "#faad14" }}>
              {data.kpi.open_scar_count}
            </div>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card title="PPM 趋势">
            {data.ppm_trend.length > 0 ? (
              <Line {...ppmTrendConfig} />
            ) : (
              <div style={{ textAlign: "center", padding: "60px 0", color: "#888" }}>
                暂无数据
              </div>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="评级分布">
            {Object.values(data.grade_distribution).some((v) => v > 0) ? (
              <Pie {...gradeDistConfig} />
            ) : (
              <div style={{ textAlign: "center", padding: "60px 0", color: "#888" }}>
                暂无数据
              </div>
            )}
          </Card>
        </Col>
      </Row>

      <Card title="供应商排名 (Top 20)" style={{ marginTop: 16 }}>
        <Table
          dataSource={data.ranking}
          columns={rankingColumns}
          rowKey="supplier_id"
          pagination={false}
          size="small"
        />
      </Card>
    </div>
  );
}

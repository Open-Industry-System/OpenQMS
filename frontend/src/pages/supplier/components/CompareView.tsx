import { useState } from "react";
import { Select, Table, Tag, Row, Col, Empty, Spin } from "antd";
import { Radar } from "@ant-design/charts";
import { DataCard, StatusBadge } from "../../../components/design";
import { getSupplierCompare, listSuppliers } from "../../../api/supplier";
import type { SupplierCompareResponse, Supplier } from "../../../types";

export default function CompareView() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [compareData, setCompareData] = useState<SupplierCompareResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const loadSuppliers = async (search: string) => {
    const result = await listSuppliers({ search, page_size: 20 });
    setSuppliers(result.items);
  };

  const handleCompare = async () => {
    if (selectedIds.length < 2) return;
    setLoading(true);
    try {
      const result = await getSupplierCompare(selectedIds);
      setCompareData(result);
    } finally {
      setLoading(false);
    }
  };

  const gradeColors: Record<string, string> = { A: "#52c41a", B: "#1677ff", C: "#faad14", D: "#ff4d4f" };

  const radarConfig = compareData
    ? {
        data: compareData.suppliers.flatMap((s) => [
          { item: "质量", user: s.name, value: s.quality_score },
          { item: "交付", user: s.name, value: s.delivery_score },
          { item: "服务", user: s.name, value: s.service_score },
          { item: "PPM", user: s.name, value: 100 - Math.min(s.ppm / 200, 100) },
          { item: "SCAR", user: s.name, value: 100 - s.open_scar_count * 10 },
        ]),
        xField: "item",
        yField: "value",
        seriesField: "user",
        meta: { value: { alias: "分数", min: 0, max: 100 } },
      }
    : null;

  const compareColumns = [
    { title: "指标", dataIndex: "metric" },
    ...selectedIds.map((id) => {
      const s = compareData?.suppliers.find((x) => x.supplier_id === id);
      return {
        title: s?.name || id,
        render: (_: unknown, record: Record<string, React.ReactNode>) => record[id],
      };
    }),
  ];

  const compareTableData = compareData
    ? [
        {
          key: "grade",
          metric: "评级",
          ...Object.fromEntries(
            compareData.suppliers.map((s) => [s.supplier_id, <Tag color={gradeColors[s.grade]} key={s.supplier_id}>{s.grade}</Tag>])
          ),
        },
        {
          key: "ppm",
          metric: "PPM",
          ...Object.fromEntries(compareData.suppliers.map((s) => [s.supplier_id, s.ppm.toFixed(0)])),
        },
        {
          key: "acceptance",
          metric: "批次合格率",
          ...Object.fromEntries(
            compareData.suppliers.map((s) => [s.supplier_id, `${(s.batch_acceptance_rate * 100).toFixed(1)}%`])
          ),
        },
        {
          key: "delivery",
          metric: "交付准时率",
          ...Object.fromEntries(
            compareData.suppliers.map((s) => [s.supplier_id, `${(s.delivery_rate * 100).toFixed(1)}%`])
          ),
        },
        {
          key: "scar",
          metric: "开放SCAR",
          ...Object.fromEntries(
            compareData.suppliers.map((s) => [
              s.supplier_id,
              <StatusBadge status={s.open_scar_count > 0 ? "open" : "closed"} key={s.supplier_id}>{s.open_scar_count}</StatusBadge>,
            ])
          ),
        },
      ]
    : [];

  return (
    <div>
      <DataCard style={{ marginBottom: 16 }} title={null}>
        <Row gutter={16} align="middle">
          <Col flex="auto">
            <Select
              mode="multiple"
              style={{ width: "100%" }}
              placeholder="选择2-4家供应商进行对比"
              maxTagCount={4}
              filterOption={false}
              onSearch={loadSuppliers}
              onChange={(values: string[]) => {
                setSelectedIds(values);
                if (values.length >= 2) {
                  setTimeout(handleCompare, 100);
                } else {
                  setCompareData(null);
                }
              }}
              options={suppliers.map((s) => ({
                label: `${s.supplier_no} - ${s.name}`,
                value: s.supplier_id,
              }))}
            />
          </Col>
        </Row>
      </DataCard>

      {loading ? (
        <div style={{ textAlign: "center", padding: "60px 0" }}><Spin size="large" /></div>
      ) : compareData ? (
        <Row gutter={16}>
          <Col span={12}>
            <DataCard title="雷达图对比">
              <Radar {...radarConfig!} />
            </DataCard>
          </Col>
          <Col span={12}>
            <DataCard title="指标明细对比">
              <Table
                className="qf-table"
                dataSource={compareTableData}
                columns={compareColumns}
                pagination={false}
                size="small"
              />
            </DataCard>
          </Col>
        </Row>
      ) : (
        <Empty description="请选择至少2家供应商" />
      )}
    </div>
  );
}

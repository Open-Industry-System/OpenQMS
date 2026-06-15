import { useState } from "react";
import { Card, Select, Table, Tag, Row, Col, Empty, Spin } from "antd";
import { useTranslation } from "react-i18next";
import { Radar } from "@ant-design/charts";
import { getSupplierCompare, listSuppliers } from "../../../api/supplier";
import type { SupplierCompareResponse, Supplier } from "../../../types";

export default function CompareView() {
  const { t } = useTranslation("supplier");
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
          { item: t("quality.column.quality"), user: s.name, value: s.quality_score },
          { item: t("quality.column.delivery"), user: s.name, value: s.delivery_score },
          { item: t("quality.column.service"), user: s.name, value: s.service_score },
          { item: "PPM", user: s.name, value: 100 - Math.min(s.ppm / 200, 100) },
          { item: "SCAR", user: s.name, value: 100 - s.open_scar_count * 10 },
        ]),
        xField: "item",
        yField: "value",
        seriesField: "user",
        meta: { value: { alias: t("quality.column.score"), min: 0, max: 100 } },
      }
    : null;

  const compareColumns = [
    { title: t("quality.compare.metric"), dataIndex: "metric" },
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
          metric: t("quality.column.grade"),
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
          metric: t("quality.column.batchAcceptanceRate"),
          ...Object.fromEntries(
            compareData.suppliers.map((s) => [s.supplier_id, `${(s.batch_acceptance_rate * 100).toFixed(1)}%`])
          ),
        },
        {
          key: "delivery",
          metric: t("quality.column.deliveryRate"),
          ...Object.fromEntries(
            compareData.suppliers.map((s) => [s.supplier_id, `${(s.delivery_rate * 100).toFixed(1)}%`])
          ),
        },
        {
          key: "scar",
          metric: t("quality.column.openScar"),
          ...Object.fromEntries(
            compareData.suppliers.map((s) => [
              s.supplier_id,
              <Tag color={s.open_scar_count > 0 ? "error" : "success"} key={s.supplier_id}>{s.open_scar_count}</Tag>,
            ])
          ),
        },
      ]
    : [];

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <Row gutter={16} align="middle">
          <Col flex="auto">
            <Select
              mode="multiple"
              style={{ width: "100%" }}
              placeholder={t("quality.compare.placeholder")}
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
      </Card>

      {loading ? (
        <div style={{ textAlign: "center", padding: "60px 0" }}><Spin size="large" /></div>
      ) : compareData ? (
        <Row gutter={16}>
          <Col span={12}>
            <Card title={t("quality.compare.radarTitle")}>
              <Radar {...radarConfig!} />
            </Card>
          </Col>
          <Col span={12}>
            <Card title={t("quality.compare.tableTitle")}>
              <Table
                dataSource={compareTableData}
                columns={compareColumns}
                pagination={false}
                size="small"
              />
            </Card>
          </Col>
        </Row>
      ) : (
        <Empty description={t("quality.compare.empty")} />
      )}
    </div>
  );
}

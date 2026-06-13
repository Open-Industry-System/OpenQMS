import { useEffect, useState } from "react";
import {
  Table, Tag, Typography, Select, App,
} from "antd";
import { listScrapRecords } from "../../api/mes";
import { useProductLineStore } from "../../store/productLineStore";
import type { MESScrapRecord } from "../../types/mes";

const { Title } = Typography;

const defectColors: Record<string, string> = {
  scrap: "red",
  rework: "orange",
  reject: "error",
};

const defectLabels: Record<string, string> = {
  scrap: "报废",
  rework: "返工",
  reject: "拒收",
};

export default function MESScrapPage() {
  const { message } = App.useApp();
  const [data, setData] = useState<MESScrapRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [defectFilter, setDefectFilter] = useState<string>("");
  const productLine = useProductLineStore((s) => s.selected);

  const fetchData = (p: number = page, currentDefectType?: string, plCode?: string | null) => {
    setLoading(true);
    listScrapRecords(p, 20, plCode || undefined, currentDefectType || undefined)
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error("加载不良记录失败"))
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

  const columns = [
    { title: "外部ID", dataIndex: "external_id", key: "external_id", width: 140 },
    {
      title: "不良类型",
      dataIndex: "defect_type",
      key: "defect_type",
      width: 100,
      render: (t: string) => (
        <Tag color={defectColors[t] || "default"}>
          {defectLabels[t] || t}
        </Tag>
      ),
    },
    {
      title: "不良分类",
      dataIndex: "defect_category",
      key: "defect_category",
      width: 120,
      render: (v: string | null) => v || "—",
    },
    {
      title: "不良数量",
      dataIndex: "defect_qty",
      key: "defect_qty",
      width: 100,
    },
    {
      title: "总数量",
      dataIndex: "total_qty",
      key: "total_qty",
      width: 100,
    },
    {
      title: "不良率 (%)",
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
      title: "不良描述",
      dataIndex: "defect_description",
      key: "defect_description",
      ellipsis: true,
      render: (v: string | null) => v || "—",
    },
    {
      title: "记录时间",
      dataIndex: "recorded_at",
      key: "recorded_at",
      width: 170,
      render: (v: string) => new Date(v).toLocaleString("zh-CN"),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16, alignItems: "center" }}>
        <Title level={4} style={{ margin: 0 }}>不良记录</Title>
        <Select
          placeholder="筛选不良类型"
          allowClear
          style={{ width: 140 }}
          value={defectFilter || undefined}
          onChange={handleDefectChange}
          options={[
            { value: "scrap", label: "报废" },
            { value: "rework", label: "返工" },
            { value: "reject", label: "拒收" },
          ]}
        />
      </div>

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
      />
    </div>
  );
}

import { useEffect, useState, useMemo } from "react";
import { Table, Button, Tag, Typography, App } from "antd";
import { ThunderboltOutlined } from "@ant-design/icons";
import { getPLMChangeOrders, triggerImpactAnalysis } from "../../api/plm";
import { useProductLineStore } from "../../store/productLineStore";
import type { PLMChangeOrder } from "../../types/plm";

const { Title } = Typography;

const statusColors: Record<string, string> = {
  open: "blue",
  in_review: "orange",
  approved: "green",
  implemented: "cyan",
  closed: "default",
  cancelled: "red",
};

const changeTypeLabels: Record<string, string> = {
  ECN: "工程变更通知",
  ECR: "工程变更请求",
  SCN: "供应商变更通知",
};

export default function PLMChangeOrdersPage() {
  const { message } = App.useApp();
  const productLine = useProductLineStore((s) => s.selected);
  const [data, setData] = useState<PLMChangeOrder[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [impactLoading, setImpactLoading] = useState<Record<string, boolean>>({});

  const fetchData = (p: number = page, plCode?: string | null) => {
    setLoading(true);
    getPLMChangeOrders({ page: p, page_size: 20, product_line_code: plCode || undefined })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error("加载变更单列表失败"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData(1, productLine);
  }, [productLine]);

  const handleImpactAnalysis = async (changeId: string) => {
    setImpactLoading((prev) => ({ ...prev, [changeId]: true }));
    try {
      await triggerImpactAnalysis(changeId);
      message.success("影响分析已触发");
    } catch {
      message.error("触发影响分析失败");
    } finally {
      setImpactLoading((prev) => ({ ...prev, [changeId]: false }));
    }
  };

  const columns = useMemo(
    () => [
      { title: "变更编号", dataIndex: "change_number", key: "change_number", width: 160 },
      { title: "标题", dataIndex: "title", key: "title", ellipsis: true },
      {
        title: "变更类型",
        dataIndex: "change_type",
        key: "change_type",
        width: 130,
        render: (t: string) => changeTypeLabels[t] || t,
      },
      {
        title: "状态",
        dataIndex: "status",
        key: "status",
        width: 100,
        render: (s: string) => <Tag color={statusColors[s] || "default"}>{s}</Tag>,
      },
      { title: "优先级", dataIndex: "priority", key: "priority", width: 80 },
      {
        title: "操作",
        key: "actions",
        width: 160,
        render: (_: unknown, record: PLMChangeOrder) => (
          <Button
            type="link"
            size="small"
            icon={<ThunderboltOutlined />}
            loading={impactLoading[record.change_id]}
            onClick={() => handleImpactAnalysis(record.change_id)}
          >
            影响分析
          </Button>
        ),
      },
    ],
    [impactLoading],
  );

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>
        PLM 变更单管理
      </Title>

      <Table
        columns={columns}
        dataSource={data}
        rowKey="change_id"
        loading={loading}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => {
            setPage(p);
            fetchData(p, productLine);
          },
        }}
      />
    </div>
  );
}

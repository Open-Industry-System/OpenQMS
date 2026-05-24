import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Table, Button, Tag, Typography, Space, Select, Popconfirm, App,
} from "antd";
import {
  PlusOutlined, FileTextOutlined, DeleteOutlined, TableOutlined,
} from "@ant-design/icons";
import { listSCs, deleteSC } from "../../api/specialCharacteristic";
import type { SpecialCharacteristic } from "../../types";
import { useAuthStore } from "../../store/authStore";

const { Title } = Typography;

const msaStatusColors: Record<string, string> = {
  PASS: "green",
  FAIL: "red",
  PENDING: "orange",
};

export default function SCListPage() {
  const { message } = App.useApp();
  const [data, setData] = useState<SpecialCharacteristic[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [scTypeFilter, setScTypeFilter] = useState<string>("");
  const [sourceTypeFilter, setSourceTypeFilter] = useState<string>("");
  const navigate = useNavigate();

  const user = useAuthStore((s) => s.user);
  const isViewer = user?.role === "viewer";

  const fetchData = (p: number = page) => {
    setLoading(true);
    listSCs({
      page: p,
      page_size: 20,
      sc_type: scTypeFilter || undefined,
      source_type: sourceTypeFilter || undefined,
    })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData();
  }, [scTypeFilter, sourceTypeFilter]);

  const handleDelete = async (id: string) => {
    try {
      await deleteSC(id);
      message.success("删除成功");
      fetchData();
    } catch {
      message.error("删除失败");
    }
  };

  const columns = [
    {
      title: "SC编号",
      dataIndex: "sc_code",
      key: "sc_code",
      width: 140,
    },
    {
      title: "名称",
      dataIndex: "sc_name",
      key: "sc_name",
      ellipsis: true,
    },
    {
      title: "类型",
      dataIndex: "sc_type",
      key: "sc_type",
      width: 80,
      render: (t: string) => (
        <Tag color={t === "CC" ? "red" : "gold"}>{t}</Tag>
      ),
    },
    {
      title: "客户符号",
      dataIndex: "customer_symbol",
      key: "customer_symbol",
      width: 100,
      render: (v: string | null) => v || "-",
    },
    {
      title: "分类",
      dataIndex: "sc_category",
      key: "sc_category",
      width: 120,
      render: (v: string | null) => v || "-",
    },
    {
      title: "来源类型",
      dataIndex: "source_type",
      key: "source_type",
      width: 100,
      render: (t: string) => (
        <Tag color={t === "DFMEA" ? "blue" : "green"}>{t}</Tag>
      ),
    },
    {
      title: "来源FMEA",
      dataIndex: "source_fmea_document_no",
      key: "source_fmea_document_no",
      width: 160,
      render: (docNo: string | null, record: SpecialCharacteristic) =>
        docNo ? (
          <Button
            type="link"
            size="small"
            onClick={() => navigate(`/fmea/${record.source_fmea_id}`)}
          >
            {docNo}
          </Button>
        ) : (
          "-"
        ),
    },
    {
      title: "MSA状态",
      dataIndex: "msa_status",
      key: "msa_status",
      width: 100,
      render: (s: string) => (
        <Tag color={msaStatusColors[s] || "default"}>{s}</Tag>
      ),
    },
    {
      title: "操作",
      key: "actions",
      width: 140,
      render: (_: unknown, record: SpecialCharacteristic) => (
        <Space>
          <Button
            type="link"
            icon={<FileTextOutlined />}
            onClick={() => navigate(`/special-characteristics/${record.sc_id}`)}
          >
            查看
          </Button>
          {!isViewer && (
            <Popconfirm
              title="确认删除该特殊特性？"
              onConfirm={() => handleDelete(record.sc_id)}
            >
              <Button type="link" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
        }}
      >
        <Space>
          <Title level={4} style={{ margin: 0 }}>
            <TableOutlined style={{ marginRight: 8 }} />
            特殊特性清单
          </Title>
          <Select
            placeholder="类型筛选"
            allowClear
            style={{ width: 120 }}
            value={scTypeFilter || undefined}
            onChange={(v) => {
              setScTypeFilter(v || "");
              setPage(1);
              fetchData(1);
            }}
          >
            <Select.Option value="">全部</Select.Option>
            <Select.Option value="CC">CC</Select.Option>
            <Select.Option value="SC">SC</Select.Option>
          </Select>
          <Select
            placeholder="来源筛选"
            allowClear
            style={{ width: 140 }}
            value={sourceTypeFilter || undefined}
            onChange={(v) => {
              setSourceTypeFilter(v || "");
              setPage(1);
              fetchData(1);
            }}
          >
            <Select.Option value="">全部</Select.Option>
            <Select.Option value="DFMEA">DFMEA</Select.Option>
            <Select.Option value="PFMEA">PFMEA</Select.Option>
          </Select>
        </Space>
        {!isViewer && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate("/special-characteristics/new")}>
            新建特殊特性
          </Button>
        )}
      </div>

      <Table
        columns={columns}
        dataSource={data}
        rowKey="sc_id"
        loading={loading}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => {
            setPage(p);
            fetchData(p);
          },
        }}
      />
    </div>
  );
}

import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Table, Button, Tag, Typography, Space, Select, Popconfirm, App, Switch,
} from "antd";
import {
  PlusOutlined, FileTextOutlined, DeleteOutlined, TableOutlined,
  SafetyCertificateOutlined, ExclamationCircleOutlined,
} from "@ant-design/icons";
import {
  listSCs, deleteSC, safetyConfirm, safetyDismiss,
} from "../../../api/specialCharacteristic";
import type { SpecialCharacteristic } from "../../../types";
import { useAuthStore } from "../../../store/authStore";
import { useProductLineStore } from "../../../store/productLineStore";

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
  const [searchParams] = useSearchParams();
  const [safetyRelatedOnly, setSafetyRelatedOnly] = useState(searchParams.get("safety_related_only") === "true");
  const [approvalStatusFilter, setApprovalStatusFilter] = useState<string>(searchParams.get("approval_status") || "");
  const [suggestedOnly, setSuggestedOnly] = useState(searchParams.get("suggested_only") === "true");
  const navigate = useNavigate();

  const user = useAuthStore((s) => s.user);
  const isViewer = user?.role === "viewer";
  const productLine = useProductLineStore((s) => s.selected);

  const fetchData = (p: number = page) => {
    setLoading(true);
    listSCs({
      page: p,
      page_size: 20,
      product_line: productLine || undefined,
      sc_type: scTypeFilter || undefined,
      source_type: sourceTypeFilter || undefined,
      safety_related_only: safetyRelatedOnly,
      approval_status: approvalStatusFilter || undefined,
      suggested_only: suggestedOnly,
    })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData(1);
  }, [scTypeFilter, sourceTypeFilter, productLine, safetyRelatedOnly, approvalStatusFilter, suggestedOnly]);

  const handleDelete = async (id: string) => {
    try {
      await deleteSC(id);
      message.success("删除成功");
      fetchData();
    } catch {
      message.error("删除失败");
    }
  };

  const handleSafetyConfirm = async (id: string) => {
    try {
      await safetyConfirm(id);
      message.success("已确认为安全特性");
      fetchData();
    } catch {
      message.error("确认失败");
    }
  };

  const handleSafetyDismiss = async (id: string) => {
    try {
      await safetyDismiss(id);
      message.success("已忽略安全建议");
      fetchData();
    } catch {
      message.error("忽略失败");
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
      width: 100,
      render: (t: string, record: SpecialCharacteristic) => (
        <Space>
          <Tag color={t === "CC" ? "red" : "gold"}>{t}</Tag>
          {record.is_safety_related && (
            <SafetyCertificateOutlined style={{ color: "#ff4d4f", fontSize: 16 }} />
          )}
          {record.is_safety_suggested && !record.is_safety_related && (
            <ExclamationCircleOutlined style={{ color: "#faad14", fontSize: 16 }} />
          )}
        </Space>
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
      width: 280,
      render: (_: unknown, record: SpecialCharacteristic) => (
        <Space>
          <Button
            type="link"
            icon={<FileTextOutlined />}
            onClick={() => navigate(`/special-characteristics/${record.sc_id}`)}
          >
            查看
          </Button>
          {record.is_safety_suggested && !record.is_safety_related && !isViewer && (
            <>
              <Button type="link" size="small" onClick={() => handleSafetyConfirm(record.sc_id)}>
                确认安全
              </Button>
              <Button type="link" size="small" danger onClick={() => handleSafetyDismiss(record.sc_id)}>
                忽略
              </Button>
            </>
          )}
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
            }}
          >
            <Select.Option value="">全部</Select.Option>
            <Select.Option value="DFMEA">DFMEA</Select.Option>
            <Select.Option value="PFMEA">PFMEA</Select.Option>
          </Select>
          <Switch
            checked={safetyRelatedOnly}
            onChange={(v) => { setSafetyRelatedOnly(v); setPage(1); }}
            checkedChildren="安全相关"
            unCheckedChildren="全部"
          />
          <Select
            placeholder="审批状态"
            allowClear
            style={{ width: 120 }}
            value={approvalStatusFilter || undefined}
            onChange={(v) => { setApprovalStatusFilter(v || ""); setPage(1); }}
          >
            <Select.Option value="">全部</Select.Option>
            <Select.Option value="pending">待提交</Select.Option>
            <Select.Option value="submitted">待审批</Select.Option>
            <Select.Option value="approved">已批准</Select.Option>
            <Select.Option value="rejected">已驳回</Select.Option>
          </Select>
          <Switch
            checked={suggestedOnly}
            onChange={(v) => { setSuggestedOnly(v); setPage(1); }}
            checkedChildren="仅建议"
            unCheckedChildren="全部"
          />
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

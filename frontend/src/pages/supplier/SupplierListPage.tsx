import { useState, useEffect, useCallback, useRef } from "react";
import {
  Card,
  Table,
  Button,
  Space,
  Input,
  Select,
  App,
  Row,
  Col,
  Statistic,
  Drawer,
  Popconfirm,
  Modal,
} from "antd";
import {
  PlusOutlined,
  ReloadOutlined,
  EyeOutlined,
  CheckCircleOutlined,
  StopOutlined,
  CloseCircleOutlined,
  RollbackOutlined,
  DownloadOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";
import type { Supplier, SupplierStats, SupplierExpiryAlert } from "../../types";
import {
  listSuppliers,
  getSupplierStats,
  getExpiryAlerts,
  approveSupplier,
  rejectSupplier,
  confirmApproved,
  suspendSupplier,
  reinstateSupplier,
  exportSuppliers,
  importSuppliers,
  downloadSupplierImportTemplate,
} from "../../api/supplier";
import ImportExcelDialog from "../../components/shared/ImportExcelDialog";
import PageShell from "../../components/design/PageShell";
import DataCard from "../../components/design/DataCard";
import StatusBadge from "../../components/design/StatusBadge";

const { Option } = Select;

const STATUS_MAP: Record<string, { label: string }> = {
  pending_review: { label: "待审核" },
  audit_required: { label: "需审核" },
  approved: { label: "已批准" },
  rejected: { label: "已拒绝" },
  suspended: { label: "已暂停" },
};

const statusVariant = (status: string): string => {
  if (status === "approved") return "success";
  if (status === "rejected") return "error";
  if (status === "pending_review") return "warning";
  return "info";
};

export default function SupplierListPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const _user = useAuthStore((s) => s.user);
  const { canEdit, canApprove } = usePermission();

  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const [stats, setStats] = useState<SupplierStats>({
    total_count: 0,
    pending_review_count: 0,
    approved_count: 0,
    cert_expiry_30d_count: 0,
  });

  const [filterName, setFilterName] = useState<string>("");
  const [filterStatus, setFilterStatus] = useState<string | undefined>();

  const [importOpen, setImportOpen] = useState(false);

  const [expiryDrawerOpen, setExpiryDrawerOpen] = useState(false);
  const [expiryAlerts, setExpiryAlerts] = useState<SupplierExpiryAlert[]>([]);
  const [expiryLoading, setExpiryLoading] = useState(false);

  const reasonInputRef = useRef<string>("");

  const fetchStats = useCallback(async () => {
    try {
      const s = await getSupplierStats();
      setStats(s);
    } catch {
      // ignore
    }
  }, []);

  const fetchSuppliers = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page, page_size: pageSize };
      if (filterName) params.search = filterName;
      if (filterStatus) params.status = filterStatus;
      const resp = await listSuppliers(params);
      setSuppliers(resp.items);
      setTotal(resp.total);
    } catch {
      message.error("加载供应商列表失败");
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize, filterName, filterStatus]);

  useEffect(() => {
    Promise.all([fetchSuppliers(), fetchStats()]);
  }, [fetchSuppliers, fetchStats]);

  const handleRefresh = () => {
    fetchSuppliers();
    fetchStats();
  };

  const handleQuery = () => {
    setPage(1);
    fetchSuppliers();
  };

  const handleOpenExpiryDrawer = async () => {
    setExpiryDrawerOpen(true);
    setExpiryLoading(true);
    try {
      const alerts = await getExpiryAlerts(90);
      setExpiryAlerts(alerts);
    } catch {
      message.error("加载证书到期提醒失败");
    } finally {
      setExpiryLoading(false);
    }
  };

  const handleApprove = async (id: string) => {
    try {
      await approveSupplier(id);
      message.success("已批准供应商");
      fetchSuppliers();
      fetchStats();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "操作失败");
    }
  };

  const handleReject = (id: string) => {
    reasonInputRef.current = "";
    Modal.confirm({
      title: "拒绝供应商",
      content: (
        <Input.TextArea
          rows={3}
          placeholder="请输入拒绝原因"
          onChange={(e) => {
            reasonInputRef.current = e.target.value;
          }}
        />
      ),
      okText: "确认拒绝",
      cancelText: "取消",
      okButtonProps: { danger: true },
      onOk: async () => {
        const reason = reasonInputRef.current || "不符合供应商资质要求";
        try {
          await rejectSupplier(id, reason);
          message.success("已拒绝供应商");
          fetchSuppliers();
          fetchStats();
        } catch (e: unknown) {
          const err = e as { response?: { data?: { detail?: string } } };
          message.error(err.response?.data?.detail || "操作失败");
        }
      },
    });
  };

  const handleConfirmApproved = async (id: string) => {
    try {
      await confirmApproved(id);
      message.success("已确认批准");
      fetchSuppliers();
      fetchStats();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "操作失败");
    }
  };

  const handleSuspend = (id: string) => {
    reasonInputRef.current = "";
    Modal.confirm({
      title: "暂停供应商",
      content: (
        <Input.TextArea
          rows={3}
          placeholder="请输入暂停原因"
          onChange={(e) => {
            reasonInputRef.current = e.target.value;
          }}
        />
      ),
      okText: "确认暂停",
      cancelText: "取消",
      okButtonProps: { danger: true },
      onOk: async () => {
        const reason = reasonInputRef.current || "供应商质量问题，暂停合作";
        try {
          await suspendSupplier(id, reason);
          message.success("已暂停供应商");
          fetchSuppliers();
          fetchStats();
        } catch (e: unknown) {
          const err = e as { response?: { data?: { detail?: string } } };
          message.error(err.response?.data?.detail || "操作失败");
        }
      },
    });
  };

  const handleReinstate = async (id: string) => {
    try {
      await reinstateSupplier(id);
      message.success("已恢复供应商");
      fetchSuppliers();
      fetchStats();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "操作失败");
    }
  };

  const columns = [
    {
      title: "编号",
      dataIndex: "supplier_no",
      width: 160,
      render: (no: string) => <span style={{ fontFamily: "monospace" }}>{no}</span>,
    },
    {
      title: "简称",
      dataIndex: "short_name",
      width: 140,
    },
    {
      title: "供货范围",
      dataIndex: "product_scope",
      ellipsis: true,
      render: (v: string | null) => v || "—",
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (status: string) => {
        const cfg = STATUS_MAP[status];
        return <StatusBadge status={statusVariant(status)}>{cfg?.label || status}</StatusBadge>;
      },
    },
    {
      title: "操作",
      width: 260,
      render: (_: unknown, record: Supplier) => (
        <Space size="small" wrap>
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/suppliers/${record.supplier_id}`)}
          >
            查看
          </Button>
          {canApprove('supplier') && record.status === "pending_review" && (
            <Popconfirm title="确认批准该供应商？" onConfirm={() => handleApprove(record.supplier_id)}>
              <Button size="small" type="primary" icon={<CheckCircleOutlined />}>
                批准
              </Button>
            </Popconfirm>
          )}
          {canApprove('supplier') && record.status === "pending_review" && (
            <Button
              size="small"
              danger
              icon={<CloseCircleOutlined />}
              onClick={() => handleReject(record.supplier_id)}
            >
              拒绝
            </Button>
          )}
          {canApprove('supplier') && record.status === "audit_required" && (
            <Popconfirm title="确认审核通过并批准？" onConfirm={() => handleConfirmApproved(record.supplier_id)}>
              <Button size="small" type="primary" icon={<CheckCircleOutlined />}>
                确认批准
              </Button>
            </Popconfirm>
          )}
          {canApprove('supplier') && record.status === "approved" && (
            <Button
              size="small"
              danger
              icon={<StopOutlined />}
              onClick={() => handleSuspend(record.supplier_id)}
            >
              暂停
            </Button>
          )}
          {canApprove('supplier') && record.status === "suspended" && (
            <Popconfirm title="确认恢复该供应商？" onConfirm={() => handleReinstate(record.supplier_id)}>
              <Button size="small" icon={<RollbackOutlined />}>
                恢复
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <PageShell
      title="供应商管理"
      subtitle="准入、绩效与证书到期监控"
      actions={
        <Space>
          {canEdit('supplier') && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate("/suppliers/new")}>
              新增供应商
            </Button>
          )}
          <Button icon={<DownloadOutlined />} onClick={() => exportSuppliers({
            search: filterName || undefined,
            status: filterStatus,
          })}>
            导出
          </Button>
          <Button icon={<UploadOutlined />} onClick={() => setImportOpen(true)}>
            导入
          </Button>
          <Button icon={<ReloadOutlined />} onClick={handleRefresh}>
            刷新
          </Button>
        </Space>
      }
    >
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title="供应商总数" value={stats.total_count} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="待审核"
              value={stats.pending_review_count}
              valueStyle={{ color: "#fa8c16" }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="已批准"
              value={stats.approved_count}
              valueStyle={{ color: "#52c41a" }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card
            style={{ cursor: "pointer" }}
            onClick={handleOpenExpiryDrawer}
            hoverable
          >
            <Statistic
              title="证书30天到期"
              value={stats.cert_expiry_30d_count}
              valueStyle={stats.cert_expiry_30d_count > 0 ? { color: "#ff4d4f" } : undefined}
            />
          </Card>
        </Col>
      </Row>

      <DataCard title="供应商清单">
        <Space style={{ marginBottom: 16 }} wrap>
          <Input
            placeholder="搜索名称 / 简称"
            allowClear
            style={{ width: 220 }}
            value={filterName}
            onChange={(e) => setFilterName(e.target.value)}
            onPressEnter={handleQuery}
          />
          <Select
            placeholder="状态"
            allowClear
            style={{ width: 140 }}
            value={filterStatus}
            onChange={(v) => setFilterStatus(v || undefined)}
          >
            <Option value="pending_review">待审核</Option>
            <Option value="audit_required">需审核</Option>
            <Option value="approved">已批准</Option>
            <Option value="rejected">已拒绝</Option>
            <Option value="suspended">已暂停</Option>
          </Select>
          <Button type="primary" onClick={handleQuery}>
            查询
          </Button>
        </Space>

        <Table
          className="qf-table"
          rowKey="supplier_id"
          columns={columns}
          dataSource={suppliers}
          loading={loading}
          pagination={{
            current: page,
            pageSize: pageSize,
            total: total,
            showSizeChanger: true,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps || 20);
            },
          }}
        />
      </DataCard>

      <Drawer
        title="证书到期提醒（90天内）"
        open={expiryDrawerOpen}
        onClose={() => setExpiryDrawerOpen(false)}
        width={640}
      >
        <Table
          className="qf-table"
          rowKey="cert_id"
          dataSource={expiryAlerts}
          loading={expiryLoading}
          pagination={false}
          columns={[
            {
              title: "供应商",
              dataIndex: "supplier_short_name",
              width: 120,
              render: (v: string, record: SupplierExpiryAlert) => v || record.supplier_name,
            },
            {
              title: "证书类型",
              dataIndex: "cert_type",
              width: 120,
            },
            {
              title: "证书编号",
              dataIndex: "cert_no",
              ellipsis: true,
            },
            {
              title: "到期日",
              dataIndex: "expiry_date",
              width: 110,
            },
            {
              title: "剩余天数",
              dataIndex: "days_remaining",
              width: 90,
              render: (days: number) => (
                <span style={{ color: days <= 30 ? "#ff4d4f" : undefined, fontWeight: days <= 30 ? 600 : undefined }}>
                  {days}天
                </span>
              ),
            },
          ]}
        />
      </Drawer>

      <ImportExcelDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={() => fetchSuppliers()}
        importFn={(file) => importSuppliers(file)}
        templateDownloadFn={downloadSupplierImportTemplate}
        hint="每行包含: 名称*, 简称*, 联系人, 电话, 邮箱, 地址, 供货范围"
      />
    </PageShell>
  );
}

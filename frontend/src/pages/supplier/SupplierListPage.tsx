import { useState, useEffect, useCallback, useRef } from "react";
import {
  Card,
  Table,
  Button,
  Tag,
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
import { useTranslation } from "react-i18next";
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

const { Option } = Select;

function useStatusMap(): Record<string, { label: string; color: string }> {
  const { t } = useTranslation("supplier");
  return {
    pending_review: { label: t("status.pending_review"), color: "orange" },
    audit_required: { label: t("status.audit_required"), color: "blue" },
    approved: { label: t("status.approved"), color: "green" },
    rejected: { label: t("status.rejected"), color: "red" },
    suspended: { label: t("status.suspended"), color: "default" },
  };
}

export default function SupplierListPage() {
  const { t } = useTranslation("supplier");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const navigate = useNavigate();
  const statusMap = useStatusMap();
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
      message.error(t("list.loadFailed"));
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
      message.error(t("list.loadExpiryAlertsFailed"));
    } finally {
      setExpiryLoading(false);
    }
  };

  const handleApprove = async (id: string) => {
    try {
      await approveSupplier(id);
      message.success(t("list.approveSuccess"));
      fetchSuppliers();
      fetchStats();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed"));
    }
  };

  const handleReject = (id: string) => {
    reasonInputRef.current = "";
    Modal.confirm({
      title: t("list.rejectSupplierTitle"),
      content: (
        <Input.TextArea
          rows={3}
          placeholder={t("messages.enterRejectReason")}
          onChange={(e) => {
            reasonInputRef.current = e.target.value;
          }}
        />
      ),
      okText: t("messages.confirmReject"),
      cancelText: tc("actions.cancel"),
      okButtonProps: { danger: true },
      onOk: async () => {
        const reason = reasonInputRef.current || t("list.defaultRejectReason");
        try {
          await rejectSupplier(id, reason);
          message.success(t("list.rejectSuccess"));
          fetchSuppliers();
          fetchStats();
        } catch (e: unknown) {
          const err = e as { response?: { data?: { detail?: string } } };
          message.error(err.response?.data?.detail || tc("messages.operationFailed"));
        }
      },
    });
  };

  const handleConfirmApproved = async (id: string) => {
    try {
      await confirmApproved(id);
      message.success(t("messages.confirmApproveSuccess"));
      fetchSuppliers();
      fetchStats();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed"));
    }
  };

  const handleSuspend = (id: string) => {
    reasonInputRef.current = "";
    Modal.confirm({
      title: t("list.suspendSupplierTitle"),
      content: (
        <Input.TextArea
          rows={3}
          placeholder={t("messages.enterSuspendReason")}
          onChange={(e) => {
            reasonInputRef.current = e.target.value;
          }}
        />
      ),
      okText: t("messages.confirmSuspend"),
      cancelText: tc("actions.cancel"),
      okButtonProps: { danger: true },
      onOk: async () => {
        const reason = reasonInputRef.current || t("list.defaultSuspendReason");
        try {
          await suspendSupplier(id, reason);
          message.success(t("list.suspendSuccess"));
          fetchSuppliers();
          fetchStats();
        } catch (e: unknown) {
          const err = e as { response?: { data?: { detail?: string } } };
          message.error(err.response?.data?.detail || tc("messages.operationFailed"));
        }
      },
    });
  };

  const handleReinstate = async (id: string) => {
    try {
      await reinstateSupplier(id);
      message.success(t("list.resumeSuccess"));
      fetchSuppliers();
      fetchStats();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || tc("messages.operationFailed"));
    }
  };

  const columns = [
    {
      title: t("list.column.supplierNo"),
      dataIndex: "supplier_no",
      width: 160,
      render: (no: string) => <span style={{ fontFamily: "monospace" }}>{no}</span>,
    },
    {
      title: t("detail.shortName"),
      dataIndex: "short_name",
      width: 140,
    },
    {
      title: t("detail.productScope"),
      dataIndex: "product_scope",
      ellipsis: true,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("list.column.status"),
      dataIndex: "status",
      width: 100,
      render: (status: string) => {
        const cfg = statusMap[status];
        return <Tag color={cfg?.color}>{cfg?.label || status}</Tag>;
      },
    },
    {
      title: tc("table.operations"),
      width: 260,
      render: (_: unknown, record: Supplier) => (
        <Space size="small" wrap>
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/suppliers/${record.supplier_id}`)}
          >
            {tc("actions.view")}
          </Button>
          {canApprove('supplier') && record.status === "pending_review" && (
            <Popconfirm title={t("messages.confirmApproveSupplier")} onConfirm={() => handleApprove(record.supplier_id)}>
              <Button size="small" type="primary" icon={<CheckCircleOutlined />}>
                {t("messages.approve")}
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
              {t("messages.reject")}
            </Button>
          )}
          {canApprove('supplier') && record.status === "audit_required" && (
            <Popconfirm title={t("messages.confirmAuditApprove")} onConfirm={() => handleConfirmApproved(record.supplier_id)}>
              <Button size="small" type="primary" icon={<CheckCircleOutlined />}>
                {t("messages.confirmApprove")}
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
              {t("messages.suspend")}
            </Button>
          )}
          {canApprove('supplier') && record.status === "suspended" && (
            <Popconfirm title={t("messages.confirmResumeSupplier")} onConfirm={() => handleReinstate(record.supplier_id)}>
              <Button size="small" icon={<RollbackOutlined />}>
                {t("messages.resume")}
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title={t("list.stats.total")} value={stats.total_count} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title={t("status.pending_review")}
              value={stats.pending_review_count}
              valueStyle={{ color: "#fa8c16" }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title={t("status.approved")}
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
              title={t("list.stats.certExpiry30d")}
              value={stats.cert_expiry_30d_count}
              valueStyle={stats.cert_expiry_30d_count > 0 ? { color: "#ff4d4f" } : undefined}
            />
          </Card>
        </Col>
      </Row>

      <Card
        title={t("list.title")}
        extra={
          <Space>
            {canEdit('supplier') && (
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => navigate("/suppliers/new")}
              >
                {t("list.addSupplier")}
              </Button>
            )}
            <Button icon={<DownloadOutlined />} onClick={() => exportSuppliers({
              search: filterName || undefined,
              status: filterStatus,
            })}>
              {tc("actions.export")}
            </Button>
            <Button icon={<UploadOutlined />} onClick={() => setImportOpen(true)}>
              {tc("actions.import")}
            </Button>
            <Button icon={<ReloadOutlined />} onClick={handleRefresh}>
              {tc("actions.refresh")}
            </Button>
          </Space>
        }
      >
        <Space style={{ marginBottom: 16 }} wrap>
          <Input
            placeholder={t("list.searchPlaceholder")}
            allowClear
            style={{ width: 220 }}
            value={filterName}
            onChange={(e) => setFilterName(e.target.value)}
            onPressEnter={handleQuery}
          />
          <Select
            placeholder={t("list.statusPlaceholder")}
            allowClear
            style={{ width: 140 }}
            value={filterStatus}
            onChange={(v) => setFilterStatus(v || undefined)}
          >
            <Option value="pending_review">{t("status.pending_review")}</Option>
            <Option value="audit_required">{t("status.audit_required")}</Option>
            <Option value="approved">{t("status.approved")}</Option>
            <Option value="rejected">{t("status.rejected")}</Option>
            <Option value="suspended">{t("status.suspended")}</Option>
          </Select>
          <Button type="primary" onClick={handleQuery}>
            {tc("actions.search")}
          </Button>
        </Space>

        <Table
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
      </Card>

      <Drawer
        title={t("list.expiryDrawerTitle")}
        open={expiryDrawerOpen}
        onClose={() => setExpiryDrawerOpen(false)}
        width={640}
      >
        <Table
          rowKey="cert_id"
          dataSource={expiryAlerts}
          loading={expiryLoading}
          pagination={false}
          columns={[
            {
              title: t("list.column.supplier"),
              dataIndex: "supplier_short_name",
              width: 120,
              render: (v: string, record: SupplierExpiryAlert) => v || record.supplier_name,
            },
            {
              title: t("table.certType"),
              dataIndex: "cert_type",
              width: 120,
            },
            {
              title: t("table.certNo"),
              dataIndex: "cert_no",
              ellipsis: true,
            },
            {
              title: t("table.expiryDate"),
              dataIndex: "expiry_date",
              width: 110,
            },
            {
              title: t("list.column.daysRemaining"),
              dataIndex: "days_remaining",
              width: 90,
              render: (days: number) => (
                <span style={{ color: days <= 30 ? "#ff4d4f" : undefined, fontWeight: days <= 30 ? 600 : undefined }}>
                  {t("messages.daysLeft", { days })}
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
        hint={t("list.importHint")}
      />
    </div>
  );
}

import { useEffect, useMemo, useState } from "react";
import {
  Table, Tag, Button, App, Space, Input, Tabs, Modal, Select,
} from "antd";
import { useTranslation } from "react-i18next";
import {
  fetchERPSuppliers,
  fetchERPCustomers,
  fetchERPMaterials,
  fetchERPLocations,
  linkERPSupplier,
  unlinkERPSupplier,
  linkERPCustomer,
  unlinkERPCustomer,
} from "../../api/erp";
import { listSuppliers } from "../../api/supplier";
import { listCustomers } from "../../api/customerQuality";
import { useProductLineStore } from "../../store/productLineStore";
import { PageShell, DataCard, StatusBadge } from "../../components/design";
import type {
  ERPSupplier,
  ERPCustomer,
  ERPMaterial,
  ERPLocation,
} from "../../types/erp";

// ─── Suppliers Tab ───

const linkStatusVariant = (v: string) => {
  switch (v) {
    case "linked": return "success";
    case "pending": return "warning";
    case "unlinked": return "error";
    default: return "info";
  }
};

function SuppliersTab() {
  const { t } = useTranslation("erp");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const productLine = useProductLineStore((s) => s.selected);
  const [data, setData] = useState<ERPSupplier[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [linkModalOpen, setLinkModalOpen] = useState(false);
  const [linkingRecord, setLinkingRecord] = useState<ERPSupplier | null>(null);
  const [selectedSupplierId, setSelectedSupplierId] = useState<string | null>(null);
  const [openqmsSuppliers, setOpenqmsSuppliers] = useState<Array<{ id: string; name: string }>>([]);
  const [suppliersLoading, setSuppliersLoading] = useState(false);

  const linkStatusLabel = useMemo((): Record<string, string> => ({
    linked: t("masterData.linkStatus.linked", "已关联"),
    pending: t("masterData.linkStatus.pending", "待关联"),
    unlinked: t("masterData.linkStatus.unlinked", "未关联"),
  }), [t]);

  const getLinkStatusLabel = (v: string) => linkStatusLabel[v] || v;

  const fetchData = (p: number, plCode?: string | null) => {
    setLoading(true);
    fetchERPSuppliers({ page: p, page_size: 20, product_line_code: plCode || undefined })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error(t("masterData.suppliers.errors.loadFailed", "加载供应商失败")))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(1, productLine); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine]);

  const openLinkModal = async (record: ERPSupplier) => {
    setLinkingRecord(record);
    setSelectedSupplierId(null);
    setLinkModalOpen(true);
    setSuppliersLoading(true);
    try {
      const resp = await listSuppliers({ page: 1, page_size: 500 });
      setOpenqmsSuppliers(
        resp.items.map((s) => ({ id: s.supplier_id, name: `${s.supplier_no} - ${s.name}` })),
      );
    } catch {
      message.error(t("masterData.suppliers.errors.loadSupplierListFailed", "加载供应商列表失败"));
    } finally {
      setSuppliersLoading(false);
    }
  };

  const handleLink = async () => {
    if (!linkingRecord || !selectedSupplierId) return;
    try {
      await linkERPSupplier(linkingRecord.erp_supplier_id, selectedSupplierId);
      message.success(t("masterData.suppliers.messages.linkSuccess", "关联成功"));
      setLinkModalOpen(false);
      fetchData(page);
    } catch {
      message.error(t("masterData.suppliers.messages.linkFailed", "关联失败"));
    }
  };

  const handleUnlink = async (record: ERPSupplier) => {
    try {
      await unlinkERPSupplier(record.erp_supplier_id);
      message.success(t("masterData.suppliers.messages.unlinkSuccess", "取消关联成功"));
      fetchData(page);
    } catch {
      message.error(t("masterData.suppliers.messages.unlinkFailed", "取消关联失败"));
    }
  };

  const columns = [
    { title: t("masterData.suppliers.columns.code", "供应商编码"), dataIndex: "supplier_code", key: "supplier_code", width: 140 },
    { title: t("masterData.suppliers.columns.name", "名称"), dataIndex: "name", key: "name", ellipsis: true },
    { title: t("masterData.suppliers.columns.status", "状态"), dataIndex: "status", key: "status", width: 100, render: (v: string) => <Tag>{v}</Tag> },
    {
      title: t("masterData.suppliers.columns.linkStatus", "关联状态"),
      dataIndex: "link_status",
      key: "link_status",
      width: 110,
      render: (v: string) => (
        <StatusBadge status={linkStatusVariant(v)}>{getLinkStatusLabel(v)}</StatusBadge>
      ),
    },
    {
      title: tc("table.operations", "操作"),
      key: "actions",
      width: 140,
      render: (_: unknown, record: ERPSupplier) => (
        <Space size={4}>
          {record.link_status !== "linked" && (
            <Button type="link" size="small" onClick={() => openLinkModal(record)}>{t("masterData.suppliers.actions.link", "关联")}</Button>
          )}
          {record.link_status === "linked" && (
            <Button type="link" size="small" danger onClick={() => handleUnlink(record)}>{t("masterData.suppliers.actions.unlink", "取消关联")}</Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <>
      <DataCard title={t("masterData.suppliers.cardTitle", "供应商")}>
        <Table
          columns={columns}
          dataSource={data}
          rowKey="erp_supplier_id"
          loading={loading}
          pagination={{
            current: page,
            total,
            pageSize: 20,
            onChange: (p) => { setPage(p); fetchData(p, productLine); },
          }}
          className="qf-table"
        />
      </DataCard>
      <Modal
        title={t("masterData.suppliers.linkModal.title", "关联 OpenQMS 供应商")}
        open={linkModalOpen}
        onOk={handleLink}
        onCancel={() => setLinkModalOpen(false)}
        okButtonProps={{ disabled: !selectedSupplierId }}
        okText={tc("actions.confirm", "确认关联")}
        cancelText={tc("actions.cancel", "取消")}
      >
        <p style={{ marginBottom: 12 }}>
          {t("masterData.suppliers.linkModal.selectPrompt", "选择要关联的 OpenQMS 供应商：")}
        </p>
        <Select
          style={{ width: "100%" }}
          placeholder={t("masterData.suppliers.linkModal.placeholder", "请选择供应商")}
          loading={suppliersLoading}
          value={selectedSupplierId}
          onChange={setSelectedSupplierId}
          options={openqmsSuppliers.map((s) => ({ value: s.id, label: s.name }))}
          showSearch
          optionFilterProp="label"
        />
      </Modal>
    </>
  );
}

// ─── Customers Tab ───

function CustomersTab() {
  const { t } = useTranslation("erp");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const productLine = useProductLineStore((s) => s.selected);
  const [data, setData] = useState<ERPCustomer[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [linkModalOpen, setLinkModalOpen] = useState(false);
  const [linkingRecord, setLinkingRecord] = useState<ERPCustomer | null>(null);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string | null>(null);
  const [openqmsCustomers, setOpenqmsCustomers] = useState<Array<{ id: string; name: string }>>([]);
  const [customersLoading, setCustomersLoading] = useState(false);

  const linkStatusLabel = useMemo((): Record<string, string> => ({
    linked: t("masterData.linkStatus.linked", "已关联"),
    pending: t("masterData.linkStatus.pending", "待关联"),
    unlinked: t("masterData.linkStatus.unlinked", "未关联"),
  }), [t]);

  const getLinkStatusLabel = (v: string) => linkStatusLabel[v] || v;

  const fetchData = (p: number, plCode?: string | null) => {
    setLoading(true);
    fetchERPCustomers({ page: p, page_size: 20, product_line_code: plCode || undefined })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error(t("masterData.customers.errors.loadFailed", "加载客户失败")))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(1, productLine); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine]);

  const openLinkModal = async (record: ERPCustomer) => {
    setLinkingRecord(record);
    setSelectedCustomerId(null);
    setLinkModalOpen(true);
    setCustomersLoading(true);
    try {
      const resp = await listCustomers({ page: 1, page_size: 500 });
      setOpenqmsCustomers(
        resp.items.map((c) => ({ id: c.customer_id, name: `${c.customer_code} - ${c.name}` })),
      );
    } catch {
      message.error(t("masterData.customers.errors.loadCustomerListFailed", "加载客户列表失败"));
    } finally {
      setCustomersLoading(false);
    }
  };

  const handleLink = async () => {
    if (!linkingRecord || !selectedCustomerId) return;
    try {
      await linkERPCustomer(linkingRecord.erp_customer_id, selectedCustomerId);
      message.success(t("masterData.customers.messages.linkSuccess", "关联成功"));
      setLinkModalOpen(false);
      fetchData(page);
    } catch {
      message.error(t("masterData.customers.messages.linkFailed", "关联失败"));
    }
  };

  const handleUnlink = async (record: ERPCustomer) => {
    try {
      await unlinkERPCustomer(record.erp_customer_id);
      message.success(t("masterData.customers.messages.unlinkSuccess", "取消关联成功"));
      fetchData(page);
    } catch {
      message.error(t("masterData.customers.messages.unlinkFailed", "取消关联失败"));
    }
  };

  const columns = [
    { title: t("masterData.customers.columns.code", "客户编码"), dataIndex: "customer_code", key: "customer_code", width: 140 },
    { title: t("masterData.customers.columns.name", "名称"), dataIndex: "name", key: "name", ellipsis: true },
    { title: t("masterData.customers.columns.status", "状态"), dataIndex: "status", key: "status", width: 100, render: (v: string) => <Tag>{v}</Tag> },
    {
      title: t("masterData.customers.columns.linkStatus", "关联状态"),
      dataIndex: "link_status",
      key: "link_status",
      width: 110,
      render: (v: string) => (
        <StatusBadge status={linkStatusVariant(v)}>{getLinkStatusLabel(v)}</StatusBadge>
      ),
    },
    {
      title: tc("table.operations", "操作"),
      key: "actions",
      width: 140,
      render: (_: unknown, record: ERPCustomer) => (
        <Space size={4}>
          {record.link_status !== "linked" && (
            <Button type="link" size="small" onClick={() => openLinkModal(record)}>{t("masterData.customers.actions.link", "关联")}</Button>
          )}
          {record.link_status === "linked" && (
            <Button type="link" size="small" danger onClick={() => handleUnlink(record)}>{t("masterData.customers.actions.unlink", "取消关联")}</Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <>
      <DataCard title={t("masterData.customers.cardTitle", "客户")}>
        <Table
          columns={columns}
          dataSource={data}
          rowKey="erp_customer_id"
          loading={loading}
          pagination={{
            current: page,
            total,
            pageSize: 20,
            onChange: (p) => { setPage(p); fetchData(p, productLine); },
          }}
          className="qf-table"
        />
      </DataCard>
      <Modal
        title={t("masterData.customers.linkModal.title", "关联 OpenQMS 客户")}
        open={linkModalOpen}
        onOk={handleLink}
        onCancel={() => setLinkModalOpen(false)}
        okButtonProps={{ disabled: !selectedCustomerId }}
        okText={tc("actions.confirm", "确认关联")}
        cancelText={tc("actions.cancel", "取消")}
      >
        <p style={{ marginBottom: 12 }}>
          {t("masterData.customers.linkModal.selectPrompt", "选择要关联的 OpenQMS 客户：")}
        </p>
        <Select
          style={{ width: "100%" }}
          placeholder={t("masterData.customers.linkModal.placeholder", "请选择客户")}
          loading={customersLoading}
          value={selectedCustomerId}
          onChange={setSelectedCustomerId}
          options={openqmsCustomers.map((c) => ({ value: c.id, label: c.name }))}
          showSearch
          optionFilterProp="label"
        />
      </Modal>
    </>
  );
}

// ─── Materials Tab ───

function MaterialsTab() {
  const { t } = useTranslation("erp");
  const { message } = App.useApp();
  const productLine = useProductLineStore((s) => s.selected);
  const [data, setData] = useState<ERPMaterial[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");

  const fetchData = (p: number, q: string, plCode?: string | null) => {
    setLoading(true);
    fetchERPMaterials({ page: p, page_size: 20, product_line_code: plCode || undefined })
      .then((res) => {
        if (q) {
          const filtered = res.items.filter(
            (item) =>
              item.material_code.toLowerCase().includes(q.toLowerCase()) ||
              item.name.toLowerCase().includes(q.toLowerCase()),
          );
          setData(filtered);
          setTotal(filtered.length);
        } else {
          setData(res.items);
          setTotal(res.total);
        }
      })
      .catch(() => message.error(t("masterData.materials.errors.loadFailed", "加载物料失败")))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(1, "", productLine); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine]);

  const handleSearch = (value: string) => {
    setSearch(value);
    setPage(1);
    fetchData(1, value, productLine);
  };

  const columns = [
    { title: t("masterData.materials.columns.code", "物料编码"), dataIndex: "material_code", key: "material_code", width: 140 },
    { title: t("masterData.materials.columns.name", "名称"), dataIndex: "name", key: "name", ellipsis: true },
    { title: t("masterData.materials.columns.specification", "规格"), dataIndex: "specification", key: "specification", width: 140, render: (v: string | null) => v || "—" },
    { title: t("masterData.materials.columns.unit", "单位"), dataIndex: "unit", key: "unit", width: 70, render: (v: string | null) => v || "—" },
    {
      title: t("masterData.materials.columns.isPurchased", "采购件"),
      dataIndex: "is_purchased",
      key: "is_purchased",
      width: 80,
      render: (v: boolean) => v ? <Tag color="blue">{t("masterData.materials.yes", "是")}</Tag> : t("masterData.materials.no", "否"),
    },
    {
      title: t("masterData.materials.columns.isManufactured", "自制件"),
      dataIndex: "is_manufactured",
      key: "is_manufactured",
      width: 80,
      render: (v: boolean) => v ? <Tag color="green">{t("masterData.materials.yes", "是")}</Tag> : t("masterData.materials.no", "否"),
    },
    { title: t("masterData.materials.columns.status", "状态"), dataIndex: "status", key: "status", width: 90, render: (v: string) => <Tag>{v}</Tag> },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
        <Input.Search
          placeholder={t("masterData.materials.searchPlaceholder", "搜索物料编码或名称")}
          allowClear
          onSearch={handleSearch}
          style={{ width: 280 }}
        />
      </div>
      <DataCard title={t("masterData.materials.cardTitle", "物料")}>
        <Table
          columns={columns}
          dataSource={data}
          rowKey="material_id"
          loading={loading}
          pagination={{
            current: page,
            total,
            pageSize: 20,
            onChange: (p) => { setPage(p); fetchData(p, search, productLine); },
          }}
          className="qf-table"
        />
      </DataCard>
    </div>
  );
}

// ─── Locations Tab ───

function LocationsTab() {
  const { t } = useTranslation("erp");
  const { message } = App.useApp();
  const productLine = useProductLineStore((s) => s.selected);
  const [data, setData] = useState<ERPLocation[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);

  const locationTypeLabel = useMemo((): Record<string, string> => ({
    warehouse: t("masterData.locations.types.warehouse", "仓库"),
    zone: t("masterData.locations.types.zone", "库区"),
    bin: t("masterData.locations.types.bin", "库位"),
    line: t("masterData.locations.types.line", "产线"),
  }), [t]);

  const fetchData = (p: number, plCode?: string | null) => {
    setLoading(true);
    fetchERPLocations({ page: p, page_size: 20, product_line_code: plCode || undefined })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error(t("masterData.locations.errors.loadFailed", "加载库位失败")))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(1, productLine); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine]);

  const columns = [
    { title: t("masterData.locations.columns.code", "库位编码"), dataIndex: "location_code", key: "location_code", width: 140 },
    { title: t("masterData.locations.columns.warehouseCode", "仓库编码"), dataIndex: "warehouse_code", key: "warehouse_code", width: 120, render: (v: string | null) => v || "—" },
    { title: t("masterData.locations.columns.zoneCode", "库区编码"), dataIndex: "zone_code", key: "zone_code", width: 120, render: (v: string | null) => v || "—" },
    {
      title: t("masterData.locations.columns.type", "类型"),
      dataIndex: "location_type",
      key: "location_type",
      width: 100,
      render: (v: string) => <Tag>{locationTypeLabel[v] || v}</Tag>,
    },
    {
      title: t("masterData.locations.columns.enabled", "启用"),
      dataIndex: "is_enabled",
      key: "is_enabled",
      width: 80,
      render: (v: boolean) => v ? <Tag color="green">{t("masterData.locations.yes", "是")}</Tag> : <Tag color="red">{t("masterData.locations.no", "否")}</Tag>,
    },
  ];

  return (
    <DataCard title={t("masterData.locations.cardTitle", "库位")}>
      <Table
        columns={columns}
        dataSource={data}
        rowKey="location_id"
        loading={loading}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => { setPage(p); fetchData(p, productLine); },
        }}
        className="qf-table"
      />
    </DataCard>
  );
}

// ─── Main Page ───

export default function ERPMasterDataPage() {
  const { t } = useTranslation("erp");

  const tabItems = [
    { key: "suppliers", label: t("masterData.tabs.suppliers", "供应商"), children: <SuppliersTab /> },
    { key: "customers", label: t("masterData.tabs.customers", "客户"), children: <CustomersTab /> },
    { key: "materials", label: t("masterData.tabs.materials", "物料"), children: <MaterialsTab /> },
    { key: "locations", label: t("masterData.tabs.locations", "库位"), children: <LocationsTab /> },
  ];

  const [activeTab, setActiveTab] = useState("suppliers");

  return (
    <PageShell title={t("masterData.title", "ERP 主数据")}>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
      />
    </PageShell>
  );
}
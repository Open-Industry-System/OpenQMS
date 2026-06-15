import { useEffect, useMemo, useState } from "react";
import {
  Table, Tag, Button, Typography, App, Space, Input, Tabs, Modal, Select,
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
import type {
  ERPSupplier,
  ERPCustomer,
  ERPMaterial,
  ERPLocation,
} from "../../types/erp";

const { Title } = Typography;

// ─── Suppliers Tab ───

const linkStatusColor = (v: string) => {
  switch (v) {
    case "linked": return "green";
    case "pending": return "orange";
    default: return "red";
  }
};

function useLinkStatusLabel() {
  const { t } = useTranslation("erp");
  return useMemo(() => ({
    linked: t("masterData.linkStatus.linked"),
    pending: t("masterData.linkStatus.pending"),
    unlinked: t("masterData.linkStatus.unlinked"),
  }), [t]);
}

function SuppliersTab() {
  const { t } = useTranslation("erp");
  const { t: tc } = useTranslation("common");
  const linkStatusLabel = useLinkStatusLabel();
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

  const fetchData = (p: number, plCode?: string | null) => {
    setLoading(true);
    fetchERPSuppliers({ page: p, page_size: 20, product_line_code: plCode || undefined })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error(t("masterData.suppliers.messages.loadFailed")))
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
      message.error(t("masterData.suppliers.messages.loadListFailed"));
    } finally {
      setSuppliersLoading(false);
    }
  };

  const handleLink = async () => {
    if (!linkingRecord || !selectedSupplierId) return;
    try {
      await linkERPSupplier(linkingRecord.erp_supplier_id, selectedSupplierId);
      message.success(t("masterData.suppliers.messages.linkSuccess"));
      setLinkModalOpen(false);
      fetchData(page);
    } catch {
      message.error(t("masterData.suppliers.messages.linkFailed"));
    }
  };

  const handleUnlink = async (record: ERPSupplier) => {
    try {
      await unlinkERPSupplier(record.erp_supplier_id);
      message.success(t("masterData.suppliers.messages.unlinkSuccess"));
      fetchData(page);
    } catch {
      message.error(t("masterData.suppliers.messages.unlinkFailed"));
    }
  };

  const columns = [
    { title: t("masterData.columns.supplierCode"), dataIndex: "supplier_code", key: "supplier_code", width: 140 },
    { title: t("masterData.columns.name"), dataIndex: "name", key: "name", ellipsis: true },
    { title: t("masterData.columns.status"), dataIndex: "status", key: "status", width: 100, render: (v: string) => <Tag>{v}</Tag> },
    {
      title: t("masterData.columns.linkStatus"),
      dataIndex: "link_status",
      key: "link_status",
      width: 110,
      render: (v: string) => <Tag color={linkStatusColor(v)}>{linkStatusLabel[v as keyof typeof linkStatusLabel] || v}</Tag>,
    },
    {
      title: t("masterData.columns.actions"),
      key: "actions",
      width: 140,
      render: (_: unknown, record: ERPSupplier) => (
        <Space size={4}>
          {record.link_status !== "linked" && (
            <Button type="link" size="small" onClick={() => openLinkModal(record)}>{t("masterData.suppliers.link")}</Button>
          )}
          {record.link_status === "linked" && (
            <Button type="link" size="small" danger onClick={() => handleUnlink(record)}>{t("masterData.suppliers.unlink")}</Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <>
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
      />
      <Modal
        title={t("masterData.suppliers.linkModal.title")}
        open={linkModalOpen}
        onOk={handleLink}
        onCancel={() => setLinkModalOpen(false)}
        okButtonProps={{ disabled: !selectedSupplierId }}
        okText={t("masterData.suppliers.linkModal.okText")}
        cancelText={tc("actions.cancel")}
      >
        <p style={{ marginBottom: 12 }}>
          {t("masterData.suppliers.linkModal.description")}
        </p>
        <Select
          style={{ width: "100%" }}
          placeholder={t("masterData.suppliers.linkModal.placeholder")}
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
  const linkStatusLabel = useLinkStatusLabel();
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

  const fetchData = (p: number, plCode?: string | null) => {
    setLoading(true);
    fetchERPCustomers({ page: p, page_size: 20, product_line_code: plCode || undefined })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error(t("masterData.customers.messages.loadFailed")))
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
      message.error(t("masterData.customers.messages.loadListFailed"));
    } finally {
      setCustomersLoading(false);
    }
  };

  const handleLink = async () => {
    if (!linkingRecord || !selectedCustomerId) return;
    try {
      await linkERPCustomer(linkingRecord.erp_customer_id, selectedCustomerId);
      message.success(t("masterData.customers.messages.linkSuccess"));
      setLinkModalOpen(false);
      fetchData(page);
    } catch {
      message.error(t("masterData.customers.messages.linkFailed"));
    }
  };

  const handleUnlink = async (record: ERPCustomer) => {
    try {
      await unlinkERPCustomer(record.erp_customer_id);
      message.success(t("masterData.customers.messages.unlinkSuccess"));
      fetchData(page);
    } catch {
      message.error(t("masterData.customers.messages.unlinkFailed"));
    }
  };

  const columns = [
    { title: t("masterData.columns.customerCode"), dataIndex: "customer_code", key: "customer_code", width: 140 },
    { title: t("masterData.columns.name"), dataIndex: "name", key: "name", ellipsis: true },
    { title: t("masterData.columns.status"), dataIndex: "status", key: "status", width: 100, render: (v: string) => <Tag>{v}</Tag> },
    {
      title: t("masterData.columns.linkStatus"),
      dataIndex: "link_status",
      key: "link_status",
      width: 110,
      render: (v: string) => <Tag color={linkStatusColor(v)}>{linkStatusLabel[v as keyof typeof linkStatusLabel] || v}</Tag>,
    },
    {
      title: t("masterData.columns.actions"),
      key: "actions",
      width: 140,
      render: (_: unknown, record: ERPCustomer) => (
        <Space size={4}>
          {record.link_status !== "linked" && (
            <Button type="link" size="small" onClick={() => openLinkModal(record)}>{t("masterData.customers.link")}</Button>
          )}
          {record.link_status === "linked" && (
            <Button type="link" size="small" danger onClick={() => handleUnlink(record)}>{t("masterData.customers.unlink")}</Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <>
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
      />
      <Modal
        title={t("masterData.customers.linkModal.title")}
        open={linkModalOpen}
        onOk={handleLink}
        onCancel={() => setLinkModalOpen(false)}
        okButtonProps={{ disabled: !selectedCustomerId }}
        okText={t("masterData.customers.linkModal.okText")}
        cancelText={tc("actions.cancel")}
      >
        <p style={{ marginBottom: 12 }}>
          {t("masterData.customers.linkModal.description")}
        </p>
        <Select
          style={{ width: "100%" }}
          placeholder={t("masterData.customers.linkModal.placeholder")}
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
      .catch(() => message.error(t("masterData.materials.messages.loadFailed")))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(1, "", productLine); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine]);

  const handleSearch = (value: string) => {
    setSearch(value);
    setPage(1);
    fetchData(1, value, productLine);
  };

  const boolTag = (v: boolean) => v ? <Tag color="blue">{t("yes")}</Tag> : t("no");

  const columns = [
    { title: t("masterData.columns.materialCode"), dataIndex: "material_code", key: "material_code", width: 140 },
    { title: t("masterData.columns.name"), dataIndex: "name", key: "name", ellipsis: true },
    { title: t("masterData.columns.specification"), dataIndex: "specification", key: "specification", width: 140, render: (v: string | null) => v || "—" },
    { title: t("masterData.columns.unit"), dataIndex: "unit", key: "unit", width: 70, render: (v: string | null) => v || "—" },
    {
      title: t("masterData.columns.isPurchased"),
      dataIndex: "is_purchased",
      key: "is_purchased",
      width: 80,
      render: (v: boolean) => boolTag(v),
    },
    {
      title: t("masterData.columns.isManufactured"),
      dataIndex: "is_manufactured",
      key: "is_manufactured",
      width: 80,
      render: (v: boolean) => boolTag(v),
    },
    { title: t("masterData.columns.status"), dataIndex: "status", key: "status", width: 90, render: (v: string) => <Tag>{v}</Tag> },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
        <Input.Search
          placeholder={t("masterData.searchPlaceholder")}
          allowClear
          onSearch={handleSearch}
          style={{ width: 280 }}
        />
      </div>
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
      />
    </div>
  );
}

// ─── Locations Tab ───

function useLocationTypeLabel() {
  const { t } = useTranslation("erp");
  return useMemo(() => ({
    warehouse: t("masterData.locationType.warehouse"),
    zone: t("masterData.locationType.zone"),
    bin: t("masterData.locationType.bin"),
    line: t("masterData.locationType.line"),
  }), [t]);
}

function LocationsTab() {
  const { t } = useTranslation("erp");
  const locationTypeLabel = useLocationTypeLabel();
  const { message } = App.useApp();
  const productLine = useProductLineStore((s) => s.selected);
  const [data, setData] = useState<ERPLocation[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);

  const fetchData = (p: number, plCode?: string | null) => {
    setLoading(true);
    fetchERPLocations({ page: p, page_size: 20, product_line_code: plCode || undefined })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .catch(() => message.error(t("masterData.locations.messages.loadFailed")))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(1, productLine); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine]);

  const boolTag = (v: boolean) => v ? <Tag color="green">{t("yes")}</Tag> : <Tag color="red">{t("no")}</Tag>;

  const columns = [
    { title: t("masterData.columns.locationCode"), dataIndex: "location_code", key: "location_code", width: 140 },
    { title: t("masterData.columns.warehouseCode"), dataIndex: "warehouse_code", key: "warehouse_code", width: 120, render: (v: string | null) => v || "—" },
    { title: t("masterData.columns.zoneCode"), dataIndex: "zone_code", key: "zone_code", width: 120, render: (v: string | null) => v || "—" },
    {
      title: t("masterData.columns.type"),
      dataIndex: "location_type",
      key: "location_type",
      width: 100,
      render: (v: string) => <Tag>{locationTypeLabel[v as keyof typeof locationTypeLabel] || v}</Tag>,
    },
    {
      title: t("masterData.columns.enabled"),
      dataIndex: "is_enabled",
      key: "is_enabled",
      width: 80,
      render: (v: boolean) => boolTag(v),
    },
  ];

  return (
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
    />
  );
}

// ─── Main Page ───

export default function ERPMasterDataPage() {
  const { t } = useTranslation("erp");
  const [activeTab, setActiveTab] = useState("suppliers");

  const tabItems = [
    { key: "suppliers", label: t("masterData.tabs.suppliers"), children: <SuppliersTab /> },
    { key: "customers", label: t("masterData.tabs.customers"), children: <CustomersTab /> },
    { key: "materials", label: t("masterData.tabs.materials"), children: <MaterialsTab /> },
    { key: "locations", label: t("masterData.tabs.locations"), children: <LocationsTab /> },
  ];

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>{t("masterData.title")}</Title>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
      />
    </div>
  );
}

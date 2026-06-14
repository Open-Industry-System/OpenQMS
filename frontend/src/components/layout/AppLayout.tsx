import { useState, useEffect, ReactNode, useMemo } from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { Layout, Menu, Button, Avatar, Dropdown, Space, Select, Segmented, Tooltip } from "antd";
import type { MenuProps } from "antd";
import {
  DashboardOutlined,
  FileTextOutlined,
  BugOutlined,
  AimOutlined,
  SafetyOutlined,
  SafetyCertificateOutlined,
  ShopOutlined,
  ToolOutlined,
  ExperimentOutlined,
  LogoutOutlined,
  UserOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  TeamOutlined,
  CustomerServiceOutlined,
  BarChartOutlined,
  AlertOutlined,
  ProjectOutlined,
  FileProtectOutlined,
  AuditOutlined,
  ShareAltOutlined,
  RadarChartOutlined,
  BuildOutlined,
  SettingOutlined,
  WarningOutlined,
  GlobalOutlined,
  BankOutlined,
  HeatMapOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import i18n from "../../i18n";
import { useAuthStore } from "../../store/authStore";
import { useProductLineStore } from "../../store/productLineStore";
import { usePermission } from "../../hooks/usePermission";
import type { ModuleKey } from "../../hooks/usePermission";

const { Header, Sider, Content } = Layout;

const MENU_KEYS = [
  "/dashboard",
  "/fmea", "/control-plans", "/apqp", "/ppap",
  "/special-characteristics", "/special-characteristics/matrix", "/special-characteristics/traceability",
  "/spc", "/msa/gauges", "/msa/studies", "/quality-goals",
  "/internal-audits", "/management-reviews",
  "/customer-quality", "/customer-audits", "/capa",
  "/suppliers", "/suppliers/quality", "/supplier-risk", "/supplier-risk/config", "/supply-chain-risk-map",
  "/iqc/inspections", "/iqc/materials", "/iqc/aql-optimization", "/scars",
  "/knowledge-graph",
  "/change-impact",
  "/mes/dashboard", "/mes/orders", "/mes/scrap", "/mes/connections",
  "/plm/dashboard", "/plm/connections", "/plm/parts", "/plm/change-orders",
  "/erp", "/erp/connections", "/erp/master-data", "/erp/supply-chain", "/erp/commercial", "/erp/traceability",
  "/group/dashboard", "/group/comparison", "/group/suppliers", "/group/audits", "/group/factories",
];

const MENU_KEY_TO_OPEN_KEYS: Record<string, string[]> = {
  "/fmea": ["grp:planning"],
  "/control-plans": ["grp:planning"],
  "/apqp": ["grp:planning"],
  "/ppap": ["grp:planning"],
  "/special-characteristics": ["grp:planning"],
  "/special-characteristics/matrix": ["grp:planning"],
  "/special-characteristics/traceability": ["grp:planning"],
  "/spc": ["grp:shopfloor"],
  "/msa/gauges": ["grp:shopfloor", "grp:msa"],
  "/msa/studies": ["grp:shopfloor", "grp:msa"],
  "/quality-goals": ["grp:shopfloor"],
  "/internal-audits": ["grp:shopfloor"],
  "/management-reviews": ["grp:shopfloor"],
  "/customer-quality": ["grp:customer"],
  "/customer-audits": ["grp:customer"],
  "/capa": ["grp:customer"],
  "/suppliers": ["grp:supplier"],
  "/suppliers/quality": ["grp:supplier"],
  "/supplier-risk": ["grp:supplier"],
  "/supplier-risk/config": ["grp:supplier"],
  "/supply-chain-risk-map": ["grp:supplier"],
  "/iqc/inspections": ["grp:supplier", "grp:iqc"],
  "/iqc/materials": ["grp:supplier", "grp:iqc"],
  "/iqc/aql-optimization": ["grp:supplier", "grp:iqc"],
  "/scars": ["grp:supplier"],
  "/knowledge-graph": ["grp:planning"],
  "/change-impact": ["grp:planning"],
  "/mes/dashboard": ["grp:mes"],
  "/mes/orders": ["grp:mes"],
  "/mes/scrap": ["grp:mes"],
  "/mes/connections": ["grp:mes"],
  "/plm/dashboard": ["grp:plm"],
  "/plm/connections": ["grp:plm"],
  "/plm/parts": ["grp:plm"],
  "/plm/change-orders": ["grp:plm"],
  "/erp": ["grp:erp"],
  "/erp/connections": ["grp:erp"],
  "/erp/master-data": ["grp:erp"],
  "/erp/supply-chain": ["grp:erp"],
  "/erp/commercial": ["grp:erp"],
  "/erp/traceability": ["grp:erp"],
  "/group/dashboard": ["grp:group"],
  "/group/comparison": ["grp:group"],
  "/group/suppliers": ["grp:group"],
  "/group/audits": ["grp:group"],
  "/group/factories": ["grp:group"],
};

interface MenuItem {
  key: string;
  icon?: ReactNode;
  label: string;
  module?: ModuleKey;
  children?: MenuItem[];
}

function stripModuleField(items: MenuItem[]): MenuProps["items"] {
  return items.map(({ module: _m, ...rest }) => ({
    ...rest,
    ...(rest.children ? { children: stripModuleField(rest.children) } : {}),
  }));
}

function getSelectedMenuKey(pathname: string): string {
  const matched = MENU_KEYS
    .filter((key) => pathname === key || pathname.startsWith(key + "/"))
    .sort((a, b) => b.length - a.length);
  return matched[0] || "/dashboard";
}

function useMenuItems(): MenuItem[] {
  const { t } = useTranslation("layout");
  return useMemo(
    () => [
      { key: "/dashboard", icon: <DashboardOutlined />, label: t("menu.dashboard") },
      {
        key: "grp:planning",
        icon: <ExperimentOutlined />,
        label: t("menu.planning"),
        module: "planning",
        children: [
          { key: "/fmea", icon: <FileTextOutlined />, label: t("menu.fmea"), module: "fmea" },
          { key: "/control-plans", icon: <FileTextOutlined />, label: t("menu.controlPlan"), module: "planning" },
          { key: "/apqp", icon: <ProjectOutlined />, label: t("menu.apqp"), module: "planning" },
          { key: "/ppap", icon: <FileProtectOutlined />, label: t("menu.ppap"), module: "ppap" },
          { key: "/special-characteristics", icon: <SafetyCertificateOutlined />, label: t("menu.specialCharacteristics"), module: "special_characteristic" },
          { key: "/knowledge-graph", icon: <ShareAltOutlined />, label: t("menu.knowledgeGraph"), module: "knowledge_graph" },
          { key: "/change-impact", icon: <RadarChartOutlined />, label: t("menu.changeImpact"), module: "fmea" },
        ],
      },
      {
        key: "grp:shopfloor",
        icon: <ToolOutlined />,
        label: t("menu.shopfloor"),
        module: "spc",
        children: [
          { key: "/spc", icon: <BarChartOutlined />, label: t("menu.spc"), module: "spc" },
          {
            key: "grp:msa",
            icon: <ToolOutlined />,
            label: t("menu.msa"),
            module: "msa",
            children: [
              { key: "/msa/gauges", label: t("menu.gaugeManagement"), module: "msa" },
              { key: "/msa/studies", label: t("menu.studyManagement"), module: "msa" },
            ],
          },
          { key: "/quality-goals", icon: <AimOutlined />, label: t("menu.qualityGoals"), module: "quality_goal" },
          { key: "/internal-audits", icon: <SafetyOutlined />, label: t("menu.internalAudit"), module: "audit" },
          { key: "/management-reviews", icon: <TeamOutlined />, label: t("menu.managementReview"), module: "management_review" },
        ],
      },
      {
        key: "grp:customer",
        icon: <CustomerServiceOutlined />,
        label: t("menu.customerQuality"),
        module: "customer_quality",
        children: [
          { key: "/customer-quality", icon: <CustomerServiceOutlined />, label: t("menu.customerComplaints"), module: "customer_quality" },
          { key: "/customer-audits", icon: <AuditOutlined />, label: t("menu.customerAudit"), module: "customer_audit" },
          { key: "/capa", icon: <BugOutlined />, label: t("menu.capa"), module: "capa" },
        ],
      },
      {
        key: "grp:supplier",
        icon: <ShopOutlined />,
        label: t("menu.supplierQuality"),
        module: "supplier",
        children: [
          { key: "/suppliers", icon: <ShopOutlined />, label: t("menu.supplierManagement"), module: "supplier" },
          { key: "/suppliers/quality", icon: <BarChartOutlined />, label: t("menu.supplierQualityDashboard"), module: "supplier" },
          { key: "/supplier-risk", icon: <WarningOutlined />, label: t("menu.supplierRiskAlert"), module: "supplier_risk" },
          { key: "/supply-chain-risk-map", icon: <HeatMapOutlined />, label: t("menu.supplyChainRiskMap"), module: "supply_chain_risk_map" },
          { key: "/scars", icon: <AlertOutlined />, label: t("menu.scarManagement"), module: "scar" },
          {
            key: "grp:iqc",
            icon: <ExperimentOutlined />,
            label: t("menu.iqc"),
            module: "iqc",
            children: [
              { key: "/iqc/inspections", label: t("menu.inspectionOrders"), module: "iqc" },
              { key: "/iqc/materials", label: t("menu.materialManagement"), module: "iqc" },
              { key: "/iqc/aql-optimization", icon: <SafetyCertificateOutlined />, label: t("menu.samplingOptimization"), module: "iqc" },
            ],
          },
        ],
      },
      {
        key: "grp:mes",
        icon: <ToolOutlined />,
        label: t("menu.mesIntegration"),
        module: "mes",
        children: [
          { key: "/mes/dashboard", label: t("menu.mesDashboard"), module: "mes" },
          { key: "/mes/orders", label: t("menu.workOrders"), module: "mes" },
          { key: "/mes/scrap", label: t("menu.scrapRework"), module: "mes" },
          { key: "/mes/connections", label: t("menu.mesConnections"), module: "mes" },
        ],
      },
      {
        key: "grp:plm",
        icon: <BuildOutlined />,
        label: t("menu.plmIntegration"),
        module: "plm",
        children: [
          { key: "/plm/dashboard", label: t("menu.plmDashboard"), module: "plm" },
          { key: "/plm/parts", label: t("menu.partList"), module: "plm" },
          { key: "/plm/change-orders", label: t("menu.changeOrderManagement"), module: "plm" },
          { key: "/plm/connections", label: t("menu.plmConnections"), module: "plm" },
        ],
      },
      {
        key: "grp:erp",
        icon: <SettingOutlined />,
        label: t("menu.erpIntegration"),
        module: "erp",
        children: [
          { key: "/erp", label: t("menu.erpDashboard"), module: "erp" },
          { key: "/erp/connections", label: t("menu.erpConnections"), module: "erp" },
          { key: "/erp/master-data", label: t("menu.masterData"), module: "erp" },
          { key: "/erp/supply-chain", label: t("menu.supplyChain"), module: "erp" },
          { key: "/erp/commercial", label: t("menu.salesCost"), module: "erp" },
          { key: "/erp/traceability", label: t("menu.batchTraceability"), module: "erp" },
        ],
      },
      {
        key: "grp:group",
        icon: <GlobalOutlined />,
        label: t("menu.groupManagement"),
        module: "group",
        children: [
          { key: "/group/dashboard", icon: <DashboardOutlined />, label: t("menu.groupDashboard"), module: "group" },
          { key: "/group/comparison", icon: <RadarChartOutlined />, label: t("menu.factoryComparison"), module: "group" },
          { key: "/group/suppliers", icon: <ShareAltOutlined />, label: t("menu.sharedSuppliers"), module: "group" },
          { key: "/group/audits", icon: <AuditOutlined />, label: t("menu.crossFactoryAudit"), module: "group" },
          { key: "/group/factories", icon: <BankOutlined />, label: t("menu.factoryManagement"), module: "group" },
        ],
      },
    ],
    [t]
  );
}

function filterMenuByPermission(
  items: MenuItem[],
  canViewFn: (m: ModuleKey) => boolean,
): MenuItem[] {
  return items
    .map((item) => {
      if (!item.module) return item;
      if (!canViewFn(item.module)) return null;
      if (item.children) {
        const filteredChildren = filterMenuByPermission(item.children, canViewFn);
        if (filteredChildren.length === 0) return null;
        return { ...item, children: filteredChildren };
      }
      return item;
    })
    .filter((item): item is MenuItem => item !== null);
}

function LanguageSwitcher() {
  return (
    <Segmented
      value={i18n.language}
      onChange={(value) => i18n.changeLanguage(value as string)}
      options={[
        { label: "中文", value: "zh-CN" },
        { label: "English", value: "en-US" },
      ]}
    />
  );
}

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const factoryScope = useAuthStore((s) => s.factoryScope);
  const factories = useAuthStore((s) => s.factories);
  const currentFactoryId = useAuthStore((s) => s.currentFactoryId);
  const setCurrentFactoryId = useAuthStore((s) => s.setCurrentFactoryId);
  const { productLines, selected, setSelected, load } = useProductLineStore();
  const { canView } = usePermission();
  const { t } = useTranslation("layout");
  useEffect(() => { load(); }, [load]);

  const menuItems = useMenuItems();
  const selectedKey = getSelectedMenuKey(location.pathname);
  const requiredOpenKeys = MENU_KEY_TO_OPEN_KEYS[selectedKey] || [];
  const [openKeys, setOpenKeys] = useState<string[]>(requiredOpenKeys);

  useEffect(() => {
    setOpenKeys((prev) => {
      const merged = new Set(prev);
      requiredOpenKeys.forEach((k) => merged.add(k));
      return Array.from(merged);
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedKey]);

  const visibleMenuItems = useMemo(
    () => filterMenuByPermission(menuItems, canView),
    [menuItems, canView]
  );

  const showFactorySwitcher = factoryScope?.accessible_factory_ids === null
    || (factoryScope?.accessible_factory_ids?.length ?? 0) > 1;

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider trigger={null} collapsible collapsed={collapsed} width={240} collapsedWidth={72}>
        <div style={{ height: 64, display: "flex", alignItems: "center", justifyContent: "center" }}>
          {!collapsed && <span style={{ fontSize: 18, fontWeight: 600 }}>OpenQMS</span>}
        </div>
        <Menu
          mode="inline"
          inlineCollapsed={collapsed}
          selectedKeys={[selectedKey]}
          openKeys={openKeys}
          onOpenChange={setOpenKeys}
          items={stripModuleField(visibleMenuItems)}
          onClick={({ key }) => {
            if (key.startsWith("grp:")) return;
            navigate(key);
          }}
          style={{ height: "calc(100vh - 64px)" }}
        />
      </Sider>
      <Layout>
        <Header style={{ padding: "0 24px", display: "flex", alignItems: "center", justifyContent: "space-between", background: "#fff" }}>
          <Tooltip title={collapsed ? t("header.expandMenu") : t("header.collapseMenu")}>
            <Button
              type="text"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed(!collapsed)}
            />
          </Tooltip>
          <Space size="middle">
            {showFactorySwitcher && (
              <Select
                style={{ width: 200 }}
                value={currentFactoryId || undefined}
                placeholder={t("header.selectFactory")}
                onChange={(v) => setCurrentFactoryId(v)}
              >
                {factories.map((f) => (
                  <Select.Option key={f.id} value={f.id}>
                    {f.code} - {f.name}
                  </Select.Option>
                ))}
              </Select>
            )}
            <Select
              allowClear
              placeholder={t("header.allProductLines")}
              style={{ width: 200 }}
              value={selected || undefined}
              onChange={(v) => setSelected(v || null)}
            >
                {productLines.map((pl) => (
                  <Select.Option key={pl.code} value={pl.code}>
                    {pl.code} - {pl.name}
                  </Select.Option>
                ))}
              </Select>
            <LanguageSwitcher />
            <Dropdown
              menu={{
                items: [
                  {
                    key: "logout",
                    icon: <LogoutOutlined />,
                    label: t("header.logout"),
                    onClick: () => { logout(); navigate("/login"); },
                  },
                ],
              }}
            >
              <Space style={{ cursor: "pointer" }}>
                <Avatar icon={<UserOutlined />} />
                <span>{user?.display_name || user?.username}</span>
              </Space>
            </Dropdown>
          </Space>
        </Header>
        <Content style={{ padding: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}

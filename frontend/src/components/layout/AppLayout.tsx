import { useState, useEffect, ReactNode } from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { Layout, Menu, Button, Avatar, Dropdown, Space, Select, Badge } from "antd";
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
  SwapOutlined,
  HeatMapOutlined,
} from "@ant-design/icons";
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

const menuItems: MenuItem[] = [
  { key: "/dashboard", icon: <DashboardOutlined />, label: "仪表盘" },
  {
    key: "grp:planning",
    icon: <ExperimentOutlined />,
    label: "前期质量策划",
    module: "planning",
    children: [
      { key: "/fmea", icon: <FileTextOutlined />, label: "FMEA 管理", module: "fmea" },
      { key: "/control-plans", icon: <FileTextOutlined />, label: "控制计划", module: "planning" },
      { key: "/apqp", icon: <ProjectOutlined />, label: "APQP 质量策划", module: "planning" },
      { key: "/ppap", icon: <FileProtectOutlined />, label: "PPAP", module: "ppap" },
      { key: "/special-characteristics", icon: <SafetyCertificateOutlined />, label: "特殊特性", module: "special_characteristic" },
      { key: "/knowledge-graph", icon: <ShareAltOutlined />, label: "知识图谱", module: "knowledge_graph" },
      { key: "/change-impact", icon: <RadarChartOutlined />, label: "变更影响分析", module: "fmea" },
    ],
  },
  {
    key: "grp:shopfloor",
    icon: <ToolOutlined />,
    label: "现场质量管理",
    module: "spc",
    children: [
      { key: "/spc", icon: <BarChartOutlined />, label: "SPC 控制图", module: "spc" },
      {
        key: "grp:msa",
        icon: <ToolOutlined />,
        label: "MSA 分析",
        module: "msa",
        children: [
          { key: "/msa/gauges", label: "量具管理", module: "msa" },
          { key: "/msa/studies", label: "研究管理", module: "msa" },
        ],
      },
      { key: "/quality-goals", icon: <AimOutlined />, label: "质量目标", module: "quality_goal" },
      { key: "/internal-audits", icon: <SafetyOutlined />, label: "内部审核", module: "audit" },
      { key: "/management-reviews", icon: <TeamOutlined />, label: "管理评审", module: "management_review" },
    ],
  },
  {
    key: "grp:customer",
    icon: <CustomerServiceOutlined />,
    label: "客户质量",
    module: "customer_quality",
    children: [
      { key: "/customer-quality", icon: <CustomerServiceOutlined />, label: "客诉/RMA", module: "customer_quality" },
      { key: "/customer-audits", icon: <AuditOutlined />, label: "客户审核", module: "customer_audit" },
      { key: "/capa", icon: <BugOutlined />, label: "8D/CAPA", module: "capa" },
    ],
  },
  {
    key: "grp:supplier",
    icon: <ShopOutlined />,
    label: "供应商质量",
    module: "supplier",
    children: [
      { key: "/suppliers", icon: <ShopOutlined />, label: "供应商管理", module: "supplier" },
      { key: "/suppliers/quality", icon: <BarChartOutlined />, label: "供货质量看板", module: "supplier" },
      { key: "/supplier-risk", icon: <WarningOutlined />, label: "供应商风险预警", module: "supplier_risk" },
      { key: "/supply-chain-risk-map", icon: <HeatMapOutlined />, label: "供应链风险地图", module: "supply_chain_risk_map" },
      { key: "/scars", icon: <AlertOutlined />, label: "SCAR 管理", module: "scar" },
      {
        key: "grp:iqc",
        icon: <ExperimentOutlined />,
        label: "来料检验",
        module: "iqc",
        children: [
          { key: "/iqc/inspections", label: "检验单", module: "iqc" },
          { key: "/iqc/materials", label: "物料管理", module: "iqc" },
          { key: "/iqc/aql-optimization", icon: <SafetyCertificateOutlined />, label: "抽样方案优化", module: "iqc" },
        ],
      },
    ],
  },
  {
    key: "grp:mes",
    icon: <ToolOutlined />,
    label: "MES 集成",
    module: "mes",
    children: [
      { key: "/mes/dashboard", label: "MES 看板", module: "mes" },
      { key: "/mes/orders", label: "工单列表", module: "mes" },
      { key: "/mes/scrap", label: "报废/返工", module: "mes" },
      { key: "/mes/connections", label: "连接管理", module: "mes" },
    ],
  },
  {
    key: "grp:plm",
    icon: <BuildOutlined />,
    label: "PLM 集成",
    module: "plm",
    children: [
      { key: "/plm/dashboard", label: "PLM 看板", module: "plm" },
      { key: "/plm/parts", label: "零件列表", module: "plm" },
      { key: "/plm/change-orders", label: "变更单管理", module: "plm" },
      { key: "/plm/connections", label: "连接管理", module: "plm" },
    ],
  },
  {
    key: "grp:erp",
    icon: <SettingOutlined />,
    label: "ERP 集成",
    module: "erp",
    children: [
      { key: "/erp", label: "ERP 看板", module: "erp" },
      { key: "/erp/connections", label: "连接管理", module: "erp" },
      { key: "/erp/master-data", label: "主数据", module: "erp" },
      { key: "/erp/supply-chain", label: "供应链", module: "erp" },
      { key: "/erp/commercial", label: "销售与成本", module: "erp" },
      { key: "/erp/traceability", label: "批次追溯", module: "erp" },
    ],
  },
  {
    key: "grp:group",
    icon: <GlobalOutlined />,
    label: "集团管理",
    module: "group",
    children: [
      { key: "/group/dashboard", icon: <DashboardOutlined />, label: "集团仪表盘", module: "group" },
      { key: "/group/comparison", icon: <RadarChartOutlined />, label: "工厂对比", module: "group" },
      { key: "/group/suppliers", icon: <ShareAltOutlined />, label: "共享供应商", module: "group" },
      { key: "/group/audits", icon: <AuditOutlined />, label: "跨厂审核", module: "group" },
      { key: "/group/factories", icon: <BankOutlined />, label: "工厂管理", module: "group" },
    ],
  },
];

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
  useEffect(() => { load(); }, [load]);

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

  const visibleMenuItems = filterMenuByPermission(menuItems, canView);

  const showFactorySwitcher = factoryScope?.accessible_factory_ids === null
    || (factoryScope?.accessible_factory_ids?.length ?? 0) > 1;

  return (
    <Layout style={{ minHeight: "100vh", background: "var(--qf-bg-base)" }}>
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        width={240}
        collapsedWidth={72}
        style={{
          background: "var(--qf-bg-panel)",
          borderRight: "1px solid var(--qf-border)",
          boxShadow: "var(--qf-shadow-md)",
          zIndex: 10,
        }}
      >
        <div
          style={{
            height: 64,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            borderBottom: "1px solid var(--qf-border)",
            gap: 8,
          }}
        >
          <div
            style={{
              width: 28,
              height: 28,
              borderRadius: 6,
              background: "linear-gradient(135deg, var(--qf-cyan), #00b8d4)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontWeight: 700,
              fontSize: 14,
              color: "#0b0d12",
              boxShadow: "0 0 12px rgba(0, 229, 255, 0.35)",
              fontFamily: "var(--qf-font-mono)",
              flexShrink: 0,
            }}
          >
            Q
          </div>
          {!collapsed && (
            <span
              style={{
                fontFamily: "var(--qf-font-display)",
                fontSize: 18,
                fontWeight: 600,
                letterSpacing: "0.04em",
                color: "var(--qf-text-primary)",
              }}
            >
              OpenQMS
            </span>
          )}
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
          className="qf-menu"
          style={{
            background: "transparent",
            borderRight: 0,
            padding: "8px 0",
          }}
          theme="dark"
        />
      </Sider>
      <Layout style={{ background: "var(--qf-bg-base)" }}>
        <Header
          style={{
            height: 64,
            padding: "0 24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "var(--qf-bg-panel)",
            borderBottom: "1px solid var(--qf-border)",
            position: "sticky",
            top: 0,
            zIndex: 9,
          }}
        >
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
            style={{
              color: "var(--qf-text-secondary)",
              width: 36,
              height: 36,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          />
          <Space size="middle">
            {showFactorySwitcher && (
              <Select
                style={{ width: 200 }}
                value={currentFactoryId || undefined}
                placeholder="选择工厂"
                onChange={(v) => setCurrentFactoryId(v)}
                suffixIcon={<SwapOutlined style={{ color: "var(--qf-cyan)" }} />}
              >
                {factories.map((f) => (
                  <Select.Option key={f.id} value={f.id}>
                    <span style={{ fontFamily: "var(--qf-font-mono)", color: "var(--qf-cyan)", marginRight: 8 }}>
                      {f.code}
                    </span>
                    {f.name}
                  </Select.Option>
                ))}
              </Select>
            )}
            <Select
              allowClear
              placeholder="全部产品线"
              style={{ width: 200 }}
              value={selected || undefined}
              onChange={(v) => setSelected(v || null)}
            >
                {productLines.map((pl) => (
                  <Select.Option key={pl.code} value={pl.code}>
                    <span style={{ fontFamily: "var(--qf-font-mono)", color: "var(--qf-cyan)", marginRight: 8 }}>
                      {pl.code}
                    </span>
                    {pl.name}
                  </Select.Option>
                ))}
              </Select>
            <Dropdown
              menu={{
                items: [
                  {
                    key: "logout",
                    icon: <LogoutOutlined style={{ color: "var(--qf-red)" }} />,
                    label: "退出登录",
                    onClick: () => { logout(); navigate("/login"); },
                  },
                ],
              }}
            >
              <Space style={{ cursor: "pointer", padding: "4px 8px", borderRadius: 8 }}>
                <Badge dot color="var(--qf-green)" offset={[-2, 24]}>
                  <Avatar
                    icon={<UserOutlined />}
                    style={{
                      background: "var(--qf-bg-elevated)",
                      color: "var(--qf-cyan)",
                      border: "1px solid var(--qf-border)",
                    }}
                  />
                </Badge>
                <span style={{ color: "var(--qf-text-primary)", fontWeight: 500 }}>
                  {user?.display_name || user?.username}
                </span>
              </Space>
            </Dropdown>
          </Space>
        </Header>
        <Content style={{ padding: 24, background: "var(--qf-bg-base)" }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}

import { useState, useEffect } from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { Layout, Menu, Button, Avatar, Dropdown, theme, Space, Select } from "antd";
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
  ApartmentOutlined,
  BankOutlined,
  SwapOutlined,
  HeatMapOutlined,
} from "@ant-design/icons";
import { useAuthStore } from "../../store/authStore";
import { useProductLineStore } from "../../store/productLineStore";
import { usePermission } from "../../hooks/usePermission";
import type { ModuleKey } from "../../hooks/usePermission";

const { Header, Sider, Content } = Layout;

// 所有菜单 key 列表（用于最长前缀匹配）
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

// 菜单 key → 需要展开的所有 SubMenu key 列表
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

function getSelectedMenuKey(pathname: string): string {
  const matched = MENU_KEYS
    .filter((key) => pathname === key || pathname.startsWith(key + "/"))
    .sort((a, b) => b.length - a.length);
  return matched[0] || "/dashboard";
}

const menuItems = [
  { key: "/dashboard", icon: <DashboardOutlined />, label: "仪表盘", module: undefined as string | undefined },
  {
    key: "grp:planning",
    icon: <ExperimentOutlined />,
    label: "前期质量策划",
    module: "planning",
    children: [
      { key: "/fmea", icon: <FileTextOutlined />, label: "FMEA 管理" },
      { key: "/control-plans", icon: <FileTextOutlined />, label: "控制计划" },
      { key: "/apqp", icon: <ProjectOutlined />, label: "APQP 质量策划" },
      { key: "/ppap", icon: <FileProtectOutlined />, label: "PPAP" },
      { key: "/special-characteristics", icon: <SafetyCertificateOutlined />, label: "特殊特性" },
      { key: "/knowledge-graph", icon: <ShareAltOutlined />, label: "知识图谱" },
      { key: "/change-impact", icon: <RadarChartOutlined />, label: "变更影响分析" },
    ],
  },
  {
    key: "grp:shopfloor",
    icon: <ToolOutlined />,
    label: "现场质量管理",
    module: "spc",
    children: [
      { key: "/spc", icon: <BarChartOutlined />, label: "SPC 控制图" },
      {
        key: "grp:msa",
        icon: <ToolOutlined />,
        label: "MSA 分析",
        children: [
          { key: "/msa/gauges", label: "量具管理" },
          { key: "/msa/studies", label: "研究管理" },
        ],
      },
      { key: "/quality-goals", icon: <AimOutlined />, label: "质量目标" },
      { key: "/internal-audits", icon: <SafetyOutlined />, label: "内部审核" },
      { key: "/management-reviews", icon: <TeamOutlined />, label: "管理评审" },
    ],
  },
  {
    key: "grp:customer",
    icon: <CustomerServiceOutlined />,
    label: "客户质量",
    module: "customer_quality",
    children: [
      { key: "/customer-quality", icon: <CustomerServiceOutlined />, label: "客诉/RMA" },
      { key: "/customer-audits", icon: <AuditOutlined />, label: "客户审核" },
      { key: "/capa", icon: <BugOutlined />, label: "8D/CAPA" },
    ],
  },
  {
    key: "grp:supplier",
    icon: <ShopOutlined />,
    label: "供应商质量",
    module: "supplier",
    children: [
      { key: "/suppliers", icon: <ShopOutlined />, label: "供应商管理" },
      { key: "/suppliers/quality", icon: <BarChartOutlined />, label: "供货质量看板" },
      { key: "/supplier-risk", icon: <WarningOutlined />, label: "供应商风险预警" },
      { key: "/supply-chain-risk-map", icon: <HeatMapOutlined />, label: "供应链风险地图" },
      { key: "/scars", icon: <AlertOutlined />, label: "SCAR 管理" },
      {
        key: "grp:iqc",
        icon: <ExperimentOutlined />,
        label: "来料检验",
        children: [
          { key: "/iqc/inspections", label: "检验单" },
          { key: "/iqc/materials", label: "物料管理" },
          { key: "/iqc/aql-optimization", icon: <SafetyCertificateOutlined />, label: "抽样方案优化" },
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
      { key: "/mes/dashboard", label: "MES 看板" },
      { key: "/mes/orders", label: "工单列表" },
      { key: "/mes/scrap", label: "报废/返工" },
      { key: "/mes/connections", label: "连接管理" },
    ],
  },
  {
    key: "grp:plm",
    icon: <BuildOutlined />,
    label: "PLM 集成",
    module: "plm",
    children: [
      { key: "/plm/dashboard", label: "PLM 看板" },
      { key: "/plm/parts", label: "零件列表" },
      { key: "/plm/change-orders", label: "变更单管理" },
      { key: "/plm/connections", label: "连接管理" },
    ],
  },
  {
    key: "grp:erp",
    icon: <SettingOutlined />,
    label: "ERP 集成",
    module: "erp",
    children: [
      { key: "/erp", label: "ERP 看板" },
      { key: "/erp/connections", label: "连接管理" },
      { key: "/erp/master-data", label: "主数据" },
      { key: "/erp/supply-chain", label: "供应链" },
      { key: "/erp/commercial", label: "销售与成本" },
      { key: "/erp/traceability", label: "批次追溯" },
    ],
  },
  {
    key: "grp:group",
    icon: <GlobalOutlined />,
    label: "集团管理",
    module: "group",
    children: [
      { key: "/group/dashboard", icon: <DashboardOutlined />, label: "集团仪表盘" },
      { key: "/group/comparison", icon: <RadarChartOutlined />, label: "工厂对比" },
      { key: "/group/suppliers", icon: <ShareAltOutlined />, label: "共享供应商" },
      { key: "/group/audits", icon: <AuditOutlined />, label: "跨厂审核" },
      { key: "/group/factories", icon: <BankOutlined />, label: "工厂管理" },
    ],
  },
];

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
  const { token: themeToken } = theme.useToken();
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
  }, [selectedKey]);

  // Filter menu groups by module permission; dashboard (no module) is always visible
  const visibleMenuItems = menuItems.filter(
    (item) => !item.module || canView(item.module as ModuleKey),
  );

  // Factory switcher visible when user has access to multiple factories (or all)
  const showFactorySwitcher = factoryScope?.accessible_factory_ids === null
    || (factoryScope?.accessible_factory_ids?.length ?? 0) > 1;

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
      >
        <div
          style={{
            height: 64,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontWeight: 700,
            fontSize: collapsed ? 16 : 20,
            color: themeToken.colorPrimary,
            borderBottom: `1px solid ${themeToken.colorBorderSecondary}`,
          }}
        >
          {collapsed ? "QMS" : "OpenQMS"}
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          openKeys={openKeys}
          onOpenChange={setOpenKeys}
          items={visibleMenuItems}
          onClick={({ key }) => {
            if (key.startsWith("grp:")) return;
            navigate(key);
          }}
          style={{ borderRight: 0 }}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            padding: "0 24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
          />
          <Space>
            {showFactorySwitcher && (
              <Select
                style={{ width: 200 }}
                value={currentFactoryId || undefined}
                placeholder="选择工厂"
                onChange={(v) => setCurrentFactoryId(v)}
                suffixIcon={<SwapOutlined />}
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
              placeholder="全部产品线"
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
            <Dropdown
            menu={{
              items: [
                { key: "logout", icon: <LogoutOutlined />, label: "退出登录", onClick: () => { logout(); navigate("/login"); } },
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
        <Content style={{ margin: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}

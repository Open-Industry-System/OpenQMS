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
} from "@ant-design/icons";
import { useAuthStore } from "../../store/authStore";
import { useProductLineStore } from "../../store/productLineStore";

const { Header, Sider, Content } = Layout;

// 所有菜单 key 列表（用于最长前缀匹配）
const MENU_KEYS = [
  "/dashboard",
  "/fmea", "/control-plans", "/apqp", "/ppap",
  "/special-characteristics", "/special-characteristics/matrix", "/special-characteristics/traceability",
  "/spc", "/msa/gauges", "/msa/studies", "/quality-goals",
  "/internal-audits", "/management-reviews",
  "/customer-quality", "/customer-audits", "/capa",
  "/suppliers", "/suppliers/quality",
  "/iqc/inspections", "/iqc/materials", "/scars",
  "/knowledge-graph",
  "/change-impact",
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
  "/iqc/inspections": ["grp:supplier", "grp:iqc"],
  "/iqc/materials": ["grp:supplier", "grp:iqc"],
  "/scars": ["grp:supplier"],
  "/knowledge-graph": ["grp:planning"],
  "/change-impact": ["grp:planning"],
};

function getSelectedMenuKey(pathname: string): string {
  const matched = MENU_KEYS
    .filter((key) => pathname === key || pathname.startsWith(key + "/"))
    .sort((a, b) => b.length - a.length);
  return matched[0] || "/dashboard";
}

const menuItems = [
  { key: "/dashboard", icon: <DashboardOutlined />, label: "仪表盘" },
  {
    key: "grp:planning",
    icon: <ExperimentOutlined />,
    label: "前期质量策划",
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
    children: [
      { key: "/suppliers", icon: <ShopOutlined />, label: "供应商管理" },
      { key: "/suppliers/quality", icon: <BarChartOutlined />, label: "供货质量看板" },
      { key: "/scars", icon: <AlertOutlined />, label: "SCAR 管理" },
      {
        key: "grp:iqc",
        icon: <ExperimentOutlined />,
        label: "来料检验",
        children: [
          { key: "/iqc/inspections", label: "检验单" },
          { key: "/iqc/materials", label: "物料管理" },
        ],
      },
    ],
  },
];

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const { token: themeToken } = theme.useToken();
  const { productLines, selected, setSelected, load } = useProductLineStore();
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
          items={menuItems}
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

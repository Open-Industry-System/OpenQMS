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
  InspectionOutlined,
  CustomerServiceOutlined,
} from "@ant-design/icons";
import { useAuthStore } from "../../store/authStore";
import { useProductLineStore } from "../../store/productLineStore";

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: "/dashboard", icon: <DashboardOutlined />, label: "仪表盘" },
  { key: "/fmea", icon: <FileTextOutlined />, label: "FMEA管理" },
  { key: "/control-plans", icon: <FileTextOutlined />, label: "控制计划" },
  { key: "/quality-goals", icon: <AimOutlined />, label: "质量目标" },
  { key: "/internal-audits", icon: <SafetyOutlined />, label: "内部审核" },
  { key: "/suppliers", icon: <ShopOutlined />, label: "供应商管理" },
  {
    key: "/iqc",
    icon: <InspectionOutlined />,
    label: "来料检验",
    children: [
      { key: "/iqc/inspections", label: "检验单" },
      { key: "/iqc/materials", label: "物料管理" },
    ],
  },
  { key: "/customer-quality", icon: <CustomerServiceOutlined />, label: "客户质量" },
  { key: "/spc", icon: <FileTextOutlined />, label: "SPC控制图" },
  { key: "/special-characteristics", icon: <SafetyCertificateOutlined />, label: "特殊特性" },
  { key: "/special-characteristics/traceability", icon: <SafetyCertificateOutlined />, label: "贯穿追踪" },
  { key: "/management-reviews", icon: <TeamOutlined />, label: "管理评审" },
  { key: "/capa", icon: <BugOutlined />, label: "8D/CAPA" },
  {
    key: "/msa",
    icon: <ToolOutlined />,
    label: "MSA分析",
    children: [
      { key: "/msa/gauges", icon: <ToolOutlined />, label: "量具管理" },
      { key: "/msa/studies", icon: <ExperimentOutlined />, label: "研究管理" },
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

  const selectedKey = "/" + location.pathname.split("/")[1];

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        style={{ background: themeToken.colorBgContainer }}
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
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ borderRight: 0 }}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            padding: "0 24px",
            background: themeToken.colorBgContainer,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            borderBottom: `1px solid ${themeToken.colorBorderSecondary}`,
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

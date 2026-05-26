import { useState } from "react";
import { Tabs } from "antd";
import { BarChartOutlined, UserOutlined, CompareOutlined } from "@ant-design/icons";
import DashboardView from "./components/DashboardView";
import SupplierDetailView from "./components/SupplierDetailView";
import CompareView from "./components/CompareView";

export default function SupplierQualityPage() {
  const [activeTab, setActiveTab] = useState("dashboard");

  return (
    <div>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: "dashboard",
            label: (
              <span>
                <BarChartOutlined />
                汇总看板
              </span>
            ),
            children: <DashboardView />,
          },
          {
            key: "detail",
            label: (
              <span>
                <UserOutlined />
                供应商详情
              </span>
            ),
            children: <SupplierDetailView />,
          },
          {
            key: "compare",
            label: (
              <span>
                <CompareOutlined />
                对比分析
              </span>
            ),
            children: <CompareView />,
          },
        ]}
      />
    </div>
  );
}

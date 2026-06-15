import { useState } from "react";
import { Tabs } from "antd";
import { useTranslation } from "react-i18next";
import { BarChartOutlined, UserOutlined, SwapOutlined } from "@ant-design/icons";
import DashboardView from "./components/DashboardView";
import SupplierDetailView from "./components/SupplierDetailView";
import CompareView from "./components/CompareView";

export default function SupplierQualityPage() {
  const { t } = useTranslation("supplier");
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
                {t("quality.tabs.dashboard")}
              </span>
            ),
            children: <DashboardView />,
          },
          {
            key: "detail",
            label: (
              <span>
                <UserOutlined />
                {t("quality.tabs.detail")}
              </span>
            ),
            children: <SupplierDetailView />,
          },
          {
            key: "compare",
            label: (
              <span>
                <SwapOutlined />
                {t("quality.tabs.compare")}
              </span>
            ),
            children: <CompareView />,
          },
        ]}
      />
    </div>
  );
}

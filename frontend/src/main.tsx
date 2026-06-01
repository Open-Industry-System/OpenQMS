import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ConfigProvider, App as AntdApp } from "antd";
import zhCN from "antd/locale/zh_CN";
import App from "./App";
import { darkTheme } from "./utils/darkTheme";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={darkTheme}>
      <BrowserRouter>
        <AntdApp>
          <App />
        </AntdApp>
      </BrowserRouter>
    </ConfigProvider>
  </React.StrictMode>
);

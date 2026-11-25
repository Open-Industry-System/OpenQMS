import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import "./styles/design-system.css";
import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ConfigProvider, App as AntdApp } from "antd";
import type { Locale } from "antd/es/locale";
import deDE from "antd/locale/de_DE";
import dayjs from "dayjs";
import "dayjs/locale/de";
import "dayjs/locale/en";
import i18n from "./i18n";
import App from "./App";
import { darkTheme } from "./utils/darkTheme";

function updateHtmlLang(lang: string) {
  document.documentElement.lang = lang === "en-US" ? "en" : "de";
  document.title = i18n.t("app.title");
}

function I18nConfigProvider({ children }: { children: React.ReactNode }) {
  const [antdLocale, setAntdLocale] = useState<Locale>(deDE);

  useEffect(() => {
    const apply = async (lang: string) => {
      const loader: () => Promise<Locale> =
        lang === "en-US"
          ? () => import("antd/locale/en_US").then((m) => m.default)
          : () => Promise.resolve(deDE);
      const locale = await loader();
      setAntdLocale(locale);
      dayjs.locale(lang === "en-US" ? "en" : "de");
      updateHtmlLang(lang);
    };
    apply(i18n.language);
    const handler = (lang: string) => apply(lang);
    i18n.on("languageChanged", handler);
    return () => {
      i18n.off("languageChanged", handler);
    };
  }, []);

  return (
    <ConfigProvider locale={antdLocale} theme={darkTheme}>
      {children}
    </ConfigProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <I18nConfigProvider>
        <AntdApp>
          <App />
        </AntdApp>
      </I18nConfigProvider>
    </BrowserRouter>
  </React.StrictMode>,
);

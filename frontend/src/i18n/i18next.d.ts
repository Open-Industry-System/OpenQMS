import "i18next";
import zhCommon from "../locales/zh-CN/common.json";
import zhLogin from "../locales/zh-CN/login.json";
import zhLayout from "../locales/zh-CN/layout.json";

declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "common";
    resources: {
      common: typeof zhCommon;
      login: typeof zhLogin;
      layout: typeof zhLayout;
    };
  }
}

import "react-i18next";

declare module "react-i18next" {
  interface CustomTypeOptions {
    defaultNS: "common";
    resources: Record<string, Record<string, string>>;
  }
}

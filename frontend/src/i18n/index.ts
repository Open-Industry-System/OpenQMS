import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import zhCommon from "../locales/zh-CN/common.json";
import zhLogin from "../locales/zh-CN/login.json";
import zhLayout from "../locales/zh-CN/layout.json";
import enCommon from "../locales/en-US/common.json";
import enLogin from "../locales/en-US/login.json";
import enLayout from "../locales/en-US/layout.json";

export const SUPPORTED_LANGUAGES = ["zh-CN", "en-US"] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

const resources = {
  "zh-CN": {
    common: zhCommon,
    login: zhLogin,
    layout: zhLayout,
  },
  "en-US": {
    common: enCommon,
    login: enLogin,
    layout: enLayout,
  },
};

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: "zh-CN",
    supportedLngs: SUPPORTED_LANGUAGES,
    detection: {
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
      lookupLocalStorage: "openqms_locale",
    },
    interpolation: {
      escapeValue: false,
    },
    defaultNS: "common",
    ns: ["common", "login", "layout"],
    react: {
      useSuspense: false,
    },
  });

export default i18n;

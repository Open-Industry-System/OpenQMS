import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

const modules = import.meta.glob<{ default: Record<string, unknown> }>(
  "../locales/**/*.json",
  { eager: true, import: "default" }
);

const resources: Record<string, Record<string, Record<string, unknown>>> = {};
for (const [path, content] of Object.entries(modules)) {
  const match = path.match(/\/locales\/([^/]+)\/([^/]+)\.json$/);
  if (!match) continue;
  const [, lng, ns] = match;
  if (!resources[lng]) resources[lng] = {};
  resources[lng][ns] = content;
}

export const SUPPORTED_LANGUAGES = ["de-DE", "en-US"] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: "de-DE",
    supportedLngs: SUPPORTED_LANGUAGES,
    detection: {
      order: ["localStorage"],
      caches: ["localStorage"],
      lookupLocalStorage: "openqms_locale",
    },
    interpolation: {
      escapeValue: false,
    },
    defaultNS: "common",
    ns: Object.keys(resources["de-DE"] || {}),
    react: {
      useSuspense: false,
    },
  });

export default i18n;

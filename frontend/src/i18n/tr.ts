import { useTranslation } from "react-i18next";
import i18n from "./index";

/**
 * Inline bilingual text for strings that have no translation key.
 * Returns the English text when the UI language is en-US, otherwise German.
 */
export function tr(de: string, en: string): string {
  return i18n.language === "en-US" ? en : de;
}

/** Hook variant: re-renders the component when the language changes. */
export function useTr(): typeof tr {
  useTranslation();
  return tr;
}

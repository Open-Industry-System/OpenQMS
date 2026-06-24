import { I18nextProvider } from 'react-i18next';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import zhPFMEA from '../../../locales/zh-CN/pfmea.json';

const i18nTest = i18n.createInstance();
i18nTest
  .use(initReactI18next)
  .init({
    lng: 'zh-CN',
    fallbackLng: 'zh-CN',
    interpolation: { escapeValue: false },
    resources: {
      'zh-CN': { pfmea: zhPFMEA },
    },
  });

export function I18nTestWrapper({ children }: { children: React.ReactNode }) {
  return <I18nextProvider i18n={i18nTest}>{children}</I18nextProvider>;
}

import { I18nextProvider } from 'react-i18next';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import zhPFMEA from '../../../locales/de-DE/pfmea.json';

const i18nTest = i18n.createInstance();
i18nTest
  .use(initReactI18next)
  .init({
    lng: 'de-DE',
    fallbackLng: 'de-DE',
    interpolation: { escapeValue: false },
    resources: {
      'de-DE': { pfmea: zhPFMEA },
    },
  });

export function I18nTestWrapper({ children }: { children: React.ReactNode }) {
  return <I18nextProvider i18n={i18nTest}>{children}</I18nextProvider>;
}

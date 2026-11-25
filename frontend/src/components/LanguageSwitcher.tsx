import { Segmented } from "antd";
import i18n from "../i18n";

export default function LanguageSwitcher() {
  return (
    <Segmented
      value={i18n.language}
      onChange={(value) => i18n.changeLanguage(value as string)}
      options={[
        { label: "Deutsch", value: "de-DE" },
        { label: "English", value: "en-US" },
      ]}
    />
  );
}
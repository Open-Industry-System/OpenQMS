import "@testing-library/jest-dom/vitest";
import i18n from "./i18n";

// Run tests in English so component tests don't depend on Chinese UI strings.
i18n.changeLanguage("en-US");

// Ant Design requires matchMedia in jsdom
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

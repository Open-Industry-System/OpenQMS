import { readFileSync } from "node:fs";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import PublicHomePage from "./PublicHomePage";
import i18n from "../../i18n";

const publicHomeStyles = readFileSync("src/pages/public/PublicHomePage.css", "utf8");

const auth = vi.hoisted(() => ({ token: null as string | null }));
vi.mock("../../store/authStore", () => ({
  useAuthStore: (selector: (state: typeof auth) => unknown) => selector(auth),
}));

function renderPage() {
  return render(<MemoryRouter><PublicHomePage /></MemoryRouter>);
}

beforeEach(async () => {
  auth.token = null;
  vi.unstubAllEnvs();
  await i18n.changeLanguage("en-US");
});

describe("PublicHomePage", () => {
  it("renders the AI-first public narrative and semantic sections", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: "Turn quality data into actionable intelligence." })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /quality engineer's copilot/i })).toBeInTheDocument();
    expect(document.querySelector("main")).toBeInTheDocument();
    expect(document.querySelectorAll("main section")).toHaveLength(5);
    expect(document.querySelector('[aria-hidden="true"]')).toBeInTheDocument();
  });

  it("uses safe links for the real GitHub repository", () => {
    renderPage();
    const links = screen.getAllByRole("link", { name: /github/i });
    for (const link of links) {
      expect(link).toHaveAttribute("href", "https://github.com/Open-Industry-System/OpenQMS");
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    }
  });

  it("exposes safe GitHub and docs links in the semantic footer", () => {
    renderPage();
    const footer = within(screen.getByRole("contentinfo"));
    const github = footer.getByRole("link", { name: "View GitHub" });
    const docs = footer.getByRole("link", { name: "Read the docs" });

    expect(github).toHaveAttribute("href", "https://github.com/Open-Industry-System/OpenQMS");
    expect(docs).toHaveAttribute("href", "https://github.com/Open-Industry-System/OpenQMS/tree/main/docs");
    for (const link of [github, docs]) {
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    }
  });

  it("hides the demo CTA when demo config is disabled", () => {
    renderPage();
    expect(screen.queryByRole("link", { name: "Online demo" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Enter system" })[0]).toHaveAttribute("href", "/login");
  });

  it("shows a Viewer demo CTA only for complete config", () => {
    vi.stubEnv("VITE_PUBLIC_DEMO_ENABLED", "true");
    vi.stubEnv("VITE_PUBLIC_DEMO_USERNAME", "viewer");
    vi.stubEnv("VITE_PUBLIC_DEMO_PASSWORD", "demo-test-password");
    renderPage();
    expect(screen.getByRole("link", { name: "Online demo" })).toHaveAttribute("href", "/login?demo=viewer");
  });

  it("keeps the Viewer route separate from the configured username", () => {
    vi.stubEnv("VITE_PUBLIC_DEMO_ENABLED", "true");
    vi.stubEnv("VITE_PUBLIC_DEMO_USERNAME", "readonly-demo");
    vi.stubEnv("VITE_PUBLIC_DEMO_PASSWORD", "demo-test-password");
    renderPage();
    expect(screen.getByRole("link", { name: "Online demo" })).toHaveAttribute("href", "/login?demo=viewer");
  });

  it("sends authenticated users to the dashboard", () => {
    auth.token = "present";
    renderPage();
    expect(screen.getAllByRole("link", { name: "Enter system" })[0]).toHaveAttribute("href", "/dashboard");
  });

  it("keeps required navigation controls in bounded rows on narrow phones", () => {
    const narrowPhoneStyles = publicHomeStyles.slice(
      publicHomeStyles.indexOf("@media (max-width: 400px)"),
      publicHomeStyles.indexOf("@media (prefers-reduced-motion: reduce)"),
    );

    expect(narrowPhoneStyles).toMatch(
      /\.public-home__nav\s*\{[^}]*display:\s*grid;[^}]*grid-template-columns:\s*minmax\(0, 1fr\);/s,
    );
    expect(narrowPhoneStyles).toMatch(
      /\.public-home__nav-actions\s*\{[^}]*width:\s*100%;[^}]*justify-content:\s*space-between;/s,
    );
  });

  it("switches the visible copy to Chinese", async () => {
    renderPage();
    fireEvent.click(screen.getByText("中文"));
    expect(await screen.findByRole("heading", { name: "让质量数据，转化为可执行智能。" })).toBeInTheDocument();
  });
});

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import PublicHomePage from "./PublicHomePage";
import i18n from "../../i18n";

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

  it("switches the visible copy to Chinese", async () => {
    renderPage();
    fireEvent.click(screen.getByText("中文"));
    expect(await screen.findByRole("heading", { name: "让质量数据，转化为可执行智能。" })).toBeInTheDocument();
  });
});

import { describe, expect, it } from "vitest";
import { getPublicDemoConfig } from "./publicDemo";

describe("getPublicDemoConfig", () => {
  it("is disabled unless the flag is exactly true", () => {
    expect(getPublicDemoConfig({
      VITE_PUBLIC_DEMO_ENABLED: "false",
      VITE_PUBLIC_DEMO_USERNAME: "viewer",
      VITE_PUBLIC_DEMO_PASSWORD: "demo-test-password",
    })).toBeNull();
  });

  it.each([
    { VITE_PUBLIC_DEMO_ENABLED: "true", VITE_PUBLIC_DEMO_USERNAME: "", VITE_PUBLIC_DEMO_PASSWORD: "demo-test-password" },
    { VITE_PUBLIC_DEMO_ENABLED: "true", VITE_PUBLIC_DEMO_USERNAME: "viewer", VITE_PUBLIC_DEMO_PASSWORD: "" },
    { VITE_PUBLIC_DEMO_ENABLED: "true", VITE_PUBLIC_DEMO_USERNAME: "viewer", VITE_PUBLIC_DEMO_PASSWORD: "   " },
  ])("fails closed when credentials are incomplete", (env) => {
    expect(getPublicDemoConfig(env)).toBeNull();
  });

  it("returns trimmed username and the original password when fully configured", () => {
    expect(getPublicDemoConfig({
      VITE_PUBLIC_DEMO_ENABLED: "true",
      VITE_PUBLIC_DEMO_USERNAME: " viewer ",
      VITE_PUBLIC_DEMO_PASSWORD: "demo-test-password",
    })).toEqual({ username: "viewer", password: "demo-test-password" });
  });
});

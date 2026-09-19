import { describe, expect, it } from "vitest";
import { getPublicDemoConfig } from "./publicDemo";

const additionalAccounts = JSON.stringify([
  { username: "manager", password: "manager-sentinel" },
  { username: "engineer", password: "engineer-sentinel" },
]);

const completeEnv = {
  VITE_PUBLIC_DEMO_ENABLED: "true",
  VITE_PUBLIC_DEMO_USERNAME: " viewer ",
  VITE_PUBLIC_DEMO_PASSWORD: "viewer-sentinel",
};

describe("getPublicDemoConfig", () => {
  it.each(["false", "True", " true", "true ", undefined])("is disabled unless the flag is exactly true (%s)", (enabled) => {
    expect(getPublicDemoConfig({
      ...completeEnv,
      VITE_PUBLIC_DEMO_ENABLED: enabled,
    })).toBeNull();
  });

  it.each([
    { VITE_PUBLIC_DEMO_ENABLED: "true", VITE_PUBLIC_DEMO_USERNAME: "", VITE_PUBLIC_DEMO_PASSWORD: "viewer-sentinel" },
    { VITE_PUBLIC_DEMO_ENABLED: "true", VITE_PUBLIC_DEMO_USERNAME: "viewer", VITE_PUBLIC_DEMO_PASSWORD: "" },
    { VITE_PUBLIC_DEMO_ENABLED: "true", VITE_PUBLIC_DEMO_USERNAME: "viewer", VITE_PUBLIC_DEMO_PASSWORD: "   " },
  ])("fails closed when Viewer credentials are incomplete", (env) => {
    expect(getPublicDemoConfig(env)).toBeNull();
  });

  it("keeps Viewer-only configuration backward compatible", () => {
    expect(getPublicDemoConfig(completeEnv)).toEqual({
      username: "viewer",
      password: "viewer-sentinel",
    });
  });

  it("returns all configured additional accounts in stable role order", () => {
    expect(getPublicDemoConfig({
      ...completeEnv,
      VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS: additionalAccounts,
    })).toEqual({
      username: "viewer",
      password: "viewer-sentinel",
      additionalAccounts: [
        { username: "engineer", password: "engineer-sentinel" },
        { username: "manager", password: "manager-sentinel" },
      ],
    });
  });

  it.each([
    ["malformed JSON", "["],
    ["an incomplete account set", JSON.stringify([
      { username: "engineer", password: "engineer-sentinel" },
    ])],
    ["a duplicate username", JSON.stringify([
      { username: "engineer", password: "engineer-sentinel" },
      { username: "engineer", password: "engineer-sentinel-duplicate" },
    ])],
    ["a blank additional password", JSON.stringify([
      { username: "engineer", password: "   " },
      { username: "manager", password: "manager-sentinel" },
    ])],
    ["a privileged admin account", JSON.stringify([
      { username: "engineer", password: "engineer-sentinel" },
      { username: "admin", password: "admin-sentinel" },
    ])],
    ["a privileged groupadmin account", JSON.stringify([
      { username: "manager", password: "manager-sentinel" },
      { username: "groupadmin", password: "groupadmin-sentinel" },
    ])],
  ])("fails closed for %s", (_reason, VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS) => {
    expect(getPublicDemoConfig({
      ...completeEnv,
      VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS,
    })).toBeNull();
  });
});

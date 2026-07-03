import { test, expect } from "@playwright/test";
import { getSeedState } from "../../fixtures/seed-state";

test("seed-state has all known records", async () => {
  const s = await getSeedState();
  expect(s.factories.length).toBeGreaterThanOrEqual(2);
  expect(s.accounts.map(a => a.username)).toEqual(
    expect.arrayContaining(["admin", "engineer", "manager", "viewer", "groupadmin"])
  );
  expect(s.known_docs.pfmea).toContain("PFMEA-E2E-001");
  expect(s.known_docs.capa).toContain("8D-E2E-001");
});

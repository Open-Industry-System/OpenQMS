import { test, expect } from "@playwright/test";
import { loginAs } from "../../fixtures/auth";
import { loginForToken } from "../../helpers/api-client";


test("loginForToken reuses global storage state before password login", async () => {
  const token = await loginForToken("engineer", "intentionally-wrong-password");
  expect(token.split(".")).toHaveLength(3);
});

test("loginAs reuses global storage state without a password login", async ({ page }) => {
  let loginRequests = 0;
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/api/auth/login") loginRequests += 1;
  });

  await loginAs(page, "engineer");

  expect(loginRequests).toBe(0);
});

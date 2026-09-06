import { test, expect } from "@playwright/test";
import { loginForToken } from "../../helpers/api-client";


test("loginForToken reuses global storage state before password login", async () => {
  const token = await loginForToken("engineer", "intentionally-wrong-password");
  expect(token.split(".")).toHaveLength(3);
});

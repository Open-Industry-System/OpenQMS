import type { Page } from "@playwright/test";
import { accountPassword } from "./seed-state";

const STORAGE_DIR = "e2e/.storage-state";

export async function loginAs(page: Page, username: string): Promise<void> {
  const password = await accountPassword(username);
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByPlaceholder(/用户名|username/i).fill(username);
  await page.getByPlaceholder(/密码|password/i).fill(password);
  await page.getByRole("button", { name: /登\s*录|login/i }).click();
  await page.waitForURL(/\/dashboard|\/capa|\/fmea/);
}

export function storageStatePath(username: string): string {
  return `${STORAGE_DIR}/${username}.json`;
}

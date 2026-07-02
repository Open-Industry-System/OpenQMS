import type { Page, Locator } from "@playwright/test";

export async function rowByDocNo(page: Page, docNo: string): Promise<Locator> {
  return page.locator(`[data-e2e="row-${docNo}"]`);
}

export async function clickByTestid(page: Page, testid: string): Promise<void> {
  await page.locator(`[data-e2e="${testid}"]`).click();
}

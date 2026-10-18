import { test, expect } from "@playwright/test";

const backend = process.env.AGENT_BACKEND_URL!;
const clean = "OpenQMS controlled attachment E2E clean fixture.\n";
const eicar = "X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*";

async function acceptance(page: import("@playwright/test").Page, action: string, nonce: string) {
  const response = await page.request.post(`${backend}/__agent_attachment_acceptance/${action}`, {
    headers: { "X-Acceptance-Nonce": nonce },
  });
  expect(response.ok(), action).toBeTruthy();
}

test("actual ClamAV task attachments are scan-gated, downloaded once, and withdrawn", async ({ page, context }) => {
  const configResponse = await page.request.get(`${backend}/__agent_attachment_acceptance/config`, {
    headers: { "X-Acceptance-Nonce": process.env.AGENT_HARNESS_NONCE! },
  });
  expect(configResponse.ok()).toBeTruthy();
  const config = await configResponse.json();
  expect(config.nonce).toBe(process.env.AGENT_HARNESS_NONCE!);
  const login = await page.request.post(`${backend}/api/auth/login`, { headers: { "X-Tenant-ID": config.tenant }, data: {
    username: config.username, password: config.password,
  }});
  expect(login.ok()).toBeTruthy();
  const tokens = await login.json();
  await context.addInitScript(({ token, refresh, tenant }) => {
    localStorage.setItem("access_token", token);
    localStorage.setItem("refresh_token", refresh);
    localStorage.setItem("tenant_slug", tenant);
    localStorage.setItem("i18nextLng", "zh");
  }, { token: tokens.access_token, refresh: tokens.refresh_token, tenant: config.tenant });

  const attachmentPosts: string[] = [];
  page.on("request", request => {
    if (new URL(request.url()).pathname.endsWith(`/agent/tasks/${config.task_id}/attachments`) && request.method() === "POST")
      attachmentPosts.push(request.postData() ?? "");
  });
  const authMe = page.waitForResponse(response => response.url().includes("/api/auth/me") && response.status() === 200);
  await page.goto(`/capa/${config.report_id}`);
  await authMe;
  await page.getByRole("button", { name: "Agent 任务", exact: true }).click();
  const chooser = page.getByRole("combobox", { name: "选择任务" });
  await expect(chooser.locator(`option[value="${config.task_id}"]`)).toBeAttached();
  await chooser.selectOption(config.task_id);
  await expect(page.getByText("任务私有附件", { exact: true })).toBeVisible();

  await acceptance(page, "off", config.nonce);
  await page.getByRole("button", { name: "关闭任务侧栏" }).click();
  await page.getByRole("button", { name: "Agent 任务", exact: true }).click();
  await expect(page.getByText("任务私有附件", { exact: true })).toHaveCount(0);
  expect(attachmentPosts).toEqual([]);
  await acceptance(page, "on", config.nonce);
  await page.getByRole("button", { name: "关闭任务侧栏" }).click();
  await page.getByRole("button", { name: "Agent 任务", exact: true }).click();
  await expect(page.getByText("任务私有附件", { exact: true })).toBeVisible();

  const file = page.locator('input[type="file"]');
  await file.setInputFiles({ name: "clean.txt", mimeType: "text/plain", buffer: Buffer.from(clean) });
  await expect(page.getByText("clean.txt", { exact: true })).toBeVisible();
  const cleanResponse = page.waitForResponse(response => response.request().method() === "POST"
    && new URL(response.url()).pathname.endsWith(`/agent/tasks/${config.task_id}/attachments`) && response.status() === 200);
  await page.getByRole("button", { name: "上传附件" }).click();
  const cleanJson = await (await cleanResponse).json();
  expect(Object.keys(cleanJson).sort()).toEqual(["attachment_id", "byte_size", "created_at", "display_name", "expires_at", "extension", "status", "updated_at"]);
  expect(cleanJson).toMatchObject({ display_name: "clean.txt", extension: "txt", byte_size: Buffer.byteLength(clean), status: "available" });
  expect(Date.parse(cleanJson.created_at)).not.toBeNaN();
  expect(Date.parse(cleanJson.updated_at)).not.toBeNaN();
  await expect(page.getByText("clean.txt · available", { exact: true })).toBeVisible();
  const [download] = await Promise.all([
    page.waitForEvent("download"), page.getByRole("button", { name: "下载", exact: true }).click(),
  ]);
  expect(download.suggestedFilename()).toBe("clean.txt");
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(chunk as Buffer);
  expect(Buffer.concat(chunks).toString()).toBe(clean);
  await expect(page.locator("iframe, embed, object, img, video, audio")).toHaveCount(0);

  await file.setInputFiles({ name: "eicar.txt", mimeType: "text/plain", buffer: Buffer.from(eicar) });
  const eicarResponse = page.waitForResponse(response => response.request().method() === "POST"
    && new URL(response.url()).pathname.endsWith(`/agent/tasks/${config.task_id}/attachments`) && response.status() === 422);
  await page.getByRole("button", { name: "上传附件" }).click();
  expect(await (await eicarResponse).json()).toEqual({ detail: "ATTACHMENT_MALWARE_REJECTED" });
  await expect(page.getByText("eicar.txt · available", { exact: true })).toHaveCount(0);

  await acceptance(page, "scanner-unavailable", config.nonce);
  await file.setInputFiles({ name: "scanner.txt", mimeType: "text/plain", buffer: Buffer.from(clean) });
  const scannerResponse = page.waitForResponse(response => response.request().method() === "POST"
    && new URL(response.url()).pathname.endsWith(`/agent/tasks/${config.task_id}/attachments`) && response.status() === 503);
  await page.getByRole("button", { name: "上传附件" }).click();
  expect(await (await scannerResponse).json()).toEqual({ detail: "ATTACHMENT_SCANNER_UNAVAILABLE" });
  await acceptance(page, "scanner-restore", config.nonce);

  await file.setInputFiles({ name: "discard.txt", mimeType: "text/plain", buffer: Buffer.from(clean) });
  await expect(page.getByText("discard.txt", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "关闭任务侧栏" }).click();
  await page.getByRole("button", { name: "Agent 任务", exact: true }).click();
  await expect(page.getByText("discard.txt", { exact: true })).toHaveCount(0);
  await acceptance(page, "withdraw", config.nonce);
  await page.getByRole("button", { name: "关闭任务侧栏" }).click();
  await page.getByRole("button", { name: "Agent 任务", exact: true }).click();
  await expect(page.getByText("任务私有附件", { exact: true })).toHaveCount(0);
  await expect(page.getByText("clean.txt", { exact: true })).toHaveCount(0);
});

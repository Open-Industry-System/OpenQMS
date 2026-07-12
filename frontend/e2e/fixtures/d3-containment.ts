import { test as base, Page, APIRequestContext } from '@playwright/test';
import * as playwright from 'playwright';
import { readFileSync } from 'fs';
import path from 'path';
// 复用现有认证 fixture（loginAs 读 seed-state 真实密码）+ API helpers
import { loginAs } from './auth';
import { loginForToken, E2E_API_BASE_URL } from '../helpers/api-client';

// P1-4 修复：每状态变更测试独享 CAPA（7 个），避免共用导致 manual 推进 D4 后其他测试失效
export const D3_CAPA_DOC_NO = '8D-E2E-D3-001';            // 主流程（D2_DESCRIPTION → 推进到 D3）
export const D3_CAPA_DOC_NO_UNIMPORTED = '8D-E2E-D3-002';  // 闸口拒绝测试（D3_INTERIM 未导入）
export const D3_CAPA_DOC_NO_REPORTED = '8D-E2E-D3-003';   // manual execution 推进 D4（D3_INTERIM + done report）
export const D3_CAPA_DOC_NO_EXEC_FORM = '8D-E2E-D3-004';  // 非法 URL 422 测试（D3_INTERIM + done report）
export const D3_CAPA_DOC_NO_VIEWER = '8D-E2E-D3-005';     // viewer 只读测试（D3_INTERIM + done report）
export const D3_CAPA_DOC_NO_NOCREDS = '8D-E2E-D3-006';    // 无凭证反向测试（D3_INTERIM）
export const D3_CAPA_DOC_NO_CROSSFACTORY = '8D-E2E-D3-007'; // 跨工厂测试（D3_INTERIM + done report + advice）
export const D3_MATERIAL_CODE = 'DC-DC-100-E2E';

// 从 e2e-env.json（global.setup.ts 已写）读 hasLLM——非查不存在的端点
export function noLlmCreds(): boolean {
  const envPath = path.resolve(process.cwd(), 'e2e/.storage-state/e2e-env.json');
  try {
    const env = JSON.parse(readFileSync(envPath, 'utf-8'));
    return !env.hasLLM;
  } catch (_err) {
    return true;  // 读不到 → 视为无凭证（skip）
  }
}

type D3Fixtures = {
  capaId: string;            // 真实 UUID（document_no 解析）
  authedRequest: APIRequestContext;  // 带 engineer token 的 request
};

export const test = base.extend<D3Fixtures>({
  // P1-3 修复：解析 document_no → UUID。CAPA 列表 API 无 document_no 查询参数（传了会被忽略），
  // 且默认只返回前 20 条——请求 page_size=1000 后客户端按 document_no 精确过滤。
  capaId: async ({ request }, provide) => {
    await provide(await capaIdFor(request, D3_CAPA_DOC_NO));
  },
  // 带 engineer token 的 request（loginForToken 换真实 token）
  authedRequest: async ({ playwright }, provide) => {
    const { accountPassword } = await import('./seed-state');
    const pw = await accountPassword('engineer');
    const token = await loginForToken('engineer', pw);
    const ctx = await playwright.request.newContext({
      baseURL: E2E_API_BASE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    await provide(ctx);
    await ctx.dispose();
  },
});

// P1-3 修复：document_no → UUID 解析 helper（page_size=1000 客户端过滤，CAPA 列表无 document_no 参数）
export async function capaIdFor(request: APIRequestContext, docNo: string): Promise<string> {
  const { accountPassword } = await import('./seed-state');
  const pw = await accountPassword('engineer');
  const token = await loginForToken('engineer', pw);
  const resp = await request.get(`${E2E_API_BASE_URL}/capa`, {
    headers: { Authorization: `Bearer ${token}` },
    params: { page: 1, page_size: 1000 },
  });
  const json = await resp.json();
  const item = (json.items || []).find((c: any) => c.document_no === docNo);
  if (!item) throw new Error(`[d3] seed CAPA ${docNo} 未找到，先跑 seed_e2e`);
  return item.report_id;
}

// P1-3 修复：groupadmin 默认 effective factory 为 None，跨工厂测试需显式传 SH factory UUID。
// groupadmin 关联 [DC-FACT-E2E, SH-FACT-E2E]；此处取 SH 工厂 UUID 用于切换工厂视角。
export async function shFactoryId(_request: APIRequestContext): Promise<string> {
  const { getSeedState } = await import('./seed-state');
  const state = await getSeedState();
  const sh = state.factories.find((f) => f.code === 'SH-FACT-E2E');
  if (!sh) throw new Error('[d3] SH-FACT-E2E factory 未 seed');
  return sh.id;
}

export const expect = test.expect;
export { loginAs };

// re-export 供 spec 直接 import（避免 spec 重复 import 多个文件）
export { loginForToken, E2E_API_BASE_URL } from '../helpers/api-client';
export { accountPassword } from './seed-state';
export { playwright };

// goToCapa 用 UUID 直接访问（路由 /capa/:id 是 UUID，无 document_no 重定向契约）
export async function goToCapa(page: Page, capaId: string): Promise<void> {
  await page.goto(`/capa/${capaId}`);
  await page.waitForLoadState('networkidle');
}

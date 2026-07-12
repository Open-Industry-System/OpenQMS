// P1-3 修复：spec 在 specs/m1-core/，fixture 在 fixtures/，相对路径为 ../../fixtures/
import {
  test, expect, loginAs, goToCapa, noLlmCreds, capaIdFor, shFactoryId,
  loginForToken, E2E_API_BASE_URL, accountPassword, playwright,
  D3_CAPA_DOC_NO_UNIMPORTED, D3_CAPA_DOC_NO_REPORTED, D3_CAPA_DOC_NO_EXEC_FORM,
  D3_CAPA_DOC_NO_VIEWER, D3_CAPA_DOC_NO_NOCREDS, D3_CAPA_DOC_NO_CROSSFACTORY,
} from '../../fixtures/d3-containment';
import type { APIRequestContext } from '@playwright/test';

test.describe('D3 containment', () => {
  // P1-4 修复：移除 describe 级统一 skip，让无凭证反向测试能在无 LLM 环境运行；
  // 依赖 done report 的测试各自 test.skip(noLlmCreds())。

  test('D3 containment main flow', async ({ page, browser, authedRequest, capaId }) => {
    // 主流程依赖 LLM 生成 done report + advice
    test.skip(noLlmCreds(), 'No AI credentials');
    // P2-1 修复：固定审计时间窗；±5s 容忍浏览器与 DB 容器的轻微时钟偏差。
    const auditStart = new Date(Date.now() - 5_000).toISOString();
    // 1. engineer D2→D3（capaId fixture 已解析 document_no→UUID）
    await loginAs(page, 'engineer');
    await goToCapa(page, capaId);  // 用 UUID 直接访问（路由无 document_no 重定向）
    await expect(page.locator('[data-e2e=capa-status]')).toHaveText('D2_DESCRIPTION');
    await page.click('[data-e2e=capa-advance]');
    await expect(page.locator('[data-e2e=capa-status]')).toHaveText('D3_INTERIM');

    // 2. import → 200 + run + 4 类快照 + report_status='done'
    const importResp = await authedRequest.post(`/capa/${capaId}/d3/import`, {data:{snapshot_types:['inventory','shipment','iqc','spc']}});
    expect(importResp.status()).toBe(200);
    const importJson = await importResp.json();
    expect(importJson.report_status).toBe('done');
    expect(importJson.run_id).toBeDefined();

    // 3. 报告 5 项齐全 + risk_level∈{high,medium,low} + status='done' + 客户名真名
    const reportResp = await authedRequest.get(`/capa/${capaId}/d3/report`);
    expect(reportResp.status()).toBe(200);
    const report = await reportResp.json();
    expect(report.status).toBe('done');
    expect(['high','medium','low']).toContain(report.risk_level);
    expect(report.batches).toBeDefined();
    expect(report.impact_qty).toBeDefined();
    expect(report.customer_impact).toBeDefined();
    expect(report.time_window).toBeDefined();
    expect(report.risk_floor).toBeDefined();
    // 客户名真名（非 customer_0X）
    if (report.customer_impact.length > 0) {
      expect(report.customer_impact[0].customer_name).not.toMatch(/^customer_\d+$/);
    }

    // 4. advice → 列表非空 + advice_type∈枚举 + source_provenance 非空 + target_batch_refs 契约
    const adviceResp = await authedRequest.post(`/capa/${capaId}/d3/advice`);
    expect(adviceResp.status()).toBe(200);
    const advice = await adviceResp.json();
    expect(advice.advice.length).toBeGreaterThan(0);
    const a = advice.advice[0];
    expect(['recall','isolate','notify_customer','strict_inspection','alternative']).toContain(a.advice_type);
    expect(a.source_provenance.length).toBeGreaterThan(0);
    expect(a.source_provenance[0].record_key).toBeDefined();  // record_key 永不为空
    // P2-2 修复：target_batch_refs 非 null 时逐项验证引用属于 report.batches[].batch_key
    const batchKeys = new Set((report.batches || []).map((b: any) => b.batch_key));
    if (a.target_batch_refs) {
      for (const ref of a.target_batch_refs) {
        expect(batchKeys.has(ref), `target_batch_refs ${ref} 不在 report.batches`).toBe(true);
      }
    }

    // 5. 采纳 1 条 → adoptions 回读 adopted
    const adviceId = a.advice_id;
    const adoptResp = await authedRequest.post(`/capa/${capaId}/d3/advice/${adviceId}/decision`, {data:{decision:'adopted',adopted_text:'召回批次'}});
    expect(adoptResp.status()).toBe(200);
    const adoptionsResp = await authedRequest.get(`/capa/${capaId}/d3/adoptions`);
    const adoptions = await adoptionsResp.json();
    expect(adoptions.some((x: any) => x.advice_id === adviceId && x.decision === 'adopted')).toBe(true);

    // 6. 记录 execution → executions 回读
    const execResp = await authedRequest.post(`/capa/${capaId}/d3/execution`, {data:{source:'manual',measure_text:'人工隔离库位 A',result_status:'in_progress'}});
    expect(execResp.status()).toBe(200);
    const execJson = await execResp.json();
    const execId = execJson.execution_id;
    const execsResp = await authedRequest.get(`/capa/${capaId}/d3/executions`);
    const execs = await execsResp.json();
    expect(execs.some((x: any) => x.execution_id === execId)).toBe(true);

    // 7. D3→D4 推进成功
    await page.click('[data-e2e=capa-advance]');
    await expect(page.locator('[data-e2e=capa-status]')).toHaveText('D4_ROOT_CAUSE');

    // 8. 审计回读：P1-3 修复——走 admin /admin/logs/audit（admin token）按 record_id 客户端过滤，
    //    非 /api/capa/{id}/audit（该端点不存在）；固定 start/end，逐页校验响应，禁止异常时无限循环。
    const adminPw = await accountPassword('admin');
    const adminToken = await loginForToken('admin', adminPw);
    const auditEnd = new Date(Date.now() + 5_000).toISOString();
    let auditPage = 1; const allAuditItems: any[] = [];
    while (true) {
      const auditResp = await authedRequest.get(`${E2E_API_BASE_URL}/admin/logs/audit`, {
        headers: { Authorization: `Bearer ${adminToken}` },
        params: { table_name: 'capa_eightd', page: auditPage, page_size: 200,
                  start: auditStart, end: auditEnd },
      });
      expect(auditResp.status()).toBe(200);
      const auditJson = await auditResp.json();
      expect(Number.isInteger(auditJson.total) && auditJson.total >= 0).toBe(true);
      expect(Array.isArray(auditJson.items)).toBe(true);
      allAuditItems.push(...auditJson.items);
      if (allAuditItems.length >= auditJson.total) break;
      // total 尚未取完却收到空页属于分页契约错误；立即失败，不继续空转。
      expect(auditJson.items.length, 'audit pagination returned an empty page before total').toBeGreaterThan(0);
      auditPage += 1;
    }
    const actions = allAuditItems.filter((l: any) => l.record_id === capaId).map((l: any) => l.action);
    expect(actions).toContain('D3_DATA_IMPORTED');
    expect(actions).toContain('D3_REPORT_GENERATED');
    expect(actions).toContain('D3_AI_ADVICE_GENERATED');
    expect(actions).toContain('D3_ADVICE_ADOPTED');
    expect(actions).toContain('D3_EXECUTION_RECORDED');
    expect(actions).toContain('TRANSITION');

    // 9. viewer 只读（P1-4 修复：新 browser context + storageState，不在已登录 engineer 的 page 中二次登录）
    const vCtx = await browser.newContext({ storageState: 'e2e/.storage-state/viewer.json' });
    const vPage = await vCtx.newPage();
    await goToCapa(vPage, capaId);
    await expect(vPage.locator('[data-e2e=d3-import-button]')).not.toBeVisible();
    await expect(vPage.locator('[data-e2e=d3-execution-add]')).not.toBeVisible();
    await expect(vPage.locator('[data-e2e=capa-advance]')).not.toBeVisible();
    await vCtx.close();
  });

  test('gate rejects without import', async ({ page, request }) => {
    const capaId = await capaIdFor(request, D3_CAPA_DOC_NO_UNIMPORTED);  // D3_INTERIM 未导入
    await loginAs(page, 'engineer');
    await goToCapa(page, capaId);
    await page.click('[data-e2e=capa-advance]');
    await expect(page.locator('text=需先导入遏制数据')).toBeVisible();
    await expect(page.locator('[data-e2e=capa-status]')).toHaveText('D3_INTERIM');  // 未推进
  });

  test('manual execution advances to D4', async ({ page, request }) => {
    test.skip(noLlmCreds(), '需 LLM 凭证生成 done report（seed 阶段）');
    const capaId = await capaIdFor(request, D3_CAPA_DOC_NO_REPORTED);  // 独享 CAPA，已 done report
    await loginAs(page, 'engineer');
    await goToCapa(page, capaId);
    await page.click('[data-e2e=d3-execution-add]');
    await page.fill('[data-e2e=d3-execution-measure]', '人工隔离库位 A');
    await page.click('[data-e2e=d3-execution-save]');  // source=manual, 无 advice
    await page.click('[data-e2e=capa-advance]');
    await expect(page.locator('[data-e2e=capa-status]')).toHaveText('D4_ROOT_CAUSE');  // 推进 003 不影响 004/005
  });

  test('evidence_refs javascript scheme rejected 422', async ({ page, request }) => {
    test.skip(noLlmCreds(), '需 LLM 凭证生成 done report');
    const capaId = await capaIdFor(request, D3_CAPA_DOC_NO_EXEC_FORM);  // 独享 CAPA（不同于 manual 测试）
    await loginAs(page, 'engineer');
    await goToCapa(page, capaId);
    await page.click('[data-e2e=d3-execution-add]');
    await page.fill('[data-e2e=d3-execution-measure]', 't');
    await page.fill('[data-e2e=d3-execution-evidence-url]', 'javascript:alert(1)');
    await page.click('[data-e2e=d3-execution-save]');
    await expect(page.locator('text=非法 url scheme')).toBeVisible();  // 422 透传
  });

  test('cross-factory advice decision 404', async ({ request }) => {
    test.skip(noLlmCreds(), '需 LLM 凭证生成 advice');
    // P1-4 修复：用独立 007 CAPA（seed 已生成 done report + advice），不复用 003 manual（manual 推进 D4 后 advice 生成会失败）
    const capaId = await capaIdFor(request, D3_CAPA_DOC_NO_CROSSFACTORY);
    // engineer（DC 工厂）取 seed 已生成的 advice
    const engPw = await accountPassword('engineer');
    const engToken = await loginForToken('engineer', engPw);
    const engReq = await playwright.request.newContext({
      baseURL: E2E_API_BASE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${engToken}` },
    });
    const adviceResp = await engReq.get(`/capa/${capaId}/d3/advice`);
    expect(adviceResp.status()).toBe(200);  // advice 必存在（007 seed 已生成）
    const adviceJson = await adviceResp.json();
    const adviceId = adviceJson.advice?.[0]?.advice_id;
    await engReq.dispose();
    // P1-4 修复：advice 生成失败必须 assert（不动态 skip 隐藏回归）
    expect(adviceId, 'advice 未生成（seed 阶段 generate_advice 失败？）').toBeTruthy();

    // groupadmin 显式传 SH factory UUID 作 ?factory_id 查询参数（默认 effective factory None）
    const groupPw = await accountPassword('groupadmin');
    const groupToken = await loginForToken('groupadmin', groupPw);
    const shFactory = await shFactoryId(request);
    const crossReq = await playwright.request.newContext({
      baseURL: E2E_API_BASE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${groupToken}` },
    });
    // P1-3 修复：factory_id 走 Query 参数（非 header）；groupadmin 切到 SH 工厂视角访问 DC 工厂 capa → 404
    const resp = await crossReq.post(`/capa/${capaId}/d3/advice/${adviceId}/decision?factory_id=${shFactory}`, {data:{decision:'adopted',adopted_text:'t'}});
    expect(resp.status()).toBe(404);  // 跨工厂（SH 工厂视角访问 DC 工厂 capa）
    await crossReq.dispose();
  });

  test('viewer read-only on D3 panel', async ({ browser, request }) => {
    test.skip(noLlmCreds(), '需 LLM 凭证生成 done report');
    const capaId = await capaIdFor(request, D3_CAPA_DOC_NO_VIEWER);  // 独享 CAPA（005 仅 done report，无 advice/adoption）
    // P1-4 修复：用新 browser context + storageState（不在已登录 engineer 的 page 中二次登录）
    const ctx = await browser.newContext({ storageState: 'e2e/.storage-state/viewer.json' });
    const page = await ctx.newPage();
    await goToCapa(page, capaId);
    // P2-1 修复：005 无 advice/adoption，改断言报告/快照只读可见 + 所有写按钮隐藏（贴合只读权限目标）
    // P1-3 修复：逗号选择器匹配多元素触发 strict-mode 错误——分别断言每张卡（单元素）
    await expect(page.locator('[data-e2e=d3-snapshot-card-inventory]')).toBeVisible();
    await expect(page.locator('[data-e2e=d3-snapshot-card-shipment]')).toBeVisible();
    await expect(page.locator('[data-e2e=d3-import-button]')).toBeHidden();
    await expect(page.locator('[data-e2e=d3-execution-add]')).toBeHidden();
    await expect(page.locator('[data-e2e=capa-advance]')).toBeHidden();
    await ctx.close();
  });

  test('no creds: advice endpoint 422 blocked + import still 200 blocked', async ({ request }) => {
    // P1-4 修复：用独立 D3_INTERIM CAPA（006），不依赖主流程 capaId（主流程无凭证时被 skip 留 D2）
    // skip 条件写正：无凭证(hasLLM=false)时跑此测试，有凭证时 skip
    if (!noLlmCreds()) test.skip(true, '此测试仅在无 LLM 凭证环境运行');
    const capaId = await capaIdFor(request, D3_CAPA_DOC_NO_NOCREDS);
    const engPw = await accountPassword('engineer');
    const engToken = await loginForToken('engineer', engPw);
    const req = await playwright.request.newContext({
      baseURL: E2E_API_BASE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${engToken}` },
    });
    const imp = await req.post(`/capa/${capaId}/d3/import`);
    expect(imp.status()).toBe(200); expect(await imp.json()).toMatchObject({report_status:'blocked'});
    const adv = await req.post(`/capa/${capaId}/d3/advice`);
    expect(adv.status()).toBe(422); expect((await adv.json()).detail.blocked).toBe(true);
    await req.dispose();
  });
});

// P1-3 修复：spec 在 specs/m1-core/，fixture 在 fixtures/，相对路径为 ../../fixtures/
import { test, expect, loginAs, goToCapa, noLlmCreds, accountPassword, loginForToken, E2E_API_BASE_URL } from '../../fixtures/d3-containment';

test.describe('D3 containment', () => {
  // noLlmCreds 现为同步函数（读 e2e-env.json hasLLM），无需 request 参数
  test.skip(noLlmCreds(), 'No AI credentials');

  test('D3 containment main flow', async ({ page, browser, authedRequest, capaId }) => {
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
});

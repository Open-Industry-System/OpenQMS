# 2026-11-16 安全扫描修复计划

**Goal:** 在扫描提交 `193746ab` 上逐项修复17项报告问题，并记录真实验证。

**Architecture:** 保留既有服务、RequestScope和事务边界。权限验证前置到读写前；凭据绑定已配置目标；不从遮罩字段向新目标继承秘密；不向真实提供商发送测试流量。

**Tech Stack:** FastAPI、SQLAlchemy、PostgreSQL15、React、TypeScript、pytest、Vitest。

## 执行方法

使用 using-git-worktrees、writing-plans、systematic-debugging、test-driven-development、dispatching-parallel-agents 和 verification-before-completion。按不重叠模块分配独立任务，逐项根因确认→失败回归→最小修复→回归验证；共享数据库测试串行协调。主控统一审查需求与代码质量、整合验证。现有主工作区未提交改动不复制。

## 逐项验收清单

- [x] 1. Starting a single-tenant deployment creates a publicly known administrator password
  - 范围：`backend/app/main.py`、`scripts/init-production-env.sh`、`README.md`、`backend/app/api/auth.py`。
  - 验收：Start a clean production-mode database and verify no published credential authenticates.；Verify explicit private-terminal bootstrap uses a unique operator-supplied password.；Verify bootstrap replacement revokes existing refresh sessions.（不增加启动就绪阻断或一次性口令机制。）

- [x] 2. Changing an MES base URL forwards the existing hidden credential to the new host
  - 范围：`backend/app/api/mes.py`、`backend/app/services/mes_connector.py`。
  - 验收：Change only `base_url` and verify every stored credential is cleared before save/test.；Reject sending when credential origin binding differs from the request origin.；Cover bearer, API-key, and Basic authentication.

- [x] 3. Testing an AI provider sends a masked stored API key to an arbitrary base URL
  - 范围：`backend/app/api/admin/ai_config.py`、`backend/app/schemas/ai_config.py`、`backend/app/services/ai_config_service.py`、`backend/app/services/llm_provider.py`、`backend/app/services/embedding_provider.py`。
  - 验收：Submit a changed base URL with blank and masked keys and verify no stored key is sent.；Require explicit re-entry when a canonical origin changes.；Test both LLM and embedding provider paths.

- [x] 4. Editing a supplier name executes script in supply-chain heatmap viewers
  - 范围：`backend/app/schemas/supplier.py`、`backend/app/services/supply_chain_risk_map/service.py`、`frontend/src/pages/supplyChainRiskMap/components/RiskHeatmap.tsx`、`frontend/src/store/authStore.ts`。
  - 验收：Render supplier names containing tags, quotes, and event handlers and verify the tooltip displays literal text.；Verify chart tooltip code never assigns untrusted values through HTML.；Verify malicious supplier text remains inert.（本轮修复注入来源；不迁移现有令牌存储到 HttpOnly Cookie。）

- [x] 5. Supplying sibling product-line identifiers exposes and changes FMEAs and control plans
  - 范围：`backend/app/core/factory_scope.py`、`backend/app/api/fmea.py`、`backend/app/api/control_plan.py`、`backend/app/services/control_plan_service.py`。
  - 验收：Exercise ALL, EXPLICIT, and NONE product-line scopes against every document route.；Reject sibling-line creation even when the line shares an allowed factory.；Reject CSR sync when either the plan or any customer is outside scope, with no partial write.

- [x] 6. Updating a special characteristic commits cross-scope safety changes before authorization
  - 范围：`backend/app/api/special_characteristic.py`、`backend/app/services/special_characteristic_service.py`。
  - 验收：Attempt each update and safety transition with an out-of-scope UUID and assert both an error response and unchanged database state.；Verify authorized transitions still commit exactly once.

- [x] 7. Requesting supply-chain risk data bypasses factory and product-line scope
  - 范围：`backend/app/api/supply_chain_risk_map.py`、`backend/app/services/supply_chain_risk_map/service.py`、`backend/app/services/supplier_risk/service.py`、`backend/app/models/supply_chain_risk_map.py`。
  - 验收：Use two factories and sibling product lines to verify every read/export/generation route rejects out-of-scope data.；Verify NONE scope returns no rows and cannot generate snapshots.；Verify mixed supplier comparison fails atomically.

- [x] 8. Reusing a rotated refresh token leaves the attacker's successor session active
  - 范围：`backend/app/services/refresh_session_service.py`、`backend/app/api/auth.py`、`frontend/src/store/authStore.ts`、`backend/app/services/user_service.py`。
  - 验收：After rotating token A to B, reuse A and verify B is also rejected.；Log out with a valid session and verify its refresh token is rejected.；Verify password reset and logout-all revoke every family.

- [x] 9. Viewing an ERP connection reveals credentials stored in URL fields
  - 范围：`backend/app/schemas/erp.py`、`backend/app/services/erp_crypto.py`、`backend/app/api/erp.py`。
  - 验收：Reject base URLs containing userinfo.；Reject or redact credential-like endpoint query parameters.；Verify every response field remains safe when nested configuration contains secret-like values.

- [x] 10. Holding one slow attachment upload blocks the scan pipeline for every tenant
  - 范围：`backend/app/api/agent_task_attachments.py`、`backend/app/services/agent_runtime/task_attachments.py`、`backend/app/config.py`。
  - 验收：Stall one tenant's upload and verify another tenant can stage and eventually scan its file.；Verify scanner capacity is acquired only after a complete bounded staging object exists.；Verify per-principal quotas prevent immediate reacquisition starvation.

- [x] 11. Uploading oversized or highly expanded workbooks can exhaust the API worker before limits apply
  - 范围：`backend/app/api/iqc.py`、`backend/app/api/spc.py`、`backend/app/api/supplier.py`、`backend/app/utils/excel.py`、`backend/app/services/supplier_service.py`、`deploy/production-edge-Caddyfile`。
  - 验收：Stream a body above the limit and verify rejection before full read or spool growth.；Reject XLSX archives that exceed entry, expanded-size, or compression-ratio budgets.；Abort parsing at `MAX_IMPORT_ROWS + 1` without constructing the full list.

- [x] 12. Guessing platform-admin passwords is not throttled at the public API edge
  - 范围：`backend/app/api/platform/auth.py`、`backend/app/api/auth.py`、`deploy/Caddyfile`。
  - 验收：Exceed the configured failure threshold and verify platform login returns 429 without password verification.；Verify limits survive process restarts and cannot be bypassed by varying account case.；Verify no new MFA requirement is introduced by this rate-limit fix.（MFA不属于本轮实现范围。）

- [x] 13. Configuring an ERP connector sends backend requests to arbitrary HTTP destinations
  - 范围：`backend/app/schemas/erp.py`、`backend/app/api/erp.py`、`backend/app/services/erp_connector.py`。
  - 验收：Reject loopback/link-local/infrastructure destinations and unapproved public or private addresses; private manufacturing CIDRs require an explicit deployment policy.；Permit explicitly approved ERP origins and relative endpoint paths.；Verify every retry preserves the validated resolved destination.

- [x] 14. Running a mutable third-party Action can compromise Oracle deployment credentials
  - 范围：`.github/workflows/oracle-deploy.yml`、`.github/workflows/oracle-preview-cleanup.yml`。
  - 验收：Fail workflow lint when an action in a credentialed job is not pinned to a full commit SHA.；Verify privileged scripts are rechecked or freshly checked out after third-party steps.

- [x] 15. Editing supplier fields plants active formulas in exported XLSX and CSV files
  - 范围：`backend/app/schemas/supplier.py`、`backend/app/services/supplier_service.py`、`backend/app/utils/excel.py`、`backend/app/services/supply_chain_risk_map/service.py`。
  - 验收：Inspect generated XLSX cell types for every formula prefix and verify they are strings.；Verify CSV output neutralizes all formula-leading and whitespace-prefixed variants.；Cover supplier and risk-map exports through the shared helper.

- [x] 16. Requesting a document version discloses full historical FMEA and control-plan snapshots
  - 范围：`backend/app/api/version.py`、`backend/app/services/version_service.py`、`backend/app/schemas/version.py`。
  - 验收：Reject version detail and compare for users without the parent module permission.；Reject wrong-factory, NONE-scope, and unassigned-product-line callers.；Allow authorized users to retrieve the same snapshots.

- [x] 17. Using ERP or PLM object IDs bypasses product-line restrictions on integrations
  - 范围：`backend/app/api/erp.py`、`backend/app/api/plm.py`。
  - 验收：For every ERP/PLM UUID route, assert an object absent from the scoped list returns 404.；Reject updates that omit `product_line_code` when the existing object is outside scope.；Retain MES product-line parity tests.

## 分工与验证

- 权限模块：5、6、7、16、17；前置工厂/产品线/模块访问检查，验证跨范围拒绝且无持久化变更。
- 连接器：2、3、9、13；验证目标修改时不能继承隐藏凭据，拒绝URL嵌入秘密，ERP仅访问部署声明的目标。
- 导入导出/UI：4、11、15；验证tooltip注入、上传与ZIP展开预算、表格公式字面量。
- 认证/附件/CI：1、8、10、12、14；验证无公开管理员口令、令牌重放撤销、慢上传不占全局扫描锁、平台认证限流、Action固定SHA。

完整环境验证使用一次性专属PG15，不指向业务库；先跑基线，再跑定向回归与最终make check及前端测试。外部模型、扫描器或远端CI不能运行时明确记限制，不以静态检查冒充真实验收。

## 执行结果

17项本地修复完成，独立复核无未关闭P1/P2。完整`make check`退出0，后端5434 passed /5 skipped /19 deselected，0失败/错误；SDK562+16+1、前端891项及类型/构建通过；真实ClamAV6+1通过。首次有效整轮36个旧夹具失败已通过仅测试修改消除，原断言保留，96项定向回归和整轮重跑通过。复盘、跳过、部署要求与原始finding链接见[修复记录](../../development/2026-11-16-security-scan-fixes.md)。勾选表示本地修复和相称回归完成，不表示云端finding已关闭或已部署。

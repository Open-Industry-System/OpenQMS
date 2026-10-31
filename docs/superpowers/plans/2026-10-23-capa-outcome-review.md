# CAPA 措施实施后集中结果审核 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 复用现有 D8 审批，集中展示并核对已经实施的纠正措施及验证结果，绑定本轮审核版本，并保证结案及归档后的已审材料不能被任何业务写入口原位改写。

**Architecture:** 保留现有 CAPA 状态机和 advance 事务；增加窄职责的已审材料写保护、结果审核读取/版本校验服务，以及 D8 只读审核面板。审批引用现有业务记录、文档版本和 AuditLog，不另建候选库、审批表、通用策略引擎或业务补偿流程。已审核心和结案后未审补充报告明确分开。

**Tech Stack:** 现有 FastAPI、SQLAlchemy async、Pydantic v2、PostgreSQL 15、React 18、TypeScript、Ant Design、pytest/httpx、Vitest、已安装 Chromium/Playwright；不新增依赖。

**日期**：2026-10-23。**依据**：[已获书面复核通过的规格](../specs/2026-10-22-capa-d4-internal-review-publication-design.md)，包含 §5.4/§8 的结案后写保护 P1。**执行状态（2026-10-27）**：用户确认采用子代理驱动，并明确授权本片独占测试资源、本地文档基线/任务提交和仅合成数据的现有测试 provider 调用。完整前置基线已通过，Task 1–2 已通过规格及质量复核；Task 2 完整聚焦回归 424 passed，权限重查、间接删除及真实竞争保护已验收，Task 3 读取及版本 DTO 的 I1–I4 首轮修正经独立复核通过（最终聚焦回归 242 passed），旧轮次采用用户批准的固定兼容规则；Task 4 实际决定绑定和生产回执已通过独立规格/质量复核，最终聚焦回归 662 passed；Task 5 生产集中面板、请求归属及终态只读经两轮修正通过独立规格/质量复核，最终前端 245 passed /27 files，类型/构建/E2E 类型通过；Task 6 未审补充派生边界亦通过独立规格/质量复核，受影响后端821 passed、前端121 passed及类型/构建通过；Task 7 实现已通过独立代码复核（665511e3），但完整真实验收2 failed /1 passed、exit1：缺少授权测试.env.e2e，正向链在D3阻断，未完成验收；当前等待测试配置，最终冻结仍待后续任务，整片尚未完成。任务完成证据记录在本计划专属台账。未授权 push、合并或部署。

**最终代码复核状态（2026-10-30）**：整片增量复核的唯一 Important I1（来源锁等待后的当前权限复核）已在 b375f26d 修正，唯一限定重审 PASS/Approved，无新代码阻塞发现。最新冻结完整命令3447 passed /2 failed /12 skipped /3 xfailed /2 xpassed /5 warnings，make exit2；两项live opt-in失败仍未解除，不能签署Task 7、Task 8或整片完成。真实正向provider/浏览器/知识/横向、实际scanner专项所需精确授权及依赖安全的最终清理保持待办；不合并、push或部署。

## Global Constraints

- 审核的是已经实施的措施及其结果，不是待验证的候选，也不是尚未执行的措施方案。
- D4、D5、D6 不新增人工批准节点；保留当前根因必须经验证、D7 完成条件和 D8 文档门禁。
- 复用 `D8_APPROVAL_PENDING -> D8_CLOSURE` 与 `D8_APPROVAL_PENDING -> D7_PREVENTION`，不增加审批状态或任意返工边。
- 驳回必须有理由；整改后重提，不自动回滚现场措施或文档。
- `D8_CLOSURE` 和 `ARCHIVED` 后，已审核心材料禁止原位改写；EDIT、APPROVE、ADMIN 都不豁免。
- 保护覆盖普通编辑、建议采纳、根因验证、D7 动作、关联维护，以及实际存在的批量、内部工具和跨模块间接写入；不为补测试而新增删除/导入接口。
- 所有 CAPA 材料写服务先锁 CAPA 父行并刷新、检查终态，再锁子行和写入；拒绝前不得产生材料变更、成功审计、embedding 或 outbox。
- 对已授权调用方，终态材料写入统一返回 `409 CAPA_REVIEWED_CONTENT_LOCKED`；无权限/不可见仍先拒绝，不泄漏受保护材料。
- `d8_closure` 在 `D8_CLOSURE` 下仍可补写，但属于“结案后补充，未纳入本次审核”；`ARCHIVED` 下仍冻结。不得作为已审依据或反向覆盖核心材料。
- 正式根因、措施、验证、驳回及审批记录不适用原候选 7 天清理；R4b-1 的 30 秒预览与 R4b-2 附件策略保持不变。
- 当前 D8 本人审批策略不变；不移植 Agent 的禁止自批，不新增允许自批开关，也不降低 APPROVE 门槛。
- 来源资料逐模块检查当前权限，控制计划归 `Module.PLANNING`，FMEA 归 `Module.FMEA`；未知或不可读的必要来源不得静默省略后放行。
- generation 隔离过期请求，不授权销毁数据；持久审核版本不绑定普通维护的 origin generation。
- 不新增候选审核表、迁移、候选开关、候选发布路由、清理 CLI；不开放 Agent 命令、插件/model 正文交付、生产部署或通用 R5 写入/补偿。
- 本计划只在当前独立 worktree 执行，不覆盖已有文档修改；不 push/merge/deploy，不改共享/种子/生产库，不自动安装浏览器。
- 实施前确认本片自有测试资源及本地提交授权。下述 commit 步骤仅在取得本片授权后执行，不继承 R4b-2 的提交或镜像授权；未获授权时保留工作树并记录未提交状态。
- 沿用 Makefile 两项 graph 排除，保留并报告既有 skip/xfail/xpass；不得把 `2999 passed` 历史基线算成本片结果。

---

## 一、预先锁定的实现决定

### 1. 写保护不是新 ACL

新增 `backend/app/services/capa_review_guard.py`，只负责报告父行锁和业务终态约束，不注册新的 capability。权限仍由现有模块入口及当前访问服务校验。

| 符号 | 精确接口与行为 |
|---|---|
| `ReviewedContentLocked` | 无私有属性的 `RuntimeError`；固定文本 `CAPA_REVIEWED_CONTENT_LOCKED`，不能被旧 `except ValueError` 吞成 400 |
| `OutcomeReviewConflict` | `RuntimeError`；固定文本 `CAPA_OUTCOME_REVIEW_CHANGED`，不夹带源数据 |
| `OutcomeReviewRequired`、`OutcomeReviewLimit` | `RuntimeError`；分别固定 `CAPA_OUTCOME_REVIEW_REQUIRED`、`CAPA_OUTCOME_REVIEW_LIMIT` |
| `lock_capa_parent(db, report_id)` | 返回锁后刷新 `CAPAEightD`；`db.no_autoflush` 下 `FOR UPDATE + populate_existing=True`，不存在抛 LookupError；不提交 |
| `assert_reviewed_material_mutable(capa, fields=None)` | 终态且 fields 为 None（子集合/关联写）或命中保护集合时抛 ReviewedContentLocked；不读库、不修改对象 |
| `lock_material_write(db, capa, fields=None)` | 先 `lock_capa_parent`，再 `assert_reviewed_material_mutable`，返回 fresh；不提交 |

`REVIEWED_STATES = frozenset({'D8_CLOSURE', 'ARCHIVED'})`。`REVIEWED_FIELDS` 至少包含 `d4_root_cause`、`d5_correction`、`d6_verification`、`d7_prevention`、`d4_retry_count`、`fmea_ref_id`、`fmea_node_id`、`factory_id`、`product_line_code`、`supplier_id`、`severity`。后三项涉及门禁/来源解释，不能在结案后借改范围或严重度改变审核依据。

`d8_closure` 不加入上述核心集合；其各状态冻结继续由原 `update_capa()` 规则处理。整包 PUT 含受保护字段时整体拒绝，包括显式 null、空串和“写回相同值”，不得先保存未冻结部分再拒绝。归档动作本身仍走现有 APPROVE 边，不属于禁止的材料写入。

### 2. 审核版本及一轮身份

新增服务 `backend/app/services/capa_outcome_review.py`，使用域分离 HMAC-SHA256：

```text
contract = capa.outcome-review.v1
HMAC domain = openqms.capa.outcome-review.v1
```

规范材料包括：tenant ID/public 身份、report/factory/product-line、上述审核相关字段、完整根因验证集合、完整 D7 动作集合、当前审核所依据的 analysis/decision ID、decision revision 与受控文档 `version_snapshot`。UUID/时间使用统一字符串；集合按稳定业务 ID 排序，JSON 使用 `sort_keys=True, ensure_ascii=False, separators=(',', ':')`。禁止用无密钥原文 hash 对外作版本。

规范材料顶层键固定为 `contract/tenant_identity/report_id/factory_id/product_line_code/round_id/core/verifications/d7_actions/doc_gate/source_versions`；内部 core 含审核字段及相关关联/严重度，API core 仅投影四段正文。doc_gate 是文档门禁决定，不是新增的 D8 审批回执。不纳入 `status`、`binding_status`、D8 决定 DTO、`d8_closure`、CAPA `updated_at`、普通 admission generation、按钮状态或当前 FMEA/CP 的最新正文；否则批准、补报告、归档或普通维护会错误改变已审核心版本。子记录实际字段及版本必须覆盖，不能仅 hash 主表更新时间。

- 新的审核轮次使用进入 `D8_APPROVAL_PENDING` 的最新 `TRANSITION` 审计 `log_id`。
- 已有待审批数据没有此审计时，使用服务端 `uuid5(NAMESPACE_URL, 'capa.outcome-review.legacy:' + str(tenant_identity) + ':' + str(report_id))` 作为固定兼容轮次。2026-10-25 用户明确批准此修订：不包含 updated_at 或其他可变维护元数据；实际材料/来源变化仍由 HMAC 检出，正常重提后使用新的 TRANSITION 审计 ID。它不是读取授权，不新增 GET 写入或迁移。
- 批准或驳回时，将 round ID、contract、HMAC revision 和来源版本标识加入既有 `D8_APPROVED`/`D8_REJECTED.changed_fields['outcome_review']`。不存正文快照或复制验证自由文本。
- 结案/归档后的轮次从新审计回执取得，不再用变过的 `updated_at` 推导。
- 历史已结案但无该回执：标为 `legacy_unversioned`，保持已结案事实和写保护，不伪造“当时已校验这一版”。
- HMAC 无法重验或密钥轮换时，不静默重签历史批准、不删除记录；显示绑定无法验证，不改变历史状态。

### 3. HTTP 与最小 DTO

保留旧 `/advance`；新增仅一个当前报告受控读取：

```text
GET /api/capa/{report_id}/outcome-review
POST /api/capa/{report_id}/advance   # 原接口，审批/驳回时加版本条件
```

`AdvanceRequest` 新增可选 `expected_outcome_revision`（64 位小写 hex）和 `expected_review_round_id`（UUID）。只有 D8 批准/驳回边要求两者，缺少时 `409 CAPA_OUTCOME_REVIEW_REQUIRED`；旧 EDIT 推进及归档不受影响。所有审批调用方必须升级，不能给缺版本的“旧客户端”留绕过；服务直接调用也不能缺少校验。

新 DTO 放 `backend/app/schemas/capa_outcome_review.py`，前端对应 `frontend/src/types/capaOutcomeReview.ts`：

```typescript
export interface CapaOutcomeReview {
  report_id: string;
  status: string;
  contract: 'capa.outcome-review.v1';
  review_round_id: string | null;
  revision: string;
  binding_status: 'pending' | 'verified' | 'legacy_unversioned' | 'unverifiable';
  core: {
    d4_root_cause: string | null;
    d5_correction: string | null;
    d6_verification: string | null;
    d7_prevention: string | null;
  };
  verifications: Verification[];
  d7_actions: D7NodeAction[];
  documents: OutcomeDocumentRef[];
  decision: OutcomeDecision | null;
  supplement: {
    text: string | null;
    review_scope: 'unreviewed_supplement';
    updated_by: string | null;
    updated_at: string | null;
  };
}
```

`Verification`、`D7NodeAction` 复用现有类型；`OutcomeDocumentRef` 精确定义为 `{module:'fmea'|'planning'; object_id:string; version_id:string; sha256:string}`；`OutcomeDecision` 为 `{action:'approved'|'rejected'; actor_id:string|null; operated_at:string; audit_id:string}`。未知 source shape、缺版本、hash 无法核对或缺必要源权限必须失败，不返回半包。

读取需要当前 CAPA VIEW/范围及全部必要 FMEA/PLANNING VIEW，响应 `Cache-Control: no-store`；服务只受理 D8_APPROVAL_PENDING、D8_CLOSURE、ARCHIVED，其他阶段返回固定 404，不生成早期候选材料包。只在这三个状态显示面板，不建立全局 inbox。GET 不触发 AI、建任务、更新当前文档、生成候选或改变审核轮次。

不沿用旧候选 200 条/1 MiB 配额。作为本计划明示、随计划审阅的技术预算，新增读取采用 `MAX_OUTCOME_REVIEW_BYTES = 8 * 1024 * 1024`：在取正文前用字段 octet_length/JSON 元数据长度预检，子集合每批 100 条，编码累计超限则在加入材料/DTO 前终止。规范材料与最终响应分别不得超过该字节预算；不设置候选保留条数或业务清理。超限整次返回固定 `409 CAPA_OUTCOME_REVIEW_LIMIT`，不得截断、漏行、假装完整或自动删除业务记录。revision 覆盖完整受审集合，正常资料处理内存有界。该数字是实现计划的技术选择，不冒称规格已确定它。

### 4. 源文档正常修订与删除

FMEA/CP 正常创建新版本继续允许；历史审核始终指向既有不可变版本，不随 latest 移动。

核验发现 `fmea_service.delete_fmea()` 会 `_null_out_fmea_references()` 并删除 `CapaD7NodeAction`；`delete_control_plan()` 会删除版本。它们必须纳入保护，不能只修 CAPA API：

1. 以已授权来源对象为目标，收集关联 CAPA（直接 FMEA 引用、D7 动作、已绑定 doc-gate 版本及新版审批回执）。只读取技术引用，不泄漏 CAPA 正文。
2. 在 ProductLine/FMEA/CP 锁之前，按 report UUID 排序锁 CAPA 父行并刷新；命中结案/归档引用即拒绝，不先清关联、删动作或写删除成功审计。
3. 按原锁序取得 ProductLine 与文档锁，再重查引用集合。若出现未锁定的新引用，抛 OutcomeReviewConflict，整次回滚后显式重试；不能持文档锁再反向获取新 CAPA 锁。
4. 仅原有、已锁定且非终态的引用允许按原逻辑处理。FK 必须保留，阻止文档锁之后新引用成功提交。
5. 不增加通用销毁能力；也不改写历史版本 snapshot。未来合规销毁另行设计。

### 5. 测试、版本和实施顺序

本片预计 **无数据库迁移**：版本回执存在既有 AuditLog，补充标记存在 DTO/既有派生 JSON 或 tags。不得因写计划而修改 frozen tv001、tv005 或 reviewed head。

测试数据库使用本轮明确自有的随机名称。完整回归若包含旧 R4a fixture，采用 `openqms_r4a_capa_outcome_<random>_test`，保留其 `openqms_r4a_*_test` 守卫，不为方便而放松历史隔离。连接凭据使用已有 Make/环境，不写入计划、命令输出或交接。

实施 Task 1 在本计划自有、已忽略的 `.superpowers/sdd/2026-10-23-capa-outcome-review/owned-env.sh` 登记测试环境（0600），供 shell 读取，不在报告/审阅包中展开。导出 `OPENQMS_OUTCOME_ROOT`、`OPENQMS_OUTCOME_PYTHON`、`PGHOST/PGPORT/PGUSER/PGPASSWORD`、`TEST_DB`、`DATABASE_URL`、`TEST_DATABASE_URL`、`PYTEST/PYTHON_BIN/ALEMBIC`。DATABASE_URL 指向另一个本轮自有 application `_test` 库，TEST_DATABASE_URL 指向上述测试库；两库均创建、迁移并登记，不能让全局导入的应用 engine 回退到 qms/生产配置。TEST_DB 必须匹配本轮已登记的随机 `_test` 名称，全部连接都必须指向本轮获授权资源。每条测试命令都重新 source 该文件，不能依赖前一次 Bash 的环境或 Make 子进程把 TEST_DATABASE_URL 传回父进程。不得把私有连接串写进任务报告、argv 或受跟踪文档。

普通 `db` fixture 的 commit 仅 flush，不能用于事务/竞争验收。新 `review_case` 用现有真实 `sessionmaker`，独立 session、真实 commit 和 Events；真实 HTTP/Chromium 使用独立 tenant 与端口。缺 PostgreSQL、测试 provider 凭据或已安装浏览器即明确 BLOCKED，不伪造通过。

## 二、文件结构与职责

| 文件 | 创建/修改 | 职责 |
|---|---|---|
| `backend/app/services/capa_review_guard.py` | 创建 | 共享父行锁、终态写保护及固定异常 |
| `backend/app/services/capa_outcome_review.py` | 创建 | 完整材料/轮次、来源权限、HMAC 版本与审批回执 |
| `backend/app/services/capa_review_source_guard.py` | 创建 | FMEA/CP 删除影响的 CAPA 引用收集与锁序保护 |
| `backend/app/schemas/capa_outcome_review.py` | 创建 | 审核/补充报告/源版本 DTO |
| `backend/app/services/capa_current_access.py` | 修改 | current_capa_actor_target，复用 fresh 当前身份/范围及明确最低等级 |
| `backend/app/services/capa_service.py` | 修改 | 普通写入、link、advance 版本绑定与批准审计 |
| `backend/app/services/capa_verification_service.py` | 修改 | 采纳、验证新增/修改；移除子先父后的锁序 |
| `backend/app/services/capa_d7_action_service.py` | 修改 | D7 确认/填充先锁父行，保留原 D7 stage 规则 |
| `backend/app/services/capa_doc_gate_service.py` | 修改 | 所有写阶段在任何变更前锁父行并检查当前阶段 |
| `backend/app/services/fmea_service.py`、`control_plan_service.py` | 修改 | 保护间接清关联、级联删除及历史版本 |
| `backend/app/api/capa.py`、`schemas/capa.py` | 修改 | 唯一读取端点、advance 预期版本、当前边权限 |
| `backend/app/api/capa_review_errors.py` | 创建 | `register_capa_review_errors(app)`，main 与自有 harness 复用四个固定 409 处理器 |
| `backend/app/main.py` | 修改 | 注册固定 409 异常处理，不新增功能开关 |
| `backend/app/services/capa_lessons_service.py`、`knowledge_sink_service.py` | 修改 | D8 补充的未审来源标识，不改变原知识沉淀事务 |
| `frontend/src/types/capaOutcomeReview.ts` | 创建 | 精确 DTO |
| `frontend/src/components/capa/CapaOutcomeReviewPanel.tsx` | 创建 | 当前结果只读面板、显式重载与版本交付 |
| `frontend/src/api/capa.ts` | 修改 | GET、AbortSignal、advance 版本字段 |
| `frontend/src/pages/capa/CAPADetailPage.tsx` | 修改 | D8 面板、唯一批准/驳回入口、终态只读与补充警示 |
| `frontend/src/locales/zh-CN/capa.json`、`en-US/capa.json` | 修改 | 审核/冲突/未审补充说明 |
| `backend/tests/capa/outcome_review_support.py` | 创建 | 自有记录、真实提交 case 与快照/清理 helpers |
| `backend/tests/capa/test_capa_review_guard.py` | 创建 | 纯业务 guard 和真实父行刷新 |
| `backend/tests/capa/test_capa_reviewed_writes.py` | 创建 | 全写入口闭集与拒绝副作用 |
| `backend/tests/capa/test_capa_review_source_guard.py` | 创建 | FMEA/CP 正常修订、删除及并发新引用 |
| `backend/tests/capa/test_capa_outcome_review.py` | 创建 | 完整版本、轮次、来源权限、历史兼容 |
| `backend/tests/capa/test_capa_outcome_decision.py` | 创建 | 真 advance 绑定、驳回/批准竞争与回执 |
| `backend/tests/capa/test_capa_outcome_api.py` | 创建 | HTTP 权限、409、缺版本与 no-store |
| `backend/tests/capa/test_capa_outcome_supplement.py` | 创建 | 未审补充不改变核心/批准绑定，归档冻结 |
| `backend/tests/capa/test_capa_review_concurrency.py` | 创建 | 锁等待、反向竞争、撤权与无副作用 |
| `frontend/src/components/capa/CapaOutcomeReviewPanel.test.tsx` | 创建 | 确切材料、乱序响应、冲突与身份失效 |
| `backend/tests/e2e/capa_outcome_review_harness.py` | 创建 | 无插件配置的自有 tenant/真实 HTTP 测试环境 |
| `backend/tests/e2e/test_capa_outcome_review_browser.py` | 创建 | 自有 Vite/已安装 Chromium 控制器 |
| `frontend/e2e/specs/capa/outcome-review.spec.ts` | 创建 | 单次结果审核、驳回、终态写保护的真实浏览器验收 |
| `frontend/playwright.agent.config.ts` | 修改 | 加单个受控 spec，不接共享 global setup |
| `docs/development/capa-outcome-review.md` | 创建 | 员工流程、配置现状、409、保留与补充说明 |

## 三、逐任务计划

### Task 1: 真实测试支撑、共享写保护与固定错误

**Files:** Create `backend/app/services/capa_review_guard.py`、`backend/app/api/capa_review_errors.py`、`backend/tests/capa/outcome_review_support.py`、`backend/tests/capa/test_capa_review_guard.py`；Modify `backend/tests/capa/conftest.py`、`backend/app/main.py`、`backend/app/services/README.md`。

**Interfaces:** 生产接口按实现决定 §1。测试 `ReviewCase` 保存 `session_factory/report_id/actor_id/factory_id/product_line_code/verification_id`，提供 `report(db)`、`scope(db)`、`snapshot()`、`set_capa_level(level)`、`set_status(status)`；fixtures `review_case` 和 `review_http_client` 在本任务定义并从 capa conftest 导入。

- [x] **Step 1: 记录实施基线和自有资源**

```bash
git status --short
git log -3 --oneline
python --version
node --version
npm --prefix frontend ls --depth=0
```

确认当前 worktree、已审规格与现有未提交 docs；测试环境仅登记自己创建的随机 DB/容器/端口。创建上文的私有 owned-env.sh；source 后核对随机库名与获授权 host/port，再按现有 Make 配置运行 `make check` 建基线。无法获得可用且获授权的测试环境则报告 BLOCKED，不能回退共享 qms/qms_test。本轮不得执行这些命令来代替用户对实施的确认。

- [x] **Step 2: 创建真实提交 case**

在 support 中定义 dataclass 与以下基础实现；不从 flush-only `db` 搬未提交对象到独立 session：

```python
from dataclasses import dataclass
from uuid import UUID
from sqlalchemy import select, update
from app.models.capa import CAPAEightD
from app.models.factory import Factory
from app.models.role import RolePermission
from app.models.user import User
from tests.conftest import _scope_for

@dataclass
class ReviewCase:
    session_factory: object
    report_id: UUID
    actor_id: UUID
    factory_id: UUID
    product_line_code: str
    verification_id: UUID

    async def report(self, db):
        return await db.scalar(select(CAPAEightD).where(
            CAPAEightD.report_id == self.report_id
        ).execution_options(populate_existing=True))

    async def scope(self, db):
        user = await db.get(User, self.actor_id)
        factory = await db.get(Factory, self.factory_id)
        return _scope_for(user, factory, [self.factory_id], 'EXPLICIT',
                          [self.product_line_code])

    async def set_status(self, status):
        async with self.session_factory() as db:
            await db.execute(update(CAPAEightD).where(
                CAPAEightD.report_id == self.report_id).values(status=status))
            await db.commit()

    async def set_capa_level(self, level):
        async with self.session_factory() as db:
            user = await db.get(User, self.actor_id)
            await db.execute(update(RolePermission).where(
                RolePermission.role_id == user.role_id,
                RolePermission.module == 'capa').values(permission_level=level))
            await db.commit()
```

`review_case` 使用 `sessionmaker`，通过 fixture monkeypatch 明确 `TENANT_MODE=single` 并在 teardown 恢复；创建唯一 Factory、ProductType、ProductLine、RoleDefinition、User、UserFactory、UserProductLine；角色含 capa=5/fmea=5/planning=5。创建 D8_APPROVAL_PENDING CAPA，D4=`扭矩不足`、D5=`更换扭矩控制工具`、D6=`实施后复测合格`、D7=`更新点检要求`；一条匹配的 passed 验证（method=observation/result=复测合格）；一份测试前置的 done/current 空 doc-gate analysis，hash 调真实 `_compute_input_hash(capa, [])`，一份 passed/no_affected_confirmed decision，以及进入 pending 的 TRANSITION 审计。全部真实 commit。

这只是单元/事务测试的已完成前置，不是 AI 或端到端审核已通过证据。`snapshot()` 用新 session 读取 CAPA 核心、全部验证/adoption/node-action、doc-gate、成功审计、embedding/outbox 标识，返回可比较字典，不输出私有字段到日志。teardown 逆序删除精确自有行：outbox/embedding、AuditLog、doc-gate decision/audit/analysis、adoption/node-action/verification、CAPA、测试创建的 CP/FMEA 及版本、user membership/user/role、line/type/factory；不使用 TRUNCATE 或全表 DELETE。后续任务新增的自有来源 ID 纳入同一清理集合。

`review_http_client` 使用真实 case session factory 和真实用户，按现有 API 单测方式注入 get_db/get_current_user/get_request_scope，使用生产 app 的路由和异常注册；每请求独立 session、真实提交/回滚，不改 authorize 返回值。真实 JWT/tenant 中间件由 Task 7 验证。

- [x] **Step 3: 写 guard RED 测试**

```python
import pytest
from app.services.capa_review_guard import (
    ReviewedContentLocked, lock_material_write,
)

@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['D8_CLOSURE', 'ARCHIVED'])
@pytest.mark.parametrize('field', [
    'd4_root_cause', 'd5_correction', 'd6_verification',
    'd7_prevention', 'fmea_ref_id', 'fmea_node_id', 'severity',
])
async def test_closed_core_is_locked(review_case, status, field):
    await review_case.set_status(status)
    async with review_case.session_factory() as db:
        capa = await review_case.report(db)
        with pytest.raises(ReviewedContentLocked,
                           match='CAPA_REVIEWED_CONTENT_LOCKED'):
            await lock_material_write(db, capa, {field})
```

另测 fields=None、显式 null 所对应字段名、补报告不被核心 guard 错拦、pending 正常可写、父行刷新替换旧 identity-map 状态、不提交或修改其他数据。

- [x] **Step 4: 运行并记录 RED**

```bash
. /Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/owned-env.sh
cd "$OPENQMS_OUTCOME_ROOT/backend"
PYTHONPATH=. "$OPENQMS_OUTCOME_PYTHON" -m pytest tests/capa/test_capa_review_guard.py -q
```

须因 guard 不存在/缺实现而失败，不接受 DB 不可达或 fixture 未定义作为 RED。

- [x] **Step 5: 实现窄 guard**

```python
from sqlalchemy import select
from app.models.capa import CAPAEightD
from app.services.capa_current_access import require_business_namespace

REVIEWED_STATES = frozenset({'D8_CLOSURE', 'ARCHIVED'})
REVIEWED_FIELDS = frozenset({
    'd4_root_cause', 'd5_correction', 'd6_verification',
    'd7_prevention', 'd4_retry_count', 'fmea_ref_id', 'fmea_node_id',
    'factory_id', 'product_line_code', 'supplier_id', 'severity',
})

class ReviewedContentLocked(RuntimeError):
    def __init__(self):
        super().__init__('CAPA_REVIEWED_CONTENT_LOCKED')

class OutcomeReviewConflict(RuntimeError):
    def __init__(self):
        super().__init__('CAPA_OUTCOME_REVIEW_CHANGED')

class OutcomeReviewRequired(RuntimeError):
    def __init__(self):
        super().__init__('CAPA_OUTCOME_REVIEW_REQUIRED')

class OutcomeReviewLimit(RuntimeError):
    def __init__(self):
        super().__init__('CAPA_OUTCOME_REVIEW_LIMIT')

async def lock_capa_parent(db, report_id):
    await require_business_namespace(db)
    with db.no_autoflush:
        capa = await db.scalar(select(CAPAEightD).where(
            CAPAEightD.report_id == report_id
        ).with_for_update().execution_options(populate_existing=True))
    if capa is None:
        raise LookupError('8D report not found')
    return capa

def assert_reviewed_material_mutable(capa, fields=None):
    if capa.status in REVIEWED_STATES and (
        fields is None or REVIEWED_FIELDS.intersection(fields)
    ):
        raise ReviewedContentLocked()

async def lock_material_write(db, capa, fields=None):
    fresh = await lock_capa_parent(db, capa.report_id)
    assert_reviewed_material_mutable(fresh, fields)
    return fresh
```

- [x] **Step 6: 注册固定 409 并验证 GREEN**

新增 `backend/app/api/capa_review_errors.py` 的 `register_capa_review_errors(app) -> None`，在 main 和测试 app 调用，注册本任务四个 RuntimeError 子类的 exception handler，返回 `{'detail': 固定码}`，不回显异常自由文本。自有 FastAPI 测试 app 也必须显式注册同一窄 handler；不得仅在 main 注册后遗漏 harness。

运行 guard 测试及 `tests/capa/test_capa_update_freeze.py` 建兼容基线，更新 services README 说明 guard 不代替权限。授权后提交本任务文件，主题 `feat(capa): add reviewed material write guard`。

### Task 2: 全部真实写入口与来源删除保护

**Files:** Modify `capa_service.py`、`capa_verification_service.py`、`capa_d7_action_service.py`、`capa_doc_gate_service.py`、`fmea_service.py`、`control_plan_service.py`；Create `capa_review_source_guard.py`、`test_capa_reviewed_writes.py`、`test_capa_review_source_guard.py`；Modify 原 freeze/API/D7/doc-gate 测试的精确预期及相关 README。

**Interfaces:** 消费 Task 1 guard。新 source helper `lock_source_capa_references(db, doc_type, doc_id) -> frozenset[UUID]`、`assert_source_references_unchanged(db, doc_type, doc_id, locked_ids) -> None`；doc_type 仅 fmea/control_plan。引用查询同时覆盖直接关联、D7 action、doc-gate version_snapshot 和新版审计回执；doc-gate 的 doc_type/doc_id 与新回执的 module/object_id 先规范成同一来源身份，`planning` 对应 `control_plan`，不能只识别一种 JSON 形状。不返回 CAPA 正文。

- [x] **Step 1: 为实际入口写 RED 矩阵**

```python
@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['D8_CLOSURE', 'ARCHIVED'])
async def test_adoption_cannot_append_after_close(review_case, status):
    from app.models.user import User
    from app.schemas.capa_verification import AdoptRequest
    from app.services.capa_verification_service import adopt_recommendation
    await review_case.set_status(status)
    before = await review_case.snapshot()
    async with review_case.session_factory() as db:
        capa = await review_case.report(db)
        user = await db.get(User, review_case.actor_id)
        with pytest.raises(ReviewedContentLocked):
            await adopt_recommendation(db, capa, AdoptRequest(
                d_step='d5', adopted_text='未审核追加', source='manual'), user)
        await db.rollback()
    assert await review_case.snapshot() == before
```

同样用现有请求模型覆盖：PUT D4/D5/D6、核心+补充混合 PUT、root verification create/update（含清空证据/换结论/换 source_ref）、既有 adoption 幂等 fast path、link_fmea、D7 record/auto_fill、doc-gate phase1/run_audit/defer/confirm/waiver。分别直接服务与 HTTP 409，不依赖 UI。不存在验证 DELETE/CAPA DELETE API：标明无此入口，不新增接口；FMEA 删除的清关联/删动作是真实需要覆盖的间接删除。

- [x] **Step 2: 运行矩阵确认 RED**

```bash
. /Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/owned-env.sh
cd "$OPENQMS_OUTCOME_ROOT/backend"
PYTHONPATH=. "$OPENQMS_OUTCOME_PYTHON" -m pytest tests/capa/test_capa_reviewed_writes.py -q
```

确认能复现实际改写或错误的 400/500；保存最小失败证据，不把通用测试框架错误算作功能 RED。

- [x] **Step 3: 接通普通编辑与关联**

`update_capa()` 最前使用 `capa = await lock_material_write(db, capa, set(update_data))`，在任何供应商处理、字段 mutate、lesson/embedding/outbox 之前执行；保留原 D7+/d8_closure freeze。`link_fmea()` 先 `lock_material_write(db,capa,{'fmea_ref_id','fmea_node_id'})`，再检查/操作来源；不再保留一条无检查的重复锁路径。

在 `capa_current_access.py` 定义 `current_capa_actor_target(db, actor_id: UUID, report_id: UUID, required_level: PermissionLevel) -> CAPAEightD`：由服务端 actor UUID 构造只含 user_id 的内部 scope，调用既有 current_capa_access，检查最低等级，再调用 current_capa_target；不接收调用方角色或范围声明。CAPA HTTP 层在 admission、锁后都用该 fresh 权限和目标范围，不能仅使用 token/旧 scope 缓存。没有调用者 scope 的内部服务仍必须做终态保护，不能引入可从请求传入的 bypass 参数。

- [x] **Step 4: 接通采纳和验证**

`adopt_recommendation()` 在 `_find_existing_adoption()` 之前执行父锁/终态保护；保留原去重和 IntegrityError 回滚语义；发生 rollback 后的既有记录返回路径也必须重新取得父锁、刷新并检查终态。`create_verification()` 必须在校验/插入任何子记录前取父锁；failed 计数不再另走晚期父锁。`update_verification()` 改为父行→verification 行，父锁后再载入原记录和更新；删除原先“先改子记录、failed 才补父锁”的分支。禁止 guard 之前 autoflush。

- [x] **Step 5: 接通 D7 及文档门禁写阶段**

D7 record/auto_fill 最前取父锁/终态检查，再执行原 `_assert_d7_stage`；终态固定 409，其他错误阶段仍保持既有业务错误，不放松 FMEA 编辑权限或推荐匹配。

doc-gate `_phase1_create_running`、`_phase3_cas`（包括 llm_error 分支）、`run_audit`、`record_defer`、`confirm_no_affected`、`record_gate_waiver` 在 demote/current/CAS/decision 变更之前取父锁、刷新并确认仍为 D8_GATE_PENDING。多阶段 LLM 调用不跨网络持事务；phase3 重入时再用 current_capa_actor_target 核验当前 actor 的 EDIT/范围并检查父行状态，终态不能修改当前/历史审核依据。GET 和只读推荐不误用写 guard。

- [x] **Step 6: 保护 FMEA/CP 间接删除**

按实现决定 §4，在原 ProductLine 锁之前获取关联 CAPA 父锁、判断终态；文档锁后重查引用集合，新增未锁引用则回滚重试，不持文档锁反向拿 CAPA 锁。FMEA 的 `_null_out_fmea_references()` 和 `delete(CapaD7NodeAction)` 必须位于此保护之后；CP 删除同样保护 snapshot 中的历史版本。

写正反测试：闭案引用阻止删除且 graph/outbox/版本/关联不变；未结案引用仍保持原清理行为；正常新建 FMEA/CP 版本继续允许；间隙中新增引用导致冲突而非漏删/死锁。引用查询应以当前 namespace 和来源 factory 为边界，固定错误不暴露无权 CAPA ID。

- [x] **Step 7: GREEN 与明确回归**

```bash
. /Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/owned-env.sh
cd "$OPENQMS_OUTCOME_ROOT/backend"
PYTHONPATH=. "$OPENQMS_OUTCOME_PYTHON" -m pytest tests/capa/test_capa_review_guard.py tests/capa/test_capa_reviewed_writes.py tests/capa/test_capa_review_source_guard.py tests/capa/test_capa_update_freeze.py tests/capa/test_capa_verification_service.py tests/capa/test_capa_verification_api.py tests/capa/test_capa_d7_action_service.py tests/capa/test_capa_d7_api.py tests/capa/test_capa_doc_gate_regression.py -q
```

追加现有 FMEA/CP 删除测试的真实文件到任务报告；仅更新终态固定 409 的断言，保留 D8 补报告例外、早期修改和来源版本正常演进。授权后提交 `fix(capa): freeze reviewed materials across write paths`。

### Task 3: 完整结果读取、来源约束与版本 DTO

**Files:** Create service/schema/outcome tests；Modify `capa_current_access.py`、`api/capa.py`、测试 support 与 API 测试；更新 API/服务 README。

**Interfaces:** `read_outcome_review(db, scope, report_id) -> CapaOutcomeReview`；`collect_outcome_material(db, capa) -> dict`；`outcome_revision(material: dict) -> str`；`resolve_review_round(db, capa) -> UUID|None`。输出严格按实现决定 §2/§3；material 是 repr 不带内容的内部值，不接收客户端 JSON。

- [x] **Step 1: 写完整版本与权限 RED**

```python
@pytest.mark.asyncio
async def test_all_verification_rows_participate_in_revision(review_case):
    from sqlalchemy import update
    from app.models.capa import CapaRootCauseVerification
    from app.services.capa_outcome_review import read_outcome_review
    async with review_case.session_factory() as db:
        old = await read_outcome_review(db, await review_case.scope(db),
                                        review_case.report_id)
    async with review_case.session_factory() as db:
        await db.execute(update(CapaRootCauseVerification).where(
            CapaRootCauseVerification.verification_id == review_case.verification_id
        ).values(result='复测结果已补充'))
        await db.commit()
    async with review_case.session_factory() as db:
        new = await read_outcome_review(db, await review_case.scope(db),
                                        review_case.report_id)
    assert old.revision != new.revision
    assert new.verifications[0].result == '复测结果已补充'
```

这里直接 SQL 只模拟真实外部提交，不用于绕过生产权限的验收。另测 D4/5/6/7、证据列表、source_ref、verification 增/删、D7 动作、gate decision/version 各变化；补充/updated_at/归档/generation 不改变核心 digest；排序不改变版本。

- [x] **Step 2: 运行 RED 并定义严格 DTO**

```bash
. /Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/owned-env.sh
cd "$OPENQMS_OUTCOME_ROOT/backend"
PYTHONPATH=. "$OPENQMS_OUTCOME_PYTHON" -m pytest tests/capa/test_capa_outcome_review.py -q
```

复用 `VerificationResponse`、`D7NodeActionResponse`，定义 OutcomeDocumentRef/OutcomeDecision/Supplement/Response；正文集合 `repr=False`，固定 contract/review_scope。新读端点拒绝非 access 用户凭据，复用当前 tenant binding；无源权返回常量 403，不返回部分材料/数量。single 明确 public，多租户不得 public fallback。

- [x] **Step 3: 实现确定性版本函数**

```python
import hashlib
import hmac
import json
from app.config import settings

def outcome_revision(material):
    canonical = json.dumps(material, sort_keys=True, ensure_ascii=False,
                           separators=(',', ':'))
    return hmac.new(settings.SECRET_KEY.encode(),
                    ('openqms.capa.outcome-review.v1\0' + canonical).encode(),
                    hashlib.sha256).hexdigest()
```

`collect_outcome_material` 只序列化本计划白名单；不得使用 ORM `__dict__`、最新源文档正文或把 d8_closure/updated_at 加进 token。按 UUID 批次读取全部验证/动作，不用 UI 页截断参与计算。来源引用对齐 report/factory/PL，FMEA 节点检查复用既有严格规则；CP source 用 PLANNING VIEW。doc-gate snapshot 绑定真实 FMEAVersion/ControlPlanVersion 的 version ID、所属对象/factory 和 SHA256；不以任意 JSON 自报版本为准。所有明确 FMEA 引用（报告、验证、D7）也进入来源版本集合：pending 时在既有 gate snapshot 外补齐当前受控版本，若没有可绑定的受控版本则固定冲突，不由 GET 创建版本。结案/归档后只能使用批准回执和既有 gate 绑定的历史版本，引用节点应对照该版本 snapshot 而非 latest graph。来源正常出新版不得让旧批准材料改绑或无故失效。历史无法恢复完整绑定时明确 legacy/无法验证，不编造历史节点或 silently 用最新版本。

- [x] **Step 4: 让读取与所见版本保持同一事务快照**

快照连接只从当前 `db.bind` 对应的测试/业务引擎和入口捕获的 TenantBinding 构造，不能从全局 DATABASE_URL 另开可能指向种子库的连接。在专用 tenant-bound REPEATABLE READ READ ONLY 快照中构造材料和 DTO（沿用 R4b-1 的安全连接/门禁模式，不改变其 canonical）；生成后在请求 DB 重查当前 actor、范围、来源、当前 round/material revision。任一变化整次冲突，不返回旧正文。不得为复用 preview 把其 200 条预算、替换词或 30 秒 TTL 搬到正式资料。

在 READ COMMITTED 的审批写事务中调用同一 material collector，但由父行/子写协议及受控来源版本锁保证一致，不在已开始事务中临时改变 isolation，也不把只读连接误当成写事务。

在测试 support 定义 `review_expectation(db, capa) -> dict`，仅用于保留既有 flush-only 单元测试；它调用真实 collector/轮次/版本函数，不替换任何权限或校验：

```python
from app.services.capa_outcome_review import (
    collect_outcome_material, outcome_revision,
)

async def review_expectation(db, capa):
    material = await collect_outcome_material(db, capa)
    return {
        'expected_outcome_revision': outcome_revision(material),
        'expected_review_round_id': material['round_id'],
    }
```

新读取 API、并发与最终验收必须使用真实提交 case，不得用该 helper 冒充完整 HTTP/RR 快照证据。

- [x] **Step 5: 加 API、历史兼容和 GREEN**

```python
@pytest.mark.asyncio
async def test_outcome_read_is_not_cached(review_http_client, review_case):
    response = await review_http_client.get(
        f'/api/capa/{review_case.report_id}/outcome-review')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['contract'] == 'capa.outcome-review.v1'
```

测试 pending/closed/archive、跨 tenant 同 UUID、源模块撤权、工厂/产品线迁移、缺失版本、legacy pending/closed、补充审计提取、HMAC 无法重验。GET 不写 audit round、业务、embedding 或 outbox。运行 outcome service/API 与 R4b-1/R4a 当前读取回归；授权后提交 `feat(capa): expose version-bound outcome review`。

### Task 4: 把批准与驳回绑定本轮实际材料

**Files:** Modify `schemas/capa.py`、`api/capa.py`、`capa_service.py`、outcome service；Create decision/concurrency/API tests；精确更新既有 advance 审批测试调用方和文档。

**Interfaces:** 新 `require_outcome_expectation(db, scope, capa, req) -> dict` 返回安全回执 metadata；`apply_outcome_expectation(db, capa, req, actor_id) -> dict` 用于 service 直接调用并执行同一校验。服务不能从客户端接收准备好的回执替代校验。原 `advance_capa(db,capa,user_id,req=None)` 签名保留，但 D8 决定不可因 req=None 绕过。

- [x] **Step 1: 写缺版本、旧版本与旧轮次 RED**

```python
@pytest.mark.asyncio
async def test_approve_without_seen_revision_is_rejected(
    review_http_client, review_case,
):
    before = await review_case.snapshot()
    response = await review_http_client.post(
        f'/api/capa/{review_case.report_id}/advance',
        json={'target_state': 'D8_CLOSURE'},
    )
    assert response.status_code == 409
    assert response.json()['detail'] == 'CAPA_OUTCOME_REVIEW_REQUIRED'
    assert await review_case.snapshot() == before
```

另测新版看完材料后修改 D6/验证、驳回重提后使用旧 round、EDIT 用户附真实 token 仍 403、合法自有 APPROVE 用户不因本人提交被新增阻断、reject_reason 空仍拒绝、直接 service 缺版本仍拒绝。

- [x] **Step 2: RED 后更新 DTO/调用契约**

```python
from pydantic import Field

# 加到既有 AdvanceRequest，不改早期推进/归档语义。
expected_outcome_revision: str | None = Field(
    default=None, pattern=r'^[0-9a-f]{64}$')
expected_review_round_id: uuid.UUID | None = None
```

仅审批/驳回两条边强制字段。不得给生产服务或 tests 加 `skip_review_version` 开关。已真实提交的单测先读取 review revision 再提交。现存 flush-only `db` 夹具不能被独立 RR 连接读取：这类原有权限/流程单测使用下面定义的同事务 review_expectation helper，或改为真实 sessionmaker case，不能盲调 GET 后得到 404。权限拒绝测试仍先 403，不为了拿 token 赋予无权用户源权限。逐一核对实际直接调用文件 `test_capa_advance_flow.py`、`test_capa_post_review_fixes.py`、`test_lateral_diffusion_service.py`、`tests/recommendation/test_capa_lesson_embedding_chain.py`、`test_lessons_extraction.py` 及 frontend/e2e 的关闭请求；只升级其中 D8 决定调用。旧夹具若缺当前已验证根因/正式措施/门禁前置，应补真实前置，而非放松新条件。早期 3-arg 推进和归档仍保留兼容。

- [x] **Step 3: 固定事务顺序**

父行锁后，基于 fresh 状态判定 EDIT/APPROVE 边；fresh 当前角色/工厂/产品线检查，审批必要源可读，round/revision 相同。批准还检查当前根因匹配 passed 记录、D5/D6 材料非空；不通过非空文本自动判断“已有效”。

批准前重新调用已有 `_d8_doc_gate_gate()` 的 C8/C9 完整检查，保留其 analysis→ProductLine→排序文档父锁，不复制一个简化版门禁；把明确引用但不在 affected snapshot 的来源父行一并纳入排序锁集合，再重算完整版本并比较预期 token。这些锁和 CAPA 父锁持有至结案事务结束。再执行原知识沉淀、横向扩散、状态变化和 outbox；任何长 await 后、最终提交前再核对当前 actor/范围/来源权限和 tenant admission，失败回滚数据库变化，不先返回审批成功。不宣称回滚可以收回既有合法外部调用已传输的信息。

驳回同样绑定所见 round/revision 与当前 APPROVE，保留必填理由和 D7 回退；不替代或执行现场补偿。内部 service 直接调用须构造当前 actor scope（服务端 UUID），复用 fresh access，不从 ORM 历史角色猜测。

- [x] **Step 4: 在既有决定审计中保存安全回执**

```python
receipt = {
    'contract': 'capa.outcome-review.v1',
    'round_id': str(round_id),
    'revision': revision,
    'doc_decision_id': str(doc_decision_id),
    'source_versions': source_versions,
}
# 增加到本次 D8_APPROVED/D8_REJECTED 的 changed_fields，不能另写第二次决定。
changed_fields['outcome_review'] = receipt
```

`round_id/revision/doc_decision_id/source_versions` 只能来自 Task 3 的校验输出。既有驳回理由仍为正式业务记录，不能复制全包正文进 audit。批准后用该 receipt 读取历史绑定；补充更新和归档不替换它。

- [x] **Step 5: 用真实会话证明两个竞争方向**

新并发测试不使用 flush-only `db`：session A 用已缓存旧 pending 对象调用真实写服务；session B 持父行锁进行真实审批并提交，A 获锁后须 ReviewedContentLocked。用 Events/SQLAlchemy 测试级 execute witness 确认 A 已到锁请求，不能靠 sleep 猜测；另查 `pg_blocking_pids` 证明确实等待。

反向让 A 修改 D6 或 verification 先提交，B 持旧 token 审批必须冲突、仍 pending，无 D8_APPROVED、知识沉淀、横向扩散或 MES 成功副作用。还测批准/驳回并发、角色在锁等待中撤权、源版本变化、事务失败和重试不重复决定。

单元/并发测试可以只替换 provider 的外部响应以隔离网络，不能替换 authorize、版本 collector、状态迁移或 commit；这不是最终真实 LLM/HTTP 通过证据。

- [x] **Step 6: GREEN 与历史闭环回归**

```bash
. /Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/owned-env.sh
cd "$OPENQMS_OUTCOME_ROOT/backend"
PYTHONPATH=. "$OPENQMS_OUTCOME_PYTHON" -m pytest tests/capa/test_capa_outcome_decision.py tests/capa/test_capa_review_concurrency.py tests/capa/test_capa_advance_flow.py tests/capa/test_capa_advance_permission.py tests/capa/test_capa_doc_gate_freshness.py tests/capa/test_knowledge_sink.py tests/capa/test_lateral_diffusion_concurrency.py -q
```

记录升级的旧审批调用方列表，禁止把旧权限/门禁断言改成“非 403 即通过”。授权后提交 `feat(capa): bind D8 decisions to reviewed outcome versions`。

### Task 5: D8 集中审核面板与终态只读

**Files:** Create `capaOutcomeReview.ts`、`CapaOutcomeReviewPanel.tsx` 及其测试；Modify `api/capa.ts`、API 测试、CAPADetailPage/测试、zh/en locales；必要时修改 D4VerificationCard 的只读展示，保持原编辑场景。

**Interfaces:** `getCapaOutcomeReview(id: string, signal?: AbortSignal): Promise<CapaOutcomeReview>`；advance 增加两个 expected 字段及可选 signal。Panel props 为 `{reportId:string; status:string; canApprove:boolean; credentialIdentity:string; onReviewChange:(review:CapaOutcomeReview|null)=>void}`。父页只从当前 Panel 成功回调取得 token，不另有隐藏批准入口。

- [x] **Step 1: 写 DTO 和材料显示 RED**

```typescript
import { render, screen } from '@testing-library/react';
import { App } from 'antd';
import { BrowserRouter } from 'react-router-dom';
import { it, expect, vi } from 'vitest';
import * as capaApi from '../../api/capa';
import CapaOutcomeReviewPanel from './CapaOutcomeReviewPanel';
import type { CapaOutcomeReview } from '../../types/capaOutcomeReview';

vi.mock('../../api/capa', async () => ({
  ...await vi.importActual<typeof import('../../api/capa')>('../../api/capa'),
  getCapaOutcomeReview: vi.fn(),
}));
const id = '00000000-0000-4000-8000-000000000001';
const reviewFixture: CapaOutcomeReview = {
  report_id: id, status: 'D8_APPROVAL_PENDING', contract: 'capa.outcome-review.v1',
  review_round_id: '00000000-0000-4000-8000-000000000002',
  revision: '1'.repeat(64), binding_status: 'pending',
  core: { d4_root_cause: '扭矩不足', d5_correction: '更换扭矩控制工具',
          d6_verification: '实施后复测合格', d7_prevention: '更新点检要求' },
  verifications: [{
    verification_id: '00000000-0000-4000-8000-000000000003', capa_id: id,
    root_cause_text: '扭矩不足', method: 'observation', result: '复测合格',
    is_verified: true, conclusion: 'passed', evidence_attachments: [],
    source_ref: null, verified_by: id, verified_at: '2026-10-23T00:00:00Z',
    created_at: '2026-10-23T00:00:00Z',
  }],
  d7_actions: [], documents: [], decision: null,
  supplement: { text: '补充说明', review_scope: 'unreviewed_supplement',
                updated_by: null, updated_at: null },
};
const renderPanel = () => render(
  <App><BrowserRouter><CapaOutcomeReviewPanel
    reportId={id} status="D8_APPROVAL_PENDING" canApprove
    credentialIdentity="owned-identity-1" onReviewChange={vi.fn()}
  /></BrowserRouter></App>,
);

it('shows actual measures and excludes the supplement from reviewed core', async () => {
  vi.mocked(capaApi.getCapaOutcomeReview).mockResolvedValue(reviewFixture);
  renderPanel();
  expect(await screen.findByText('实施后复测合格')).toBeInTheDocument();
  expect(screen.getByText('结案后补充，未纳入本次审核')).toBeInTheDocument();
  expect(screen.getByTestId('capa-outcome-core')).not.toHaveTextContent('补充说明');
});
```

上面的无 FMEA/CP 场景允许 documents 为空；另加真实 document ref 与 D7 action fixture 验证来源版本和权限失败的显示，不以空集合代替来源契约覆盖。使用与现有页面测试相同的 i18n/auth store 包装；将 getByTestId 配置为 data-e2e 并在测试结束恢复，避免污染其他文件。

- [x] **Step 2: 定义新读取与 advance 类型**

```typescript
export async function getCapaOutcomeReview(id: string, signal?: AbortSignal) {
  return (await client.get<CapaOutcomeReview>(
    `/capa/${id}/outcome-review`, { signal },
  )).data;
}
```

类型严格复用完整 DTO；不缓存到 Zustand/localStorage/IndexedDB，不把普通报告改成 30 秒自动消失。既有 Axios 401 自动重放若覆盖 advance，需为这条决定 POST 加精确不自动重放规则并测 `frontend/src/api/client.ts`；不能重写全站认证状态机。

- [x] **Step 3: 实现纯文本集中面板**

D8 pending/closed/archive 展示根因、实际措施、D6 结果、验证方法/结论/证据元数据、D7 记录和受控版本；证据不内联执行 URL/HTML，不提取附件。显示当前状态和 legacy/无法验证绑定，不把 D7 pending 画成 verified，不把非空 D6 自动画成“有效”。必要源读取失败时不显示批准按钮，不能以“部分加载成功”放行。

- [x] **Step 4: 唯一决定入口绑定当前面板**

```typescript
const req: AdvanceRequest = {
  target_state: 'D8_CLOSURE',
  expected_outcome_revision: review.revision,
  expected_review_round_id: review.review_round_id!,
};
await advanceCAPA(id, req);
```

上述代码只在 pending、canApprove、review 与当前身份/report 匹配、round 非空且未决定时运行；reject 同 token 加原 reject_reason。清空 token 后不能自动后台重取并批准；409 提示材料变化/已冻结，显式重新加载并重新核对。重复点击禁用，不自动重发决定。

用会话 epoch 和 controller registry 中止该面板全部并发请求；身份/token/tenant/report/selection 改变、401/403/404 或关闭时清空 review/理由。每次 await 后检查 epoch，旧成功和旧拒绝都不能覆盖新身份。新读请求失败不得继续保留可批准的旧 token；不无谓给整页普通业务状态引入新全局缓存。

- [x] **Step 5: 关闭所有终态核心编辑入口**

CAPADetailPage 的 handleUpdate/Replace/Append/Undo/link 在调用 API 前检查当前终态与核心字段；父页将 `canEdit && !reviewedState` 传到所有实际材料编辑组件。pending 仍保留原阶段规则。终态面板为只读；补报告在 closed 下可编辑，在 archived 下不可编辑且始终显示未审标识。不用这个本地检查代替 Task 2 后端保护。

- [x] **Step 6: 乱序响应测试、GREEN 与类型检查**

测试 A 请求未回→同文档切 B→A 成功/拒绝迟到；旧 token 不能批准；closed/admin 没有核心编辑/采纳按钮；D4/D5/D6 原可编辑流程无新审批按钮；补报告不改变 approved core 标志。

```bash
. /Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/owned-env.sh
cd "$OPENQMS_OUTCOME_ROOT/frontend"
npx vitest run src/components/capa/CapaOutcomeReviewPanel.test.tsx src/pages/capa/CAPADetailPage.test.tsx src/api/capa.test.ts
npx tsc --noEmit
npm run build
npx tsc --noEmit -p tsconfig.e2e.json
```

授权后提交 `feat(capa): add consolidated D8 outcome review panel`。

### Task 6: 未审补充报告的来源与派生结果边界

**Files:** Modify `backend/app/services/capa_lessons_service.py`、`backend/app/services/knowledge_sink_service.py`、`backend/app/services/recommendation_sources_extra.py`、`backend/app/api/knowledge.py`、outcome service、`tests/capa/test_knowledge_api.py`、`tests/recommendation/test_capa_lesson_embedding_chain.py` 和 Task 5 面板测试；Create `test_capa_outcome_supplement.py`。

**Interfaces:** 补充来源统一字面量 `unreviewed_supplement`。`KnowledgeEntry.fields['closure_review_scope']` 使用该值；D8 `CapaLessonLearned.tags` 追加固定 `review_scope:unreviewed_supplement`（去重），D7 lessons 不借此被标为 approved。不新增模型列/迁移，不改旧知识授权/分类。

- [x] **Step 1: 写补充不改变批准绑定 RED**

```python
@pytest.mark.asyncio
async def test_supplement_never_rebinds_approval(review_case):
    from app.services.capa_service import update_capa
    from app.services.capa_outcome_review import read_outcome_review
    await review_case.set_status('D8_CLOSURE')
    async with review_case.session_factory() as db:
        before = await read_outcome_review(db, await review_case.scope(db),
                                           review_case.report_id)
        capa = await review_case.report(db)
        await update_capa(db, capa, {'d8_closure': '补充说明'}, review_case.actor_id)
    async with review_case.session_factory() as db:
        after = await read_outcome_review(db, await review_case.scope(db),
                                          review_case.report_id)
    assert before.revision == after.revision
    assert before.decision == after.decision
    assert after.supplement.review_scope == 'unreviewed_supplement'
```

另以 Task 4 真实新回执重复同测试，确认 verified 绑定不变；legacy 不伪造新版已验证回执。mixed PUT（d8_closure+d5）整体拒绝，archived 仍不能补写。

- [x] **Step 2: 在原来源抽取处加明确未审语义**

`_extract_lessons(..., source_d_step='d8')` 在生成 tags 时加入固定 tag；`_assemble_deterministic_fields()` 为 closure 增加 `closure_review_scope`。现有 `_extract_d8_with_cleanup` 的 savepoint、旧 embedding/outbox 清理和失败回滚顺序保持，不先 mutate capa；不产生新的 D8_APPROVED，也不重签 receipt。

在传给既有摘要流程的字段/提示中明确 closure 是未审补充，不能解释为已审根因或已验证效果；不扩大送模字段或新增 provider 调用。下游读取投影必须保留该机器标记：knowledge API 在返回 source_type=capa 且含 closure 的 fields 副本中补齐 unreviewed_supplement；recommendation_sources_extra 读到 source_d_step=d8 时把同一未审标记带入来源元数据，必要时在派生文本前标明“未审核补充”。不得 mutate ORM 或回填历史数据库。旧数据无标记不默认为 approved，只有文本的消费者也不能根据来源 CAPA 已结案就将其当成已审依据。

- [x] **Step 3: 补充修改责任 metadata**

outcome GET 只从该报告最近包含 d8_closure 的 UPDATE 审计取得 updated_by/updated_at；不把 CAPA 主表 updated_at 当成补充的专属时间。没有审计时返回 null，不推测操作人。界面显示未审标识和可用的修改责任信息；不复制审计中的私有 before/after 到新 DTO。

- [x] **Step 4: GREEN 与原知识链回归**

```bash
. /Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/owned-env.sh
cd "$OPENQMS_OUTCOME_ROOT/backend"
PYTHONPATH=. "$OPENQMS_OUTCOME_PYTHON" -m pytest tests/capa/test_capa_outcome_supplement.py tests/recommendation/test_capa_lesson_embedding_chain.py tests/capa/test_knowledge_sink.py tests/capa/test_capa_update_freeze.py -q
```

验证既有补报告能力仍可用，但任何派生结果都没有“该补充已批准”标志；D7 正式核心及其引用不变。授权后提交 `fix(capa): distinguish unreviewed closure supplements`。

### Task 7: 真正员工 HTTP、租户及浏览器验收

**2026-10-31 用户批准的验收分层**：真实 AI 正向闭环与双模块撤权保护分开取证。正向用例必须执行实际 provider、业务门禁、生产 advance、浏览器批准、知识沉淀和横向扩散；不能用模拟结果替代。FMEA 与 PLANNING 撤权用例允许建立明确标注的确定性保护前置（含真实受控版本和来源绑定），随后通过真实员工 HTTP、数据库与当前权限校验分别断言整包拒绝和零成功副作用。该前置不得经新增 nonce/HTTP 假批准接口提供，不计作真实 AI 影响选择或门禁成功，不再要求不受控的 AI 在同一轮必选全部候选文档。必须保留两个模块的独立拒绝断言，不能仅检查 AI 本次恰好选中的子集。既有业务状态、门禁、来源权限和生产行为不变；此调整不豁免任一剩余检查或最终清理。

**Files:** Create outcome harness/browser/spec；Modify `playwright.agent.config.ts`；补齐 API/concurrency tests，更新相关 README。

**Interfaces:** `owned_outcome_server` fixture 返回 `{app, base_url, tenant_slug, report_id, editor_login, approver_login, session_factory, binding, nonce}`；`session_factory` 创建真实 TenantSession。仿照现有 owned harness 的 provision/loopback/teardown，但不调用 `owned_local_trial.enable()`、插件注册、DIRECT 替换或旧 scanner 配置。

- [x] **Step 1: 创建隔离生命周期并登记清理**

仅使用当前获授权的随机 `_test` DB，真实 public/tenant migrations、业务租户和当前角色。新 FastAPI app 挂真实 auth/capa/product-line/fmea/control-plan/knowledge 路由、TenantContextMiddleware 与 Task 1 窄异常处理；不替换 normal get_db/权限判断/commit。

使用分配的 loopback socket 和已有 Chromium；复制既有 Vite 控制器的 no-proxy、安全 env 白名单、进程失败检测、finally 关闭自有进程。harness 的 nonce 控制端点只用于切换真实权限/并发窗口和读取自有断言数据，不提供 fake approval/doc-gate/版本响应。

- [x] **Step 2: 验证无需逐步审批的正向业务链**

工程师经实际业务端点形成可验证根因、填正式措施/实施结果；D7 按现有要求处理，D8 文档门禁使用当前获授权测试 provider 和真实业务服务，最后提交到 pending。不要用“状态直接设为 pending”代替这条正向链的证据。

最终 provider/知识沉淀/横向扩散链缺凭据或不可用时，报告 BLOCKED 并保留真实错误类别；不能在最终验收 monkeypatch passed gate、sink、authorize 或生产 advance。单独的保护场景可预置终态记录，但不能将其计作正向结案已贯通。

- [x] **Step 3: 写浏览器用例**

```typescript
await page.getByTestId('capa-outcome-core').waitFor();
await expect(page.getByTestId('capa-outcome-core'))
  .toContainText('实施后复测合格');
const closed = page.waitForResponse(r =>
  r.url().endsWith(`/capa/${reportId}/advance`) &&
  r.request().method() === 'POST');
await page.getByTestId('capa-outcome-approve').click();
expect((await closed).status()).toBe(200);
await expect(page.getByTestId('capa-status')).toHaveText('D8_CLOSURE');
await expect(page.getByTestId('capa-outcome-core')).toHaveAttribute('data-readonly', 'true');
```

`reportId` 从 harness config 获取，正常登录获取当前 token；不直接注入伪造的 APPROVE store。测试从网络捕获实际发出的 expected revision/round，断言与显示版本相同，而不是只看按钮文案。

- [x] **Step 4: 反向、保护与同文档身份切换**

覆盖 EDIT 审批 403；审批期间 D6/验证变更导致旧版本 409；驳回必须理由并回到 D7，重提后旧轮次失效；批准后 PUT/采纳/验证直接 HTTP 均 409，材料/副作用快照不变；补报告只显示未审；归档后只读；source 撤权不返回半包；真实同 document 切换用户后旧响应不能回填或继续批准。

用 Task 4 并发测试证明等待锁的真实修改被拒绝，不用浏览器 sleep 替代事务证明。跨 tenant 同 UUID、当前工厂/PL/来源权限在真实 HTTP 上各有断言。

- [x] **Step 5: 运行真实验收并记录退出码**

```bash
. /Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/owned-env.sh
cd "$OPENQMS_OUTCOME_ROOT/backend"
PYTHONPATH=. "$OPENQMS_OUTCOME_PYTHON" -m pytest tests/capa/test_capa_review_concurrency.py tests/capa/test_capa_outcome_api.py -q
PYTHONPATH=. "$OPENQMS_OUTCOME_PYTHON" -m pytest tests/e2e/test_capa_outcome_review_browser.py -q
```

受控 runner 将 config 的 testMatch 增加 `**/capa/outcome-review.spec.ts`，调用与现有一样的已安装 Playwright CLI，retries=0、workers=1。缺浏览器不能自动下载安装。所有关键项需真实执行；skip 只能作为未验证限制，不能写成通过。授权后提交 `test(capa): verify outcome review and post-close immutability`。

### Task 8: 规格/故事同步、冻结回归与交接

**Files:** Create `docs/development/capa-outcome-review.md`；Modify `PROGRESS.md`、当前规格、runtime roadmap、`docs/permissions.md`、实际受影响 API/services/前端 README；按实际契约同步 US-E2E-01.3 及需要变化的 01.7/01.8、对应 verify skills。不得无关升级全部故事或修改未变的日期。

**Interfaces:** 没有新业务接口；产出真实验收台账与可重跑命令，标明 legacy、未审补充、终态 409 和受控修订未实现。

- [ ] **Step 1: 写操作指南和受影响故事**

指南明确工程师和审核人的操作、角色配置当前仅用户分配 UI/权限 API、审批是结果接受不是外发、补充不是已审更正、正式资料没有 7 天清理、自批不变、错误后的显式重新核对、历史无绑定状态。

实施完成时，将 01.3 从 v1 修订为 v2（终态不可覆写及所见版本），01.7 从 v2 修订为 v3（最终决定时复核现有门禁），01.8 从 v1 修订为 v2（未审补充来源语义），修订日期使用实际完成日期；保留 D7 pending 范围。同步 `.claude/skills/verify-capa-8d-d4-d7-audit/SKILL.md`、`verify-capa-8d-doc-update-gate/SKILL.md`、`verify-capa-8d-knowledge-sink/SKILL.md` 的故事版本/日期与受影响剧本，之后才用于走查。本轮写计划不提前改故事或 skill 的已实现契约。更新仅服务本片，不新增现场执行模型。

- [ ] **Step 2: 自检规格覆盖与源码冻结**

逐条对照本文末覆盖表；记录源码/配置文件 SHA256 manifest（排除文档和 node_modules/临时文件）。实际查询数据库证明没有新候选表/迁移或开关，不以“本来没写”代替范围检查；记录使用的 public/tenant head 不变。

- [ ] **Step 3: 冻结后完整门禁**

```bash
. /Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/owned-env.sh
cd "$OPENQMS_OUTCOME_ROOT"
make check
cd "$OPENQMS_OUTCOME_ROOT/frontend"
npx vitest run src/api/capa.test.ts src/pages/capa/CAPADetailPage.test.tsx src/components/capa
npx tsc --noEmit -p tsconfig.e2e.json
```

`make check` 必须使用登记的自有随机 DB 配置；原有两项 graph 忽略明确列入报告。重复真实 outcome 浏览器；回归受影响的 R4a/R4b-1/R4b-2 链，若需要真实 ClamAV 专用环境，只在其精确镜像/资源本轮仍获授权时执行，否则明确阻塞项。不得启动或清除别人的历史诊断 Compose。

- [ ] **Step 4: 核对结果而非预写通过**

记录实际测试数、失败/skip/xfail/xpass/warnings、命令和退出码，解释专用 gate 与普通 suite 的区别；核对 manifest 未变。若最后又改源码，相关 gate 与完整冻结验证重新执行，不能用改前的绿灯收口。

- [ ] **Step 5: 清理自有资源并交接**

只删除登记属于本片的随机库、schema、卷、端口监听和子进程；确认无挂起事务/浏览器/Vite。校验本地文档链接、代码引用、`git diff --check` 和实际变更清单；保留 worktree，不自动 merge/push/deploy。授权后提交文档与最终测试修正，主题 `docs(capa): close consolidated outcome review acceptance`；否则如实报告未提交。

## 四、规格覆盖与实施台账

| 规格要求 | 对应任务 | 最终应有证据 |
|---|---|---|
| §1–3 不逐步审批，D4 必须验证 | 4、5、7、8 | 正常前期推进、验证失败阻断，无候选审批 UI/表 |
| §4 审核真实措施和结果 | 3、4、5、7 | 完整材料 DTO、人工所见版本、无自动有效结论 |
| §5 通过/驳回/重提 | 4、7 | 唯一 D8 决定、必填理由、合法 D7 回退、新轮次 |
| §5.4 P1 终态全入口冻结 | 1、2、4、7 | 服务/API 矩阵、FMEA/CP 间接删除、锁等待正反竞争 |
| §6 当前权限和自批不变 | 2、3、4、7 | EDIT/APPROVE、当前撤权/范围、无新增自批判断 |
| §7 来源权限和正式保留 | 2、3、6、8 | 全源权限、历史文档版本、无 7 天正式记录清理 |
| §8 所见版本/审计/竞态 | 3、4、7 | HMAC+round、真实提交、回执无正文、无重复副作用 |
| §9 界面与失效 | 5、7 | 只读核心、未审补充、旧响应/旧 token 无效 |
| §10 撤回原候选技术方案 | 全部、8 | 无候选表/路由/开关/CLI、无 plugin/model 扩权 |
| §11 复用与范围 | 1–8 | 无新状态/迁移/补偿/现场执行模型，原链路回归 |
| §12 验收与 §13 授权 | 7、8 | 真实 gate/完整 make check/指纹/自有清理/未部署 |

实施时逐任务记录：起止提交（或未提交状态）、RED/GREEN 命令与退出码、规格/质量复核、真实竞争/浏览器证据及未解决阻塞。本文所有复选框当前为空，不能据计划中的期望结果宣称实现完成。

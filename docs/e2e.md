# E2E Test Suite

Browser full-stack E2E via Playwright against a dedicated docker-compose stack. Manual only — not in CI.

## Run

```bash
make e2e           # up + migrate + seed + playwright test
make e2e-up        # start e2e stack (db/redis/backend/frontend)
make e2e-seed      # re-run deterministic seed (idempotent)
make e2e-down      # down -v (clears e2e DB volume)
make e2e-reset     # down -v + up + migrate + seed
```

Single module: `make e2e TEST_ARGS="--grep m1-core/fmea"`.

## Credentials

The seeded Compose suite has no committed credential template. Supply an authorized local profile only when an explicitly live test requires it; missing provider configuration means that AI-only specs skip with a warning while the non-AI suite remains runnable. Do not put a provider key in shell history, receipts, uploaded artifacts, or a copied source tree.

## Conventions

- Seed known docs use `-E2E-` infix (`PFMEA-E2E-001`); write-flow created docs use `E2E-` prefix at start (`E2E-M1-CAPA-001`). Cleanup never deletes seed.
- Account names/factories come from `/api/e2e/seed-state` — never hardcode in specs.
- Selectors use `data-e2e="..."` attributes; prefer `getByRole`. AI assertions check structure/behavior, never exact text.
- `workers:1`, `fullyParallel:false` (serial — cleanup prefixes must not race).
- E2E endpoints are gated: `E2E_MODE=1` AND `TENANT_MODE != "production"` or they don't load.

## Add a spec

1. Add input fixtures under `frontend/e2e/fixtures/input/` if needed.
2. Write `frontend/e2e/specs/<module>/<name>.spec.ts`; `loginAs(page, role)`; use `data-e2e` testids; `afterAll` → `cleanupByPrefix("E2E-<module>")`.
3. Add `data-e2e` attributes to the production component if missing (testability only).
4. Run `make e2e TEST_ARGS="--grep <name>"` to verify in isolation.

## CI 分层验收（Task 7）

此分层 CI 与上面的手工 Compose E2E 独立。它使用经过归属核验的单一
PostgreSQL 测试目标，普通层不设置 `E2E_MODE`，并显式清空 provider 与 embedding
凭据。不要借用 `make e2e-*` 的 reset/seed，或把其历史收据作为 CI 的通过证据。

### 本地受控入口

在新鲜 source export 中先提供 `OPENQMS_TEST_RESOURCE_FILE` 和唯一的
`TEST_DATABASE_URL`，再按层运行以下 Make 入口：

```bash
make check             # check-backend + check-frontend；不包含 browser/live/scanner
make check-backend     # 核验、建库/迁移同一测试目标，再运行 deterministic pytest
make check-browser     # 同一已核验目标上的 deterministic Chromium 保护层
make check-live        # 仅显式授权的 live provider 层
make agent-attachment-e2e  # 独立实际 ClamAV 过程＋host browser gate
```

`make check-test-db` 是 check/check-backend/check-browser/check-live 的前置步骤：它先核验 container 归属，再仅创建
`*_test` 数据库并执行迁移。`make check-browser` 只解析项目已安装的 Chromium；
不会下载浏览器。前端依赖必须在 export 内由 lockfile 执行 `npm ci` 安装，不能复制
`node_modules` 或以 `npm install` 替代。`agent-attachment-e2e` 是独立 scanner gate，
不属于 `make check`。

本地 resource registration 是禁止 group/world 写入的 secret-free JSON（允许 0644；建议 0600），至少含
`container`、完整 `container_id`、`owner_nonce`、`image`、`host`、`port`、
`test_database`、`application_database` 与可选 `volume`。容器必须带
`openqms.owner=<owner_nonce>` 标签，端口必须精确匹配 loopback URL；注册文件不含
URL、密码或 provider 配置。若本地同时设置 `PG15_CONTAINER` 供快照工具使用，
它必须等于登记的容器名称或完整 ID，且不得混入 CI run/job metadata。迁移 fixture
只在实际创建自己的临时库后登记 `OPENQMS_MIGRATION_TEST_DATABASE_URL`；快照工具
仅允许该登记的 `*_test` URL 或基础测试库，且实例端点、用户和凭据必须一致。
CI service 改用 `PG15_CONTAINER` 与
`openqms.ci.run` / `openqms.ci.attempt` / `openqms.ci.job` 三个标签，不能伪造
GitHub metadata 走本地路径。

### 环境、收据与状态

普通 api/browser/scanner 子进程只接收白名单的系统/运行变量；`LLM_*`、
`OPENAI_*`、`ANTHROPIC_*` 和 `EMBEDDING_*` 凭据清空；SDK 的
`OPENAI_BASE_URL` / `ANTHROPIC_BASE_URL` 从子进程环境移除，而非设为空字符串，
避免 SDK 把空值当成实际端点。应用 `LLM_BASE_URL` 等字段仍显式清空；
`LLM_TIMEOUT` 不以空字符串注入。live 仅接受显式 `--test-profile` 或 live job 的 Environment 配置，且 profile
只进入 live 子进程；不能隐式读取 `.env` 或继承代理/ambient provider 值。
可选 `LLM_TIMEOUT` 未设置或为空时为 30 秒；显式提供时必须是 1–120 的整数。
显式 `OPENQMS_AGENT_BROWSER_EXECUTABLE` 在 controller 解析为绝对、已验证的可执行路径，
仅该已允许的键传入 browser/live/scanner pytest 子进程，不因缓存缺失改用其他浏览器。

runner 将 raw JUnit 与 hook 文件保存在私有临时目录，只发布过滤后的 log 与 JSON
receipt。receipt 记录 selected/passed/failed/errors/skipped/xfail/xpass/deselected/
warnings、命令、退出码和耗时。browser/live/scanner 显式 gate 不接受 skip、xfail
或 xpass；普通 backend 层如实记录既有环境依赖 skip，不将被跳过用例称为通过。
所有层均要求非零实际选中数、完整 receipt 且退出码为零。
GitHub 每个执行层显式设置专用 `OPENQMS_TEST_ARTIFACTS` 目录，`always()` 上传实际
`*-receipt.json` 和过滤后的 `*.log`，包括失败结果；frontend 类型/构建分别保留实际命令、
日志与退出码（不是 pytest 计数）。runner 在控制台显示目录、计数与退出码，失败时显示
过滤后的诊断。不要上传 raw XML/hooks、profile/env、resource registration 或整个临时根目录。
本地可设置一个新的专用绝对目录；未设置时由 runner 分配并打印目录，不复用既有收据。

scanner 在 owned Compose teardown 前从已停止的 process 容器导出实际收据/日志至
`<artifacts>/process/`，host browser 写入 `<artifacts>/browser/`；导出只复制受控普通文件，
以 host 用户重新创建可读文件，不继承容器 root 的 0600 所有权。process receipt 仅提取
测试的安全 observations：daemon/definitions 的 VERSIONCOMMANDS、EICAR FOUND、解析阶段、
恶意/加密/展开限制拒绝与 clean 下载；不复制原始 XML。`cleanup.json` 记录 export/down/
资源检查退出码及实际剩余容器/卷/网络数，失败也保留。清理只限本次随机 project，保留
controller 已登记的 PG container、volume 与其他项目资源。

### GitHub 边界

自动 workflow 在所有分支 push 与指向 `main` 的 PR 运行；fork PR 无密钥。真实 live
和 scanner 仅为 `workflow_dispatch`，只允许 main：preflight 先冻结 main SHA，
后续 job checkout 该 SHA。summary 验证实际 receipt 的 SHA、完整计数、命令、
退出码和非空 log；scanner 还必须有两个 stage、实际 observations 与成功 cleanup；
单独写出的 PASSED wrapper 不能代替实际结果。workflow_dispatch 文件必须先正式进入
默认分支 main，才能执行远端手动事件。仅 live job 使用固定 `ci-acceptance` Environment
及其审批、测试模型配置；scanner job 不读取模型凭据，也不依赖该 Environment。管理员只需配置 main/Environment 的审批人与允许的测试配置，不在
文档或 workflow 中代为配置 secrets、Environment 或分支保护。未获 push/dispatch
授权、未触发的远端自动或手动 gate 分别记录 `BLOCKED` / `NOT_REQUESTED`，绝不能用
本地或静态收据替代。

## Owned CAPA outcome-review acceptance (Task 7)

This gate is separate from the seeded Compose suite above. Do **not** use its
reset/seed commands or six synthetic passed-gate reports as positive evidence.
Use an explicitly registered owned target and a dependency-complete Python
interpreter. Database preparation is a separate verified Make step; do not reset
shared data, enable plugins, install a local browser, or copy production config.

From the repository root with `OPENQMS_TEST_RESOURCE_FILE` and the matching
`TEST_DATABASE_URL` set:

```bash
python backend/tests/e2e/capa_outcome_runner.py api
python backend/tests/e2e/capa_outcome_runner.py acceptance --test-profile "$TEST_PROVIDER_PROFILE"
```

`api` runs the outcome API/concurrency and runner tests plus the unmarked,
provider-free HTTP source-denial protection. `acceptance` orchestrates separate
api/browser/live pytest processes: only live gets the validated provider config.
The browser-only diagnostic covers CAPA protection; `make check-browser` selects
all deterministic browser protections. Missing configuration/provider/browser or
an unexecuted required gate is failure, never a skip/pass.

There is no implicit private `run-owned.py`, historical resource registry or
`.env.e2e` discovery. Live config comes only from explicit `--test-profile PATH`
or the explicit live job Environment mapping. The allowed provider fields are
`LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`, `LLM_TIMEOUT`; profile
loading performs no shell evaluation or dotenv interpolation. Ordinary children
cannot inherit provider credentials, vendor SDK endpoint overrides or proxies.
Node/Vite/Chromium receive only the separate runtime allowlist and disposable
fixture logins, never provider/database credentials. Invalid live configuration
fails in preflight rather than silently exercising a fallback.

`owned_outcome_server` provisions two nonce-owned business tenants with real
migrations and TenantSession, normal auth/permissions/get_db/commit, allocated
loopback sockets, and narrow production review-error handlers. Identical report
UUIDs in separate schemas contain distinguishable material. Legacy terminal
protection records are explicitly synthetic, contain no fabricated approval or
gate, and cannot count as a successful lifecycle. An unbound legacy source
correctly returns conflict rather than reconstructing an approval version.

The live report starts at D1 through the real business POST. D3 import/provider,
root-cause verification, implemented D5/D6 material, current D7 dispositions and
real D8 document services precede pending. Empty-source and new-controlled-document
paths are distinct. The latter publishes actual FMEA/CP versions and requires the
provider's actual affected documents and real audit to pass; no invented decision
or skipped source is substituted. Knowledge/lateral services run unmodified on
browser approval. A legitimate empty lateral result is not evidence of a lateral
LLM call. Pending/stale-round assertions remain unverified when the provider blocks.

Chromium logs in normally and captures the actual outgoing displayed revision/
round on approval. Same-document identity switching calls the production login
action with real credentials while a nonce-controlled window holds actual server
response bytes; no forged store authority, synthetic DTO or browser sleep.
Post-close direct HTTP rejection compares material/audit/embedding/outbox snapshots.
Supplement is visibly unreviewed; archive-only supplement keeps existing 400,
while reviewed-core or mixed PUT remains 409. Transaction proofs use actual
PostgreSQL blocking witnesses, including rejection source-row waits.

Timestamped redacted logs/exit JSON and secret-free teardown journals use
`OPENQMS_TEST_ARTIFACTS`, a unique `RUNNER_TEMP` child, or a private temporary
directory, never a fixed historical `.superpowers` path. Fixtures clean only
their recorded tenants, sockets and child processes. Registered PostgreSQL
resources are not stopped by these fixtures; the scanner gate separately cleans
only its own random Compose project. Normal backend hashing explicitly
uses `public.digest`, matching the existing tenant trigger without adding public
to strict search_path. CP creation returns the existing eager-loaded service view
so async serialization does not lazy-load `items` after commit.

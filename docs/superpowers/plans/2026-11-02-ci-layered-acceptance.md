# CI 分层验收 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使功能分支在干净 Linux checkout 中自动完成无模型后端、前端与浏览器保护检查，并提供仅 main 可触发的真实 provider / ClamAV 手动验收。

**Architecture:** 保留现有业务与真实租户/HTTP/进程链，在测试边界补齐逐用例分组、可移植资源验证、浏览器定位和环境隔离。普通 CI 与真实验收分离进程、配置及证据；CI 适配验证完成后，另在隔离工作区集成 main，保留双方权限保护。

**Tech Stack:** Python 3.12 / pytest / PostgreSQL 15 + pgvector / FastAPI 既有测试 harness；Node 20 / 项目锁定的 Playwright / Chromium；GitHub Actions / Docker Compose / ClamAV 1.4.3。

## Global Constraints

- 依据：[CI 分层设计](../specs/2026-11-01-ci-layered-acceptance-design.md)。本次用户要求据此写计划，视作计划阶段依据；不代表实施或付费验收已执行。
- 不改生产业务、权限、状态机或默认能力；runtime/附件默认关闭、baseline DENY、本人审批限制及当前来源检查不变。
- 不读取/上传本地密钥，不修改用户删除的 `.env.e2e.example`，不配置 GitHub Secrets / Environment / 分支保护。
- 不靠忽略整个 `tests/e2e/`、弱化安全断言、伪造门禁或新增 xfail 获得绿灯。
- 保留原两项 graph 排除：`tests/test_graph_sync_worker.py`、`tests/test_graph_projection.py`。
- backend：`not ci_browser and not live_provider and not real_scanner`；browser：`ci_browser and not live_provider and not real_scanner`；live：`live_provider`。
- 普通 job 的 `E2E_MODE` 不设置，不写成字符串 `false`；provider/embedding 凭据显式为空。
- timeout 保持既有 1–120 秒合法范围；真实配置只进入 live 子进程。
- 自动检查 `contents: read`、checkout `persist-credentials: false`；不用 `pull_request_target`。
- 手动 workflow 仅 `workflow_dispatch`，枚举 `live-capa` / `scanner` / `all`，仅 main；固定 Environment `ci-acceptance`。
- ClamAV 固定 `clamav/clamav:1.4.3_base@sha256:be37f82c9cccf6c2559a44b8fb537e6f11e8547b37988650b169c4540c2f298c`，Ubuntu x64；PG 延续 `pgvector/pgvector:pg15`，不复制本机 arm64 digest。
- 显式 gate 的 skip、零选中、continue-on-error、空日志不得算通过；未请求的另一 gate 记 `NOT_REQUESTED`。
- 不自动安装用户本机浏览器，不使用共享 E2E reset/seed，不 shutdown Docker / prune 或清理其他项目。
- 本计划本身不授权提交、push、PR、merge 或部署；每任务提交点仅在获得相应授权后执行。

---

## 0. 基线、执行范围与文件地图

执行目录为现有工作树 `.claude/worktrees/agent-module-permission-kernel`，分支 `feature/agent-task-runtime-foundation`，计划审阅时 HEAD 为 `ef3e24e076d5ef313e415d768567809987da04bc`。不得在根目录旧分支实现或复制其未提交 CI 改动。已有 `PROGRESS.md`、`docs/architecture.md`、开发基线文档改动及示例删除须保留。

本轮只新增此计划；实施分为 A（Task 1–7，CI 适配）、B（Task 8，隔离集成和 PR 交接）。B 不阻塞 A 的交付，但未经授权不执行 Git 外发/合并。手动 workflow 文件进入 main 且管理员完成 Environment 后，才能取得远端手动验收证据，不用 YAML 检查冒充。

| 文件 | 职责 / 改动 |
|---|---|
| `backend/pytest.ini` | 注册三个 marker，开启 strict markers |
| `backend/tests/e2e/test_*.py`（Task 1 清单） | 按具体测试分类，不改业务断言 |
| `backend/tests/ci/test_layer_selection.py`（新） | 收集/分组覆盖与互斥契约，不连接 DB |
| `backend/tests/ci/owned_resources.py`（新） | 验证实例/目标库，所有建库与迁移共用不可变目标 |
| `scripts/check-ci-pure.py`（新） | 在 conftest 导入前设置专用测试 URL 并阻断网络连接 |
| `backend/tests/ci/test_owned_resources.py`（新） | 资源缺失、伪造、错库/端口/owner、legacy PG 冲突及缺库顺序负例 |
| `backend/tests/ci/prepare_database.py`（新） | 同一已核验目标上的建库、身份复核和公共迁移 |
| `backend/tests/ci/browser_runtime.py`（新） | 浏览器解析与 Node 子进程白名单 |
| `backend/tests/ci/test_browser_runtime.py`（新） | 解析失败及凭据隔离测试 |
| `backend/tests/ci/acceptance_config.py`（新） | 显式 live 配置验证；无私有 profile 导入 |
| `backend/tests/ci/test_acceptance_config.py`（新） | 缺配置/timeout/环境污染负例 |
| `backend/tests/ci/gate_results.py`、`test_gate_results.py`（新） | JUnit 计数、脱敏、必需 gate 完成判定 |
| `backend/tests/e2e/capa_outcome_harness.py` | 替换私有资源登记及固定产物目录，保留真实 tenant provisioning |
| `backend/tests/e2e/capa_outcome_runner.py`、`test_capa_outcome_runner.py` | 移除私有 runner；分进程执行 api/browser/live/acceptance |
| `frontend/playwright.agent.config.ts` | 显式路径优先，否则项目 Playwright 默认 Chromium |
| `Makefile` | 分层入口；保持 scanner Compose 入口并增强收据/清理 |
| `.github/workflows/test.yml` | 所有分支 push / main PR，无密钥三层及 docs |
| `.github/workflows/acceptance.yml`（新） | main-only dispatch 预检与两个独立真实 gate |
| `backend/tests/ci/test_workflow_contract.py`（新） | YAML/事件/权限/secret job 边界静态回归 |
| `docs/e2e.md`、`docs/development.md`、`PROGRESS.md` | 分层使用说明、实际验证结果和限制 |

新增支持代码仅供测试使用，不进入 `backend/app/`。不创建通用测试平台。不增加生产依赖；YAML 校验优先使用已有工具，需新增工具时在 CI 显式安装测试用工具，不修改应用 requirements。

### 实施前基线

- [ ] 阅读工作树的 `AGENTS.md`、`PROGRESS.md` 最新条目、`docs/DECISIONS.md` 相关测试约定、开发基线；记录 `git status --short`、HEAD、依赖版本。
- [ ] **先建立纯测试引导入口，再运行基线。** 新增 `scripts/check-ci-pure.py`，内容如下；这是实施阶段第一项测试基础设施，不在本次计划修订中创建或执行。选择已安装项目依赖的 Python 解释器；没有解释器时明确 BLOCKED，不假定工作树存在 `.venv/bin/python`。以下命令统一从仓库根目录执行，`python` 表示该解释器。

```python
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
os.environ.pop('ALLOW_SEED_DB_TESTS', None)
os.environ['SECRET_KEY'] = 'test-secret-key-for-ci-pure-only'
os.environ['TEST_DATABASE_URL'] = (
    'postgresql+asyncpg://ci_pure:ci_pure@127.0.0.1:1/openqms_ci_pure_test'
)

def reject_network(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo', 'socket.sendto'}:
        raise RuntimeError('pure_test_network_forbidden')

sys.addaudithook(reject_network)
os.chdir(ROOT / 'backend')
sys.path.insert(0, str(ROOT / 'backend'))
import pytest
raise SystemExit(pytest.main(sys.argv[1:]))
```

引导在导入 pytest / 业务 conftest 前显式设置合法 `_test` URL，不连接该端口、不绕过种子库保护。SQLAlchemy 创建 engine 不等于发起连接，可以正常收集；一旦尝试网络连接则失败。先以临时纯测试断言 `os.environ['TEST_DATABASE_URL']` 等于上值、`ALLOW_SEED_DB_TESTS` 不存在，并用 `pytest.raises(RuntimeError, match='pure_test_network_forbidden')` 包围 `socket.create_connection(('127.0.0.1', 1))`，证明 guard 生效；再跑下面基线。所有 collection / pytest 样本子进程也必须通过此入口（不可直接 `python -m pytest` 绕开）；禁止通过 shell/Node 或其他进程联网。此入口仅用于不请求 DB fixture 的纯测试，不能用作真实数据库或浏览器验收。

- [ ] 在不读取 `.env.e2e` 的环境中先跑无 DB runner 测试与前端类型检查，记录真实失败而非引用旧 3450 结果：

```bash
python scripts/check-ci-pure.py tests/e2e/test_capa_outcome_runner.py -q -rA
make check-frontend-tsc
```

- [ ] 实际 DB/browser 基线需要新登记自有测试资源；先完成 Task 2 的只读验证，再迁移/运行。不连接默认开发库。无可用资源时将该项记 BLOCKED，不启动未经批准的本机依赖。

## Task 1: 建立可审计的逐用例分组

**Files:** Modify `backend/pytest.ini`；以下测试文件；Create `backend/tests/ci/__init__.py`、`backend/tests/ci/test_layer_selection.py`。

**Interfaces:** 产生严格 marker 和三个固定选择表达式，后续 Makefile/workflow 必须一致。收集测试用 pytest collection API，不加载业务 fixture、不调用外部服务。

- [x] **Step 1 — 写失败分类测试。** 在收集完成的 items 上检查固定节点：

```python
BACKEND = 'not ci_browser and not live_provider and not real_scanner'
BROWSER = 'ci_browser and not live_provider and not real_scanner'
LIVE = 'live_provider'

def layer(item):
    marks = {m.name for m in item.iter_markers()}
    if 'live_provider' in marks:
        return 'live'
    if 'real_scanner' in marks:
        return 'scanner'
    return 'browser' if 'ci_browser' in marks else 'backend'
```

用 `pytest.main(['--collect-only', '-q', ...], plugins=[collector])` 捕获节点，不递归收集本分类测试自身。断言下表每一节点/参数实例存在且归属正确；全集与四层并集相等，任意两层交集为空；不允许同节点同时 live/scanner。修改一个 marker 后测试必须失败。

| 文件 / 节点 | 分类 |
|---|---|
| `test_agent_readonly_resume_process.py::test_actual_local_browser_sidebar_acceptance`（全部参数实例） | ci_browser，仅该函数 |
| `test_agent_local_trial_browser.py::test_normal_policy_local_browser_lifecycle_revoke_and_current_source_withdrawal` | ci_browser |
| `test_d4_text_preview_browser.py::test_actual_employee_preview_masks_text_and_withdraws_changed_or_denied_sources` | ci_browser |
| `test_capa_outcome_review_browser.py::test_employee_chromium_terminal_protection` | ci_browser |
| 同文件 `test_live_employee_http_provider_chromium_outcome_review` | live_provider（可兼标 ci_browser） |
| 同文件 `test_employee_controlled_source_modules_fail_closed` | backend；保留 FMEA/PLANNING 两次真实 HTTP 整包拒绝 |
| `test_agent_task_attachment_browser.py::test_actual_clamav_attachment_browser_acceptance` | real_scanner（可兼标 ci_browser） |
| `test_agent_task_attachment_process.py` 实际使用 `actual_attachment_stack` 的六个测试 | real_scanner |
| 同文件 `test_actual_attachment_stack_requires_compose_opt_in` | backend；不得随模块整体标记 |
| readonly/local-trial 非浏览器进程、权限、消息、checkpoint、迁移测试 | backend |

- [x] **Step 2 — 运行 RED。** `python scripts/check-ci-pure.py tests/ci/test_layer_selection.py -q`；预期分类断言失败，不应因 DB 连接失败。
- [x] **Step 3 — 注册 marker 并逐函数加标。** pytest.ini 添加：

```ini
addopts = --strict-markers
markers =
    ci_browser: deterministic installed-browser protection
    live_provider: explicit real provider acceptance
    real_scanner: explicit real ClamAV acceptance
```

保留已有 asyncio/pythonpath/testpaths 配置。对实际浏览器调用与真实 provider/scanner fixture 做一次定向盘点，若发现清单之外节点，将确切 nodeid 纳入分类测试，不按目录隐藏。
- [x] **Step 4 — GREEN / 收集核账。** 重跑分类测试；用 `python scripts/check-ci-pure.py --collect-only` 加对应 `-m` 表达式和原 graph 排除，执行三个表达式及 scanner 的 collect-only，记录各层 nodeid 和数量，不称 collect 为实际通过。
- [ ] **Step 5 — 审阅提交点。** 只暂存 pytest.ini、被标记测试和新增分类测试；授权后提交 `test(ci): classify deterministic browser and live acceptance`。

**执行记录（2026-11-02）：** Task 1 实现与一次 fix 后独立复核通过；纯分类 3 passed，保留 3 项既有 warnings。提交点未执行，变更保持未提交；计数仅为 collection 结果。详细证据在本计划专属 SDD 记录。

## Task 2: 用版本管理支持替换私有资源依赖

**Files:** Create `backend/tests/ci/owned_resources.py`、`test_owned_resources.py`、`prepare_database.py`；Modify `backend/tests/e2e/capa_outcome_harness.py`、`capa_outcome_runner.py`。

**Interfaces:** `verify_owned_instance(source: Mapping[str, str]) -> VerifiedTestTarget` 返回不可变实例/目标库描述；`ensure_test_database(target: VerifiedTestTarget) -> None` 仅在该实例创建目标测试库；`verify_owned_database(target: VerifiedTestTarget) -> str` 在目标库存在后核对当前库/用户并返回规范化测试 URL；`artifact_directory(source: Mapping[str, str]) -> Path` 返回本次专用目录。CI 输入 `PG15_CONTAINER`、`TEST_DATABASE_URL`、`GITHUB_RUN_ID`、`GITHUB_RUN_ATTEMPT`、`GITHUB_JOB`；本地显式输入 `OPENQMS_TEST_RESOURCE_FILE` 与测试 URL，不接受旧目录隐式默认。

- [x] **Step 1 — 写 RED 负例矩阵。** 参数化测试缺登记、缺 container、错误完整 ID/owner/image、非 loopback、数据库非 `_test`、错端口、伪造 `GITHUB_ACTIONS=true`、URL 查询参数覆写 host、DB 当前库/用户不符；所有负例断言不调用迁移/建租户/删除动作。

```python
@pytest.mark.parametrize('url', [
    'postgresql+asyncpg://u:p@db.example.test:5432/qms_test',
    'postgresql+asyncpg://u:p@127.0.0.1:5432/qms',
    'postgresql+asyncpg://u:p@127.0.0.1:5432/qms_test?host=remote',
])
def test_rejects_unowned_target_before_database_io(url, monkeypatch):
    monkeypatch.setattr('tests.ci.owned_resources.inspect_container',
                        lambda *_: pytest.fail('must reject before inspect'))
    with pytest.raises(ValueError):
        verify_owned_instance({'TEST_DATABASE_URL': url})
```



另加参数化负例：合法 `TEST_DATABASE_URL` 配置同时带入指向其他实例/身份/库的 `PGHOST`、`PGPORT`、`PGUSER`、`PGPASSWORD`、`TEST_DB` 或 `PGADMIN_URL`。任一显式冲突必须在打开连接前拒绝，断言 inspect 后也无 SQL、无 CREATE、无迁移；特别覆盖 CI 随机端口 URL 与旧默认 5432 不一致。提供精确一致和仅 URL 两个正例，不能通过丢弃冲突输入掩盖错误。

- [x] **Step 2 — RED。** `python scripts/check-ci-pure.py tests/ci/test_owned_resources.py -q`；预期新接口缺失/验证断言失败。
- [x] **Step 3 — 最小实现。** `inspect_container(container: str) -> dict` 用参数列表运行 `docker inspect`，解析完整 ID、Config.Image、Config.Labels、实际 HostPort。CI 对照三个标签 `openqms.ci.run` / `openqms.ci.attempt` / `openqms.ci.job`，不只信环境变量；本地登记明确记录 container_id、owner_nonce、image、host、port、test_database、application_database，与实时结果逐项比较。先验证 URL（禁止改变端点的 query）及显式旧变量一致性，再核对 inspect；异常只输出稳定诊断，不输出 URL/密码。

使用 frozen dataclass `VerifiedTestTarget` 保存 `container_id, host, port, username, password, database, async_url, admin_url`（password/URL 字段 `repr=False`）。唯一配置来源为显式 `TEST_DATABASE_URL`，用 SQLAlchemy URL API 解析/派生 driver 与 `/postgres` 管理连接，正确保留编码密码；不得再从 PG 变量拼接另一条连接。显式旧变量只作一致性断言，不作为第二来源。Make 的历史默认值不能冒充显式输入：移除建库路径对默认 `PG*` / `PGADMIN_URL` 的读取，若保留兼容入口，仅传递用户 environment/command-line 显式设置的值，先验证一致再继续。

**目标库不存在的顺序：** (1) 纯解析与旧变量一致性校验；(2) docker inspect 验证归属、完整容器 ID、镜像和实际端口；(3) 从同一 target 派生 `/postgres` 管理连接，仅只读核验 `current_database() = 'postgres'`、`current_user = target.username`，以及 `pg_database` 中目标库是否存在；(4) 所有验证通过后才允许 `CREATE DATABASE`，使用正确引用的 SQL identifier，仅创建 target.database；(5) 用同 target 的 async_url 连接新/已有库，核对当前库/用户；(6) 将该规范化 URL 同时用于公共迁移、租户 fixture 及 pytest。数据库不存在不是放宽实例归属验证的理由，不回落其他实例或开发库。

新增调用顺序测试：缺库正例精确记录 `inspect → admin identity → existence → create → target identity → migration`；错 owner/端口/旧 PG 变量/管理用户均零写入；已存在库不得 CREATE。`ensure_test_database` 不重新读环境，迁移调用同样接收 target 派生 URL，不重新拼 PG 连接。

本地 registration 的 `owner_nonce` 对应 `openqms.owner`，要求显式登记且文件只读访问；CI 不要求历史私有文件。允许 loopback `127.0.0.1` / `::1` / `localhost`，端口匹配真实映射；拒绝业务库和共享 seed 库。

`artifact_directory` 优先 `OPENQMS_TEST_ARTIFACTS`，否则 `RUNNER_TEMP` 下唯一子目录，本地用 `tempfile.mkdtemp`；新建登记文件权限 0600，无凭据。把 harness/浏览器收尾中的 WORK journal 路径改为该目录。保留已有真实平台迁移、TenantSession、员工登录、事务门禁及精确租户清理，不停 CI service。
- [x] **Step 4 — GREEN。** 纯测试正例使用可控 inspect/SQL 响应；另在新授权隔离 PG 上实际核验 ID/映射/DB 身份，跑双来源 HTTP 拒绝节点。核验前后其他容器不变，临时租户清零。
- [ ] **Step 5 — 审阅提交点。** `test(ci): validate owned test resources without private registry`；不纳入本地登记或日志。

**执行记录（2026-11-02）：** Task 2 经一次 URL 查询参数拒绝修正后独立复核通过；所有权纯测试 28 passed，另有修正前组合纯测试 31 passed、专属 PG15 真实迁移及无 provider 双来源 HTTP 1 passed。无提交；两项覆盖/措辞 Minor 已记入最终复核台账。

## Task 3: 可移植 Chromium 与 Node 白名单

**Files:** Create `backend/tests/ci/browser_runtime.py`、`test_browser_runtime.py`；Modify `frontend/playwright.agent.config.ts`、Task 1 的所有浏览器控制器和 `capa_outcome_runner.py`。

**Interfaces:** `resolve_browser(frontend: Path, source: Mapping[str, str]) -> Path`；`browser_environment(source: Mapping[str, str], runtime: Mapping[str, str]) -> dict[str, str]`。未知 runtime key 拒绝；Node 不获得 DB/provider 密钥。

- [x] **Step 1 — RED 测试。** 显式 executable 优先、显式失效不 fallback、无 Playwright/无 Chromium 明确失败、默认通过项目 Playwright 解析、不自动安装；传入 DB/provider/代理/`NODE_OPTIONS`/任意新变量均不进入 Node。

```python
def test_browser_environment_is_allowlist():
    env = browser_environment(
        {'PATH': '/safe', 'LLM_API_KEY': 'fake-secret', 'DATABASE_URL': 'fake-db',
         'NODE_OPTIONS': '--require unsafe', 'UNEXPECTED_SECRET': 'fake-secret'},
        {'AGENT_BROWSER_URL': 'http://127.0.0.1:40123'})
    assert env == {'PATH': '/safe', 'NO_PROXY': '*', 'no_proxy': '*',
                   'AGENT_BROWSER_URL': 'http://127.0.0.1:40123'}
```

- [x] **Step 2 — RED。** `python scripts/check-ci-pure.py tests/ci/test_browser_runtime.py -q`。
- [x] **Step 3 — 实现解析与迁移调用方。** 从 frontend cwd 使用清理后的 system env 执行：

```javascript
const { chromium } = require('@playwright/test');
process.stdout.write(chromium.executablePath());
```

路径必须为实际文件，运行前可执行性检查；显式路径也相同验证。Playwright 配置改为：

```typescript
launchOptions: process.env.OPENQMS_AGENT_BROWSER_EXECUTABLE
  ? { executablePath: process.env.OPENQMS_AGENT_BROWSER_EXECUTABLE }
  : {},
```

system 白名单保持 `PATH, HOME, TMPDIR, LANG, LC_ALL`；runtime 白名单逐项来自现有调用方的 BACKEND_URL、AGENT_BROWSER_URL、AGENT_BACKEND_URL、nonce、一次性员工 login、tenant/report/task/run/checkpoint/scenario IDs、artifact 路径及 browser executable。不得直接接受任意 `AGENT_*` 前缀。保留所有现有 runtime 参数名称，补测试覆盖每个控制器的实际参数集合；员工凭据只限 fixture 创建账号，禁用真实用户凭据。

替换 CAPA 硬编码 CHROMIUM 与 readonly/local-trial/D4/attachment 控制器的缓存路径及黑名单 env；保留超时、一次性 Blob 下载、来源失效、终态以及进程 finally 清理。
- [x] **Step 4 — GREEN。** 支持层测试、runner 环境回归；现有依赖已安装时跑 browser 层。未安装本机依赖只记 BLOCKED，不偷偷安装。CI 中由 Task 6 显式安装。
- [ ] **Step 5 — 审阅提交点。** `test(ci): resolve project chromium and isolate browser environments`。

**执行记录（2026-11-02）：** Task 3 独立复核 spec PASS / quality APPROVE；纯支持层与 runner 18 passed，实际浏览器层 11 passed / 3514 deselected / 5 既有 warnings，tsc exit0。首次调用误配库名与迁移中的 frontend 初始化顺序错误均已纠正并保留失败记录；历史 local-trial 库名前缀已替换为更强的真实资源核验。提交点未执行。

## Task 4: live 配置、独立进程与可信结果收据

**Files:** Create `backend/tests/ci/acceptance_config.py`、`test_acceptance_config.py`、`gate_results.py`、`test_gate_results.py`；Modify CAPA runner、runner tests、live 测试入口。

**Interfaces:** `validate_live_configuration(values: Mapping[str, str]) -> dict[str, str]`（无效抛 ValueError）；`redact(text: str, secrets: Sequence[str]) -> str`；`summarize_junit(path: Path) -> dict[str, int]`；`require_gate_success(summary: Mapping[str, int], exit_code: int) -> None`。收据字段 `layer, command, selected, passed, failed, errors, skipped, xfailed, xpassed, deselected, warnings, exit_code, status`，未执行计数为 null 而非 0。

- [x] **Step 1 — 写 RED 配置及结果测试。** 缺 provider/model/API key（需要时）/本地 provider 端点、timeout `0/121/noninteger`、变量插值或换行拒绝；有效 1/120 接受。伪造 JUnit 覆盖零测试、skip、xfail/xpass、错误退出、空文件/损坏文件。使用实际 pytest 生成的小型样本确认 xfail/xpass 的解析，不能将 xfail 归为普通 skip 后重复计数。

```python
@pytest.mark.parametrize('summary,code', [
    ({'selected': 0, 'passed': 0, 'skipped': 0}, 0),
    ({'selected': 1, 'passed': 0, 'skipped': 1}, 0),
    ({'selected': 1, 'passed': 1, 'skipped': 0}, 1),
])
def test_requested_gate_cannot_succeed_without_completion(summary, code):
    with pytest.raises(ValueError):
        require_gate_success(summary, code)
```

- [x] **Step 2 — RED。** `python scripts/check-ci-pure.py tests/ci/test_acceptance_config.py tests/ci/test_gate_results.py -q`。
- [x] **Step 3 — 实现与 runner 改造。** 删除私有 `run-owned.py` 动态导入、固定 WORK、隐式 `.env.e2e` 读取和 `E2E_MODE='false'`。沿用 `api|browser|live|acceptance` CLI 目的；`acceptance` 顺序启动 api/browser/live 三个独立 pytest 子进程，只有 live 进程配置 provider。本地 profile 仅在显式参数 `--test-profile PATH` 下读取，延用不插值的 provider_environment；CI 从显式 env 映射调用 validator，绝不自动找文件。

普通子进程显式清空 LLM/OPENAI/ANTHROPIC/EMBEDDING 凭据及相关 provider endpoint/config，并移除 E2E_MODE；预检确认 Settings 结果仍默认无 provider，不能依赖 shell 变量缺失而被 `.env` 补入。live 配置在加载业务 Settings 前构造到新进程，不整段 pytest monkeypatch 全局 Settings。浏览器安装、DB 所有权和 provider/model/timeout 验证通过后才可发真实请求；外部失败、fallback 或无实际 provider 执行证据均不能签成功。

每层用 `--junitxml` 和 `-rA` 记录结果；对普通层允许已记录环境依赖 skip，但 browser 与显式真实 gate 不允许 skip/xfail/xpass。普通已有 xfail/xpass 如存在如实记录，不新增。计数从 pytest 结构化 hook/JUnit 组合取得，deselected/warnings 用 hook 记录，不能靠宽泛正则猜测。退出码与完整结果同时判定。

日志按实际 API key、敏感端点、DB URL/密码及认证 header 脱敏，长串优先；provider/model/timeout 不作为替换词。流式输出入文件前过滤，截图仅从受控场景输出，trace 保持 off；不上传原始 env/profile、资源凭据或未过滤 stdout。新增 fake-secret 回归覆盖异常/traceback、URL 编码密码和 Authorization header。finally 仅清理本次 PID/租户，收据不含秘密。
- [x] **Step 4 — GREEN。** 新纯测试与 `test_capa_outcome_runner.py`；使用假 provider 配置证明普通/browser 子进程拿不到配置、live 子进程能拿到允许键，不调用模型。真实执行留在授权 gate。
- [ ] **Step 5 — 审阅提交点。** `test(ci): isolate live configuration and enforce gate evidence`。

**执行记录（2026-11-02）：** Task 4 经一次 hook 传递与 DSN 脱敏修正后复核通过；38 项纯测试含真实受保护子进程收据 smoke 通过，3 项既有 warnings。未运行真实 provider；内部 pytest_entrypoint 测试 seam Minor 留最终复核。未提交。

## Task 5: Makefile 分层入口及真实 scanner 完成约束

**Files:** Modify `Makefile`、`backend/tests/e2e/test_agent_task_attachment_process.py`、`test_agent_task_attachment_browser.py`；Extend `test_layer_selection.py` / `test_gate_results.py`。仅确有需要才修改 Compose；当前 `docker/postgres/Dockerfile` 已是多架构 pg15，不为计划猜测而改镜像。

**Interfaces:** `make check` = deterministic backend + frontend；`make check-browser` = 自动 browser；`make check-live` = 独立 live；`make agent-attachment-e2e` = 原真实过程/浏览器链。

- [x] **Step 1 — RED。** 用 `make -n` 验证三个选择表达式、两个 graph ignores、live 无普通混跑；scanner 显式执行但 opt-in 缺失不能 skip 通过。保留普通层 `test_actual_attachment_stack_requires_compose_opt_in` 对未请求配置行为的覆盖。
- [x] **Step 2 — 添加 Make 选择常量与目标。**

```make
PYTEST_BACKEND_MARKS := not ci_browser and not live_provider and not real_scanner
PYTEST_BROWSER_MARKS := ci_browser and not live_provider and not real_scanner
PYTEST_LIVE_MARKS := live_provider
```

backend 命令增加 `-m '$(PYTEST_BACKEND_MARKS)'`；browser/live 与 runner 共用配置、资源及收据接口，分别选择另外两个表达式。新增 `.PHONY` / help，修正“make check 绿色等价全部 CI 绿色”的旧注释。保留 `check-test-db` 的“隔离测试库创建＋公共迁移”职责，但**替换现有双来源实现**，不能保留从 PGHOST/PGPORT/PGUSER/TEST_DB 拼接建库连接的内联脚本。新增测试专用 `backend/tests/ci/prepare_database.py`，一次执行 `verify_owned_instance(source) → ensure_test_database(target) → verify_owned_database(target) → alembic upgrade head`，迁移子进程 `DATABASE_URL` 固定为 target.async_url；不重新读取其他连接目标。Make 只把显式测试 URL、所有权输入及用户显式 legacy 配置交给该入口，不将历史默认 PG 值传作独立建库配置。公共迁移与后续 pytest 使用同一规范化目标，tenant 迁移仍走真实平台流程。CI 中公共迁移步骤也调用此入口，禁止在核验前直接运行 alembic。
- [x] **Step 3 — scanner 增强。** 继续固定 Compose profile、随机 project/nonce 与真实 daemon。真实 scanner fixture 被显式选择时缺依赖 fail，非显式配置单测仍能验证原 opt-in 行为。scanner 两个阶段都生成收据并 require_gate_success，不能仅因 Compose exit 0 或 stdout 含 passed 签成功。

不固定宣称“7 个真实扫描测试”：当前过程模块包含 1 个 opt-in 单测及 6 个实际扫描测试，按当前实际选中结果分别核账。记录 daemon/definitions、VERSIONCOMMANDS、EICAR FOUND、加密/展开限制、clean 下载。清理 trap 保留原失败退出码；cleanup 失败使 gate 非成功。down 后按 project 标签核查容器/卷/网络全部消失，不影响其他 project；取消/信号时尽力清理并记非完成，不称通过。
- [x] **Step 4 — GREEN。** `make -n check-backend check-browser check-live agent-attachment-e2e`；跑纯测试、受影响普通后端。获授权后实际 scanner，核查固定镜像/真实输出和清理；无资源记 BLOCKED。
- [ ] **Step 5 — 审阅提交点。** `build(ci): expose deterministic and explicit acceptance targets`。

**执行记录（2026-11-02）：** Task 5 经现有 backend workflow 统一入口补充后复核 PASS；纯测试 66 passed / 3 既有 warnings，make dry-run 通过；实际固定 ClamAV 过程 6/6＋浏览器 1/1，专属容器/卷/网络清理通过。曾发生 copied-image cwd、空 timeout 与相对 Compose 清理路径失败，均保留记录后修正；核心登记库经协调方只读复核可达，完整 Make 回归留 Task 7。未提交。

## Task 6: 自动无密钥 CI 与 main-only 手动 workflow

**Files:** Modify `.github/workflows/test.yml`；Create `.github/workflows/acceptance.yml`、`backend/tests/ci/test_workflow_contract.py`。

**Interfaces:** 自动 job `backend-tests/frontend-checks/browser-protection/docs-check`；手动 `preflight/live-capa/scanner/summary`。`gate` 是固定 choice，其他输入不接受。

- [x] **Step 1 — RED 静态契约。** 用 `python scripts/check-ci-pure.py tests/ci/test_workflow_contract.py -q` 执行。测试所有分支 push（不含 tag）、main PR、最小权限、无 persistent checkout 凭据、无 secrets 引用的自动 jobs、browser 安装步骤、main-only preflight、固定 Environment、固定输入、手动无 cancel-in-progress。用支持 YAML 1.2 的解析器或 actionlint；不让 YAML 1.1 将 `on` 误当布尔值后测试空对象仍通过。
- [x] **Step 2 — 自动 workflow。** 事件/安全骨架：

```yaml
on:
  push:
    branches: ['**']
  pull_request:
    branches: [main]
permissions:
  contents: read
concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

每个 checkout `persist-credentials: false`。保留 backend 的 schema/SPC/import/preflight 步骤，所有需 DB 的步骤须在 Task 5 统一目标的 prepare_database 通过后运行，pytest 走统一 backend 选择。backend/browser 分开 PostgreSQL service，随机 host 映射 `5432/tcp`；URL 使用 `job.services.postgres.ports[5432]`，container 用 `job.services.postgres.id`；service options 添加 Task 2 三个 run/attempt/job 标签和既有健康检查。

显式空 provider/embedding 配置，E2E_MODE 不设置；不 source 本地文件。前端 `npm ci`，沿用锁定版本；先验证 lockfile，失败记录原因后处理，不换为 npm install 绕过。browser job 安装 Python 后端依赖、Node 20、`npm ci`、`npx --no-install playwright install --with-deps chromium`，然后 `make check-browser`。Node 子进程环境仍走白名单。

docs-check 保留 PR 文档例外机制，并识别 `.github/workflows/`、`Makefile`、`backend/tests/`、`frontend/e2e/`、Playwright config 的测试基础设施改动；文档认可 `docs/**`、`AGENTS.md`、根/模块 README，不恢复 CLAUDE.md。失败产物只上传过滤后的文件，使用 `if: failure()`，缺少证据文件不得伪造空产物。
- [x] **Step 3 — 手动 workflow。** 无秘密 preflight 强制如下检查，拒绝时明确 exit 1：

```bash
set -euo pipefail
[ "$GITHUB_EVENT_NAME" = workflow_dispatch ]
[ "$GITHUB_REF" = refs/heads/main ]
case "$GATE" in live-capa|scanner|all) ;; *) exit 1 ;; esac
```

preflight 固定 checkout main 并记录 SHA，下游 checkout 该 SHA，避免审核等待期间 main 漂移。live/scanner 按 choice 分别运行，只依赖 preflight，不互相依赖。live 固定 `environment: ci-acceptance`；配置只在需要的 live 执行步骤提供 `vars.LLM_PROVIDER`、`vars.LLM_MODEL`、`vars.LLM_TIMEOUT` 与 `secrets.LLM_API_KEY`、`secrets.LLM_BASE_URL`，不向 npm 安装/普通 pytest/上传步骤提供。live 单独 PG、项目 Chromium 与 `make check-live`；scanner 无模型 Secrets，安装浏览器及运行 `make agent-attachment-e2e`。

手动不配置自动取消在途收费验收。summary `if: always()` 且结合 preflight/job result/结构化收据，要求被请求 gate 确实成功；未请求标 NOT_REQUESTED，cancelled/blocked/无收据均非通过。不要用 `continue-on-error`。
- [x] **Step 4 — GREEN。** 跑静态契约及 actionlint（若工具不可用记录限制，不声称通过）；核查自动 workflow 无 secret 表达式、无绝对路径、两 workflow 输入/表达式合法。真实远端 run 仍待 Task 7/8，不能替代。
- [ ] **Step 5 — 审阅提交点。** `ci: add secretless branch checks and protected manual gates`。

**执行记录（2026-11-02）：** Task 6 源码与独立语义复核 PASS，契约 15 passed / 3 既有 warnings；actionlint 不在 PATH，协调方安装固定外部来源被权限控制拒绝，未重试或绕过，静态 lint 保留 BLOCKED 待明确来源授权。未运行 GitHub 自动/手动事件，未配置 Environment/Secrets；未提交。

**静态检查补充（23:35 CST）：** 用户明确授权安装指定 actionlint v1.7.7；实际检查发现 8 处端口索引类型问题，已改为字符串键并通过 scoped re-review。15 项契约测试重新通过，协调方亲自运行最终 actionlint exit0/无输出；此前静态 lint 阻塞已解除。

## Task 7: 干净 checkout 验证与文档交接

**Files:** Modify `docs/e2e.md`、`docs/development.md`、`PROGRESS.md`；必要时仅更新 `docs/architecture.md` 的相关 CI 当前事实，不改业务故事/verify skill 日期。

**Interfaces:** 验证矩阵分别报告 LOCAL / STATIC / GITHUB_AUTO / GITHUB_MANUAL；状态 PASS / FAIL / BLOCKED / NOT_REQUESTED，不合并成一个“全部通过”。

- [x] **Step 1 — 纯测试。** 使用第 0 节入口，整个导入/收集/运行过程均有不可连接 URL 与网络 guard；任何意外连接都是失败，不能改为 skip。

```bash
python scripts/check-ci-pure.py tests/ci/ tests/e2e/test_capa_outcome_runner.py -q -rA
make check-frontend-tsc
make check-frontend-build
```

- [x] **Step 2 — 干净环境实际执行。** 从已授权提交的冻结 SHA 创建新的隔离 checkout（使用 using-git-worktrees）；不复制 `.superpowers`、`.env*`、node_modules 或私有登记。只带入测试专用依赖与新授权测试资源，使用当前 lockfile 安装，不自动给本机装 Chromium。

依次执行 `make check`、`make check-browser`，后端真实 PG / 公共及租户迁移、no-LLM 默认关闭、权限/消息/checkpoint、双模块 HTTP 拒绝都必须保留。扫描 tracked 测试/配置中的 `/Users/`、旧 `owned-resources.json`、`run-owned.py`、固定日期 WORK 引用；允许文档历史说明，但执行路径必须为零。登记文件只允许显式新入口，不隐式读私有资源。
- [x] **Step 3 — 失败路径和泄密验证。** 运行错 owner/端口/DB/browser/live 配置的测试，证明拒绝发生在实际副作用前。使用虚构 sentinel 检查 Node env 与准备上传的全部产物，确保无 key/URL/密码/header 泄漏。保留真实 warnings 和失败原因，不能仅记录最终 exit 0。
- [x] **Step 4 — 文档。** 写出四个 make 入口、每层边界、依赖安装步骤、登记格式/所有权标签、显式本地 profile 参数、安全产物、清理范围。管理员配置指南只列 Environment 需要的审批人/允许 main/测试配置，不代执行。强调 fork PR 无密钥、workflow_dispatch 文件需先在 main、真实验收未跑不算通过。
- [ ] **Step 5 — 远端自动检查。** 只有获 push 授权才推功能分支，记录实际 GitHub run URL/SHA/job 结果、计数/exit；未授权或未触发记 BLOCKED。远端自动三层通过是阶段 A 验收目标；手动 gate 在 main/Environment 就绪前保留 BLOCKED，不用旧本地收据替代。
- [x] **Step 6 — 阶段 A 交接。** 更新 PROGRESS 最新条目链接计划、已完成 Task、真实结果和下一步集成限制，不覆盖用户已有基线条目。不把旧 3450 或 MES33 算入本次全量。授权后提交 `docs(ci): document layered verification and evidence boundaries`。

**执行记录（2026-11-03）：** 本地实现/验证/交接完成，整体与修正复核Important全部关闭。最终同源完整3622 passed/4 skipped/19 deselected/5 warnings，tsc/build通过；浏览器11、纯184、API定向85、真实ClamAV6＋1及真实证据保留/清理通过。临时核心PG与named volume仅核验owner/fullID/零client后处置。Source export不是已提交checkout；Step5远端自动检查因未授权提交/推送保留BLOCKED，手动/provider为NOT_REQUESTED，不能当作已验收。证据保留于本计划SDD目录；用户现有改动与.env示例删除均保留，所有提交点未执行。

## Task 8: 独立集成 main、回归与 PR 检查点

**Files:** 集成时以实际冲突为准；已知 8 个文件如下。此任务在 A 的自动检查通过后启动，使用 using-git-worktrees；不在有用户未提交改动的现工作树直接 merge。

**Interfaces:** 输入冻结的功能分支 SHA 与重新 fetch 后 main SHA；输出集成分支、冲突决策表、合并后各层证据及 PR 交接。fetch/push/PR/正式 merge 依当阶段用户授权；本计划不自动授权外发。

- [ ] **Step 1 — 刷新并冻结两侧。** 获授权后 fetch，记录两个 SHA，使用 `git merge-tree --write-tree <main-sha> <feature-sha>` 刷新预检，不把历史“8 个”当永久事实。用原生工作树工具或 git worktree 创建从功能 SHA 开始的集成分支，再 merge 精确 main SHA；不要从落后本地 main 开始，也不整体 cherry-pick 覆盖谱系。
- [ ] **Step 2 — 先写冲突保护回归再解冲突。** 对下表建立/补齐真实失败断言；以服务/API 实际结果核验，不只比较文本或 dataclass 字段。

| 文件 | 合并时必须同时保留 |
|---|---|
| `backend/app/services/agent/permissions/access.py` | main：无界工厂 GROUP ADMIN、产品线明确行级豁免、申请人审批限制；feature：受控 profile、当前租户/权限/来源重查 |
| `backend/app/services/agent/permissions/catalog.py` | 声明归属、五元白名单/默认 DENY 与 runtime 控制能力；不将 local_metadata 试用扩大为写入 |
| `backend/app/services/agent/permissions/types.py` | 两侧类型字段及其安全语义，调用方同步，不能给缺失授权字段默认放行 |
| `backend/app/services/capa_agent_projection.py` | main 的只读 CAPA 数据边界与 feature 的租户快照/来源复核，跨模块当前撤权整包拒绝 |
| `backend/app/models/__init__.py` | 两侧模型注册齐全，无丢表/重复登记；迁移导入真实可执行 |
| `backend/tests/migrations/test_supplier_risk_capa_inputs_migration.py` | 两侧迁移覆盖、独立测试库及隔离清理，不删断言解决冲突 |
| `PROGRESS.md` | 两侧历史与最新已验证事实；旧结果不冒充集成后结果 |
| `docs/architecture.md` | 已实现事实与目标设计区分，CI/权限入口无相互覆盖 |

负例至少包括：非 GROUP ADMIN 无界工厂拒绝、无豁免无界产品线拒绝、申请人不能审批自己、跨租户/来源撤权拒绝、默认 DENY/runtime 关闭。正例仅测试明确授权受控 profile，不能为通过回归放宽接口。
- [ ] **Step 3 — 合并后验证。** 在集成专属测试资源跑权限目录及 CAPA 投影相关测试、全部迁移测试，再 `make check` / `make check-browser`；实际命令/选中数写交接，不从任一侧历史结果继承绿灯。验证 tenant/public heads、模型导入、前端类型/构建、消息/checkpoint/附件默认关闭。资源只清本次创建的租户/进程/project。
- [ ] **Step 4 — PR 检查点。** 经审阅、获 push/PR 授权且集成自动检查通过后，创建或更新匹配本分支的 PR，不重复创建。PR 列出冲突决策、验证命令/计数、手动门禁未运行状态及 Environment 前置条件。若已有 Draft PR 则核实其 head/base 后更新，不根据历史记忆臆测 PR 状态。
- [ ] **Step 5 — main 手动门禁与最终合并边界。** 正式合并需要另行授权。由于设计限定 acceptance 仅 main，feature PR 无法预先获得其远端成功；先让 workflow 经审阅正式进入 main，再由管理员完成 Environment 并显式触发 live-capa/scanner/all。这是发布验收的后置阻塞，不把自动 CI 当真实验收替代。

若用户要求“真实远端 gate 必须先通过才能合并任何代码”，与 main-only 约束构成循环，必须先澄清/调整发布分步顺序，不能偷偷允许任意 ref 或移除保护。生产部署始终另行安排。

## 自检与完成判据

- [ ] 设计 §3–4 → Task 1/5/6：逐项分类、无密钥三层、docs 同步；不粗放排除 e2e。
- [ ] 设计 §5 → Task 4/6/8：固定输入、main-only、Environment、预检、独立 live、scanner 及 NOT_REQUESTED。
- [ ] 设计 §6 → Task 2/7：真实容器/标签/映射/DB 用户验证，真实 tenant provisioning，无私有登记依赖。
- [ ] 设计 §7 → Task 3：可移植浏览器、Node 白名单、无自动本机安装。
- [ ] 设计 §8 → Task 4/5/6：计数/警告/退出码、脱敏、最小清理、取消不算通过。
- [ ] 设计 §9–10 → Task 7/8：源码/静态/本地/远端证据分离；不读取 Secrets、不恢复示例、不越权提交部署。

**交付判定：**计划完成不等于 CI 已实施；A 完成不等于 main 已集成；自动三层通过不等于真实验收通过；main 手动 gate 未实际运行前不能签全层完成。

## 2026-11-02 计划复核修订

- P1：Task 2/5/6 明确单一已核验目标、legacy PG 冲突拒绝、目标库缺失的先验实例核验、建库/迁移/pytest 同源及零写入负例。
- P2：第 0 节新增导入前配置与网络 guard 的纯测试入口；基线、Task 1–4/6/7 的纯测试与 collection 统一通过该入口，不设置种子库绕过开关。
- 本次只修订文档；入口脚本和支持模块均为待实施内容，未运行测试，不将静态检查记为 RED/GREEN 实证。

## 最终状态（2026-11-03）

Task1–7本地实施、同源完整回归与交接已完成；各任务提交点、Task7远端自动证据与Task8尚未授权执行，不勾选为通过。后续授权后按CI文件清单提交/推送，拿到真实GitHub自动结果后再做隔离main集成。真实provider/手动workflow仍须main与Environment就绪后显式执行；部署另行安排。

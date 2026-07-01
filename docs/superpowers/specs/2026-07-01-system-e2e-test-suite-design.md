# 系统级端到端测试套件设计

**日期**: 2026-07-01
**分支**: `fix/dashboard-admin-pages` → 经 worktree `e2e-spec`
**状态**: 设计已与用户逐节确认，待 spec review

## 1. 目标与范围

为 OpenQMS 建立**浏览器全栈端到端测试套件**：Playwright 驱动真实浏览器 → 前端(:5173) → 后端(:8000) → 真实 Postgres，覆盖登录/RBAC/工厂隔离、FMEA、CAPA 8D、看板下钻等用户旅程，最终覆盖全部模块。

**不做**：API 级 E2E 扩展（已有 `test_supply_chain_risk_e2e.py` 等后端 pytest 覆盖）、单元/组件测试（vitest/pytest 已有）。本套件只补"整条真实用户旅程"这一层。

**运行方式**：纯手动 `make e2e`，**不接入 CI**。理由：E2E 慢且依赖真实 LLM 凭证，作为本地/手动回归手段，而非 PR 必过门。

**分阶段交付**：本 spec 一次性规划 M0-M5；实现按 M0→M5 顺序 PR 增量落地，首版交付到 **M1**（基础设施 + 核心回归网），M2-M5 各自后续 PR。

| 阶段 | 内容 |
|---|---|
| **M0 基础设施** | docker-compose e2e override、seed_e2e、Playwright 配置、fixtures/helpers、`make e2e*` 目标、文档 |
| **M1 核心回归网** | ①登录+RBAC+工厂隔离 ②FMEA 生命周期 ③CAPA 8D 生命周期 ④看板下钻 |
| **M2 质量核心** | ⑤控制计划 ⑥SPC ⑦MSA ⑧特殊特性 |
| **M3 供应商/客户** | ⑨供应商+评级 ⑩IQC ⑪供货看板+风险预警 ⑫SCAR ⑬客诉/RMA ⑭APQP/PPAP |
| **M4 AI/图谱/集成** | ⑮知识图谱+RAG ⑯智能推荐 ⑰协同编辑 ⑱MES/PLM/ERP 连接器 ⑲管理后台+日志 |
| **M5 Agent 基座** | HITL 审批 / 三态 commit / Guardrails / 工具白名单 |

## 2. 现状

- **后端**：104 个 pytest 文件，多对真实 Postgres 的 unit/service 测试；`test_supply_chain_risk_e2e.py` 是 API 级 E2E（httpx + ASGITransport + 真实 DB）。
- **前端**：~30 个 vitest unit/component 测试。`@playwright/test` ^1.60.0 **已安装**，`frontend/playwright.config.ts` 已存在（baseURL `:5173`、chromium、`workers:1` on CI），`frontend/e2e/` 有 2 个 spec（`capa-draft.spec.ts`、`i18n.spec.ts`）——但假设栈已手动起、硬编码 URL、未进任何 npm script/CI、无确定性种子。
- **Docker**：`docker-compose.yml` 跑 db/redis/backend（无 frontend 服务）；`frontend/Dockerfile` 跑 `vite dev` 于 :5173。
- **CI**：`test.yml` 有 backend-tests / frontend-checks / docs-check 三 job，无 E2E job。本次**不改 CI**。
- **`make check`**：backend pytest + frontend tsc + build，无 E2E。
- **种子账号**：admin / engineer / manager / viewer（密码见 CLAUDE.md）。

## 3. 整体架构

```
                       ┌─────────────────────────────────────────┐
                       │          make e2e   (手动，无 CI)          │
                       │  up 简档 → migrate → seed_e2e → 跑 → (不自动 down) │
                       └────────────────────┬─────────────────────┘
                                            │
                ┌───────────────────────────▼───────────────────────────┐
                │   docker-compose.e2e.yml (override, profile=e2e)      │
                │   db(pgvector,:5433) redis backend(:8000) frontend(:5174) │
                │   专用库 qms_e2e（独立卷 pgdata_e2e），TENANT_MODE=single │
                │   backend 读 .env.e2e 的 LLM 凭证 + DATABASE_URL        │
                └───────────────────────────┬───────────────────────────┘
                                            │ http://localhost:5173, /api → :8000
                ┌───────────────────────────▼───────────────────────────┐
                │   Playwright (chromium)  testDir: frontend/e2e         │
                │   baseURL http://localhost:5173                        │
                │   workers:1, fullyParallel:false, retries:CI=2        │
                │                                                         │
                │   fixtures: auth(role)→storageState  seed-state        │
                │   input 文档库(喂 UI) / 后端 payload(API 造前置)        │
                │   cleanup-registry: track(id) → afterEach LIFO drain   │
                │   specs: m1-core/ m2-quality/ .../ m5-agent/            │
                └─────────────────────────────────────────────────────────┘
```

要点：
- **新增** `docker-compose.e2e.yml`（override：e2e profile，backend 指向 e2e 库，加 frontend 服务，backend 注入 LLM 凭证 env）。现有 `docker-compose.yml` 不动。
  - **独立卷与端口**：e2e db 用独立 volume `pgdata_e2e`（不复用开发的 `pgdata`，否则既有卷使 `POSTGRES_DB: qms_e2e` 初始化脚本失效、库不会被创建），主机端口绑 `5433`（避开开发库 5432 冲突）；`.env.e2e` 的 `DATABASE_URL` 指向 `:5433/qms_e2e`。frontend 绑 `5174`（避开 `:5173`），Playwright `baseURL` 同步改 `:5174`。
  - **强制单租户**：e2e 简档 `TENANT_MODE=single`，避免 SaaS schema-per-tenant 的子域名伪造（`tenant1.localhost`）配置复杂度；工厂行级隔离在单租户下用 `factory_id` 验证。多租户子域名场景留作 M4 单独 spec，不在默认套件。
- **新增** `backend/app/seed_e2e.py`（确定性、幂等，独立于 demo `app.seed`）。
- **新增** `backend/app/api/e2e.py` 只读 `/api/e2e/seed-state` 端点（仅 e2e 简档暴露），避免前后端常量双源漂移。**生产门控**：路由注册处双重校验 `E2E_MODE=="1" and settings.TENANT_MODE != "production"`，否则整组路由不载入——即便生产环境误注入 `E2E_MODE=1` 也绝不暴露种子元数据。
- **新增** `frontend/e2e/` 下 fixtures/helpers/specs 分阶段目录；现有 2 spec 迁入 `m1-core/` 并改用新 fixtures。
- **新增** `make e2e` / `e2e-up` / `e2e-seed` / `e2e-down` / `e2e-reset` 目标（不并入 `make check`）。
- **不改** `test.yml`（不接入 CI）。

## 4. 组件与文件布局

```
docker-compose.e2e.yml                # e2e profile override：db 卷 pgdata_e2e + :5433，frontend :5174
.env.e2e.example                       # 模板（入库）：DATABASE_URL(:5433/qms_e2e)、TENANT_MODE=single、E2E_LLM_*；.env.e2e gitignore
backend/app/seed_e2e.py                # 确定性种子（已有记录，幂等可重跑）
backend/app/seed_e2e_constants.py     # 单号/工厂码等常量（seed 与端点共用）
backend/app/e2e_input_fixtures/        # 后端输入文档库（API 造前置数据用）
  pfmea_graph_sample.py                #   示例 PFMEA 7 步图谱 JSON
  dfmea_graph_sample.py
  capa_create_payload.py
  spc_measurements.py
  iqc_inspection_lot.py
  supplier_payload.py
  ...（每个写流程一份示例文档）
backend/app/api/e2e.py                 # 只读 /api/e2e/seed-state 端点（生产门控：E2E_MODE=1 且非 production 才载入路由）

Makefile                               # 新增 e2e* 目标

frontend/playwright.config.ts          # 改：workers:1, fullyParallel:false, globalSetup, storageState 目录
frontend/e2e/
  global.setup.ts                      # 凭证检测+报警、seed-state 校验、4+1 角色 UI 登录存 storageState
  global.teardown.ts                   # 仅报告（库由 make e2e-down 清）
  fixtures/
    auth.ts                            # loginAs(role) → storageState 复用（admin/engineer/manager/viewer/group_admin）
    seed-state.ts                      # 拉取并缓存 /api/e2e/seed-state
    input/                             # 前端输入文档库（喂 UI 表单）
      pfmea-wizard-inputs.ts
      capa-form-inputs.ts
      spc-data-entry.ts
      iqc-inspection-form.ts
      supplier-form.ts
      ...
  helpers/
    e2e-utils.ts                        # 导航、表格行按文档号定位、Antd Select/Modal 交互
    api-client.ts                       # axios 直打 :8000（带 token），写流程造前置/清理
    cleanup-registry.ts                 # ★ track(kind,id) 压栈；drain() LIFO DELETE
  specs/
    m1-core/  m2-quality/  m3-supplier-customer/  m4-ai-integration/  m5-agent/
    _guards/
      seed.guard.spec.ts               # 断言 seed-state 已知记录齐全，缺失即早停
      ai-credentials.guard.spec.ts     # 凭证齐全→烟测 complete_json；缺失→skip+warn
  README.md                             # 如何跑、如何加 spec、输入文档库约定
docs/e2e.md                             # 套件总览（满足 docs-check）
CLAUDE.md                               # 命令节追加 make e2e
```

### 4.1 两类被测数据

- **种子态**（已有记录，供读流程断言）：`seed_e2e.py` 灌入固定工厂/产品线/用户/已知单号记录（如 `PFMEA-E2E-001`、`8D-E2E-001`），经 `/api/e2e/seed-state` 暴露其单号与 id。
- **输入态**（代表性创建数据，供写流程在 UI/API 输入）：前后端**各一份**输入文档库——前端 `fixtures/input/*.ts` 喂 UI 表单（端到端真实路径），后端 `e2e_input_fixtures/*.py` 供 spec 经 `api-client.ts` 直接造前置数据（绕过 UI、只测目标流程、提速）。两侧文档描述同一份"示例实体"，README 标注对应关系避免漂移。

### 4.2 逐 spec 清理（写流程）

- `cleanup-registry.ts`：`track(kind, id)` 压栈；`drain()` 在 `afterEach` 按 LIFO 逆序 `DELETE`，保证父子 FK 顺序正确、测试顺序无关。
- 写 spec 每次创建（UI 触发后取 id，或 API 直造）都进栈；teardown 失败时打印未清记录的 kind+id 到 stderr，**不**让清理失败挂掉后续 spec。
- 这样 `make e2e -- --grep m1-core/fmea` 只起库+种子+跑该 spec，无需整轮，迭代快。
- 种子幂等：`seed_e2e` 用 upsert/固定 UUID，`make e2e-up` 可安全重跑；残留写数据不影响种子，重残留由 `make e2e-reset` 兜底。

## 5. 运行时序与数据流

### 5.1 一键全跑 `make e2e`

```
1. make e2e-up
   docker compose -f docker-compose.yml -f docker-compose.e2e.yml --profile e2e up -d
   → db(:5433, 卷 pgdata_e2e) / redis / backend(:8000) / frontend(:5174)
   → backend 注入 TENANT_MODE=single、DATABASE_URL→:5433/qms_e2e、E2E_MODE=1
2. 等待健康：backend /healthz 轮询至 200（总超时 60s，未达即明确报错并打印 backend logs），db pg_isready
3. alembic upgrade head（e2e 库）
4. python -m app.seed_e2e            # 幂等灌入已知记录
5. npx playwright test               # global.setup.ts 先跑：
   ├─ 凭证检测：缺失 → stderr 醒目报警横幅 + 写 e2e-env.json
   ├─ GET /api/e2e/seed-state → 校验种子就位
   └─ 4+1 角色 UI 登录 → 存 storageState/*.json
6. 各 spec 用 storageState 跑：
   ├─ 读流程：断言 seed-state 已知记录
   └─ 写流程：UI 填表 / API 造前置 → create → track(id) → 断言 → afterEach drain()
7. (不自动 down，便于看现场) → 手动 make e2e-down 清
```

### 5.2 单模块迭代 `make e2e -- --grep m1-core/fmea`

```
前置（一次性，库已起+种子已灌，幂等可跳过）：make e2e-up && make e2e-seed
然后：npx playwright test --grep "m1-core.*fmea"
→ 只跑匹配 spec，写数据 afterEach 自清，种子不动，改完即重跑
```

### 5.3 写流程数据流（以新建 8D 为例）

```
spec (m1-core/capa.spec.ts)
  ├─ loginAs("engineer") ← storageState/engineer.json
  ├─ goto /capa
  ├─ 填表：fixtures/input/capa-form-inputs.ts 的字段
  ├─ 提交 → 列表出现新行 → 取 id（data-e2e testid 或 API 按 document_no 查）
  ├─ track("capa", id) ──┐
  ├─ 断言：状态=新建、审计日志含 create
  ├─ 继续 D1→D8 流转、AI 草拟按钮可见性…
  └─ afterEach: cleanup.drain() → DELETE /api/capa/{id}（LIFO）←─┘
```

### 5.4 时序约束

- **token 过期**：JWT 120min。长套件可能超时。`storageState` 在 setup 存好；spec 遇 401 时 fixture 兜底用 `api-client.ts` 重新登录刷 storageState（不走 UI，避免卡死）。
- **后端异步**（DBLogHandler 队列、Outbox 推送、协同短轮询）：用 `waitForResponse`/`expect.poll` 轮询断言，**禁用**裸 `waitForTimeout`。
- **前端**：e2e 跑 `vite dev`，首访问冷启动等 `networkidle` 而非固定 sleep。

## 6. 错误处理与 flake 防御

1. **选择器脆弱**——优先 `getByRole` / `data-testid`；为 E2E 在关键交互元素加 `data-e2e="..."`（如 `capa-create-btn`、`row-{document_no}`）。这是对生产代码的**最小定向改动**，仅为可测性，不引入测试专用分支。中文文本断言用正则容忍空白（`/登\s*录/`）。表格行按文档号定位而非"第 N 行"。
2. **AI 调用走真实 LLM**（非固定桩）：
   - 凭证从本地 `.env.e2e`（gitignore）读：`E2E_LLM_API_KEY` / `E2E_LLM_BASE_URL` / `E2E_LLM_PROVIDER`（ark/deepseek/openai）。
   - 后端 e2e 简档据此覆盖活跃 provider、key、base_url；`llm_timeout` 设 **30s**（默认 5s < 真实 ~9s Ark 调用 → 超时静默 fallback；e2e 要真实调用，必须留足余量）。
   - Playwright AI 断言用 `expect.poll(...,{timeout:30s})` + `waitForResponse`。
   - **断言只验结构/行为，绝不文本匹配**（真实 LLM 非确定性，精确文本必 flake）：
     - 推荐 → 卡片 DOM 存在、关键字段齐全、`AP ∈ {H,M,L}`、`S/O/D ∈ 1..10`。
     - AI 草拟 → 目标编辑器区域**非空**、字符数 > N、含预期 HTML 标签层级（如小节容器节点存在），**不**断言具体文字。
     - 趋势解读 → 返回非空、含中文、分段节点存在，不断言逐句。
   - provider 适配坑：setup 阶段先做一次 `complete_json` 烟测；失败即跳过 AI spec 组并报告（参照 `ai-credentials.guard`）。
3. **凭证缺失报警**（非静默）：
   - `global.setup.ts` 缺凭证 → stderr 醒目横幅 `⚠️ E2E_LLM_API_KEY 未配置 → AI spec 组将跳过` + 写 `e2e-env.json`。
   - `ai-credentials.guard.spec.ts`：齐全→烟测 `complete_json`（失败即 fail，暴露适配问题）；缺失→`test.skip()` + `console.warn`，list reporter 可见。
   - 绝不静默：setup 横幅 + reporter warn 两层。
4. **残留数据/清理失败**：`drain()` 包 `afterEach`、try/each；失败打印未清记录，不挂后续 spec；重残留由 `make e2e-reset` 兜底。写数据单号用确定性前缀 `E2E-{module}-{seq}`，避开 seed-state 已占单号集合。
5. **栈未就绪**：健康轮询 60s 超时即明确报错并打印 backend logs，不静默继续。
6. **并发与重试**：`workers:1`、`fullyParallel:false`、CI `retries:2`、本地 `retries:0`（本地立刻看见 flake）、`trace:"on-first-retry"`。
7. **环境隔离**：e2e 库 `qms_e2e`（独立卷 `pgdata_e2e`、端口 `:5433`）与开发库 `qms` / CI 测试库 `qms_test` 完全分开；`down -v` 清卷。`/api/e2e/seed-state` 与 LLM 凭证注入由环境变量 `E2E_MODE=1` 开关，生产/正常 CI 不暴露。
8. **生产泄露门控**：`/api/e2e/seed-state` 路由注册处双重校验 `E2E_MODE=="1" and settings.TENANT_MODE != "production"`；条件不满足则**整组 e2e 路由不载入**，即便生产环境误注入 `E2E_MODE=1` 也绝不暴露种子元数据/账号信息。

## 7. 套件自身验证（meta）

- 干净环境 `make e2e-reset && make e2e` 全绿（无 AI 凭证时）或 AI 组 skip-with-warning。
- `--grep <module>` 单模块独立跑通，证明逐 spec 清理闭环。
- `seed.guard.spec.ts` 断言 seed-state 已知记录齐全，缺失即早停，避免下游误报。
- README 给"如何加一个新 spec"步骤模板：建输入文档 → 写 spec → track/drain → `--grep` 验证。

## 8. CI 接入（不做）

- **不**新增 `.github/workflows` e2e job，**不**改 `test.yml`，**不**注入 CI secrets，**不**上传 artifact。
- E2E 是本地/手动回归手段。`make check` 仍是 PR 必过门，不含 E2E。

## 9. 文档同步（docs-check）

- 触发 docs-check 的改动：`backend/app/seed_e2e*.py`、`backend/app/e2e_input_fixtures/`、`backend/app/api/e2e.py`（均匹配 `backend/app/`）。`frontend/e2e/*` 不匹配 `frontend/src/`、`docker-compose.e2e.yml` 不匹配 `docker-compose\.ya?ml$`，故不触发。
- 需新增 `docs/e2e.md`（套件总览）+ `CLAUDE.md` 命令节追加 `make e2e`，满足 docs-check。
- `frontend/e2e/README.md` 与 `docs/e2e.md` 互补。

## 10. 风险与权衡

| 风险 | 对策 |
|---|---|
| 真实 LLM 非确定性 → AI spec flake | 断言结构/行为非文本；30s 超时；`retries:2`+trace |
| 选择器随 UI 漂移脆裂 | `data-e2e` testid 为主，文本正则容忍 |
| 串行慢 | E2E 可靠优先于快；单模块 `--grep` 提速迭代；日后写流程多可演进到 per-worker 库 |
| `data-e2e` 改生产代码 | 仅可测性最小改动，无测试专用分支 |
| 种子与 demo seed 漂移 | 独立 `seed_e2e`，不依赖 `app.seed` |
| e2e db 卷/端口与开发库冲突（既有卷使 `POSTGRES_DB` 初始化失效、端口占用） | 独立卷 `pgdata_e2e` + 端口 `:5433`（db）/`:5174`（frontend）；`DATABASE_URL` 指向 `:5433/qms_e2e` |
| 多租户子域名伪造增加本地配置复杂度 | e2e 简档强制 `TENANT_MODE=single`，factory 行级隔离用 `factory_id` 在单租户下验证；多租户场景留 M4 单独 spec |
| e2e 端点生产泄露 | 路由注册双重门控 `E2E_MODE=1 且非 production`，否则不载入 |

## 11. 验收标准（首版 M0+M1）

1. `make e2e-reset && make e2e` 在干净环境一键全绿（无 LLM 凭证时 AI 组 skip+warning，其余全过）。
2. `make e2e -- --grep m1-core` 单模块独立跑通，写数据 afterEach 自清、种子不动。
3. M1 四个流程 spec 全绿：①**5 角色（4+1：admin/engineer/manager/viewer/group_admin）**登录+权限门控+跨工厂行级隔离不可见 ②新建 FMEA→编辑→推荐按钮→版本快照 ③新建 8D→D1-D8 流转→审批/关闭 ④看板 KPI 卡→过滤列表→详情。
4. LLM 凭证齐全时 AI 相关断言全绿——**仅验结构/行为**（推荐卡片 DOM 存在、`AP∈{H,M,L}`、`S/O/D∈1..10`；草拟编辑器非空含预期 HTML 层级；趋势解读非空含中文分段），绝不文本匹配。
5. `docs/e2e.md` + `CLAUDE.md` 更新，`docs-check` 过。
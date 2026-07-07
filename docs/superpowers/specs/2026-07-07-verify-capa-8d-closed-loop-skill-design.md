# 设计：verify-capa-8d-closed-loop skill（US-E2E-01 端到端验收走查）

**状态**: 定稿，待用户复核
**日期**: 2026-07-07
**依据**: `docs/user-stories/US-E2E-01-capa-8d-closed-loop.md`（定稿 v7，2026-07-07）
**类型**: OpenQMS 专属的 technique/reference skill（非 discipline-enforcing）

## 目标

创建一个项目级 skill `.claude/skills/verify-capa-8d-closed-loop/SKILL.md`，指导 agent 用真实浏览器（Playwright MCP `browser_*`）把用户故事 US-E2E-01（8D 全程闭环）走一遍，逐条验收每条验收标准，输出一份 markdown 验收报告。

这与现有的 `make e2e` Playwright spec 套件**互补**、不替代：
- `make e2e`：写 TypeScript spec，headless 跑在专用 e2e 栈，复现性由代码保证。
- 本 skill：agent 交互式驱动真实浏览器，逐条对照用户故事验收，产出人可读的验收报告。

## 关键决策

| 项 | 决策 |
|---|---|
| 产物 | 验收走查 → markdown 报告 |
| 范围 | OpenQMS 专属（账号/selector/baseURL/8D 流程/LLM 强制前置路径都内联） |
| app 启动 | 默认连 :5174 e2e 栈；未跑则 `make e2e-up && make e2e-seed` 拉起服务（**不**跑 spec）；干净环境用 `make e2e-reset` |
| AI 步骤 | 当作已实现去测；真点「接受/采纳」；走完整 12 阶段 DAG |
| 缺 LLM 凭证 | 提示用户配置 `.env.e2e` 后再跑（交互式，给字段清单） |
| 结构形态 | 方案 A：写死 B/C 剧本（非实时推导） |
| 同步机制 | CLAUDE.md 加规则 + skill 顶部版本声明 + agent 跑前比对 |
| skill 名 | `verify-capa-8d-closed-loop` |

## Skill 身份

- **存放**: `.claude/skills/verify-capa-8d-closed-loop/SKILL.md`（项目级，随仓库走）
- **类型**: technique/reference —— 给清晰步骤 + 查表 + 优秀实例；不做 rationalization 表 / red flags（那是 discipline-enforcing skill 的事）
- **description**（触发条件，第三人称，只写何时用不写怎么做）:
  > Use when asked to verify / walk through / 验收 / 走查 the OpenQMS CAPA 8D closed-loop user story (US-E2E-01) end-to-end in a real browser — e.g. "验收 US-E2E-01" / "walk through this user story" / "端到端测试这个用户故事". Drives the live app via Playwright browser tools, logs in as each role, fills/clicks through the 8D flow, asserts each acceptance criterion, and writes a markdown pass/fail report.

## 走查剧本结构（skill 主体）

按 US-E2E-01 的「主流程 10 步 + 12 阶段 DAG」组织。每步统一四段式：

```
### 步骤 N：<动作>
- 做什么：登录 / 填表 / 点按钮 / 断言
- 期望：UI 应呈现 / 状态应变为 / 字段落库
- 断言：检查 [具体 selector / API / DB]，通过条件
- 落库：此步应写入的审计日志 / 数据记录
```

### A 段 — 启动与前置

1. 默认连 `:5174`（e2e 栈）。检测 `:5174` 是否在跑；未跑则 `make e2e-up && make e2e-seed` 拉起服务并 seed（**不**用 `make e2e`——它会跑整套 Playwright spec）。需要干净环境时用 `make e2e-reset`。
   - **不支持默认连 dev 栈 `:5173`**：skill 依赖 `/api/e2e/seed-state` 和 `/api/e2e/cleanup`，这些路由只在 `E2E_MODE=1` 且非 production 时注册（`backend/app/main.py:450`），只有 e2e compose 设了 `E2E_MODE=1`（`docker-compose.e2e.yml:21`）。
   - 若用户强制用 `:5173`，skill 必须先 `GET /api/e2e/seed-state` 验证可达；不可达 → 停下，提示改用 e2e 栈（`make e2e-up`）。
2. 读 `.env.e2e`：
   - LLM 凭证齐（`LLM_PROVIDER`/`LLM_API_KEY`/`LLM_MODEL`/`LLM_BASE_URL`）→ 继续。
   - 缺 → 停下，提示用户配置（给字段清单），配好后再继续。不自行降级跑。
3. 读 skill 顶部记的故事版本，与 `docs/user-stories/US-E2E-01-...md` 顶部「状态: 定稿 vX（日期）」比对；不一致 → 停下，提示先同步（见「同步」一节）。
4. 用浏览器 MCP 打开 baseURL，拉 `/api/e2e/seed-state` 拿账号密码（不硬编码）。

### B 段 — 8D 全程闭环走查（主流程 10 步）

每步四段式，内联具体 selector。10 步骨架（B1/B5 详写为锚点，其余同形，完整四段式留到实现阶段写进 SKILL.md）：

- **B1** engineer 登录 → CAPA 列表 → `[data-e2e="capa-create"]` → 新建 8D：单号 `E2E-STORY-CAPA-001` / 标题「来料螺栓尺寸超差」/ 严重度「致命」 / 产品线 `DC-DC-100-E2E`。断言：列表出现该单号；`GET /api/capa/{report_id}` 回读 `status == "D1_TEAM"`（CAPAResponse 字段是 `status`，非 `current_step`；初始值 `D1_TEAM`，见 `backend/app/schemas/capa.py:34` / `models/capa.py:23`）；审计 1 条 CREATE（engineer）。
- **B2** D1 团队组建，指定 8D 负责人。
- **B3** D2 问题描述 + `[data-e2e="capa-ai-draft"]` AI 草拟 → 确认后保存。
- **B4** D3 临时措施。
- **B5** D4 根因分析 → 推进到 D4 → 触发 AI 推荐（见 C1）→ `[data-e2e="d4-adopt"]` 采纳 → 现场验证（见 C2）→ 确认根因 → `[data-e2e="capa-advance"]` 推进 D4→D5。断言：未验证根因时 D4→D5 阻断；审计 1 条 TRANSITION。
- **B6** D5 永久措施 → 触发 AI 推荐（见 C1）→ `[data-e2e="d5-adopt-suggestion"]` / `[data-e2e="d5-adopt-control"]` 采纳 → 保存。
- **B7** D6 实施验证 → 推进 D6→D7。
- **B8** D7 预防复发 → `[data-e2e="d7-auto-fill"]` / `[data-e2e="d7-confirm"]` / `[data-e2e="d7-skip"]`，含 AI 预防提示。
- **B9** manager 登录 → 列表见待审批 8D → 详情 → 审批 D7→D8 关闭。断言：engineer 不能审批 D7→D8（权限）。
- **B10** viewer 登录 → 列表见已关闭 8D → 详情可读，无编辑/推进/删除按钮。断言：只读可见。

### C 段 — AI 推荐流程编排走查（D4/D5 各跑一次完整 12 阶段 DAG）

#### C1 触发 + 12 阶段断言

触发 D4RecPanel / D5RecPanel 推荐，对 `i=1..12` 查 `[data-e2e="rec-dag-stage-<i>"]`。注意 `RecommendationDAG` 只在节点上暴露 `data-status` 属性；`source`（Tag）、`hit_count`（Badge）、`summary`（Text）是节点的**可见文本**，从渲染内容读取（`frontend/src/components/capa/RecommendationDAG.tsx:45-51`）：

| i | 阶段 | 期望状态 |
|---|---|---|
| 1 | 上下文采集 | done |
| 2 | 本产品 FMEA 检索 | done |
| 3 | 全局知识库 RAG（pgvector） | done |
| 4 | 同类型产品知识库 | done 或 skipped（注明） |
| 5 | 经验教训库 | done 或 skipped |
| 6 | SPC 异常关联 | done 或 skipped（无 SPC 数据） |
| 7 | MES 设备/过程数据 | done 或 skipped |
| 8 | IQC 来料检验（本批螺栓） | done |
| 9 | 供货历史 | done |
| 10 | 规则启发 | done |
| 11 | LLM 融合排序 | done（需 LLM 凭证） |
| 12 | 输出推荐列表 | done |

断言：
- 推荐列表非空、每条带 source provenance 标签、`AP∈{H,M,L}`、`S/O/D∈1..10`。
- 阶段 `hit_count`/`summary` 可见（非黑盒）。
- D4 和 D5 各跑一遍，分别记录。

#### C2 真点接受 + 现场验证（D4）

- 点 `[data-e2e="d4-adopt"]` 采纳一条候选根因。
- 点 `[data-e2e="d4-verification-new"]` 打开新建验证表单，依次：
  - 填 `[data-e2e="verification-method"]`（input，验证方法）
  - 填 `[data-e2e="verification-result"]`（textarea，测量/观察结果）
  - 上传证据：点 `[data-e2e="verification-evidence"]` 内的「添加证据」按钮触发文件选择 → 用浏览器 MCP `browser_file_upload` 传临时证据文件（Ant `Upload`，`beforeUpload={() => false}`，只收集 fileList 不自动上传）
  - 勾 `[data-e2e="verification-form-is-verified"]`（**新建表单**的 Switch；**不要**点列表上的 `[data-e2e="verification-is-verified"]`——那是已有记录的切换开关）
  - 提交 `[data-e2e="verification-submit"]`
- 断言：`[data-e2e="verification-status"]` 显示已验证；`GET /api/capa/{report_id}/root-cause-verifications` 回读验证记录落库可追溯。
- 断言：未验证时 D4→D5 阻断；验证通过后可推进。

#### 证据附件上传

skill 在 `$CLAUDE_JOB_DIR/tmp`（或 fixture）生成一个临时证据文件（小 PNG 或文本）。上传方式：点 `[data-e2e="verification-evidence"]` 区域的「添加证据」按钮触发原生文件选择对话框 → 浏览器 MCP `browser_file_upload`（paths 指向临时文件）。断言上传后 fileList 含该文件、详情页可见附件名。

### D 段 — 收尾与报告

- 清理：从 `/api/e2e/seed-state` 取 admin 密码 → `POST /api/auth/login` 拿 admin token → `POST /api/e2e/cleanup?prefix=E2E-STORY-`（后端 gated 端点，只删本前缀走查产生的记录，**不删 seed**）。
- 汇总每步标签 → 写报告 → 关浏览器。

## 内联查表（skill 里给 agent 速查）

1. **账号表**：从 `/api/e2e/seed-state` 动态取密码；列 4 角色 + 各自能/不能推进的 D 步。
2. **selector 表**：上述所有 `[data-e2e="..."]` 一览（统一带引号，避免 agent 复制出不稳定 selector）；每项标注断言读取方式——属性（如 `data-status`）还是可见文本（如 stage 的 `source`/`hit_count`/`summary`）。
3. **8D 状态机表**：`D1_TEAM → D2_DESCRIPTION → D3_INTERIM → D4_ROOT_CAUSE → D5_CORRECTION → D6_VERIFICATION → D7_PREVENTION → D8_CLOSURE`（`backend/app/state_machines/eightd_state.py`）；回退边 `D4→D3`、`D6→D5`（对应「现场验证不通过回到上一步」）；每步需权限——D1–D6 推进需 EDIT（engineer 可），D7→D8 需审批（manager 可，engineer 不可）；不可跳步。
4. **审计轨迹期望**：1 CREATE + 7 TRANSITION；6 条 D1→D2…D6→D7 由 engineer，末条 D7→D8 由 manager（故事「D1-D7 由现场质量工程师」指 D 步内容归属，过渡归属按此拆分）。
5. **报告模板**：见下。

## 缺陷分类（每步打一个标签）

| 标签 | 含义 | 例子 |
|---|---|---|
| **PASS** | 通过，断言全满足 | D4→D5 推进成功、落库正确 |
| **PASS-NOTE** | 通过但有备注（不阻断） | SPC 阶段 `skipped` 且注明「无 SPC 数据」（故事允许） |
| **FAIL** | 断言失败 = 缺陷 | FMEA 阶段状态 `error`、推荐列表空、provenance 缺失、未验证却放行 D4→D5 |
| **MISSING** | 故事要求的功能根本不存在 = 缺陷 | D4RecPanel 没渲染、`[data-e2e="rec-dag-stage-*"]` 找不到、无「采纳」按钮 |

约定：**MISSING 和 FAIL 都算缺陷**（严重度不同）；都在报告「缺陷清单」单列。PASS-NOTE 不算缺陷。

「当作已实现去测」的落地：agent 找不到 selector / 面板没渲染 → 直接判 MISSING，**不**自行脑补「这功能可能还没做所以跳过」。

## 报告格式 + 落点

- 路径：`docs/e2e/reports/US-E2E-01-<YYYY-MM-DD>.md`（新增 `docs/e2e/reports/` 子目录）。
- 截图：每个 FAIL/MISSING 用浏览器 MCP 截图存 `docs/e2e/reports/assets/US-E2E-01-<date>/step-<n>.png`，报告引用路径。
- 结构：
  1. **头部**：故事名 + 版本 + skill 依据版本 + 走查时间 + app commit + LLM 凭证状态。
  2. **总览**：PASS/PASS-NOTE/FAIL/MISSING 计数 + 整体结论（PASS / 有缺陷 / BLOCKED）。
  3. **B 段步骤表**：10 步 × {做什么 / 期望 / 断言结果 / 标签}。
  4. **C 段 DAG 阶段矩阵**：D4 和 D5 各一张 12 阶段表（index / 名称 / 来源 / 状态 / 命中数 / 摘要 / 标签）。
  5. **审计轨迹核对**：从 `/api/e2e/seed-state` 取 admin 密码 → `POST /api/auth/login` 拿 token → `GET /api/admin/logs/audit?table_name=capa_eightd&page=1&page_size=200&start=<走查开始ISO>` → 客户端按 `record_id` == 该 8D id 过滤（`/api/audit-logs?target_id` 不存在，勿用）。期望 1 CREATE + 7 TRANSITION；6 条 D1→D2…D6→D7 由 engineer、末条 D7→D8 由 manager。过渡断言形状：`changed_fields.old_status` / `changed_fields.new_status` / `operated_by`（参考 `frontend/e2e/specs/m1-core/capa-story-closed-loop.spec.ts:240-249`）。
  6. **AI 采纳留痕核对**（同上 audit 查询）：过滤 `action == "ADOPT_RECOMMENDATION"`，断 `changed_fields.source` 真值、`changed_fields.stage_index` 为数字、`operated_by == "engineer"`（`adopt-recommendation` 是 POST 写入、无 GET 回读端点，留痕只能从审计查；参考 `capa-story-closed-loop.spec.ts:248-256`）。
  7. **落库抽查**：`GET /api/capa/{report_id}` 回读，核对 `document_no`/`title`/`severity`/`status`/各 D 步字段；`GET /api/capa/{report_id}/root-cause-verifications` 核对验证记录。
  8. **缺陷清单**：所有 FAIL + MISSING，每条含「步骤 / 期望 / 实际 / 严重度 / 截图路径」。
  9. **证据附件**：现场验证上传的文件名 + 上传后是否在详情可见。

## 同步机制

用户故事与 skill 是单向派生关系：

```
docs/user-stories/US-E2E-01-capa-8d-closed-loop.md  (源头，含「状态: 定稿 vX（日期）」)
        ↓ 派生
.claude/skills/verify-capa-8d-closed-loop/SKILL.md  (剧本，顶部声明依据的故事版本)
```

### skill 内（顶部 + 维护节）

- 顶部声明：
  ```
  依据：docs/user-stories/US-E2E-01-capa-8d-closed-loop.md
  故事版本：定稿 v7（2026-07-07）
  同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步。
  ```
- 维护节：agent 跑前比对 skill 内版本与故事顶部实际版本；不一致 → 停下，提示用户先同步；同步 = 重读故事 → 逐条核对剧本 → 改 SKILL.md → 更新顶部版本声明 → 重跑。

### CLAUDE.md（项目级规则，对所有 verify-* skill 通用）

新增一节：

```markdown
## User Story ↔ Skill 同步规则

每个 `verify-*` skill 是某条用户故事的**派生走查剧本**（单向派生）：

- 源头：`docs/user-stories/US-<id>-<name>.md`（含「状态: 定稿 vX（日期）」）
- 派生：`.claude/skills/verify-<name>/SKILL.md`（顶部声明依据的故事版本）

**规则**：当用户故事的版本号或日期变更，对应 skill 剧本必须重新核对并同步，
更新顶部版本声明后才能用于走查。agent 每次跑 `verify-*` skill 前先比对
skill 内记的故事版本与用户故事顶部实际版本——不一致则停下、提示用户先同步。
```

## 需要修改 / 新增的文件

| 文件 | 动作 |
|---|---|
| `.claude/skills/verify-capa-8d-closed-loop/SKILL.md` | 新增（skill 主体） |
| `CLAUDE.md` | 新增「User Story ↔ Skill 同步规则」一节 |
| `docs/e2e/reports/` | 新增目录（报告落点，首次走查时由 agent 创建） |
| `docs/e2e/reports/assets/` | 新增目录（截图落点） |

## 不在本 skill 范围

- 写 TypeScript Playwright spec（那是 `frontend/e2e/specs/` + `make e2e` 的职责）。
- 测 US-E2E-01 之外的用户故事（另起 `verify-<name>` skill）。
- AI 推荐准确率 / 排序质量评测（需标注数据集，故事已声明不在范围）。
- 工厂隔离的跨厂验证（故事已声明另立）。

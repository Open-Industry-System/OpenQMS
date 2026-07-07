---
name: verify-capa-8d-closed-loop
description: Use when asked to verify / walk through / 验收 / 走查 the OpenQMS CAPA 8D closed-loop user story (US-E2E-01) end-to-end in a real browser — e.g. "验收 US-E2E-01" / "walk through this user story" / "端到端测试这个用户故事". Symptoms include needing to confirm acceptance criteria pass, check the AI recommendation orchestration DAG, or produce an acceptance report for the 8D closed-loop story.
---

> 依据：docs/user-stories/US-E2E-01-capa-8d-closed-loop.md
> 故事版本：定稿 v7（2026-07-07）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-capa-8d-closed-loop

## Overview

把用户故事 US-E2E-01（8D 全程闭环 + AI 多源推荐 + 根因现场验证 + 流程可视化）在真实浏览器里走一遍，逐条验收每条验收标准，输出 markdown 验收报告。用浏览器 MCP（`browser_*`）驱动；账号从 `/api/e2e/seed-state` 动态取；断言走 UI selector + 回读 API + 审计 API。

这是 acceptance walk（人可读验收报告），不是 Playwright spec——spec 写在 `frontend/e2e/specs/`，本 skill 不写 spec。

## When to Use

**用**：用户说「验收 US-E2E-01」「走查这个用户故事」「端到端测试 CAPA 8D 闭环」等。
**不用**：测其他用户故事（另起 `verify-*` skill）；写/改 Playwright spec；AI 推荐准确率评测。

## 前置（开始前必须全部满足，否则停下）

1. **故事版本一致**：读本 skill 顶部「故事版本」，与 `docs/user-stories/US-E2E-01-capa-8d-closed-loop.md` 顶部「状态: 定稿 vX（日期）」比对；不一致 → 停下，提示用户先同步（见「维护」），不跑。
2. **e2e 栈在跑**：`curl -sf http://localhost:5174` 验证可达。
   - 不可达 → 跑 `make e2e-up && make e2e-seed` 拉起服务并 seed（**不**用 `make e2e`，它会跑整套 Playwright spec）。干净环境用 `make e2e-reset`。
   - 默认只用 `:5174`（e2e 栈）。`/api/e2e/seed-state` 和 `/api/e2e/cleanup` 只在 `E2E_MODE=1` 且非 production 注册（`backend/app/main.py:450`），只有 e2e compose 设了 `E2E_MODE=1`（`docker-compose.e2e.yml:21`）。
   - 用户强制 `:5173`（dev 栈）→ 必须先 `GET /api/e2e/seed-state` 验证可达；不可达 → 停下，提示改用 e2e 栈。
3. **LLM 凭证齐**：读 `.env.e2e`，要 `LLM_PROVIDER`/`LLM_API_KEY`/`LLM_MODEL`/`LLM_BASE_URL` 四项全有。
   - 缺 → 停下，提示用户配置（给字段清单），配好后再继续。**不自行降级跑**（AI 步骤是本故事头条验收项，缺凭证无法验收）。
4. **拿账号**：`GET /api/e2e/seed-state` 取 admin/engineer/manager/viewer 密码（不硬编码）。

## 账号 × 权限表

| 账号 | 角色 | 能推进的 D 步 | 不能 |
|---|---|---|---|
| engineer | field_qe | D1→D2…D6→D7（EDIT） | D7→D8（需审批） |
| manager | 8D 负责人 | D7→D8（审批） | — |
| viewer | 只读 | 无 | 任何编辑/推进 |
| admin | 全权 | 全部 | — |

## selector 表

| selector | 读取方式 | 用途 |
|---|---|---|
| `[data-e2e="capa-create"]` | 点击 | 新建 8D |
| `[data-e2e="capa-advance"]` | 点击 | 推进下一步（D1→…→D8 共用；D7→D8 需 canApprove） |
| `[data-e2e="capa-ai-draft"]` | 点击 | AI 草拟（D2/D3/D4/D5/D6 label 上的草拟入口） |
| `[data-e2e="d4-adopt"]` | 点击 | D4 采纳推荐根因 |
| `[data-e2e="d4-verification-new"]` | 点击 | D4 新建现场验证表单 |
| `[data-e2e="verification-method"]` | 填 input | 验证方法 |
| `[data-e2e="verification-result"]` | 填 textarea | 测量/观察结果 |
| `[data-e2e="verification-evidence"]` | 点内「添加证据」→ 文件选择 | 证据附件（Ant Upload） |
| `[data-e2e="verification-form-is-verified"]` | 勾 Switch | **新建表单**的「已验证」 |
| `[data-e2e="verification-is-verified"]` | — | **不要点**——已有记录列表的切换开关 |
| `[data-e2e="verification-submit"]` | 点击 | 提交验证 |
| `[data-e2e="verification-status"]` | 读可见文本 | 验证状态 |
| `[data-e2e="d5-adopt-suggestion"]` | 点击 | D5 采纳推荐措施 |
| `[data-e2e="d5-adopt-control"]` | 点击 | D5 采纳为控制措施 |
| `[data-e2e="d7-auto-fill"]` | 点击 | D7 AI 预防提示自动填充 |
| `[data-e2e="d7-confirm"]` | 点击 | D7 确认预防项 |
| `[data-e2e="d7-skip"]` | 点击 | D7 跳过预防项（需填理由） |
| `[data-e2e="rec-dag-stage-<i>"]` | 读 `data-status` 属性 + 节点内可见文本 | 12 阶段 DAG 第 i 阶段（`source`/`hit_count`/`summary` 是 Tag/Badge/Text，不是属性） |
| `[data-e2e^="rec-source-"]` | 读 Tag 文本（模板 `rec-source-${match_source}`） | 每条推荐的来源 provenance 标签（D4RecPanel:143 / D5RecPanel:100,174） |
| `[data-e2e^="rec-item-stage-"]` | 读 Tag 文本（模板 `rec-item-stage-${stage_index}`） | 每条推荐命中的阶段索引（D4RecPanel:147 / D5RecPanel:104,178） |

**无 data-e2e 的字段**：D1 团队表、D2/D3/D4/D5/D6/D7 的 TextArea、登录表单。**CAPA 各 D 步 TextArea 不要用 `getByLabel`**——label 是 `renderLabelWithDraft` 渲染的自定义节点（含「撤销修改」+ AI 草拟按钮，`CAPADetailPage.tsx:273`），Ant `getByLabel` 不可靠。用现有 E2E 验证过的模式：先 `waitForStep` 等该步 label 文本可见，再 `page.locator("textarea").first()` 定位当前步唯一的 TextArea，填值后 `.evaluate((el) => el.blur())` 触发 onBlur 落库（参考 `frontend/e2e/specs/m1-core/capa-story-closed-loop.spec.ts:110`）。登录用 `getByLabel("用户名")` / `getByLabel("密码")` + 登录按钮文本（登录表单是标准 Ant Form，`getByLabel` 可用）。

## 8D 状态机

`D1_TEAM → D2_DESCRIPTION → D3_INTERIM → D4_ROOT_CAUSE → D5_CORRECTION → D6_VERIFICATION → D7_PREVENTION → D8_CLOSURE`（`backend/app/state_machines/eightd_state.py`）。回退边 `D4→D3`、`D6→D5`（验证不通过回到上一步）。不可跳步。D1–D6 推进需 EDIT（engineer 可）；D7→D8 需审批（manager 可，engineer 不可）。

## 走查剧本

### A. 启动（前置 4 项全过后）

- `browser_navigate("http://localhost:5174")` → `GET /api/e2e/seed-state` 拿账号密码。
- 记录走查开始 ISO 时间（audit 查询的 `start` 窗口用）。

### B. 8D 闭环（10 步，每步四段式）

#### B1 engineer 登录 + 新建 8D
- **做**：`browser_navigate` 登录页 → 按 label 填用户名/密码（engineer）→ 点登录 → 进 CAPA 列表 → 点 `[data-e2e="capa-create"]` → 填单号 `E2E-STORY-CAPA-001` / 标题「来料螺栓尺寸超差」/ 严重度「致命」/ 产品线 `DC-DC-100-E2E` → 提交。
- **期望**：列表出现该单号；详情页 Steps 高亮 D1。
- **断言**：`GET /api/capa/{report_id}` 回读 `status == "D1_TEAM"`、`title`/`severity`/`document_no`/`product_line_code` 正确。
- **落库**：审计 1 条 CREATE，`operated_by == "engineer"`。

#### B2 D1 团队组建
- **做**：D1 视图下用 `getByPlaceholder("成员姓名")` 填名 + Select 选 role（含一人为「8D 团队负责人」）→ 点「添加成员」加 2–3 人。
- **期望**：团队成员表出现新增行。
- **断言**：`GET /api/capa/{report_id}` 回读 `d1_team` 数组含所加成员。
- **落库**：UPDATE 审计（engineer）。

#### B3 D2 问题描述 + AI 草拟
- **做**：等 D2 label「5W2H 问题描述」可见 → `page.locator("textarea").first()` 填描述 → `.blur()` 落库 → 点 `[data-e2e="capa-ai-draft"]` 触发 AI 草拟 → 确认/采纳后保存。
- **期望**：AI 草拟返回文本；保存后字段落库。
- **断言**：回读 `d2_description` 非空。
- **落库**：UPDATE + AI 草拟留痕。

#### B4 D3 临时措施
- **做**：等 D3 label「临时遏制措施」可见 → `page.locator("textarea").first()` 填临时围堵 → `.blur()` 保存。
- **期望**：字段落库。
- **断言**：回读 `d3_interim` 非空。
- **落库**：UPDATE。

#### B5 D4 根因分析（含 AI 推荐 + 现场验证）
- **做**：点 `[data-e2e="capa-advance"]` 推进到 D4 → 触发 D4 AI 推荐（见 C1）→ 点 `[data-e2e="d4-adopt"]` 采纳一条候选根因 → 现场验证（见 C2）→ 等 D4 label「根因分析 (5Why / 鱼骨图)」可见 → `page.locator("textarea").first()` 填根因 → `.blur()` 落库 → 点 `[data-e2e="capa-advance"]` 推进 D4→D5。
- **期望**：D4 视图出现 D4RecPanel + D4VerificationCard + 根因 TextArea。
- **断言**：**未完成现场验证时 D4→D5 应被阻断**（advance 报错或禁用）；验证通过后才可推进。
- **落库**：审计 1 条 TRANSITION `D4_ROOT_CAUSE → D5_CORRECTION`，`operated_by == "engineer"`。

#### B6 D5 永久措施（含 AI 推荐）
- **做**：推进到 D5 → 触发 D5 AI 推荐（见 C1）→ 点 `[data-e2e="d5-adopt-suggestion"]`（或 `d5-adopt-control`）采纳 → 等 D5 label「永久纠正措施」可见 → `page.locator("textarea").first()` 填措施 → `.blur()` 保存。
- **期望**：D5RecPanel + 措施 TextArea。
- **断言**：回读 `d5_correction` 非空；采纳留痕（审计 `action == "ADOPT_RECOMMENDATION"`）。
- **落库**：UPDATE + 采纳留痕。

#### B7 D6 实施验证
- **做**：等 D6 label「效果验证」可见 → `page.locator("textarea").first()` 填验证结果 → `.blur()` 保存 → 点 `[data-e2e="capa-advance"]` 推进 D6→D7。
- **期望**：字段落库；推进成功。
- **断言**：回读 `d6_verification` 非空；审计 1 条 TRANSITION `D6_VERIFICATION → D7_PREVENTION`，`operated_by == "engineer"`。

#### B8 D7 预防复发（含 AI 预防提示）
- **做**（两部分，分开落库）：
  1. **D7 预防措施正文**：等 D7 label「预防复发措施」可见 → `page.locator("textarea").first()` 填预防措施正文 → `.blur()` 落库 `d7_prevention`（`CAPADetailPage.tsx:570`，Text 列 `models/capa.py:31`）。
  2. **D7 节点动作（AI 预防提示）**：对每个预防项用 `[data-e2e="d7-auto-fill"]`（AI 填充）/ `[data-e2e="d7-confirm"]`（确认）/ `[data-e2e="d7-skip"]`（跳过，填理由）——这些按钮写 **node-action 记录**，不写 `d7_prevention`。
- **期望**：D7 预防项全部确认或跳过后才可推进。
- **断言**：`GET /api/capa/{report_id}` 回读 `d7_prevention` 非空；`GET /api/capa/{report_id}/d7-node-actions` 回读节点动作记录（`capa.py:717`）；engineer 此时**不能**推进 D7→D8（见 B9）。
- **落库**：`d7_prevention` UPDATE + node-action 记录 + D7 skip reasons 审计（若跳过）。

#### B9 manager 登录 + 审批 D7→D8 关闭
- **做**：登出 → manager 登录 → CAPA 列表见该 8D（待审批）→ 进详情 → 点 `[data-e2e="capa-advance"]`（D7→D8，需 canApprove）→ 关闭。
- **期望**：manager 能推进；engineer 不能（先切 engineer 验证 `capa-advance` 不可见/禁用，再切 manager 推进）。
- **断言**：`GET /api/capa/{report_id}` 回读 `status == "D8_CLOSURE"`；审计 1 条 TRANSITION `D7_PREVENTION → D8_CLOSURE`，`operated_by == "manager"`。
- **注意**：`advance_capa` 只改 `status` + 写 TRANSITION 审计，**不**自动填 `d8_closure`（`capa_service.py:427`）。若故事要求关闭内容落库，关闭后**单独**一步：等 D8 label 可见 → `page.locator("textarea").first()` 填关闭总结 → `.blur()` 落库 `d8_closure`（Text 列 `models/capa.py:32`）；否则只断言 `status == "D8_CLOSURE"`。

#### B10 viewer 只读可见
- **做**：登出 → viewer 登录 → CAPA 列表见已关闭 8D → 进详情可读内容。
- **期望**：详情可见，但无 `[data-e2e="capa-create"]` / `capa-advance` / 编辑控件。
- **断言**：`capa-advance` 不存在或禁用；各 TextArea `disabled`。
- **落库**：viewer 不产生任何写审计。

### C. AI 推荐流程编排（D4/D5 各跑完整 12 阶段 DAG）

#### C1 触发 + 12 阶段断言

在 D4RecPanel / D5RecPanel 触发推荐。对 `i=1..12` 查 `[data-e2e="rec-dag-stage-<i>"]`：

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

读 `data-status` 属性；`source`（Tag）/`hit_count`（Badge）/`summary`（Text）是节点可见文本，从渲染内容读（`frontend/src/components/capa/RecommendationDAG.tsx:45-51`）。

**断言**：
- 推荐列表非空；每条推荐可见 `[data-e2e^="rec-source-"]`（来源 provenance 标签）和 `[data-e2e^="rec-item-stage-"]`（命中阶段索引）；`AP∈{H,M,L}`、`S/O/D∈1..10`。
- 阶段 `hit_count`/`summary` 可见（非黑盒）。
- D4、D5 各跑一遍，分别记录。

#### C2 真点接受 + 现场验证（D4）

- 点 `[data-e2e="d4-adopt"]` 采纳一条候选根因。
- 点 `[data-e2e="d4-verification-new"]` 打开新建验证表单：
  - 填 `[data-e2e="verification-method"]`（input）
  - 填 `[data-e2e="verification-result"]`（textarea）
  - 上传证据：点 `[data-e2e="verification-evidence"]` 内「添加证据」按钮触发文件选择 → `browser_file_upload` 传临时证据文件（在 `docs/e2e/reports/assets/US-E2E-01-<date>/evidence-<n>.png` 生成一个小 PNG，与截图同目录）
  - 勾 `[data-e2e="verification-form-is-verified"]`（**不要**点 `verification-is-verified`）
  - 点 `[data-e2e="verification-submit"]`
- **断言**：`[data-e2e="verification-status"]` 显示已验证；`GET /api/capa/{report_id}/root-cause-verifications` 回读验证记录含 method/result/evidence。
- **断言**：未验证时 D4→D5 阻断；验证通过后可推进。

### D. 收尾 + 报告

- **清理**：admin token（seed-state 取密码 → `POST /api/auth/login`）→ `POST /api/e2e/cleanup?prefix=E2E-STORY-`（只删本前缀走查记录，**不删 seed**）。
- 关浏览器。
- 写报告（见「报告模板」）。

## 缺陷分类（每步打一个标签）

| 标签 | 含义 | 例子 |
|---|---|---|
| **PASS** | 断言全满足 | D4→D5 推进成功、落库正确 |
| **PASS-NOTE** | 通过但有备注（不阻断） | SPC 阶段 skipped 且注明「无 SPC 数据」 |
| **FAIL** | 断言失败 = 缺陷 | FMEA 阶段 status=error、推荐列表空、provenance 缺失、未验证却放行 D4→D5 |
| **MISSING** | 故事要求的功能根本不存在 = 缺陷 | D4RecPanel 没渲染、`[data-e2e="rec-dag-stage-*"]` 找不到、无采纳按钮 |

**MISSING 和 FAIL 都算缺陷**，在报告「缺陷清单」单列。PASS-NOTE 不算缺陷。

**当作已实现去测**：找不到 selector / 面板没渲染 → 直接判 MISSING，**不**自行脑补「这功能可能还没做所以跳过」。

每个 FAIL/MISSING 用浏览器 MCP 截图存 `docs/e2e/reports/assets/US-E2E-01-<date>/step-<n>.png`。

## 报告模板

路径：`docs/e2e/reports/US-E2E-01-<YYYY-MM-DD>.md`

```markdown
# US-E2E-01 验收报告 — <date>

- 故事版本：定稿 v7（2026-07-07）
- skill 依据版本：v7（2026-07-07）
- 走查时间：<开始ISO> ~ <结束ISO>
- app commit：<git rev-parse HEAD>
- LLM 凭证状态：齐全 / 缺（哪几项）

## 总览
- PASS: N | PASS-NOTE: N | FAIL: N | MISSING: N
- 整体结论：PASS / 有缺陷 / BLOCKED

## B 段步骤表
| 步 | 做什么 | 期望 | 断言结果 | 标签 |
|---|---|---|---|---|
| B1 | 新建 8D | status=D1_TEAM | GET 回读 status=D1_TEAM | PASS |
| ... |

## C 段 DAG 阶段矩阵（D4）
| i | 名称 | 来源 | 状态 | 命中数 | 摘要 | 标签 |
|---|---|---|---|---|---|---|
| 1 | 上下文采集 | ... | done | ... | ... | PASS |
| ... |

## C 段 DAG 阶段矩阵（D5）
（同上）

## 审计轨迹核对
- 期望：1 CREATE + 7 TRANSITION（6 条 D1→D2…D6→D7 by engineer，末条 D7→D8 by manager）
- 实际：`GET /api/admin/logs/audit?table_name=capa_eightd&page=1&page_size=200&start=<开始ISO>` 按 record_id 过滤 → 列出每条 old_status/new_status/operated_by
- 结果：PASS/FAIL

## AI 采纳留痕核对
- `action == "ADOPT_RECOMMENDATION"` 条数、changed_fields.source / stage_index / operated_by
- 结果：PASS/FAIL

## 落库抽查
- `GET /api/capa/{report_id}`：document_no / title / severity / status / 各 D 步字段
- `GET /api/capa/{report_id}/root-cause-verifications`：验证记录
- 结果：PASS/FAIL

## 缺陷清单
| 步 | 期望 | 实际 | 严重度 | 截图 |
|---|---|---|---|---|
| ... |

## 证据附件
- 上传文件名 + 详情页是否可见
```

## 维护（同步）

本 skill 是用户故事的**单向派生剧本**。每次跑前：

1. 读 skill 顶部「故事版本」。
2. 读 `docs/user-stories/US-E2E-01-capa-8d-closed-loop.md` 顶部「状态: 定稿 vX（日期）」。
3. 版本号/日期一致 → 直接跑。
4. 不一致 → 停下，提示用户：「用户故事已更新到 vX，skill 剧本仍停在 vY，需同步后再跑。要我现在同步吗？」
   - 同步 = 重读故事 → 逐条核对剧本（步骤/断言/selector/状态机）→ 改 SKILL.md → 更新顶部版本声明 → 重跑。

`CLAUDE.md` 里有项目级同步规则（对所有 `verify-*` skill 通用）。引用校验脚本：`bash .claude/skills/verify-capa-8d-closed-loop/scripts/verify-refs.sh`。

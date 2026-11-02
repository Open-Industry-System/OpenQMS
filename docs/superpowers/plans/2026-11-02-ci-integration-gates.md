# CI 独立提交接入与分层门禁 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 等外部 Claude Code CI Agent 完成交付，将其独立提交接入现有语义集成分支，以本轮专属资源运行分层门禁，再进入剩余架构阶段设计。

**Architecture:** 只集成已提交成果，不复制正在变化的工作树。保留 `20570157` 的权限/租户/来源合同，测试资源与 CI Agent 完全隔离。backend、browser、frontend 和显式真实验收分别留收据，后续功能只在相应阶段设计与门禁满足后实施。

**Tech Stack:** Git worktrees、pytest、PostgreSQL15/pgvector、Node/Playwright、GitHub Actions 现有分层合同。

---

## 0. 当前事实与授权边界

- 本地集成起点：`20570157755ec197d68431e5215811bca02fce7c`，分支 `integration/agent-main-semantic-20261102`；其两个父为 runtime `ef3e24e0` 和 main `d8e2cef5`。
- 外部 CI 工作树：`.claude/worktrees/agent-module-permission-kernel`，只读检查。2026-11-02 本轮首次核对仍为 `ef3e24e0`，Task1–5 已复核、Task6 workflow 实施中，完整冻结及干净 checkout 尚未完成，CI 路径仍有未提交改动。这不是交付完成。
- 保留用户删除 `.env.e2e.example`；CI 路径干净不要求恢复该删除。
- 不修改外部工作树/index、不复制其未提交源码，不代替它执行提交，不借它的容器/profile/证据。
- 不直接更新 main、push、建 PR、部署或开启生产能力。手动远端验收不能为触发 workflow 而自动合 main。
- 只读准备使用定向 read/glob/grep；本会话没有 CodeGraph 工具。准备审查不代替最终固定提交复核。

## Task 1: 监听交付并确认精确提交

**Files:** Read external `PROGRESS.md` and `docs/superpowers/plans/2026-11-02-ci-layered-acceptance.md`; no external writes.

- [x] 确认当前 HEAD、dirty 范围、进度和相关 Claude 进程名/工作目录，不读进程参数、环境或私有会话日志。
- [x] 建立内核文件系统事件监听 Git branch ref；不使用 sleep/busy-poll。另保留低频进度提醒，以识别未提交交付或切分支。
- [ ] 出现提交后读取以下证据，不能仅因 HEAD 改变就认定全部收尾：

```bash
git -C .claude/worktrees/agent-module-permission-kernel log --oneline ef3e24e0..HEAD
git -C .claude/worktrees/agent-module-permission-kernel status --short
git -C .claude/worktrees/agent-module-permission-kernel diff --stat ef3e24e0..HEAD
```

- [ ] 读取最终进度确认实现/复核/冻结/干净 checkout 的真实状态；阶段性提交与最终交付分开。不把 collection 数量当运行结果。
- [ ] 记录精确 CI commit SHA；用户删除、私有profile、临时登记/日志不进入提交。若最终只有未提交交付，先取得明确交付方式，不擅自替外部 Agent 提交。

## Task 2: 接入并复核双侧合同

**Files:** Existing integration branch; conflicts expected mainly in `PROGRESS.md` and `docs/architecture.md`; review source CI committed file list before editing.

- [ ] 重读最终提交的 Make、runner、tests/ci、workflow 与 CI 设计，不能使用下面静态预览风险充当固定提交结论。
- [ ] 把已核验精确SHA存入CI_COMMIT，在本地集成工作树执行 `git merge --no-commit --no-ff "${CI_COMMIT:?verified CI commit required}"`；先用 `git cat-file -t "$CI_COMMIT"` 确认为commit，不能用分支浮动值。
- [ ] 逐项处理实际冲突；保留双方历史，最新事实改为集成分支，不保留互相矛盾的“唯一开发入口”。用户删除示例仍不恢复。
- [ ] 保留默认 DENY/runtime/附件关闭、GROUP ADMIN 工厂规则、新鲜显式 line bypass、owner-module approval、申请人/执行人隔离、六字段来源/四键授权、租户 generation/严格 search_path。
- [ ] 检查 public head `20261102_agent_mainline_merge`、tenant `tv006_agent_read_tasks` 和旧 read-task/runtime 两表族；保留历史 tv005 阶段断言，不能全部机械改 tv006。
- [ ] 最终固定提交审查重点：Docker published HostIp 与 URL host 兼容且不放宽远端/owner验证；显式 Chromium 路径能抵达真正 pytest 子进程；旧文档不再引导隐式私有profile；backend 既有skip与显式gate严格策略区分。若实质失败，新增最小回归先红后绿，只改集成工作树。

## Task 3: 准备本轮独占资源与依赖

**Files:** Runtime-only resource registration outside tracked source; no user secret/profile reads.

- [x] 扩展本工作树按需检出的 scripts/frontend/docker/workflow/docs，核验所需文件和原有排除文件；不复制外部Agent未提交文件或node_modules。
- [x] 核对已安装 Python 完整依赖、Node 引擎、项目 Chromium。Python CI参考3.12；Node采用满足锁文件引擎的版本，不只看package声明最低18；当前预览jsdom要求20.19+/22.13+/24+。缺少安装条件时明确报告，不擅自换版本或升级锁文件。

**2026-11-03 准备证据（不是接入后门禁结果）**：目录扩展一度等待旧public-home文档的dataless对象，已仅中止本轮扩展并移除经绝对路径/零字节核验的checkout碎片，改为精确CI路径；语义集成提交和外部工作树未变。已恢复与提交blob一致的PPT服务并加入包含规则，避免其被旧排除规则再次移除。`npm ci --offline --ignore-scripts --no-audit --no-fund` 从本机缓存安装491包，禁止浏览器下载，锁文件与package文件无diff；TypeScript5.9.3/Vite5.4.21/Vitest4.1.7/Playwright1.60.0已可用。项目默认Chromium路径已核验存在可执行，esbuild本地TS转换通过，均未启动浏览器或服务。可用项目Python为3.11.15、Node为26.13.0，不冒称与Linux/Python3.12/Node20的CI环境相同；未运行接入后的任何gate。
- [ ] 使用本地已缓存 pgvector PG15 镜像创建本轮独占容器、自有卷和随机 nonce；明确 `127.0.0.1` 随机发布端口。记录完整64位ID、Config.Image精确值、owner标签、实际映射和唯一volume。
- [ ] 按最终 owned_resources 合同生成0600无凭据登记，包含 container/container_id/owner_nonce/image/host/port/test_database/application_database；两个库名不同，测试库 `_test` 后缀。数据库用户只用于该实例并能建立派生随机迁移库。
- [ ] 显式设置 OPENQMS_TEST_RESOURCE_FILE/TEST_DATABASE_URL，不设置 PG15_CONTAINER（它选择另一CI标签路径），清除冲突legacy PG变量。登记和URL同时校验，不连接默认开发库。
- [ ] provider/embedding密钥对普通子进程为空，移除 E2E_MODE 而非写字符串 false；不读取 `.env.e2e` 或隐式测试profile。

## Task 4: 分层运行并留完整结果

**Files:** Final Makefile/runner/test contracts; artifacts outside tracked source.

- [ ] 先运行纯支持和runner回归（PY为已核验解释器）：

```bash
"$PY" scripts/check-ci-pure.py tests/ci/ tests/e2e/test_capa_outcome_runner.py -q -rA
```

- [ ] 经最终纯引导入口执行collect-only核四层分区/全集，保留原 graph 两排除；新增主线与本轮回归改变计数，不能硬套旧3450/11/1/7。
- [ ] 在已登记专属资源执行以下真实入口，逐命令记录退出码与收据：

```bash
make check-backend PYTHON_BIN="$PY"
make check-browser PYTHON_BIN="$PY"
make check-frontend-tsc
make check-frontend-build
```

- [ ] 前端额外执行项目完整Vitest与E2E类型检查；若复现默认并行资源超时，保留首轮失败且记录限制workers复跑，不改超时掩盖失败。
- [ ] backend不得有fail/error或零选中；browser/live/scanner显式gate还不得skip/xfail/xpass。读取收据、原始退出码与日志，不只信摘要。
- [ ] 真实provider仅使用另行明确授权配置，不隐式读私有profile；缺配置记NOT_REQUESTED/需授权，不称通过。真实scanner若执行，先确认固定端口无他人占用；不停止其他Agent资源。它们不属于普通backend/browser默认依赖。
- [ ] 对失败做根因与最小回归；不新增xfail、不忽略整个e2e目录、不弱化权限/来源/终态断言。

## Task 5: 复核、交接与资源收尾

**Files:** Modify local `PROGRESS.md`, `docs/architecture.md`, `docs/development/agent-main-semantic-integration.md`; create separate gate report.

- [ ] 独立规格与质量复核固定源码；静态语法/空白/冲突标记/迁移图与最终diff审查。
- [ ] 记录每层实际结果与未执行层、准确源码SHA及CI来源，不把历史通过数替代本轮结果。
- [ ] 收齐所有本轮后台job；停止监听并删除提醒。核验owner/ID/自有volume/零测试客户端后仅清理本轮容器卷和进程，不prune或停其他服务。
- [ ] 仅在本地集成分支提交经复核结果，核验工作树干净/main refs未变；保留工作树供后续开发。

## 后续架构顺序（不是跨阶段一次性实施授权）

CI接入与门禁完成后，依现行路线逐片：R4b剩余受控正文/附件交付与SDK/可信部署 → R5逐业务命令、版本幂等和操作账本/补偿 → R6替换正式D4/D5入口 → R7第二插件接续与逐模块推广。每片独立spec/plan/测试/复核；涉及真正未决的数据归属、外发类别、审批矩阵或补偿语义先确认。

旧D4候选审核/发布/7天清理提案已撤回，不复活旧候选表/路由或造第二条AI写路径；已完成D8正式结果集中审核不等于平台两阶段模型操作审核。只读检查点重开不等于业务回滚。模块化单体逻辑边界不等于整仓搬modules、中央数据中心或微服务化。

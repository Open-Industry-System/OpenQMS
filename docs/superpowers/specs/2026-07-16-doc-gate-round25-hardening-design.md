# CAPA 文档门禁 Round 25 加固设计

日期：2026-07-16

## 目标

关闭 Round 24 复审确认的五类缺口：已发布 Alembic revision 不会重跑、audit 与 waiver 之间的版本漂移、运行时与 preflight 的 waiver 校验漂移、preflight 缺少 C9 校验，以及 Make DAG 无法保证发布顺序。

## 约束

- 不修改已经发布的 `20260715_waiver_items` revision 行为来承担线上修复。
- 历史 waiver 无法用现有数据证明满足 Round 25 完整性时，一律 fail-closed 失效。
- waiver 只能豁免同一 audit batch 中完整列举的 CP `blocked_modify`；其他阻塞条件不可豁免。
- audit 之后文档发生任何版本变化，都必须重新 audit，不能在 waiver 时接受未审核的新版本。
- D8 gate 与部署 preflight 使用同一套严格 waiver 语义。

## 方案

### 1. 后继迁移

新增 `20260716_doc_gate_waiver_hardening`，父 revision 指向当前 head。迁移将所有历史 `waiver_reason IS NOT NULL` 的 decision 降级为 blocked，并清除 waiver 字段和 version snapshot，使 Round 21–24 的 generic、partial 或未严格验证 waiver 全部失效。迁移保留既有 `AuditLog` 历史，并为受影响 current analysis 写入明确的失效原因，供操作人员重新 audit/waive。

不回写或修改旧 revision 文件；测试从旧 head 建库并插入历史 structured waiver，再升级新 head，证明后继迁移真实执行。

### 2. 统一严格校验

在 doc-gate service 中提供共享 validator，输入 current analysis、latest decision、audit rows 和 live document versions，输出已验证 waiver key 集合。它必须验证：

- decision 为 latest passed structured waiver；
- 每个 item 结构完整，且 `audit_run_id` 与 decision 一致；
- audit batch 覆盖 analysis 的所有 affected document；
- 全部未覆盖项都属于 CP `modify/cp_item` 且被精确列入 waiver；
- audit `version_after.version_id/sha256` 与 live latest 完全一致；
- waiver 保存的 version ID/hash 与 audit/live latest 一致；
- target key 在该版本中仍不存在。

任何格式错误、缺行、额外或残余阻塞、版本漂移都抛错，不允许跳过未知 item。

### 3. 签发、运行门禁和 preflight

`record_gate_waiver` 在 analysis 锁内读取 latest decision、audit batch 和 live versions，调用共享 validator 的签发路径。audit version 与 live latest 不一致时拒绝签发并要求重新 audit。

`_d8_doc_gate_gate` 保留 C9 与 C8 校验，并对 structured waiver 调用严格读取校验；历史或损坏数据不能依靠空 snapshot/异常 JSON 放行。

preflight 对每个 current analysis 重算 C9。C9 mismatch、无效 waiver 或 stale version 都输出 blocking break；只有完整验证通过的精确 key 才能从 lineage break 中扣除。

### 4. 串行发布入口

提供单一 shell 脚本作为规范入口，使用 `set -euo pipefail` 串行执行：

1. 迁移目标数据库；
2. 代码检查；
3. 目标数据库 preflight；
4. 显式 rollout 命令。

Make target 只调用该脚本，不再用可被 `make -j` 并行调度的独立 prerequisites 表达顺序。rollout 命令必须显式提供，缺失则失败，避免只打印“可以发布”。

## 测试策略

按 TDD 增加以下回归：

1. 数据库已在旧 `waiver_items` revision 且含 Round 23 structured waiver时，升级新 head 后 waiver 被失效；
2. audit 后、waiver 前生成新版本，waiver 拒绝；
3. malformed item、audit run 不匹配、audit batch 缺行均使 D8 gate 与 preflight 阻断；
4. C9 stale analysis 即使含版本未漂移的 waiver，preflight 仍阻断；
5. 发布入口在并行 make 下仍保持严格顺序，缺少 rollout 命令时失败。

完成后运行 CAPA doc-gate 聚焦测试、迁移测试、完整后端测试、前端类型检查与构建，并确认 Alembic 单 head 和 `git diff --check`。

## 非目标

- 不改变 CP/FMEA diff 或 keypoint 语义。
- 不扩展可豁免文档类型。
- 不重构无关 CAPA 状态机或部署平台。

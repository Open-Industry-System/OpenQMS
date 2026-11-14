# R4b 主线集成实施计划

> 使用 subagent-driven-development 逐项实施与独立规格、质量复核；共享文件串行修改。

目标：从最新 origin/main 集成已验收 dcda1d55，提交独立分支并创建面向 main 的草稿 PR；不合并、不部署、不启用模型。

## 已核实基线与归属

- origin/main：`5b712d94ed08412a6c3d92e4dca2d9193b5959d3`；合并基点：`4a00636f2928d0a4d3ca2de56599ad1ae3b57fb6`。
- 输入：`dcda1d5590d083c6732bb3fad0d7b5d4156ba4f6`；原 R4b 工作树干净，保留不动。
- 新工作树：`/Users/sam/.codex/worktrees/0cd0/OpenQMS`；分支 `integration/r4b-main-20261114`，本会话独占。应用会话及 Git 分支清单未发现另一活跃集成执行者。主目录其他任务的改动保留。
- 实际冲突17项：Makefile、PROGRESS.md、tenant runner/tv006、模型注册、权限access/catalog/types、readonly_delivery/runtime_access/task_service、tenant_migrator/schema_diff、两迁移测试、CAPA投影测试、架构文档。

## 执行关口

- [x] 逐项解决权限/运行时冲突，审查自动合并及 main 权限修复，不整批选边。
- [x] 合并 public/tenant 迁移图；保留发布 revision，核对冻结快照及双分支 predecessor parity，补真实三路径与tenant迁移回归。
- [x] 合并模型注册、Make/CI、测试和文档，保留 PR #29 行为；完成独立规格与质量复核。
- [x] 新建本次独立 owner-bound PG15、专属卷、数字回环端点及私有登记；不复用 R4B-CLEANUP-01。先迁移、再冲突焦点测试。
- [x] 在候选提交上运行 make check、browser、pure、前端单测/E2E类型及相称附件授权/PR #29门禁；记录失败修复、skip与未运行项。
- [ ] 精确提交、普通push独立分支、创建draft PR、跟踪自动CI并修复集成失败；最终交接SHA、PR和明确合并判断。

资源清理：R4B-CLEANUP-01继续延期，全部旧资源保留。本次新测试资源另行登记与交接；不删除或修改其他容器/卷，不使用prune。

## 本地验收证据

冻结执行候选78b428d2，1575文件manifest前后相同。make check后端4973通过/4可选skip/19未选/6警告，SDK562+16+1，前端tsc/build；独立browser11无skip、pure321、Vitest822/95文件、E2E类型通过。三条public升级与tenant两旧head/空路径、27 guards真实通过。新资源采用同一独占实例内的qms_test满足main原固定库名守卫；初始库保留。资源残留与哨兵只读核验正常，详情见[交接](../../development/r4b-main-integration.md)。此快照为发布前记录，远端CI不能预写为通过。

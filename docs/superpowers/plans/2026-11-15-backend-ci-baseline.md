# PR 后端 CI 首轮优化实施计划

目标：优先消除PR重复push运行，保留测试集合、单一后端 job、浏览器门禁和退出语义，先建立可实测的准备/收集/执行基线。

- [x] 读取开工约定、关键决策、CI 分层约定；刷新 origin/main，固定 `d3c0ada8`，在独立 worktree 工作。
- [x] 核实PR #33重复事件、main保护/ruleset和runner；push限制main，保留PR/默认checkout/concurrency及native语义，事件矩阵先11失败后通过。
- [x] 读取近期成功 PR job 日志/步骤时间戳，区分 PR head 与实际 merge SHA；未知阶段标为未测得。
- [x] 核对 `prepare_database`、Make prerequisite 与手工检查：后者仅 Pydantic/SPC 计算，不依赖已迁移数据库；保留 Make 唯一准备和 runner 再校验。
- [x] 先运行计时失败测试，再在既有 `gate_results` 插件观察 collection/runtestloop 和 phase report；计时写入既有私有 hooks 和过滤日志，保持 receipt schema，最多20项、移除参数值，不改变退出状态。
- [x] 自动 workflow 删除前置重复准备；backend/browser setup-python 启用 pip 下载缓存，覆盖 requirements 和后端 SDK 构建配置/工作流内工具版本；安装命令不变。
- [x] 运行 pure 合约、工作流语法、实际成功/失败入口；创建本任务独占 PG15，从空库运行 `make check-backend`，保持既有排除与可选 skip。
- [x] 在 PROGRESS 与 CI 文档记录实测、环境限制、下一次 PR 指标及下一阶段建议；保留本地分支，不 push/merge。

执行采用当前会话逐项实施；用户本轮指令已给出范围和验收标准，不重复请求方案审批。不会创建新 PR 或触发远端运行。

最终证据：pure350通过，正常空库后端5269通过/4skip/19deselected，preflight/import通过，1073执行文件一致；专用PG/卷/凭据已清理，未提交/push/merge。详见PROGRESS及docs/development/backend-ci-timing.md。

后续授权：用户确认本批独立提交、push并开PR送审；原“不push”边界对应首轮本地验收。fixture优化另批，R6 Task1可并行但须核对实际合入基线。

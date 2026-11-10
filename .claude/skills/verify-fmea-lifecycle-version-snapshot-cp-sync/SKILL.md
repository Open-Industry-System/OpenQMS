---
name: verify-fmea-lifecycle-version-snapshot-cp-sync
description: Use when asked to verify / walk through / 验收 / 走查 OpenQMS 子故事 US-E2E-02.18（版本快照 + CP 联动；FMEAVersion.snapshot/major_no/minor_no/sha256_hash/change_type + PFMEA APPROVED 时 CP sync_pending 置位）end-to-end — e.g. "验收 02.18" / "走查 FMEA 版本快照 CP 联动" / "verify version-snapshot-cp-sync". Symptoms include needing to confirm 提交/审批各生成快照、CP sync 是 durable outbox（非直接两阶段调用）、幂等键 (fmea_id, fmea_version_id, cp.sync_pending_set)、CP 审计 changed_fields 仅 sync_pending + trigger_fmea_version_id。
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.18-version-snapshot-cp-sync.md
> 故事版本：定稿 v6（2026-11-03）
> 剧本版本：v6（2026-11-03）

# 版本快照与 CP 特性同步

## 使用与前置

用于验收 US-E2E-02.18。先核对上述故事版本／日期；不一致先同步再走查。先取得服务、独立库和测试数据授权。专用环境按 docs/e2e.md；不得未经授权执行共享 reset/seed。新 fixture 唯一命名并记录 IDs，审批使用不同的真实授权账号。AI_REQUIRED=false，本剧本不证明 AI、CSR、PPAP、scanner 或 live Neo4j 可用。

## 公共数据契约

- 功能仍用 Process*Function 与 HAS_FUNCTION／FUNCTION_MAPPED_TO。新字段是 characteristics[]：id（稳定 UUID）/kind/name/specification/unit/classification/reference/related_product_characteristic_ids。
- PFMEA kind 由唯一真实 HAS_FUNCTION 所属决定：ProcessStep=product；ProcessWorkElement=process，后者必须唯一属于同工序。DFMEA 的 System/Subsystem/Component 所属均 product，即使类型名是 ProcessWorkElementFunction。缺失／歧义复核，不猜测。
- 名称为空显示必填，不保存空白；改名保留 UUID。分类与 kind 独立，不按严重度或类别自动 CC/SC。新 CC/SC 在 characteristics[].classification；旧 Function.classification 只兼容参考。
- characteristics 缺失/null 显示历史参考提示，不自动转换；显式 [] 不回退旧字段。查看历史快照不修改集合、UUID 或源数据。

## 可复用特性专项走查

1. 以合法新草稿及已声明的结构／失效链 API 前置进入页面；确认 status=draft，guards 启用。打开向导功能分析，legacy 提示出现且 GET 不新增 characteristics。
2. PFMEA 同一工序：步骤功能 UI 录入 2 产品；工作要素功能 UI 录入 3 过程。使用 aria-label「特性名称」「规范／公差」「特殊分类」「关联产品特性」及按钮「新增产品特性」「新增过程特性」「确认特性」。模拟数值不是客户批准。
3. 保存草稿、刷新、重新进入功能分析；GET 核对两个集合与稳定 UUID。DFMEA 共享类型 UI 只有产品入口，保存刷新仍 kind=product。
4. 完成既有向导／审批流程；不能直接写 approved 或禁用 trigger 构造通过。查看版本快照时输入禁用、无新增入口，版本 hash verify 通过。

## 本故事补充：真实 CP 导入与同步

1. 合法提交／不同授权人批准，分别产生 submit／approve 快照；核对 major/minor、sha256_hash、created_by/at。hash verify 通过，历史只读。
2. PFMEA 批准事务写 CPSyncOutbox，键 (fmea_id,fmea_version_id,cp.sync_pending_set)；独立 cp_sync_worker 原子置 pending、每个实际翻转 CP 一条 UPDATE 审计并完成 outbox。重复消费幂等；DFMEA 不置 CP pending。审批事务不提前写 CP 审计。
3. CP「从 PFMEA 导入」明确选真正批准版本，点击预览，选择 5 项后确认；回读五个独立行（2 产品+3 过程，非笛卡尔积），来源只读。
4. 正常 PUT 设置手工评价／样本／频次／控制／反应字段。源合法返工改至少两特性，再提交批准；打开实际 sync-preview。用另一次合法 CP 更新使锁陈旧，确认必须实际 409，旧预览失效、没有自动应用。
5. 点击「重新生成预览」，只接受一项；核对 pending 与未接受项旧基线。再显式新预览、接受剩余；刷新核对行 UUID 不变、逐行 source_characteristic_ref.accepted_source_version_id 正确、手工执行字段保留。全覆盖才推进文档来源跟踪；真正 no-op 不重写逐行基线。
6. preview/confirm 必须携带 source_fmea_version_id、expected_lock_version、preview_digest、selected_candidate_keys；禁用受保护／冲突候选，删除默认不选。活动 CAPA、执行／SC 关联和 legacy 混合行保守保留，未解决仍 pending。已批准 CP 不因同步绕过编辑保护。

审计核对审批固定 2 条（fmea_documents/TRANSITION、fmea_versions/CREATE）；worker 每个 false→true CP 一条 control_plans/UPDATE，changed_fields 为 sync_pending+trigger_fmea_version_id，不虚称修改 source_fmea_version_id。

## 执行与结果模板

特性专项自动浏览器：`make e2e-run TEST_ARGS='--config=playwright.characteristic.config.ts e2e/specs/m1-core/characteristic-correction.spec.ts'`。独立配置不运行共享 global setup/reset，先确认已授权的本地服务、owned endpoint 和 bootstrap，并设置 CHARACTERISTIC_PYTHON 指向既有只读测试解释器；不得据该命令跳过环境审批。

记录：故事／剧本版本、API 前置与真实 UI 步骤分开、实际命令／退出码／passed/failed/skipped/xfail/xpass/warnings、截图路径与 LOOK 观察、审计／版本 IDs、清理及保留对象。每项写 PASS/FAIL/BLOCKED/NOT_RUN；专项通过不代表本故事全部历史能力重新验收。证据回填 docs/development/characteristic-correction-acceptance.md，不能以静态阅读或模拟成功替代浏览器。

## 维护

用户故事版本或日期改变，先核对实际源码与步骤，再同步本剧本版本／日期并运行相关验收。保留原有历史运行结论，新增结果只针对实际运行范围；不要把旧“待实现”或旧行号当现状。

## 2026-11-03 v6：单位恰好一次与晚到事件

- CP 标准列不变；specification_tolerance 从该对象的 specification＋unit 投影。明确单位恰好一次；原文本已带该单位不重复追加。specification 为 None/空白时，只有 unit 不成为有效控制准则；不做未授权的量值换算。新自动 SC spec_requirement 共用同一小格式化函数，submitted/approved 安全材料仍只提示复核，不能自动改写。
- 单独修改 unit 也必须出现在 import/sync/stale-check 的同源投影中，沿实际接受快照三方比较，保留明确清空；实际 CP API 与 UI 都回读单位，不仅检查 FMEA 输入。旧测试记录与不可变快照不批量修复或冒充手工覆盖。
- 独立 worker 采用 scope→CP parent 的既有有序互斥协议，等待后重读 CP。晚到事件若该 CP 已完整接受同一或更新的、hash/工厂/来源有效的批准基线，不再恢复 pending，也不重复审计；不能只凭文档 source_fmea_version_id 判断完成（部分首次导入也可能有它）。逐行实际接受快照、源身份及覆盖必须有效；未变行可保留旧接受版本。
- 真正更新/未处理/部分接受/未知基线仍保守提示 needs-update；worker 不清除已有 pending，不改源指针、项目或业务字段，仅真实 false→true 写 sync_pending＋trigger_fmea_version_id 审计，outbox 同事务完成。
- 验收必须同时覆盖 worker-first 和 late delivery：暂停且验证仅属本次实例的 worker，真实批准→新 CP 创建/UI 导入→释放后仍不 pending；保留真实部分待办，暂停 worker→合法源返工/单位修改/新批准→UI 完整同步→释放后仍不 pending。按确切版本查只读 outbox completed 是交付后的断言，不能是唯一避免应用顺序缺陷的前置条件。真实独立事务回归另覆盖旧事件在新基线后到达、部分/未知基线及实际锁等待后 fresh-row 重读。
- 新运行使用唯一 CHARACTERISTIC_RUN_TAG，manifest/evidence/PNG/test-results 独立路径；不得覆盖 404b462f 等先前证据。CHARACTERISTIC_WORKER_PID 需指向本次自己启动且命令/cwd 已核对的独立 CP worker；失败时恢复该 worker，不停其他服务。只读原测试解释器、owned endpoint、权限与业务保护要求不变。

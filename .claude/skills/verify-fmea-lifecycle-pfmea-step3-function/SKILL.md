---
name: verify-fmea-lifecycle-pfmea-step3-function
description: Use when asked to verify / walk through / 验收 / 走查 OpenQMS 子故事 US-E2E-02.3（PFMEA Step3 功能分析：为每个结构节点录入 ProcessItemFunction/ProcessStepFunction/ProcessWorkElementFunction + HAS_FUNCTION 边 + FUNCTION_MAPPED_TO 边 + 结构化 characteristics 与独立 CC/SC）end-to-end — e.g. "验收 02.3" / "走查 PFMEA Step3" / "verify pfmea-step3-function".
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.3-pfmea-step3-function.md
> 故事版本：定稿 v3（2026-11-03）
> 剧本版本：v3（2026-11-03）

# PFMEA Step3 功能与产品／过程特性

## 使用与前置

用于验收 US-E2E-02.3。先核对上述故事版本／日期；不一致先同步再走查。先取得服务、独立库和测试数据授权。专用环境按 docs/e2e.md；不得未经授权执行共享 reset/seed。新 fixture 唯一命名并记录 IDs，审批使用不同的真实授权账号。AI_REQUIRED=false，本剧本不证明 AI、CSR、PPAP、scanner 或 live Neo4j 可用。

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

## 本故事补充

逐一核对每个分析范围结构节点 HAS_FUNCTION；FUNCTION_MAPPED_TO 连上下层功能而非结构。ProcessItemFunction 是过程项功能，不新增本次结构化特性。步骤产品与工作要素过程各有多项，过程关联只允许同工序产品。功能描述不等于特性名称。保存后 graph_data 与 UPDATE 审计存在；Step4 仍遵守既有门禁。

## 执行与结果模板

特性专项自动浏览器：`make e2e-run TEST_ARGS='--config=playwright.characteristic.config.ts e2e/specs/m1-core/characteristic-correction.spec.ts'`。独立配置不运行共享 global setup/reset，先确认已授权的本地服务、owned endpoint 和 bootstrap，并设置 CHARACTERISTIC_PYTHON 指向既有只读测试解释器；不得据该命令跳过环境审批。

记录：故事／剧本版本、API 前置与真实 UI 步骤分开、实际命令／退出码／passed/failed/skipped/xfail/xpass/warnings、截图路径与 LOOK 观察、审计／版本 IDs、清理及保留对象。每项写 PASS/FAIL/BLOCKED/NOT_RUN；专项通过不代表本故事全部历史能力重新验收。证据回填 docs/development/characteristic-correction-acceptance.md，不能以静态阅读或模拟成功替代浏览器。

## 维护

用户故事版本或日期改变，先核对实际源码与步骤，再同步本剧本版本／日期并运行相关验收。保留原有历史运行结论，新增结果只针对实际运行范围；不要把旧“待实现”或旧行号当现状。

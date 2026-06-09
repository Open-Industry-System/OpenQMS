# 质量趋势 AI 解读 Widget 设计

**日期**: 2026-06-09  
**状态**: 已批准，待实施计划  
**模块**: Phase 4 高级分析 + AI 解读  
**入口**: 自定义仪表盘 Widget

---

## 目标

实现一个仪表盘 Widget：**质量趋势 AI 解读**。它面向管理者和质量工程师，在现有 dashboard 中解释最近质量趋势，回答三个问题：

1. 质量趋势是变好还是变差？
2. 哪些证据支持这个判断？
3. 下一步应该优先处理什么？

首版采用“规则摘要 + 手动 AI 深度解读”模式：Widget 默认快速展示规则摘要；用户点击按钮后才调用 LLM 生成深度解读。这样保证首屏加载快、成本可控，并且在未配置 LLM 时仍可用。

---

## 范围

### 包含

- 新增 dashboard widget 类型：`quality_trend_ai_summary`
- 聚合核心质量闭环数据：
  - SPC 异常趋势、未确认告警、低 Cpk/Ppk 特性
  - CAPA/8D 打开、超期、关键阶段积压
  - FMEA 高 RPN / 高 AP 风险项变化
- 默认展示规则摘要：风险等级、结论、证据、建议动作
- 手动触发 AI 深度解读
- 产品线过滤沿用当前 dashboard 选择器
- LLM 不可用时保留规则摘要
- AI 调用审计日志

### 不包含

- 不开发 PLM/ERP 相关能力
- 不新增独立趋势分析页面
- 不自动修改 SPC/CAPA/FMEA 数据
- 不自动创建 CAPA、不确认 SPC 告警、不优化 FMEA
- 不做跨租户、多工厂集团汇总
- 不在 dashboard 加载时自动调用 LLM
- 首版不聚合客诉/RMA；外部质量趋势可作为下一版扩展

---

## 用户体验

Widget 使用紧凑决策卡片布局。

默认状态显示：

- 时间窗口：默认近 30 天
- 当前产品线：使用 dashboard 的产品线过滤
- 风险等级：`low | medium | high | insufficient_data`
- 一句话结论
- 3-5 条关键证据
- 2-3 条建议动作
- “AI 深度解读”按钮

点击“AI 深度解读”后：

- 按钮显示 loading
- 成功后在 Widget 下半部分展示 AI 解读
- 失败时显示“AI 解读暂不可用，请稍后重试”，规则摘要保持可见
- 切换产品线或刷新仪表盘后重新加载规则摘要，AI 解读按缓存命中情况展示或重新触发

---

## 架构

### 后端

新增 `backend/app/services/quality_trend_service.py`，职责：

- 聚合 SPC/CAPA/FMEA 指标
- 生成规则摘要
- 计算证据 hash
- 构造 AI prompt
- 调用 `request.app.state.llm_provider`
- 校验 AI 结构化输出
- 写入 AI 调用审计日志

Dashboard API 增加按需端点：

- `GET /api/dashboard/widgets`：当请求包含 `quality_trend_ai_summary` 时返回规则摘要数据
- `POST /api/dashboard/widgets/quality-trend/interpret`：手动触发 AI 深度解读

`GET /api/dashboard/widgets` 当前返回 `DashboardWidgetsResponse`，实施时必须新增 `quality_trend` 字段，payload 命名为：`quality_trend: { summary: QualityTrendSummary }`。不要直接返回未声明的顶层 key，避免 Pydantic 响应模型丢弃数据。`get_widgets_data` 需要识别 `quality_trend_ai_summary`，并把结果写入 `result["quality_trend"]`。

该 widget 的布局可见权限映射到 `dashboard`，因为它显示在仪表盘中；但数据聚合不能只依赖 dashboard 权限。实施时必须按 evidence 来源做模块级过滤：

- 用户有 `spc` view 权限时，才纳入 SPC 证据
- 用户有 `capa` view 权限时，才纳入 CAPA/8D 证据
- 用户有 `fmea` view 权限时，才纳入 FMEA 证据
- 用户缺少某模块权限时，省略该类 evidence，并在规则摘要 metadata 中记录 `omitted_modules`
- 如果三类模块权限都缺失，Widget 返回 `insufficient_data`，不调用 AI

因此 `WIDGET_MODULE_MAP["quality_trend_ai_summary"] = "dashboard"` 只用于布局保存和 Widget 可见性校验，不代表自动获得 SPC/CAPA/FMEA 数据访问权。

`POST` 端点复用同一套聚合逻辑，确保规则摘要和 AI prompt 基于同一份证据。

### 前端

新增 Widget 组件：

- `frontend/src/components/dashboard/widgets/QualityTrendAIWidget.tsx`

修改现有 dashboard widget 体系：

- 后端：`WIDGET_MODULE_MAP` 新增 `quality_trend_ai_summary -> dashboard`
- 后端：`WIDGET_MIN_SIZES` 新增默认尺寸和最小尺寸
- 后端：`DashboardWidgetsResponse` 新增 `quality_trend: dict = Field(default_factory=dict)`
- 后端：`get_widgets_data` 增加 `needs_quality_trend = "quality_trend_ai_summary" in types`
- 前端：`DashboardWidgetsData` 新增 `quality_trend?: { summary?: QualityTrendSummary }`
- 前端：`createEmptyData()` 初始化 `quality_trend: {}`
- 前端：Widget 类型定义新增 `quality_trend_ai_summary`
- 前端：Widget registry 注册新组件
- 前端：Widget library 新增 `ai` 分类；`WidgetCategory` union 扩展为包含 `"ai"`，`categoryLabels` 增加 `ai: "AI/高级分析"`，默认展开项包含该分类
- 前端：dashboard API client 增加 `interpretQualityTrend()`

---

## 数据模型

首版不新增数据库业务表。规则摘要实时聚合。AI 结果优先使用 Redis 短期缓存；如果 Redis 未配置，可退回进程内缓存，但实施文档必须明确单机多进程或多节点部署会产生重复 LLM 调用风险。

AI 缓存 key 不包含 `user_id`，但必须包含规范化数据范围。权限和产品线访问在接口层校验；相同授权范围、时间窗口、证据 hash 的用户应复用同一份 AI 解读，以提高缓存命中率。

缓存 key 形如：`quality_trend:interpret:{scope_hash}:{window_days}:{evidence_hash}`。

`scope_hash` 计算规则：

- 用户显式选择单一产品线时，scope 描述为该产品线 code
- 用户未选择产品线时，scope 描述为后端实际用于过滤的 `filter_codes` 排序列表
- 对 scope 描述计算 SHA-256，避免 key 过长
- Prompt 中也必须包含相同 scope 描述，例如 `产品线范围：DC-DC-100` 或 `产品线范围：用户可访问产品线集合（N 条）`

缓存策略：

- 成功 AI 解读缓存 TTL：30 分钟
- LLM 未配置、结构化解析失败、上游 4xx/5xx 错误不缓存
- 并发点击同一 key 时，后端应尽量合并同 key in-flight 请求；如果首版不实现合并，至少通过前端 loading 禁用和后端限流降低重复调用
- 进程重启后内存缓存丢失；Redis 缓存不受单进程重启影响

### `GET /api/dashboard/widgets` 响应片段

```json
{
  "quality_trend": {
    "summary": {
      "risk_level": "medium",
      "headline": "过程稳定性下降，需关注高风险特性",
      "evidence": [
        {
          "id": "spc_alarm_count",
          "label": "SPC 异常告警",
          "value": 8,
          "trend": "+3 vs previous window",
          "severity": "warning"
        }
      ],
      "actions": [
        {
          "priority": "high",
          "text": "优先复核未确认 SPC 异常并关联 FMEA 高风险项"
        }
      ],
      "data_window_days": 30,
      "generated_at": "2026-06-09T00:00:00Z",
      "evidence_hash": "sha256:7f4a9d6c2b1e8a03",
      "ai_available": true,
      "metadata": {
        "omitted_modules": [],
        "available_modules": ["spc", "capa", "fmea"],
        "scope_description": "产品线范围：DC-DC-100",
        "selected_product_line": "DC-DC-100"
      }
    }
  }
}
```

### `POST /api/dashboard/widgets/quality-trend/interpret` 响应

```json
{
  "summary": "最近 30 天质量风险呈上升趋势，主要由 SPC 异常集中和 CAPA 关闭延迟驱动。",
  "possible_causes": ["关键过程波动增加", "纠正措施闭环滞后"],
  "impact_scope": ["DC-DC-100 产品线", "高 RPN 相关特性"],
  "recommended_actions": [
    {
      "priority": "high",
      "action": "复核未确认 SPC 告警并创建必要的 CAPA",
      "reason": "异常点集中在最近 7 天"
    }
  ],
  "evidence_refs": ["spc_alarm_count", "high_rpn_count"],
  "confidence": "medium",
  "model": "configured-provider-model",
  "evidence_hash": "sha256:7f4a9d6c2b1e8a03",
  "scope_hash": "sha256:91b7c12d8e4f6a20",
  "generated_at": "2026-06-09T00:00:00Z",
  "cached": false
}
```

---

## 指标口径

首版必须基于现有数据结构可落地，不依赖尚不存在的版本快照或外部系统数据。

### 时间窗口

- 当前窗口：`now - 30 days <= event_time < now`
- 上一窗口：`now - 60 days <= event_time < now - 30 days`
- `event_time` 按模块选择：
  - SPC：`spc_alarms.triggered_at`
  - CAPA/8D：创建/更新时间字段按现有模型可用字段选择；超期按目标日期字段存在时计算，否则首版只统计打开和状态积压
  - FMEA：`fmea_documents.updated_at` 用于“近期风险文档变化”，节点级变化不做历史对比

### 数据不足阈值

对整个有效 scope 聚合后判断数据不足。用户未选择产品线时，scope 是后端实际授权过滤后的产品线集合；集合内某个单产品线无数据只作为 metadata 或 evidence 标注，不直接否决整个聚合结果。

满足以下情况时，返回 `insufficient_data` 或降低置信度：

- SPC 当前窗口告警数和样本批次数均为 0
- CAPA/FMEA 当前窗口无打开项且上一窗口也无对比项
- 可用证据少于 2 类模块

### SPC 指标

- 异常趋势：当前窗口 `SPCAlarm` 数量与上一窗口数量比较
- 未确认告警：`SPCAlarm.status = "open"` 且 `acknowledged_at IS NULL`
- 低 Cpk/Ppk：当前 dashboard 的 `spc.capability_summary.cpk_avg` 仍为 `None`，因此首版不把 Cpk/Ppk 作为硬性风险证据；如实施中可复用已有 SPC 能力计算函数，则只统计最近窗口内低于阈值的特性，否则显示为 `not_available`

### CAPA/8D 指标

- 打开数量：状态不属于关闭/归档集合的 CAPA
- 超期数量：仅在模型存在目标关闭日期或计划日期字段时计算；字段不可用时不伪造超期数据
- 阶段积压：统计 D4/D5/D7 等关键阶段状态下的打开项数量

### FMEA 指标

- 高 RPN：通过现有 FMEA graph utility 生成 RPN 行，以 `severity * occurrence * detection` 或已有 row RPN 字段计算
- 高 AP：首版只能在节点字段中已存在 AP/action priority 时读取；如果当前 graph utility 未返回 AP，则不把高 AP 作为必选证据，只在后续实施中补充明确计算函数后启用
- 变化口径：首版按 FMEA 文档 `updated_at` 和当前图中的高 RPN 数量判断“近期风险文档变化”，不声称支持节点级历史变化

### Evidence Hash

`evidence_hash` 基于所有展示给用户或传给 LLM 的派生证据字段计算，而不是只基于当前窗口原始值。输入包括：scope 描述、available_modules、omitted_modules、window_days、当前窗口值、上一窗口值或 delta、trend、severity、evidence id、label、actions。规范化时按 evidence id 排序，并对 module 列表排序，确保同一证据产生稳定 hash。

---

## 规则摘要逻辑

风险等级按证据累积分判定：

- `high`：存在明显质量恶化信号，例如 SPC 异常显著增加且 CAPA 超期或高 RPN 风险同时存在
- `medium`：存在单一或轻度复合风险信号，例如异常告警增加、部分 CAPA 超期、高风险 FMEA 项未优化
- `low`：数据充足且未出现明显恶化信号
- `insufficient_data`：SPC/CAPA/FMEA 数据不足以判断趋势

规则摘要必须可解释：每个结论都要对应 `evidence` 中的至少一个数据点。

---

## LLM 设计

现有 `LLMProvider` 支持 Claude/OpenAI/local。首版复用该抽象，不新建 provider 体系。

质量趋势模块不硬编码模型 ID。实施时使用项目现有 `create_llm_provider()` 和 `settings.LLM_MODEL` 配置；如果未配置 LLM provider，则进入规则摘要模式并返回 `ai_available = false`。如需要调整 Claude 默认模型，应作为 `llm_provider.py` 的独立配置修正处理，而不是由该 Widget 在业务代码中覆盖。

AI prompt 只包含：

- 聚合后的指标
- 证据 ID、标签、数值、趋势
- scope 描述和可选的已选产品线 code
- 时间窗口
- `available_modules` 和 `omitted_modules`，防止 LLM 把“无权限省略”误解为“无风险”

AI prompt 不包含：

- 用户 token 或权限信息
- 原始附件内容
- 大段自由文本
- 用户不可访问产品线的数据

AI 输出必须是结构化 JSON。后端对字段存在性和枚举值做校验；校验失败视为 AI 调用失败，前端保留规则摘要并显示可重试状态。

当前 `LLMProvider.complete(prompt, response_schema)` 接口虽接收 `response_schema`，但现有 Claude 实现依赖模型输出文本再 `json.loads`。实施时必须加强解析稳健性：优先让 provider 按 schema 约束输出；如果 provider 返回被 Markdown 代码块包裹的 JSON，服务层需要清洗代码块并截取首个 JSON object 后再校验。清洗失败不得影响规则摘要。

---

## 权限与安全

- 规则摘要读取需要 `dashboard` 查看权限
- AI 解读触发也需要 `dashboard` 查看权限，因为不修改业务数据
- 产品线访问控制必须在聚合前执行
- AI 解读只作为建议，不自动执行任何业务动作
- LLM 调用失败不影响 dashboard 其它 Widget
- 所有 AI 调用写入 `AuditLog`

`AuditLog.table_name` 和 `AuditLog.record_id` 均非空。质量趋势解读没有单一业务记录，因此审计写入使用：

- `table_name`: `quality_trends`
- `record_id`: 每次 AI 解读调用生成的 `uuid.uuid4()`，作为该次聚合解读事件 ID
- `action`: `AI_TREND_INTERPRET`
- 业务上下文放入 `new_values`
- `changed_fields` 只记录 `{"event_type": "ai_trend_interpret"}`，方便未来筛选
- `old_values`: `None`

AI 调用审计不应出现在 dashboard “最近操作”列表中。实施时 `get_recent_actions` 需要过滤 `table_name = "quality_trends"` 或 `action = "AI_TREND_INTERPRET"`，避免用户看到无业务单据编号的内部 AI 调用记录。

审计日志 `new_values` 字段：

- `action`: `AI_TREND_INTERPRET`
- `product_line_scope`
- `selected_product_line`
- `scope_hash`
- `data_window_days`
- `success`
- `duration_ms`
- `model`
- `evidence_hash`
- `error`

---

## 错误处理

### LLM 未配置

- 规则摘要正常返回
- `ai_available = false`
- 前端禁用或提示配置缺失
- 如果用户仍调用 `POST /interpret`，后端返回 `503 Service Unavailable`

### LLM 调用失败

- 上游 LLM 请求失败返回 `502 Bad Gateway`
- 结构化输出解析或校验失败返回 `502 Bad Gateway`
- 限流返回 `429 Too Many Requests`
- 数据不足时前端禁用按钮；若仍调用 POST，返回 `422 Unprocessable Entity`
- 前端显示“AI 解读暂不可用，请稍后重试”
- 规则摘要保持可见
- 写入失败审计

### 限流与并发点击

- 前端在 AI 请求进行中禁用“AI 深度解读”按钮
- 后端按用户做短窗口限流，首版目标为每用户每分钟 3-5 次
- 如果同一 `scope_hash + window_days + evidence_hash` 已有缓存结果，直接返回缓存，不计入 LLM 调用

### AI 解读过期

- AI 结果必须携带生成时使用的 `evidence_hash`
- 前端当前规则摘要的 `evidence_hash` 与已展示 AI 结果不一致时，清空或弱化旧解读
- 过期提示文案：`数据已更新，点击重新生成 AI 解读`

### 数据不足

- 返回 `risk_level = insufficient_data`
- 显示“数据不足以判断趋势”
- AI 按钮禁用或提示需要更多数据

---

## 测试计划

### 后端

- 聚合服务：SPC 异常 + 高 RPN + CAPA 超期时风险等级升高
- 聚合服务：无数据时返回 `insufficient_data`
- 聚合服务：产品线过滤只统计可访问产品线
- 聚合服务：缺少 spc/capa/fmea 模块权限时省略对应 evidence，并记录 `omitted_modules`
- 聚合服务：三类模块权限都缺失时返回 `insufficient_data` 且不允许 AI 调用
- 聚合服务：Cpk/Ppk 不可用时不产生虚假的低能力证据
- 聚合服务：AP 字段不存在时不产生虚假的高 AP 证据
- AI 解读：fake `LLMProvider` 返回结构化 JSON 时成功
- AI 解读：LLM 抛错时返回可处理错误，规则摘要仍可用
- AI 解读：缓存 key 包含 `scope_hash + data_window_days + evidence_hash`，不包含 `user_id`
- AI 解读：未选择产品线时，两个不同授权产品线集合产生不同 `scope_hash`
- AI 解读：上一窗口值或 delta 变化时，`evidence_hash` 必须变化
- AI 解读：available/omitted modules 变化时，`evidence_hash` 必须变化
- AI 解读：成功结果缓存 30 分钟，失败结果不缓存
- AI 解读：限流阻止同一用户短时间重复触发 LLM
- API：`DashboardWidgetsResponse` 包含 `quality_trend.summary`，不会丢弃新 payload
- API：`WIDGET_MODULE_MAP`、`WIDGET_MIN_SIZES` 支持 `quality_trend_ai_summary`
- API：AI 调用审计写入 `table_name="quality_trends"`、随机 `record_id`、上下文在 `new_values`
- API：recent actions 不展示 `AI_TREND_INTERPRET`
- API：未登录返回 401
- API：无 dashboard 权限返回 403
- API：LLM 未配置时 POST 返回 503
- API：结构化输出失败返回 502
- API：数据不足 POST 返回 422
- API：viewer 可查看规则摘要并触发 AI 解读

### 前端

- Widget 出现在 WidgetLibraryPanel 的 `ai` 分类下
- `categoryLabels` 和默认展开项支持 `ai` 分类
- 加入看板后展示规则摘要
- 点击 AI 深度解读显示 loading 和成功结果
- AI 失败时显示错误提示，不影响其它 Widget
- 切换产品线后刷新规则摘要
- 当前规则摘要 `evidence_hash` 变化时，旧 AI 解读显示过期提示并要求重新生成
- AI POST 响应携带 `evidence_hash`、`scope_hash`、`generated_at`、`cached`，前端据此判断 stale 状态

---

## 验收标准

- Dashboard 首屏不等待 LLM
- 未配置 LLM 时 Widget 仍展示规则摘要
- AI 只在用户点击后调用
- 规则摘要和 AI 解读引用同一份证据
- 产品线过滤和 dashboard 权限生效
- 缺少 SPC/CAPA/FMEA 模块 view 权限时，对应 evidence 不出现在规则摘要、prompt、AI 解读输入中
- AI 调用写入审计日志
- Widget 能清楚回答趋势、证据、下一步动作

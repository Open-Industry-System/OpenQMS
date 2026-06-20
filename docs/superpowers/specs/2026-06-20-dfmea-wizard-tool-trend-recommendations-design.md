# DFMEA 向导 5T「工具 / 趋势」推荐设计

- 日期：2026-06-20
- 分支：`fix/fmea-fixes`
- 状态：已与用户确认设计，待出实现计划

## 1. 背景与目标

DFMEA 生成向导（`DFMEAWizardPage.tsx`，路由 `/fmea/wizard/:id`）的 Step 0 是 AIAG-VDA **5T 范围定义**，含 5 个字段：团队 / 时间范围 / 工具 / 任务 / 趋势。其中「工具」与「趋势」目前是**纯文本输入框**，用户无从下手、容易写空或写得不规范。

目标：给「工具」「趋势」两个字段增加**推荐选项**——既要开箱即用的常用预设（让用户「搞几个选项去选」），又能在预设不够时按当前产品线/任务做 AI 建议。

## 2. 现状

- `DFMEAWizardPage.tsx` 的 `renderStep0()`（约 165–196 行）：team / tool / task / trend 为 `<Input>`，timeframe 为 antd `DatePicker.RangePicker`。
- `WizardScope` 类型中 `tool` / `trend` 均为 `string`。
- 已有推荐能力：`SmartSuggestionDropdown` 组件 + 后端 `RecommendationService`（`POST /fmea/{fmea_id}/recommend`，前端 `getRecommendations`），支持 trigger 类型 `failure_mode / failure_effect / failure_cause / measure / optimization`，走「规则→图谱相似→LLM 增强」三段式并带缓存。
- 孤儿组件 `GenerationWizard.tsx`（弹窗版向导）**无任何 import**，已被 `DFMEAWizardPage` 取代，本设计**不修改**它。

## 3. 决策汇总（已与用户确认）

| 决策 | 选择 |
|---|---|
| 推荐机制 | **混合**：预设快选 chip + 可选 ✨AI 推荐按钮 |
| 单选/多选 | **多选**；存为「、」分隔 string（向后兼容） |
| 输入控件 | antd `Select mode="tags"`（已选项显示为控件内 tag）+ 下方预设 chip toggle + ✨AI 按钮 |
| AI 建议落地方式 | **点击才加入**（不自动填，符合「推荐→用户选」） |
| 后端 | 仅新增 trigger 类型 + prompt 模板，**不新建 API 端点** |

## 4. 数据模型（向后兼容）

`tool` / `trend` 在 `WizardScope` 中**保持 `string`**。多个值用「、」(顿号) 拼接存盘：

```
存盘:  "边界图、P图、接口矩阵"
内存:  ["边界图", "P图", "接口矩阵"]   ← Select tags 用
```

新增工具 `frontend/src/utils/wizardScopeTokens.ts`（与 `wizardTimeframe.ts` 同级、同样自包含可测）：

- `parseScopeTokens(s: string): string[]` —— 按 `/[、,;，；]/` 切分、`trim`、去空串。兼容历史逗号分隔值。
- `stringifyScopeTokens(arr: string[]): string` —— `join("、")`，空数组 → `""`。

旧的单个自由文本值（如 `"FMEA模板"`）→ `parseScopeTokens` 返回单元素数组 → 渲染为一个 tag。**不破坏存量数据**。

## 5. 前端：新复用组件 `ScopeTagField`

文件：`frontend/src/components/dfmea/ScopeTagField.tsx`

封装「工具」「趋势」完全相同的交互：

```
工具  ┌──────────────────────────────┐
      │ 边界图 ×   P图 ×              │   ← antd Select mode="tags"
      └──────────────────────────────┘      (可手输自定义 tag)
  快选：[接口矩阵] [FTA] [功能分析]          ← 未选中预设，点击 toggle 进/出 Select
  [✨ AI推荐]  →  紫色 AI 建议 chip：⭐参数图  ⭐设计评审   (点击才加入)
```

Props：

```ts
interface ScopeTagFieldProps {
  value: string;                       // wizardScope.tool / .trend（「、」分隔）
  onChange: (v: string) => void;       // 回写「、」分隔 string
  presets: string[];                   // 预设清单（从 i18n 取）
  triggerType: "dfmea_tool" | "dfmea_trend";
  fmeaId: string;
  context: Record<string, unknown>;    // { fmea_title, product_line_code, task, team }
}
```

行为：

- `Select` 受控值 = `parseScopeTokens(value)`；其 `onChange` → `stringifyScopeTokens(next)` → 调 `onChange`。`mode="tags"` 自带「输入回车即新增 tag」。
- 预设 chip：点击 → 在 Select 值数组里 add/remove 该 token（toggle）。已选中项不出现在「快选」行（避免重复）。
- ✨AI 按钮：点击调 `getRecommendations(fmeaId, { trigger_type: triggerType, context, scope: "current_product_line", include_graph: false })`。结果渲染成紫色 `⭐xx` chip，**点击才加入** Select（不自动填）。按钮 loading 时转圈；无结果 / 失败时 `message.warning` 提示，不阻塞。

接入点：`DFMEAWizardPage.tsx` 的 `renderStep0()` 把「工具」「趋势」两处 `<Input>` 换成 `<ScopeTagField>`，传 `presets={t("wizard.scope.toolPresets", { returnObjects: true })}`、`context={{ fmea_title: fmea?.title, product_line_code: fmea.product_line_code, task: wizardScope.task, team: wizardScope.team }}`。team / timeframe / task **不动**。

## 6. 预设清单（领域内容）

存于 i18n（`zh-CN/dfmea.json` + `en-US/dfmea.json`）的数组 `wizard.scope.toolPresets` / `wizard.scope.trendPresets`，每条双语。存盘值 = 所选语言文本（与现有 team/task 行为一致）。

**工具（DFMEA 分析方法）：**

| zh-CN | en-US |
|---|---|
| 边界图 | Boundary Diagram |
| P图/参数图 | Parameter Diagram (P-Diagram) |
| 接口矩阵 | Interface Matrix |
| 功能分析 | Function Analysis |
| 故障树分析 | Fault Tree Analysis (FTA) |
| DFMEA模板 | DFMEA Template |
| 历史经验教训库 | Lessons Learned Library |

**趋势（趋势数据/信息源）：**

| zh-CN | en-US |
|---|---|
| 历史FMEA | Historical FMEA |
| 售后/现场故障数据 | Field/Warranty Data |
| 客户投诉 | Customer Complaints |
| CAPA记录 | CAPA Records |
| 召回/法规数据 | Recall/Regulatory Data |
| 审核发现 | Audit Findings |
| 设计变更历史 | Design Change History |

## 7. 后端改动（最小）

仅两处，**不加新 API 端点**（复用 `POST /fmea/{fmea_id}/recommend` → `RecommendationService.recommend`）：

1. **`backend/app/schemas/recommendation.py`** —— `RecommendRequest.trigger_type` 的 `Literal` 增加 `"dfmea_tool"`、`"dfmea_trend"`。
2. **`backend/app/services/recommendation_service.py`** —— `PROMPT_TEMPLATES` 新增两模板，占位符 `{fmea_title}` / `{product_line_code}` / `{task}` / `{team}` / `{historical_patterns}`，指示 LLM 返回**中文**建议项（与 zh-UI 一致），沿用现有 `SuggestionList` 校验输出。

**图谱相似自然失效（无害）**：`_query_graph_similarity` 对非 `failure_mode` 取 `context.get("failure_mode") or ""`，这两 trigger 无该键 → query_text 空 → 立即返回 `[]`。前端 `include_graph:false` 进一步省掉该跳。

**规则引擎**对新 trigger 无规则 → 空返回，不报错。

**缓存**按 `(fmea_id, trigger_type, context_hash)` 自动生效。

## 8. i18n

`zh-CN/dfmea.json` 与 `en-US/dfmea.json` 的 `wizard.scope` 下新增：

- `toolPresets: [...]` / `trendPresets: [...]`（数组）
- `aiRecommend: "✨ AI推荐"` / `aiRecommendLoading: "推荐中…"`
- `aiRecommendEmpty: "暂无 AI 建议"` / `aiRecommendFailed: "AI 推荐失败，请稍后重试"`

## 9. 测试

- **前端**
  - `utils/wizardScopeTokens.test.ts`：「、/,/;」切分、空值、trim、单值。
  - `components/dfmea/ScopeTagField.test.tsx`：预设 chip toggle 进/出 Select；AI 按钮点击 mock `getRecommendations` → 出现紫色建议 chip → 点击加入；loading / 失败态。
- **后端**
  - 扩展现有推荐测试：`dfmea_tool` trigger 在 mock LLM 下返回建议；无 LLM 时优雅降级（空 / `rule_fallback`）。
- **回归**：`npm test -- --run`（前端）、`pytest tests/ -x`（后端）。

## 10. 范围边界（不改动）

- 孤儿组件 `GenerationWizard.tsx`（已被取代、无 import）。
- team / timeframe / task 三个字段。
- 5T 字段存盘结构（仍是 wizardScope 内 string）。
- 推荐端点与 `SmartSuggestionDropdown` 本身。

## 11. 风险与权衡

- **存盘值随语言**：切换 zh/en 后旧 tag 文本不匹配预设。与现有 team/task/trend 自由文本行为一致，可接受；不引入语言中立 key（YAGNI）。
- **AI 不可用降级**：LLM 未配置或超时 → 现有三段式返回空/`rule_fallback`，前端 `message` 提示，预设快选仍可用。
- **顿号分隔的边界**：理论上某 tag 文本含「、」会被误切。预设清单均不含「、」，自定义手输含「、」属极端情况，不额外处理。

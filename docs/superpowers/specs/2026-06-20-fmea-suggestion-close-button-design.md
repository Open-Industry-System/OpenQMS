# FMEA 智能推荐下拉框 × 关闭按钮

**日期**: 2026-06-20
**范围**: `frontend/src/components/dfmea/SmartSuggestionDropdown.tsx` + i18n + 测试

## 背景

FMEA 编辑器里每一个可推荐的单元格（失效模式 / 失效后果 / 失效原因 / 措施 / 优化 / 建议措施）都渲染成一个 `SmartSuggestionDropdown`：一个带灯泡图标的 `Input`，输入 ≥2 字符后防抖 500ms 调 `/api` 取建议并打开下拉面板。

当前面板只能通过三种方式关闭：按 `Esc` 键、点输入框外（blur 后 200ms）、选中某条建议。**没有任何可见的关闭按钮**。用户希望有一个显性的 × 关闭按钮。

## 目标

在下拉面板上加一个可见的 × 关闭按钮，点击即收起面板。行为与现有 `Esc`/blur 一致，只是提供可见入口。

## 非目标

- 不做「禁用推荐功能」的开关（用户明确不要）。
- 不改其它推荐入口（向导里的推荐、`InlineRecommendations` 卡片——后者目前未被引用）。
- 不动输入框、防抖、范围单选、建议条目点击等现有逻辑。

## 设计

### 组件改动 — `SmartSuggestionDropdown.tsx`

1. 调整 antd import 行（当前为 `Input, Dropdown, Tag, Spin, Alert, Typography, Radio`）：
   - **新增** `Button`（关闭按钮用）。
   - **移除** `Alert` —— 当前 `Alert` 被引入但组件内从未使用，已产生 lint warning，借此一并清掉，避免继续增加 lint 噪声。
   - 从 `@ant-design/icons` 引入 `CloseOutlined`。

2. 在 `dropdownContent` 最前面加一个**独立的 header/action 行**（而非用绝对定位浮在内容之上），彻底避免与 scope 单选行、confidence Tag、banner 文本重叠：

```tsx
<div
  style={{
    display: "flex",
    justifyContent: "flex-end",
    padding: "2px 4px",
    borderBottom: "1px solid var(--qf-border)",
  }}
>
  <Button
    type="text"
    size="small"
    icon={<CloseOutlined />}
    onMouseDown={(e) => e.preventDefault()}
    onClick={(e) => { e.stopPropagation(); setOpen(false); }}
    aria-label={t("smartSuggestion.close")}
    title={t("smartSuggestion.close")}
  />
</div>
```

   - 关闭按钮独占一行，右对齐，下方留一条分割线；其后的 error / fallback / llm / scope / suggestions 依次排列，不会与按钮重叠。
   - `onMouseDown={(e) => e.preventDefault()}` 阻止点击按钮时先触发输入框 `onBlur` 的 200ms 延迟关闭路径，让「点击关闭」成为一个干净、即时的独立显式动作（不依赖 blur race）。
   - `onClick` 里 `stopPropagation` + `setOpen(false)`。
   - 不需要给原 banner / scope 行 / suggestion item 预留右侧 padding——header 行方案已规避遮挡。

   > 备选（不采用）：绝对定位 `top:4 right:4` 浮在内容之上。需要给每一段预留右侧空间，且当 scope 行文案变长（如「仅当前产品线」+ 权限提示）或 suggestion 右侧 confidence Tag 较宽时仍可能遮挡。header 行更稳，故选之。

### i18n

`src/locales/zh-CN/dfmea.json` 和 `src/locales/en-US/dfmea.json` 的 `smartSuggestion` 节点下新增：

- zh-CN: `"close": "关闭"`
- en-US: `"close": "Close"`

### 交互

- 点击 × → `setOpen(false)`，下拉面板消失。
- `onMouseDown.preventDefault()` 让关闭不经 blur 200ms 路径，即时生效。
- `onClick.stopPropagation()` 避免触发父级任何处理（当前面板内无父级 handler，防御性写法）。
- 不影响 `Escape`、blur、选中条目等既有关闭路径。

## 测试

`SmartSuggestionDropdown.test.tsx` 新增一条用例，沿用现有文件的模式（`<App>` 包裹、`vi.useFakeTimers()`、mock `getRecommendations` / `usePermission`）：

1. `mockedGetRecommendations.mockResolvedValueOnce(...)` 返回**完整的 `RecommendResponse`**（不能只给 suggestions）：

```ts
{
  suggestions: [{ name: "焊接不良", confidence: 0.8, source: "rule", explanation: "..." }],
  source: "rule",
  cached: false,
  llm_available: true,
  graph_match_count: 0,
  effective_scope: "global",
}
```

   （`source` 须为 `"rule" | "graph" | "hybrid" | "rule_fallback" | "graph_enriched"` 之一；这里用 `"rule"` 避免 fallback banner 出现干扰断言。）

2. `renderDropdown()` 后在输入框 `fireEvent.change` 输入 `"焊接"`，`await vi.advanceTimersByTimeAsync(500)` 触发防抖。
3. `waitFor` 等下拉面板（AntD portal 渲染到 `document.body`）出现建议文本「焊接不良」。
4. 用 `screen.getByRole("button", { name: "Close" })` 选中关闭按钮（en-US locale 下 `aria-label="Close"`），`fireEvent.mouseDown` + `fireEvent.click`。
5. `waitFor` 断言建议文本「焊接不良」已不在 DOM（`queryByText` 返回 null），即面板已收起。

## 验证

以下命令均在 `frontend/` 目录下运行：

```bash
npm run lint
npm run build      # 含 tsc --noEmit
npm test -- SmartSuggestionDropdown --run
```
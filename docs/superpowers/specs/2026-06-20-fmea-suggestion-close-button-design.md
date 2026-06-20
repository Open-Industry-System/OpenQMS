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

1. 从 `@ant-design/icons` 引入 `CloseOutlined`。
2. 给最外层 `dropdownContent` 容器 div 加 `position: "relative"`，作为关闭按钮的定位锚点。
3. 在容器内最前面渲染一个关闭按钮：

```tsx
<Button
  type="text"
  size="small"
  icon={<CloseOutlined />}
  onClick={(e) => { e.stopPropagation(); setOpen(false); }}
  aria-label={t("smartSuggestion.close")}
  title={t("smartSuggestion.close")}
  style={{ position: "absolute", top: 4, right: 4, zIndex: 1 }}
/>
```

按钮浮在右上角，无论当前显示哪一条 banner（error / fallback / rule-only）都可见。

### i18n

`src/locales/zh-CN/dfmea.json` 和 `src/locales/en-US/dfmea.json` 的 `smartSuggestion` 节点下新增：

- zh-CN: `"close": "关闭"`
- en-US: `"close": "Close"`

### 交互

- 点击 × → `setOpen(false)`，下拉面板消失。
- `stopPropagation` 避免触发父级任何处理（当前面板内无父级 handler，防御性写法）。
- 不影响 `Escape`、blur、选中条目等既有关闭路径。

## 测试

`SmartSuggestionDropdown.test.tsx` 新增一条用例：

1. 渲染组件，mock `getRecommendations` 返回 ≥1 条建议。
2. 输入 ≥2 字符触发防抖，等下拉面板出现。
3. 点击关闭按钮（按 `aria-label` 选中）。
4. 断言下拉面板内容已不在 DOM 中（`queryByText` 建议文本为 null，或 `open` 状态为 false 的可观测表现）。

## 验证

- `npm run lint`
- `npm run build`（含 `tsc --noEmit`）
- `npm test -- SmartSuggestionDropdown --run`（或现有测试命令）
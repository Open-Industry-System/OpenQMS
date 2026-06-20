# FMEA 智能推荐下拉框 × 关闭按钮 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 FMEA 编辑器的智能推荐下拉框加一个可见的 × 关闭按钮，点击即时收起面板。

**Architecture:** 在 `SmartSuggestionDropdown` 的下拉面板内容最前面加一个独立的 header/action 行（右对齐关闭按钮 + 底部分割线），点击 `setOpen(false)`；用 `onMouseDown.preventDefault()` 绕开输入框 blur 的 200ms 延迟路径。配套加 i18n key、清理未使用的 `Alert` import、补一条测试。

**Tech Stack:** React 18 + TypeScript 5.6 + Ant Design（`package.json` 声明 `^5.21.0`，本地实际安装 `5.29.3`）+ react-i18next + Vitest + @testing-library/react

## Global Constraints

- 所有命令在 `frontend/` 目录下运行。
- UI 文案中文（zh-CN 为准），en-US 同步。
- 遵循项目既有风格：`var(--qf-*)` CSS 变量、`t()` i18n、antd `Button type="text" size="small"`。
- AntD Dropdown 关闭后销毁弹层用**当前** prop `destroyOnHidden`（不要用已废弃的 `destroyPopupOnHide`）。`destroyOnHidden` 默认关闭，必须显式开启，否则关闭后弹层 DOM 仍留在 portal，`queryByText` 仍能查到，测试会失败。
- 不做禁用推荐的开关；不动其它推荐入口。
- Surgical changes：只改与本需求相关的行。

---

## File Structure

- **Modify** `frontend/src/locales/zh-CN/dfmea.json` —— 在 `smartSuggestion` 节点加 `close` 键。
- **Modify** `frontend/src/locales/en-US/dfmea.json` —— 同上（英文）。
- **Modify** `frontend/src/components/dfmea/SmartSuggestionDropdown.tsx` —— import 调整 + 加 header 关闭按钮。
- **Modify** `frontend/src/components/dfmea/SmartSuggestionDropdown.test.tsx` —— 新增关闭按钮测试用例。

---

### Task 1: i18n — 新增 `smartSuggestion.close` 键

**Files:**
- Modify: `frontend/src/locales/zh-CN/dfmea.json`（`smartSuggestion` 节点，约 237-258 行）
- Modify: `frontend/src/locales/en-US/dfmea.json`（`smartSuggestion` 节点，约 237-258 行）

**Interfaces:**
- Produces: `t("smartSuggestion.close")` 可用 —— zh-CN 返回 `"关闭"`，en-US 返回 `"Close"`。Task 2 的测试与组件均依赖此键。

- [ ] **Step 1: zh-CN 加键**

在 `frontend/src/locales/zh-CN/dfmea.json` 的 `smartSuggestion` 对象内，在 `"ruleOnlyMode": "仅规则引擎模式"` 行之后加一个逗号并新增 `close` 键：

```json
    "aiUnavailable": "AI 建议暂不可用，已使用规则引擎",
    "ruleOnlyMode": "仅规则引擎模式",
    "close": "关闭"
  },
```

- [ ] **Step 2: en-US 加键**

在 `frontend/src/locales/en-US/dfmea.json` 的 `smartSuggestion` 对象内，把 `"ruleOnlyMode": "Rule engine only mode"` 行改为加逗号并新增 `close`：

```json
    "aiUnavailable": "AI suggestions unavailable, rule engine fallback used",
    "ruleOnlyMode": "Rule engine only mode",
    "close": "Close"
  },
```

- [ ] **Step 3: 校验 JSON 合法**

Run: `node -e "JSON.parse(require('fs').readFileSync('src/locales/zh-CN/dfmea.json','utf8')); JSON.parse(require('fs').readFileSync('src/locales/en-US/dfmea.json','utf8')); console.log('ok')"`
Expected: 输出 `ok`，无 JSON 解析错误。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/locales/zh-CN/dfmea.json frontend/src/locales/en-US/dfmea.json
git commit -m "i18n(dfmea): add smartSuggestion.close key"
```

---

### Task 2: TDD 关闭按钮（测试 + 组件）

**Files:**
- Modify: `frontend/src/components/dfmea/SmartSuggestionDropdown.tsx`
- Test: `frontend/src/components/dfmea/SmartSuggestionDropdown.test.tsx`

**Interfaces:**
- Consumes: Task 1 的 `t("smartSuggestion.close")`。
- Produces: 下拉面板顶部一个 `Button`，`aria-label` 为 `t("smartSuggestion.close")`（en-US 下为 `"Close"`），点击后 `open` 变为 false。

- [ ] **Step 1: 写失败测试**

在 `frontend/src/components/dfmea/SmartSuggestionDropdown.test.tsx` 现有 `describe` 块内、现有 `it(...)` 之后追加一个用例：

```tsx
  it("closes the dropdown when the close button is clicked", async () => {
    mockedGetRecommendations.mockResolvedValueOnce({
      suggestions: [{ name: "焊接不良", confidence: 0.8, source: "rule", explanation: "rule hit" }],
      source: "rule",
      cached: false,
      llm_available: true,
      graph_match_count: 0,
      effective_scope: "global",
    });

    renderDropdown();
    const input = screen.getByRole("textbox");

    fireEvent.change(input, { target: { value: "焊接" } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    await waitFor(() => {
      expect(screen.getByText("焊接不良")).toBeInTheDocument();
    });

    const closeBtn = screen.getByRole("button", { name: "Close" });
    fireEvent.mouseDown(closeBtn);
    fireEvent.click(closeBtn);

    // AntD Dropdown 关闭时有 exit motion，依赖 setTimeout/rAF；
    // 用 fake timers 时需显式 flush，否则弹层不会真正卸载，queryByText 仍能查到。
    await act(async () => {
      await vi.runOnlyPendingTimersAsync();
    });

    expect(screen.queryByText("焊接不良")).not.toBeInTheDocument();
  });
```

> 该用例依赖组件给 `<Dropdown>` 加 `destroyOnHidden`（见 Step 4b）。**优先按上面的 fake-timer flush 方式**，不要走下面的 fallback 除非实测失败。若确需切换：在该断言前 `vi.useRealTimers()`，断言后**立即** `vi.useRealTimers()` 之后用 `vi.useFakeTimers()` 恢复（或在测试末尾 `vi.useRealTimers()` 清理）——当前测试文件没有 `afterEach`，不恢复会污染后续用例的 timer 模式。

- [ ] **Step 2: 运行测试，确认失败**

Run: `npm test -- SmartSuggestionDropdown --run`
Expected: FAIL —— `getByRole("button", { name: "Close" })` 找不到该按钮（组件尚未渲染关闭按钮）。

- [ ] **Step 3: 改组件 —— 调整 import**

在 `frontend/src/components/dfmea/SmartSuggestionDropdown.tsx`：

第 3 行，从 antd 的 import 中**移除 `Alert`**、**新增 `Button`**：

```tsx
import { Input, Dropdown, Tag, Spin, Button, Typography, Radio } from "antd";
```

第 4 行，从 icons 引入 `CloseOutlined`：

```tsx
import { BulbOutlined, StarOutlined, SettingOutlined, GlobalOutlined, CloseOutlined } from "@ant-design/icons";
```

- [ ] **Step 4: 改组件 —— 加 header 关闭按钮**

在 `dropdownContent` 的最外层 `<div ...>` 紧接其后、`{error && (...)}` 之前，插入 header/action 行。原代码（约 180-190 行）：

```tsx
  const dropdownContent = (
    <div
      style={{
        width: 360,
        background: "var(--qf-bg-panel)",
        border: "1px solid var(--qf-border-strong)",
        borderRadius: "var(--qf-radius-md)",
        boxShadow: "var(--qf-shadow-md)",
        color: "var(--qf-text-primary)",
      }}
    >
      {error && (
```

改为：

```tsx
  const dropdownContent = (
    <div
      style={{
        width: 360,
        background: "var(--qf-bg-panel)",
        border: "1px solid var(--qf-border-strong)",
        borderRadius: "var(--qf-radius-md)",
        boxShadow: "var(--qf-shadow-md)",
        color: "var(--qf-text-primary)",
      }}
    >
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
      {error && (
```

- [ ] **Step 4b: 给 `<Dropdown>` 加 `destroyOnHidden`**

同文件末尾的 `<Dropdown>` 元素（约 280-285 行）：

```tsx
    <Dropdown
      open={open && !disabled}
      popupRender={() => dropdownContent}
      trigger={[]}
      placement="bottomLeft"
    >
```

改为：

```tsx
    <Dropdown
      open={open && !disabled}
      popupRender={() => dropdownContent}
      trigger={[]}
      placement="bottomLeft"
      destroyOnHidden
    >
```

> 说明：`destroyOnHidden` 默认关闭；开启后 `open` 变 false 时弹层 DOM 真正从 portal 卸载，使 Step 1 测试的 `queryByText("焊接不良").not.toBeInTheDocument()` 成立，也顺带消除关闭后残留隐藏 DOM 的隐患。不要用已废弃的 `destroyPopupOnHide`。

- [ ] **Step 5: 运行测试，确认通过**

Run: `npm test -- SmartSuggestionDropdown --run`
Expected: PASS —— 两个用例（原有取消用例 + 新关闭用例）全绿。

- [ ] **Step 6: lint + build**

Run: `npm run lint`
Expected: 无新增 warning（`Alert` 未使用 warning 应已消除；无未使用变量）。

Run: `npm run build`
Expected: 成功（`tsc --noEmit` + `vite build` 无报错）。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/components/dfmea/SmartSuggestionDropdown.tsx frontend/src/components/dfmea/SmartSuggestionDropdown.test.tsx
git commit -m "feat(dfmea): add close button to smart-suggestion dropdown; drop unused Alert import"
```
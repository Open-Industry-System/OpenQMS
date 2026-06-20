# DFMEA 向导「时间范围」日历选择器设计文档

**日期**: 2026-06-20
**状态**: 已评审（待实现）
**优先级**: P2
**类型**: UX 改进

---

## 背景与动机

DFMEA 生成向导第 0 步（5T 范围界定）中，「时间范围 Timing」字段目前是一个纯文本 `Input`，用户需要手动输入如 "2026年Q1-Q3" 这样的描述，体验差且格式不统一。

i18n 标签 `wizard.scope.timeframe` 的描述明确写道：*"DFMEA 的**起止时间**..."*，示例为 *"时间范围：2026年Q1-Q3"* —— 说明该字段语义上是一个**日期区间**（起止），而非单个时间点。

**目标**：将该字段替换为日历区间选择器，让用户通过日历直观选择起止日期，统一格式，提升 UX。

### 约束

- 该字段会持久化到后端 graph JSONB（`fmea_documents.graph_data` 内的 `wizardScope.timeframe`），需向后兼容已存在的草稿数据。
- `dayjs` 已是项目依赖（`^1.11.13`），antd `DatePicker`/`RangePicker` 已在 Gauge、SPC 页面使用，dayjs locale 在 `main.tsx` 全局配置。**无需引入新依赖。**

---

## 核心决策

| 决策项 | 选择 | 原因 |
|--------|------|------|
| 选择器类型 | antd `DatePicker.RangePicker`（区间） | 标签语义为「起止时间」 |
| 序列化方案 | **方案 A**：保留 `timeframe: string`，序列化为 `"YYYY-MM-DD ~ YYYY-MM-DD"` | 外科手术式、数据契约不变、向后兼容 |
| 改动位置 | 两处都改：`GenerationWizard.tsx` + `DFMEAWizardPage.tsx` | 同一字段、保持 UX 一致 |
| 是否新增依赖 | 否 | dayjs + antd RangePicker 已就绪 |
| 校验是否变更 | 否（`timeframe` 保持可选） | step0 `canProceed` 只校验 `team` + `task` |
| i18n 标签 | 不新增 | antd ConfigProvider 已动态切换 locale，选择器占位符/日历自动本地化 |

### 为什么选方案 A 而非拆字段（方案 B）

方案 B（拆成 `timeframe_start` / `timeframe_end`）需要改 `WizardScope` 类型、两处调用、以及 seed 示例图，影响面更大；且会让已存在的 `timeframe` 键孤立，旧草稿静默丢失该值。方案 A 零类型改动，旧版自由文本（如 `"Q1-Q3"`）只是无法回填到选择器（显示空），但值仍保留在存储中不丢失。契合 CLAUDE.md 第 2 条（简洁）、第 3 条（外科手术式改动）。

---

## 详细设计

### 1. 新增 helper：`frontend/src/utils/wizardTimeframe.ts`

两个纯函数，供两处复用，避免重复逻辑：

```ts
import dayjs, { Dayjs } from 'dayjs';

/** 区间 → 可读字符串，不完整返回空串 */
export function rangeToTimeframe(range: [Dayjs, Dayjs] | null): string {
  if (!range || !range[0] || !range[1]) return '';
  return `${range[0].format('YYYY-MM-DD')} ~ ${range[1].format('YYYY-MM-DD')}`;
}

/** 可读字符串 → 区间，无法解析（含旧版自由文本）返回 null，绝不抛错 */
export function timeframeToRange(timeframe: string): [Dayjs, Dayjs] | null {
  const m = timeframe.match(/^(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})$/);
  if (!m) return null;
  return [dayjs(m[1]), dayjs(m[2])];
}
```

关键点：`timeframeToRange` 对任何无法匹配的输入返回 `null`，保证旧数据/异常数据不会让选择器崩溃。

### 2. `frontend/src/components/dfmea/GenerationWizard.tsx`（第 180 行附近）

- 导入：`antd` 导入里加上 `DatePicker`；顶部 `import { rangeToTimeframe, timeframeToRange } from '../../utils/wizardTimeframe';` 以及 `import type { Dayjs } from 'dayjs';`
- 将第 180 行的文本 `Input` 替换为：

```tsx
<DatePicker.RangePicker
  style={{ width: '100%' }}
  value={timeframeToRange(data.scope.timeframe)}
  onChange={(range) =>
    updateData({ scope: { ...data.scope, timeframe: rangeToTimeframe(range as [Dayjs, Dayjs] | null) } })
  }
/>
```

> 说明：该弹窗路径下 `generateSkeleton` 本就不把 scope 写入图（既有行为），此处仅改 UX，不涉及持久化往返。

### 3. `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`（第 155–156 行）

- 同样的导入补充。
- 将第 155–156 行的文本 `Input` 替换为接到 `wizardScope.timeframe` 的 `DatePicker.RangePicker`：

```tsx
<DatePicker.RangePicker
  style={{ width: '100%' }}
  value={timeframeToRange(wizardScope.timeframe || '')}
  onChange={(range) =>
    updateGraphData(nodes, edges, { ...wizardScope, timeframe: rangeToTimeframe(range as [Dayjs, Dayjs] | null) })
  }
/>
```

> 这条路径会把 `wizardScope`（含 `timeframe`）持久化到后端，因此「保存的字符串 → 重新打开草稿 → 选择器回填」的往返在这里得到验证。

### 4. 单元测试：`frontend/src/utils/wizardTimeframe.test.ts`

vitest 覆盖：
- 双向往返：`rangeToTimeframe([d('2026-01-01'), d('2026-09-30')])` → `"2026-01-01 ~ 2026-09-30"`，再 `timeframeToRange` 还原回同区间。
- 空值：`rangeToTimeframe(null)` → `''`；`timeframeToRange('')` → `null`。
- 旧版自由文本：`timeframeToRange('2026年Q1-Q3')` → `null`（优雅降级，不抛错）。

---

## 明确不改（外科手术式）

- `WizardScope.timeframe?: string` 类型 —— 保持 `string`（`types/index.ts:96`）
- 第 0 步 `canProceed` 校验 —— 仅查 `team` + `task`，`timeframe` 保持可选
- i18n 标签 `wizard.scope.timeframe` —— 已存在
- `generateSkeleton` —— scope 本就不写入图，不触碰
- 后端、数据库、schema、迁移 —— 全部不动

---

## 验证

1. **单测**：`cd frontend && npm test`（vitest，含新 helper 测试通过）
2. **Lint**：`npm run lint`（无新增告警）
3. **类型+构建**：`npm run build`（tsc + vite build 通过）
4. **手动端到端**（`docker compose up` 后用 engineer 账号登录）：
   - 打开 DFMEA 向导独立页（`/fmea/wizard/:id`）→ 第 0 步 → 点「时间范围」→ 弹出日历，选择起止日期 → 输入框显示 `2026-01-01 ~ 2026-09-30`
   - 前进 → 返回第 0 步 → 确认选择器仍显示已选区间
   - 完成向导并保存 → 重新打开该草稿 → 确认选择器正确回填
   - 在编辑器内的弹窗向导同样验证一遍

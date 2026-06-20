# DFMEA 向导「时间范围」日历选择器设计文档

**日期**: 2026-06-20
**状态**: 已评审修订版 v2
**优先级**: P2
**类型**: UX 改进

---

## 背景与动机

DFMEA 生成向导第 0 步（5T 范围界定）中，「时间范围 Timing」字段目前是一个纯文本 `Input`，用户需要手动输入如 "2026年Q1-Q3" 这样的描述，体验差且格式不统一。

i18n 标签 `wizard.scope.timeframe` 的描述明确写道：*"DFMEA 的**起止时间**..."*，示例为 *"时间范围：2026年Q1-Q3"* —— 说明该字段语义上是一个**日期区间**（起止），而非单个时间点。

**目标**：将该字段替换为日历区间选择器，让用户通过日历直观选择起止日期，统一格式，提升 UX。

### 约束

- 该字段会持久化到后端 graph JSONB（`fmea_documents.graph_data` 内的 `wizardScope.timeframe`），需向后兼容已存在的草稿数据。
- `dayjs` 已是项目依赖（`^1.11.13`），antd `DatePicker.RangePicker` 已在 `internalAudit/InternalAuditListPage.tsx` 与 `supplier/components/DashboardView.tsx` 使用（Gauge/SPC 用的是单个 `DatePicker`），dayjs locale 在 `main.tsx` 全局配置。**无需引入新依赖。**

---

## 核心决策

| 决策项 | 选择 | 原因 |
|--------|------|------|
| 选择器类型 | antd `DatePicker.RangePicker`（区间） | 标签语义为「起止时间」 |
| 序列化方案 | **方案 A**：保留 `timeframe: string`，序列化为 `"YYYY-MM-DD ~ YYYY-MM-DD"` | 外科手术式、数据契约不变、向后兼容 |
| 改动位置 | 两处都改：`GenerationWizard.tsx` + `DFMEAWizardPage.tsx` | 同一字段、保持 UX 一致 |
| 字段标签 | **Step 0 全部 5 个字段加 label**（团队/时间范围/工具/任务/趋势） | 当前 5 个字段仅靠 placeholder 标识，选值后 placeholder 消失、身份丢失；RangePicker 尤甚（双框立即被日期填满）。复用现有 i18n key，无需新增 label 文案 |
| helper 类型 | `rangeToTimeframe` 入参取 `null \| [Dayjs\|null, Dayjs\|null]`，与 antd onChange 真实类型对齐 | 调用处无需 `as` 强转，与 `DashboardView.tsx` 既有写法一致；自然处理半选/清空 |
| 旧值处理 | 无法解析的旧自由文本：选择器显示空，并在控件下方提示「当前旧格式值：xxx（重新选择以更新）」 | 否则用户重开旧草稿会以为 Timing 丢了（纯兼容性 UX 回归） |
| 是否新增依赖 | 否 | dayjs + antd RangePicker 已就绪 |
| 校验是否变更 | 否（`timeframe` 保持可选） | step0 `canProceed` 只校验 `team` + `task` |

### 为什么选方案 A 而非拆字段（方案 B）

方案 B（拆成 `timeframe_start` / `timeframe_end`）需要改 `WizardScope` 类型、两处调用、以及 seed 示例图，影响面更大；且会让已存在的 `timeframe` 键孤立，旧草稿静默丢失该值。方案 A 零类型改动，旧版自由文本（如 `"Q1-Q3"`）只是无法回填到选择器（显示空 + 下方提示），但值仍保留在存储中不丢失。契合 CLAUDE.md 第 2 条（简洁）、第 3 条（外科手术式改动）。

---

## 详细设计

### 1. 新增 helper：`frontend/src/utils/wizardTimeframe.ts`

两个纯函数，供两处复用。入参类型与 antd `RangePicker` 的 `onChange` 真实类型（`null | [Dayjs | null, Dayjs | null]`）对齐，调用处无需 `as` 强转；解析时用 dayjs **严格模式**校验日期有效性（`2026-02-31`、`2026-13-01` 这类形状正确但非法的输入返回 `null`）：

```ts
import dayjs, { Dayjs } from 'dayjs';

/** 区间 → 可读字符串；null 或任一侧为空返回空串 */
export function rangeToTimeframe(range: [Dayjs | null, Dayjs | null] | null): string {
  if (!range || !range[0] || !range[1]) return '';
  return `${range[0].format('YYYY-MM-DD')} ~ ${range[1].format('YYYY-MM-DD')}`;
}

/** 可读字符串 → 区间；无法解析或日期非法（含旧版自由文本）返回 null，绝不抛错 */
export function timeframeToRange(timeframe: string): [Dayjs, Dayjs] | null {
  const m = timeframe.match(/^(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})$/);
  if (!m) return null;
  const start = dayjs(m[1], 'YYYY-MM-DD', true);
  const end = dayjs(m[2], 'YYYY-MM-DD', true);
  return start.isValid() && end.isValid() ? [start, end] : null;
}
```

关键点：`timeframeToRange` 对任何无法匹配或日期非法的输入返回 `null`，保证旧数据/异常数据不会让选择器崩溃。

### 2. `frontend/src/components/dfmea/GenerationWizard.tsx`（第 173–186 行 Step 0）

- 导入：`antd` 导入加 `DatePicker`；顶部 `import { rangeToTimeframe, timeframeToRange } from '../../utils/wizardTimeframe';`（无需引入 `Dayjs` 类型——helper 已封装）。
- **Step 0 全部 5 个字段加 label**（复用现有 i18n key `wizard.scope.team/timeframe/tool/task/trend`）。label 用轻量 `<div>` 包裹，**不硬编码颜色**以兼容暗色主题（继承 antd 主题文本色）。可用文件内小 label 包裹组件减少 5× 重复：
  ```tsx
  const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
    <div>
      <div style={{ marginBottom: 4 }}>{label}</div>
      {children}
    </div>
  );
  ```
- 「时间范围」字段由文本 `Input` 替换为 `RangePicker`，**无 `as` 强转**：

```tsx
<Field label={t('wizard.scope.timeframe')}>
  <DatePicker.RangePicker
    style={{ width: '100%' }}
    value={timeframeToRange(data.scope.timeframe)}
    onChange={(range) => updateData({ scope: { ...data.scope, timeframe: rangeToTimeframe(range) } })}
  />
</Field>
```

> 说明：该弹窗路径每次打开都是全新 state（`initialWizardData()`），`timeframe` 恒为空，故无需「旧值提示」；此处仅改 UX。

### 3. `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`（第 150–164 行 Step 0）

- 同样的导入补充 + `Field` label 包裹 + 5 字段加 label。
- 「时间范围」替换为 `RangePicker`，接到 `wizardScope.timeframe`，通过 `updateGraphData(...)` 写回（**无强转**）：
  ```tsx
  <Field label={t('wizard.scope.timeframe')}>
    <DatePicker.RangePicker
      style={{ width: '100%' }}
      value={timeframeToRange(wizardScope.timeframe || '')}
      onChange={(range) => updateGraphData(nodes, edges, { ...wizardScope, timeframe: rangeToTimeframe(range) })}
    />
  </Field>
  ```
- **旧值提示**（仅此文件需要——草稿会被重新打开）：当 `wizardScope.timeframe` 非空且 `timeframeToRange()` 返回 `null` 时，在选择器下方显示一行提示。选择新区间即替换旧值：
  ```tsx
  {wizardScope.timeframe && !timeframeToRange(wizardScope.timeframe) && (
    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
      {t('wizard.scope.legacyTimeframe', { value: wizardScope.timeframe })}
    </Typography.Text>
  )}
  ```

> 这条路径会把 `wizardScope`（含 `timeframe`）持久化到后端，因此「保存的字符串 → 重新打开草稿 → 选择器回填 / 旧值提示」的往返在这里得到验证。

### 4. i18n：新增 1 个 key（`legacyTimeframe`）

label 复用现有 key，**仅新增**「旧值提示」文案，加入两个 locale 文件的 `wizard.scope` 下（`zh-CN/dfmea.json` 第 13–21 行、`en-US/dfmea.json` 对应段）：

```jsonc
// zh-CN
"legacyTimeframe": "当前旧格式值：{{value}}（重新选择以更新）"
// en-US
"legacyTimeframe": "Legacy value: {{value}} (re-select to update)"
```

### 5. 单元测试：`frontend/src/utils/wizardTimeframe.test.ts`

vitest 覆盖：
- 双向往返：`rangeToTimeframe([d('2026-01-01'), d('2026-09-30')])` → `"2026-01-01 ~ 2026-09-30"`，再 `timeframeToRange` 还原回同区间。
- 半选/清空：`rangeToTimeframe([d1, null])` → `''`；`rangeToTimeframe(null)` → `''`；`timeframeToRange('')` → `null`。
- 旧版自由文本：`timeframeToRange('2026年Q1-Q3')` → `null`。
- **非法日期**（严格校验）：`timeframeToRange('2026-02-31 ~ 2026-09-30')` → `null`；`timeframeToRange('2026-13-01 ~ 2026-09-30')` → `null`。

---

## 明确不改（外科手术式）

- `WizardScope.timeframe?: string` 类型 —— 保持 `string`（`types/index.ts:96`）
- 第 0 步 `canProceed` 校验 —— 仅查 `team` + `task`，`timeframe` 保持可选
- `generateSkeleton` —— scope 本就不写入图，不触碰
- 后端、数据库、schema、迁移 —— 全部不动

---

## 验证

1. **单测**：`cd frontend && npm test -- --run`（vitest 单次运行退出，含新 helper 全部用例）
2. **Lint**：`cd frontend && npm run lint`（无新增告警）
3. **类型+构建**：`cd frontend && npm run build`（tsc + vite build 通过）
4. **手动端到端**（`docker compose up` 后用 engineer 账号登录）：
   - 打开 DFMEA 向导独立页（`/fmea/wizard/:id`）→ 第 0 步 → 5 个字段均有可见 label → 点「时间范围」→ 弹出日历，选择起止日期 → 显示 `2026-01-01 ~ 2026-09-30`
   - 前进 → 返回第 0 步 → 确认选择器仍显示已选区间（label 不变）
   - 完成向导并保存 → 重新打开该草稿 → 确认选择器正确回填
   - **旧值兼容**：构造一个 `wizardScope.timeframe = "2026年Q1-Q3"` 的草稿（或用旧数据）→ 重开 → 选择器为空，下方提示「当前旧格式值：2026年Q1-Q3（重新选择以更新）」→ 选新区间后提示消失、旧值被替换
   - 在编辑器内的弹窗向导同样验证一遍 label + 选择器

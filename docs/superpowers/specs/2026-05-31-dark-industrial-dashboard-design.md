# OpenQMS 深色主题仪表盘设计

**创建日期**: 2026-05-31
**修订**: v5 — 非目标声明、小屏折叠规则、Lighthouse/Playwright 验证计划
**状态**: 待实现

---

## 1. 设计原则

### 1.1 主任务定义

**质量负责人在 30 秒内识别最需要处理的质量风险，并进入处置动作。**

仪表盘不是信息展示页面，是**决策入口**。每个元素必须服务于：看到问题 → 理解优先级 → 进入处置。任何不服务于这个链路的元素都是噪声。

### 1.2 设计约束

| 维度 | 约束 |
|------|------|
| 首屏 TTI | ≤ 2s（含数据请求） |
| 首屏 JS 总量 | ≤ 300KB gzipped（当前约 280KB，dark theme 增量 ≤ 5KB） |
| 网络请求 | 首屏 ≤ 3 个 API 调用（已合并为 summary + alerts + recent） |
| 外部资源 | 默认不引入 Google Fonts 等外链字体 |
| 动画 | 默认关闭，`prefers-reduced-motion: no-preference` 时启用 |
| 对比度 | 所有文字 ≥ WCAG AA（4.5:1），关键数据 ≥ 7:1 |

### 1.3 深色主题不是装饰

深色主题的理由是**减少长时间使用的眼睛疲劳**和**让状态色（红/黄/绿）在低亮度环境中更突出**。不是为了"科技感"。移除所有纯装饰元素：网格纹理、发光边框、数字滚动动画、卡片入场动画。

### 1.4 非目标（本轮不实现）

| 非目标 | 原因 | 后续路径 |
|--------|------|---------|
| 浅色主题 / 主题切换 | 降低范围，避免每个 token、图表、状态色变成双路径验证 | 所有颜色已通过 `theme.useToken()` 获取，后续只需增加一组 token + 切换入口 |
| 仪表盘自定义布局 | 用户自定义拖拽卡片超出本轮范围 | 信息架构已按优先级固定，后续可加配置 |

---

## 2. 用户角色与权限矩阵

### 2.1 角色定义

| 角色 | 代号 | 仪表盘可见内容 |
|------|------|--------------|
| 管理员 | admin | 全部 |
| 质量工程师 | quality_engineer | 全部 |
| 经理 | manager | 全部 |
| 查看者 | viewer | 只读，隐藏"快速入口" |

### 2.2 权限影响

- viewer 看到的 KPI 卡片不可点击导航（仅展示数字）
- viewer 隐藏"快速入口"区块
- 空状态文案区分"无数据"（尚未创建）和"无权限"（无权查看）

---

## 3. 仪表盘信息架构

### 3.1 页面结构

```
┌─────────────────────────────────────────────────────┐
│  质量仪表盘                                    [产品线] │
├────────────┬────────────┬────────────┬──────────────┤
│  待办事项   │  超期任务   │  高风险项   │  本月新增    │
│  红/黄/绿   │  红/0=绿   │  红/0=绿   │  趋势箭头    │
├────────────┴────────────┴────────────┴──────────────┤
│  待处置事项 ─────────────────────────────────────── │
│  ┌─────────────┐ ┌─────────────┐ ┌───────────────┐ │
│  │ 高 RPN FMEA  │ │ 超期 CAPA   │ │ PPM 超标供应商 │ │
│  │              │ │              │ │               │ │
│  │ PFMEA-001    │ │ 8D-003      │ │ 供应商A        │ │
│  │ RPN=240      │ │ 超期5天      │ │ PPM=850       │ │
│  │ [前往审批→]  │ │ [前往跟进→] │ │ [前往查看→]   │ │
│  └─────────────┘ └─────────────┘ └───────────────┘ │
├─────────────────────────────┬───────────────────────┤
│  最近操作                   │  快速入口              │
│  ● 刚刚   创建 PFMEA-001   │  [新建 FMEA]          │
│  ● 2小时前 更新 8D-003     │  [新建 CAPA]          │
│  └─── 时间线 ───            │  [新建客诉]           │
└─────────────────────────────┴───────────────────────┘
```

### 3.2 信息优先级

| 优先级 | 区块 | 决策支持 |
|--------|------|---------|
| P0 | KPI 指标卡 | 一眼看出整体健康度 |
| P1 | "待处置事项"风险列表 | 明确下一步动作 |
| P2 | 最近操作 | 上下文连续性 |
| P3 | 快速入口 | 减少导航步骤（viewer 隐藏） |

---

## 4. KPI 指标卡设计

### 4.1 数据定义

| 卡片 | 数据来源 | 计算逻辑 | 阈值 | 点击目标 |
|------|---------|---------|------|---------|
| 待办事项 | `summary.pending_actions` | CAPA 未完成 + FMEA 待审批 | >0 黄色, 0 绿色 | `/capa?pending_action=true` |
| 超期任务 | `summary.overdue_tasks` | CAPA 截止日期 < 今天 | >0 红色, 0 绿色 | `/capa?overdue=true` |
| 高风险项 | `summary.high_risk_items` | FMEA RPN ≥ 200 或 AP=H | >0 红色, 0 绿色 | `/fmea?risk=high` |
| 本月新增 | `summary.month_trend` | 本月新增记录数 vs 上月，百分比变化 | 正=绿色+↑, 负=红色+↓, 零=灰色+— | 不可点击 |

### 4.2 组件规格

```
┌─────────────────────────────┐
│  待办事项                    │  ← 14px, colorTextSecondary
│                             │
│  12                         │  ← 32px, 600字重, colorText
│                             │
│  较昨日 +3                   │  ← 12px, colorTextTertiary (#8696a8, AA ✓)
└─────────────────────────────┘
  ↑ 顶部 3px 边框：状态色（红/黄/绿）
```

- 数字不使用滚动动画，直接渲染
- 卡片圆角 `token.borderRadiusLG`（8px）
- 背景 `token.colorBgContainer`
- 可点击卡片：`cursor: pointer`，hover 时背景微亮（`colorBgElevated`）

### 4.3 状态矩阵（KPI 卡片）

| 状态 | 视觉表现 | 交互 |
|------|---------|------|
| empty（首次使用，无数据） | 数字"—"，灰色边框，辅助文字"暂无记录" | 不可点击 |
| loading | Ant Design Skeleton（标题+数字+辅助文字） | 不可点击 |
| error | 数字"—"，灰色边框，辅助文字"加载失败" | 辅助文字为可点击的"重试"链接 |
| success-正常（0） | 数字"0"，绿色边框 | 可点击（viewer 不可点击） |
| success-警告（>0） | 实际值，黄色边框，"较昨日 +N" | 可点击 |
| success-危险 | 实际值，红色边框，"较昨日 +N" | 可点击 |
| focus | 2px `colorPrimary` 外轮廓（`outline-offset: 2px`） | Enter 触发导航 |
| disabled（viewer） | 完整展示，`cursor: default`，无 hover 效果 | 不可点击，无键盘焦点 |

### 4.4 空状态

- 数据为 0 且无错误：显示 "0"，绿色边框，辅助文字显示 "暂无"
- API 失败：显示 "—"，灰色边框，显示重试链接
- 从未初始化（首次使用）：显示 "—"，引导用户创建第一条记录

---

## 5. 风险列表设计

### 5.1 区块标题

**"待处置事项"** — 不是"高 RPN FMEA"、"超期 CAPA"等技术术语。标题表达的是用户行动，不是数据分类。

### 5.2 列表项设计

每个列表项是一个**可行动的卡片**，包含：

| 元素 | 内容 | 样式 |
|------|------|------|
| 主标题 | 文档编号（等宽字体） | 14px, colorText |
| 副标题 | 风险描述或超期信息 | 12px, colorTextSecondary |
| 右侧标签 | 风险指标（RPN/天数/PPM） | pill 形状，状态色背景 |
| 操作 | 根据类型：FMEA→"前往审批"、CAPA→"前往跟进"、供应商→"前往查看" | 12px, colorPrimary |

### 5.3 风险标签颜色

| 指标 | 值 | 背景 | 文字 |
|------|-----|------|------|
| RPN | ≥200 | rgba(239,68,68,0.12) | colorError |
| RPN | 100-199 | rgba(245,158,11,0.12) | colorWarning |
| 超期天数 | >0 | rgba(239,68,68,0.12) | colorError |
| PPM | >500 | rgba(239,68,68,0.12) | colorError |
| PPM | 200-500 | rgba(245,158,11,0.12) | colorWarning |

### 5.4 状态矩阵（待处置事项列表）

| 状态 | 视觉表现 | 交互 |
|------|---------|------|
| empty | 居中文案："暂无待处置事项，当前无超期或高风险项" | — |
| loading | Skeleton 列表（3 行占位） | — |
| error | 居中文案"加载失败" + 重试 Button（`type=default`） | 点击重试 |
| success（有数据） | 列表项展示，每项可独立操作 | 每项可点击导航 |
| success（空数据） | 同 empty | — |
| focus | 列表项获得 2px `colorPrimary` 外轮廓 | Enter 触发导航 |
| disabled（viewer） | 列表项展示，操作链接隐藏 | 不可点击 |

---

## 6. 最近操作设计

### 6.1 数据来源

`getDashboardRecentActions()` 返回最近 10 条操作记录。

### 6.2 列表项

| 元素 | 内容 |
|------|------|
| 时间 | 相对时间："刚刚"（<5分钟）、"N分钟前"（<1小时）、"N小时前"（<24小时）、"昨天"（<48小时）、"MM-DD HH:mm"（更早） |
| 操作类型 | 创建/更新/审批/驳回 |
| 目标 | 文档编号 + 文档类型 |
| 链接 | 点击跳转到详情页 |

### 6.3 状态矩阵（最近操作）

| 状态 | 视觉表现 | 交互 |
|------|---------|------|
| empty | 居中文案："暂无操作记录" | — |
| loading | Skeleton 列表（5 行占位） | — |
| error | 居中文案"加载失败" + 重试 Button | 点击重试 |
| success（有数据） | 时间线列表，每项可点击 | 跳转到详情页 |
| success（空数据） | 同 empty | — |
| focus | 列表项获得 `colorPrimary` 外轮廓 | Enter 跳转 |
| disabled | 不适用（viewer 可查看操作记录） | — |

---

## 7. 快速入口设计

### 7.1 规则

- viewer 角色隐藏整个区块
- 按钮文案明确动作："新建 FMEA"、"新建 CAPA"、"新建客诉"
- 按钮样式：`type="default"`，不是 `type="primary"`（避免视觉权重过高）

### 7.2 状态矩阵（快速入口）

| 状态 | 视觉表现 | 交互 |
|------|---------|------|
| default | 3 个 Button（`type=default`），`block` 宽度 | 点击跳转创建页 |
| loading | 不适用（静态按钮，无数据依赖） | — |
| error | 不适用 | — |
| success | 同 default | — |
| focus | 按钮获得 `colorPrimary` 外轮廓 | Enter 触发 |
| disabled（viewer） | 整个区块隐藏（`display: none`） | — |

### 7.2 空状态

不适用（按钮始终显示，除非权限限制）。

---

## 8. 主题系统

### 8.1 设计决策

使用 Ant Design 5 `darkAlgorithm` + 全局 Token 覆盖。**单一事实来源**：所有颜色通过 `theme.useToken()` 获取，不引入原生 CSS 变量。

### 8.2 Ant Design Token 配置

```typescript
const darkTheme = {
  algorithm: theme.darkAlgorithm,
  token: {
    // 背景层级
    colorBgLayout: '#0a0e1a',
    colorBgContainer: '#111827',
    colorBgElevated: '#1f2937',

    // 文字层级
    colorText: '#f0f9ff',
    colorTextSecondary: '#94a3b8',
    colorTextTertiary: '#8696a8',  // 调亮以满足 12px AA（4.5:1）

    // 边框
    colorBorder: 'rgba(148, 163, 184, 0.2)',
    colorBorderSecondary: 'rgba(148, 163, 184, 0.1)',

    // 强调色（状态色）
    colorPrimary: '#3b82f6',
    colorSuccess: '#10b981',
    colorWarning: '#f59e0b',
    colorError: '#ef4444',
    colorInfo: '#06b6d4',

    // 基础参数
    borderRadius: 8,
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif",
    fontSize: 14,

    // 动画时长（复用 AntD 内置，不手写）
    motionDurationMid: '0.2s',
    motionDurationSlow: '0.3s',
  },
  components: {
    Layout: {
      headerBg: '#111827',
      bodyBg: '#0a0e1a',
      siderBg: '#111827',
    },
    Card: {
      colorBgContainer: '#111827',
    },
    Menu: {
      colorBgContainer: 'transparent',
      colorItemBgHover: '#374151',
      colorItemBgSelected: '#1f2937',
    },
    Table: {
      colorBgContainer: '#111827',
      headerBg: '#1f2937',
    },
  },
};
```

### 8.3 字体策略

| 优先级 | 方案 | 条件 |
|--------|------|------|
| 默认 | `system-ui` + 系统等宽字体 | 无外部依赖 |
| 增强 | JetBrains Mono（CDN） | 用户在设置中手动开启 |

KPI 数字和文档编号使用等宽字体：`'SF Mono', 'Cascadia Code', 'Consolas', monospace`（系统内置，零网络请求）。

### 8.4 对比度验证

| 组合 | 前景 | 背景 | 对比度 | WCAG |
|------|------|------|--------|------|
| 主标题/卡片 | #f0f9ff | #111827 | 15.2:1 | AAA ✓ |
| 次要文字/卡片 | #94a3b8 | #111827 | 6.8:1 | AA ✓ |
| 辅助文字/卡片 | #8696a8 | #111827 | 5.2:1 | AA ✓（12px 可用） |
| 成功标签 | #10b981 | rgba(16,185,129,0.12) on #111827 | 5.1:1 | AA ✓ |
| 危险标签 | #ef4444 | rgba(239,68,68,0.12) on #111827 | 4.7:1 | AA ✓ |

---

## 9. 图表主题适配

### 9.1 ECharts 注册主题

```typescript
echarts.registerTheme('openqms-dark', {
  backgroundColor: 'transparent',
  textStyle: { color: '#94a3b8', fontSize: 12 },
  title: { textStyle: { color: '#f0f9ff' } },
  legend: { textStyle: { color: '#94a3b8' } },
  tooltip: {
    backgroundColor: '#1f2937',
    borderColor: 'rgba(148,163,184,0.2)',
    textStyle: { color: '#f0f9ff' },
  },
  xAxis: {
    axisLine: { lineStyle: { color: 'rgba(148,163,184,0.2)' } },
    splitLine: { lineStyle: { color: 'rgba(148,163,184,0.1)' } },
    axisLabel: { color: '#94a3b8' },
  },
  yAxis: {
    axisLine: { lineStyle: { color: 'rgba(148,163,184,0.2)' } },
    splitLine: { lineStyle: { color: 'rgba(148,163,184,0.1)' } },
    axisLabel: { color: '#94a3b8' },
  },
  series: {
    // 调色板与状态色一致
    color: ['#3b82f6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444'],
  },
});
```

### 9.2 @ant-design/charts

通过 ConfigProvider Token 自动继承暗色主题。如需额外配置，使用其 `theme` 属性。

---

## 10. 无障碍与动画

### 10.1 prefers-reduced-motion

```typescript
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// 在 ConfigProvider 中
token: {
  motionDurationMid: prefersReducedMotion ? '0s' : '0.2s',
  motionDurationSlow: prefersReducedMotion ? '0s' : '0.3s',
}
```

所有 CSS transition 和动画必须响应此媒体查询。

### 10.2 键盘导航

- KPI 卡片：可聚焦（tabIndex=0），Enter 触发导航
- 风险列表项：可聚焦，Enter 触发导航
- 快速入口：标准 Button 键盘行为
- 侧边栏菜单：Ant Design Menu 内置键盘支持

### 10.3 屏幕阅读器

- KPI 卡片添加 `aria-label`："待办事项：12 项"
- 风险列表添加 `role="list"`，列表项添加 `role="listitem"`
- 状态色辅以文字标签（不依赖颜色传达信息）

---

## 11. 响应式设计

### 11.1 断点

| 设备 | 断点 | 调整 |
|------|------|------|
| 桌面 | ≥1280px | 4 列 KPI，3 列风险，2 列底部 |
| 小桌面 | 1024-1279px | 侧边栏折叠，其余同桌面 |
| 平板 | 768-1023px | 2 列 KPI，1 列风险，1 列底部 |
| 手机 | <768px | 全部单列 |

### 11.2 侧边栏

- 桌面：展开 220px，可折叠至 80px
- 平板/手机：默认折叠，点击展开为 overlay

### 11.3 小屏区块优先级与折叠规则

为避免 P2/P3 区块在小屏上挤压 P0/P1，按以下规则处理：

| 区块 | 优先级 | 平板（768-1023px） | 手机（<768px） |
|------|--------|-------------------|---------------|
| KPI 指标卡 | P0 | 正常显示（2 列） | 正常显示（1 列） |
| 待处置事项 | P1 | 正常显示 | 正常显示 |
| 最近操作 | P2 | 正常显示 | **默认折叠**，点击展开 |
| 快速入口 | P3 | 正常显示 | **默认折叠**，点击展开 |

**折叠交互：**
- 折叠时显示区块标题 + 展开箭头（`DownOutlined`）
- 展开时显示完整内容 + 收起箭头（`UpOutlined`）
- viewer 角色在手机端不显示快速入口折叠项（直接隐藏）

---

## 12. 实现计划

### 12.1 阶段一：主题基础

1. `App.tsx` 中配置 ConfigProvider（使用 8.2 完整配置）
2. 注册 ECharts `openqms-dark` 主题（9.1）
3. 在组件中用 `theme.useToken()` 替换硬编码颜色
4. 添加 `prefers-reduced-motion` 响应逻辑

### 12.2 阶段二：布局与导航

1. AppLayout 侧边栏样式适配 Token
2. 顶栏样式适配
3. 折叠/展开交互

### 12.3 阶段三：仪表盘页面

1. KPI 卡片：数据定义、状态矩阵、空状态、错误状态
2. 风险列表："待处置事项"、状态矩阵、空状态
3. 最近操作：时间格式、空状态
4. 快速入口：viewer 隐藏逻辑
5. 权限适配

### 12.4 阶段四：通用组件

1. 卡片、按钮、表单、表格、标签统一适配 Token
2. 状态覆盖：empty/loading/error/success/focus/disabled

### 12.5 阶段五：业务页面适配

1. FMEA、CAPA、SPC、供应商等页面通用样式检查
2. ECharts 图表主题验证
3. 响应式验证

---

## 13. 验收标准

| 维度 | 标准 |
|------|------|
| 主任务 | 质量负责人 30 秒内识别最高优先级风险 |
| 可读性 | 所有文字 ≥ WCAG AA（4.5:1） |
| 状态覆盖 | 每个关键组件覆盖 empty/loading/error/success/focus/disabled |
| 无障碍 | 键盘可达，屏幕阅读器可用，prefers-reduced-motion 响应 |
| 性能 | 首屏 TTI ≤ 2s，首屏 JS 总量 ≤ 300KB gzipped，dark theme 增量 ≤ 5KB，API ≤ 3 |
| 功能完整 | 现有功能无回归 |
| 动画 | 默认关闭（reduced-motion），开启时使用 AntD Motion Token |

---

## 14. 实现后验证计划

实现完成后，使用以下工具验证验收标准：

### 14.1 Lighthouse 验证

| 指标 | 目标 | 验证方法 |
|------|------|---------|
| Performance | ≥ 90 | `lighthouse http://localhost:5173/dashboard --view` |
| 首屏 JS 总量 | ≤ 300KB gzipped | Lighthouse "Reduce unused JavaScript" + Network 面板 |
| TTI | ≤ 2s | Lighthouse Treo 或 WebPageTest |
| 对比度 | 全部通过 | Lighthouse "Color contrast is satisfactory" |

### 14.2 Playwright 自动化验证

```typescript
// 键盘路径验证
test('KPI cards are keyboard navigable', async ({ page }) => {
  await page.goto('/dashboard');
  await page.keyboard.press('Tab');
  // 第一个 KPI 卡片获得焦点
  await expect(page.locator('.kpi-card').first()).toBeFocused();
  await page.keyboard.press('Enter');
  // 导航到对应页面
  expect(page.url()).toContain('/capa');
});

// reduced-motion 验证
test('respects prefers-reduced-motion', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/dashboard');
  // 验证所有 transition 为 0s
  const transitions = await page.evaluate(() =>
    getComputedStyle(document.body).transitionDuration
  );
  expect(transitions).toBe('0s');
});

// API 请求数验证
test('dashboard loads with ≤ 3 API calls', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', req => {
    if (req.url().includes('/api/')) requests.push(req.url());
  });
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  expect(requests.length).toBeLessThanOrEqual(3);
});
```

### 14.3 手动验证清单

| 检查项 | 方法 |
|--------|------|
| 键盘 Tab 顺序 | 逐个 Tab 遍历所有可交互元素 |
| 屏幕阅读器 | VoiceOver（Mac）读出 KPI 和列表内容 |
| 对比度 | Chrome DevTools → Accessibility 面板 |
| 响应式 | Chrome DevTools 切换 768px / 1024px / 1280px |
| 状态色不依赖颜色 | 灰度模式下仍可区分正常/警告/危险 |

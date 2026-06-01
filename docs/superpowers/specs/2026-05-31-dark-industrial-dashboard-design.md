# 深色工业仪表盘主题设计

**创建日期**: 2026-05-31
**状态**: 待实现
**设计者**: Claude Code

---

## 1. 设计概览

### 1.1 视觉方向

**"精密工业控制室"** — 深色背景、高对比度数据展示、精密的网格系统，灵感来源于现代工厂的数字孪生（Digital Twin）监控系统和航空电子仪表盘。

### 1.2 设计目标

- **数据优先**: 高对比度文字和图表，确保远距离可读性
- **状态清晰**: 红（危险）、黄（警告）、绿（正常）的工业标准色编码
- **专业感**: 微妙的科技感纹理、等宽数字字体、精确的间距系统
- **低视觉疲劳**: 深色背景减少长时间使用的眼睛疲劳

### 1.3 技术方案

- 基于Ant Design 5.x 的 ConfigProvider + `theme.darkAlgorithm`
- 自定义设计令牌微调工业质感
- CSS变量覆盖关键样式
- 适度动画：页面加载渐入、卡片hover效果、数字滚动计数

---

## 2. 色彩系统

> **注意：** 本节中 `--xxx` 标记为设计概念名称，实际实现时全部映射到 Ant Design Token，不在代码中引入原生 CSS 变量。映射关系见附录 11.1。

### 2.1 背景层级

| 设计概念 | Ant Design Token | 值 | 用途 |
|---------|-----------------|-----|------|
| --bg-primary | `token.colorBgLayout` | #0a0e1a | 页面主背景 - 接近黑色的深蓝灰 |
| --bg-surface | `token.colorBgContainer` | #111827 | 卡片/面板背景 |
| --bg-elevated | `token.colorBgElevated` | #1f2937 | 悬浮/选中状态 |
| --bg-hover | 组件级 Token `colorItemBgHover` | #374151 | hover状态 |

### 2.2 文字颜色

| 设计概念 | Ant Design Token | 值 | 用途 |
|---------|-----------------|-----|------|
| --text-primary | `token.colorText` | #f0f9ff | 主标题 - 高亮白 |
| --text-secondary | `token.colorTextSecondary` | #94a3b8 | 次要文字 - 蓝灰 |
| --text-muted | `token.colorTextTertiary` | #64748b | 辅助文字 - 暗灰 |
| --text-disabled | `token.colorTextDisabled` | #475569 | 禁用状态 |

### 2.3 强调色

| 用途 | Ant Design Token | 值 |
|------|-----------------|-----|
| 主交互色 | `token.colorPrimary` | #3b82f6 |
| 数据高亮 | `token.colorInfo` | #06b6d4 |
| 成功/正常 | `token.colorSuccess` | #10b981 |
| 警告 | `token.colorWarning` | #f59e0b |
| 危险/异常 | `token.colorError` | #ef4444 |

### 2.4 边框与分隔

| 设计概念 | Ant Design Token | 值 |
|---------|-----------------|-----|
| --border-subtle | `token.colorBorderSecondary` | rgba(148, 163, 184, 0.1) |
| --border-default | `token.colorBorder` | rgba(148, 163, 184, 0.2) |
| --border-glow | 自定义扩展 Token（见附录） | rgba(59, 130, 246, 0.3) |

---

## 3. 布局设计

### 3.1 整体结构（保持现有布局）

| 区域 | 尺寸 | 说明 |
|------|------|------|
| 侧边栏 | 220px（折叠后80px） | 深色背景导航 |
| 顶栏 | 64px | 产品线选择器、用户信息 |
| 内容区 | 自适应 | 24px 内边距 |

### 3.2 侧边栏改进

- **背景色**: `--bg-surface` (#111827)
- **Logo区域**: 居中显示 "OpenQMS"，使用 --accent-primary 色
- **菜单项**:
  - 默认状态：透明背景，--text-secondary 图标和文字
  - 悬停状态：--bg-hover 背景，文字变亮
  - 选中状态：左侧3px --accent-primary 竖线 + 渐变背景
- **子菜单展开**: 带有微弱的展开/收起动画

### 3.3 顶栏改进

- **背景**: `--bg-surface` + 底部1px `--border-subtle`
- **折叠按钮**: 图标按钮，hover时背景变亮
- **产品线选择器**:
  - 深色下拉框样式
  - 边框: 1px --border-default
  - 下拉菜单: --bg-elevated 背景
- **用户区域**:
  - 头像：40px圆形，带1px --accent-primary 边框
  - 下拉菜单：深色背景，带阴影

### 3.4 内容区改进

- **背景**: `--bg-primary` + 微妙的网格纹理
- **卡片容器**: --bg-surface 背景，无默认边框
- **页面标题**: 24px, 600字重，--text-primary

---

## 4. 仪表盘页面设计

### 4.1 KPI 卡片区域

**布局**: 4列等宽，16px间距 (Row gutter)

**卡片样式**:
```
┌─────────────────────────────┐
│ ▓▓▓ (顶部3px状态色边框)      │
│                             │
│  📊 待办事项                 │
│                             │
│  ┌─────────────────────┐   │
│  │       12            │   │  ← 48px, JetBrains Mono
│  │    ─────────        │   │
│  └─────────────────────┘   │
│                             │
│  较昨日 +3                   │
└─────────────────────────────┘
```

**状态色边框映射**:
| 指标 | 边框颜色 |
|------|----------|
| 待办事项 | --accent-warning |
| 超期任务 | --accent-danger |
| 高风险项 | --accent-danger |
| 本月趋势 | 正数: --accent-success / 负数: --accent-danger |

**卡片交互**:
- 悬停：translateY(-4px) + 阴影增强
- 点击：导航到对应详情页
- 数字动画：从0滚动到目标值，1.5s ease-out

### 4.2 风险预警区域

**布局**: 3列等宽，16px间距

**卡片样式**:
- 标题：16px, 500字重，带右侧数量徽章
- 列表项：
  - 默认：透明背景
  - 悬停：--bg-elevated 背景
  - 圆角：4px
  - 内边距：12px 8px

**列表项内容**:
```
┌─────────────────────────────────────┐
│ PFMEA-2026-001          [RPN=240]  │  ← 编号：等宽字体
│ 结构功能失效                       │  ← 描述：--text-secondary
└─────────────────────────────────────┘
```

**标签样式**:
- 高RPN: --accent-danger 背景
- 超期天数: --accent-warning 背景
- PPM超标: --accent-warning 背景

### 4.3 最近操作区域

**时间线样式**:
```
│
●──── 2026-05-31 14:30
│     FMEA - PFMEA-2026-001
│     创建文档
│
●──── 2026-05-31 11:20
│     ...
```

**元素**:
- 时间线竖线：2px, --border-default
- 圆点：8px, 根据操作类型着色
- 操作描述：--text-secondary

### 4.4 快速入口区域

**按钮样式**:
- 主按钮：--accent-primary 背景，白色文字
- 次要按钮：--bg-elevated 背景，--text-primary 文字
- 悬停：亮度提升10%
- 圆角：6px
- 内边距：12px 24px

---

## 5. 通用组件样式

### 5.1 按钮

| 类型 | 样式 |
|------|------|
| Primary | --accent-primary 背景，白色文字 |
| Default | --bg-elevated 背景，--border-default 边框 |
| Text | 透明背景，hover时--bg-hover |
| Danger | --accent-danger 背景，白色文字 |

### 5.2 卡片

```css
.card {
  background: var(--bg-surface);
  border-radius: 8px;
  border: none;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
  transition: transform 0.2s, box-shadow 0.2s;
}

.card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
}
```

### 5.3 表格

- 表头：--bg-elevated 背景，--text-secondary 文字
- 表格行：默认透明，hover时--bg-hover
- 边框：底部 1px --border-subtle
- 斑马纹：奇数行 --bg-surface / 偶数行 微亮

### 5.4 表单

- 输入框：--bg-elevated 背景，--border-default 边框
- 聚焦时：--accent-primary 边框 + 微弱发光
- 标签：--text-secondary
- 错误状态：--accent-danger 边框

### 5.5 标签/徽章

| 类型 | 背景 | 文字 |
|------|------|------|
| 成功 | rgba(16, 185, 129, 0.15) | --accent-success |
| 警告 | rgba(245, 158, 11, 0.15) | --accent-warning |
| 危险 | rgba(239, 68, 68, 0.15) | --accent-danger |
| 信息 | rgba(59, 130, 246, 0.15) | --accent-primary |

---

## 6. 字体系统

### 6.1 字体族

```css
:root {
  --font-sans: system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-mono: "JetBrains Mono", "SF Mono", "Fira Code", monospace;
}
```

### 6.2 字体规格

| 用途 | 字体 | 大小 | 字重 | 行高 |
|------|------|------|------|------|
| 页面标题 | --font-sans | 24px | 600 | 1.2 |
| 区块标题 | --font-sans | 18px | 600 | 1.3 |
| 卡片标题 | --font-sans | 16px | 500 | 1.4 |
| 正文 | --font-sans | 14px | 400 | 1.5 |
| 辅助文字 | --font-sans | 12px | 400 | 1.4 |
| KPI数字 | --font-mono | 48px | 700 | 1 |
| 数据/编号 | --font-mono | 14px | 400 | 1.4 |

### 6.3 JetBrains Mono 引入

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
```

---

## 7. 动画系统

### 7.1 页面加载动画

**KPI卡片依次渐入**:
```css
@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.kpi-card:nth-child(1) { animation-delay: 0ms; }
.kpi-card:nth-child(2) { animation-delay: 100ms; }
.kpi-card:nth-child(3) { animation-delay: 200ms; }
.kpi-card:nth-child(4) { animation-delay: 300ms; }
```

**数字滚动动画**:
- 使用 `react-countup` 或自定义 React hook
- 从0滚动到目标值
- 持续时间：1.5s
- 缓动函数：ease-out

### 7.2 交互动画

**卡片悬停**:
```css
.card {
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}
```

**按钮点击**:
```css
.button:active {
  transform: scale(0.98);
}
```

**列表项悬停**:
```css
.list-item {
  transition: background-color 0.15s ease;
}

.list-item:hover {
  background-color: var(--bg-elevated);
}
```

### 7.3 过渡时间规范（使用 Ant Design Motion Token）

> **注意：** 不手写 CSS transition 时长，优先复用 AntD 内置 Motion Token，确保全系统动画节奏一致。

| 类型 | Ant Design Token | 值 | 用途 |
|------|-----------------|-----|------|
| 微交互（hover） | `token.motionDurationMid` | 0.2s | 卡片悬浮、列表项高亮 |
| 状态变化 | `token.motionDurationSlow` | 0.3s | 面板展开、下拉菜单 |
| 页面元素入场 | `token.motionDurationSlow` + stagger | 0.3s + delay | KPI卡片依次渐入 |
| 数字动画 | 自定义（requestAnimationFrame） | 1000-1500ms | useCountUp hook |

---

## 8. 响应式设计

### 8.1 断点

| 设备 | 断点 | 布局调整 |
|------|------|----------|
| 桌面端 | ≥1280px | 完整布局，侧边栏展开 |
| 小桌面 | 1024-1279px | 侧边栏折叠，内容区自适应 |
| 平板端 | 768-1023px | 2列KPI，侧边栏折叠 |
| 移动端 | <768px | 单列布局，底部导航 |

### 8.2 KPI卡片响应式

```css
/* 默认4列 */
.kpi-grid {
  grid-template-columns: repeat(4, 1fr);
}

/* 平板端2列 */
@media (max-width: 1023px) {
  .kpi-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* 移动端单列 */
@media (max-width: 767px) {
  .kpi-grid {
    grid-template-columns: 1fr;
  }
}
```

---

## 9. 实现计划

### 9.1 阶段一：主题基础（预计 2-3 小时）

1. 在 `App.tsx` 中配置 `ConfigProvider` 暗色主题（使用附录 11.2 完整配置）
2. 注册 ECharts 自定义 `industrialDark` 主题（见附录 11.4）
3. 引入 JetBrains Mono 字体
4. 在现有组件中用 `theme.useToken()` 替换硬编码颜色值

### 9.2 阶段二：布局与导航（预计 2-3 小时）

1. 改造 AppLayout 侧边栏样式
2. 改造顶栏样式
3. 添加背景网格纹理
4. 测试折叠/展开动画

### 9.3 阶段三：仪表盘页面（预计 3-4 小时）

1. 改造 KPI 卡片组件（使用 `token` 控制颜色和动画时长）
2. 实现 `useCountUp` hook（requestAnimationFrame，见附录 11.5）
3. 改造风险预警列表
4. 改造时间线样式
5. 实现页面加载 stagger 动画（使用 `token.motionDurationSlow`）

### 9.4 阶段四：通用组件（预计 2-3 小时）

1. 统一卡片样式
2. 统一按钮样式
3. 统一表单样式
4. 统一表格样式
5. 统一标签/徽章样式

### 9.5 阶段五：业务页面适配（预计 3-4 小时）

1. FMEA 列表/编辑页面
2. CAPA 列表/详情页面
3. SPC 控制图页面
4. 供应商管理页面
5. 其他页面通用样式检查

---

## 10. 验收标准

1. **视觉一致性**: 所有页面使用统一的深色主题
2. **可读性**: 文字对比度符合 WCAG AA 标准（≥4.5:1）
3. **动画流畅**: 无明显卡顿，动画不干扰操作
4. **响应式**: 在桌面、平板、移动端均正常显示
5. **功能完整**: 现有功能无回归问题
6. **性能**: 主题切换无闪烁，首屏加载时间无明显增加

---

## 11. 附录：Ant Design 主题配置

### 11.1 Token 体系说明

本设计**不使用原生 CSS 变量**（如 `--bg-surface`），而是将所有颜色定义映射到 Ant Design 5 的 Token 体系中，确保**单一事实来源（Single Source of Truth）**。实现时通过 `theme.useToken()` hook 获取颜色值，避免维护两套变量系统导致主题切换时状态不一致。

**设计概念 → Ant Design Token 映射表：**

| 设计概念 | Ant Design 全局 Token | 值 |
|---------|----------------------|-----|
| --bg-primary | `colorBgLayout` | #0a0e1a |
| --bg-surface | `colorBgContainer` | #111827 |
| --bg-elevated | `colorBgElevated` | #1f2937 |
| --text-primary | `colorText` | #f0f9ff |
| --text-secondary | `colorTextSecondary` | #94a3b8 |
| --text-muted | `colorTextTertiary` | #64748b |
| --border-subtle | `colorBorderSecondary` | rgba(148,163,184,0.1) |
| --border-default | `colorBorder` | rgba(148,163,184,0.2) |
| --accent-primary | `colorPrimary` | #3b82f6 |
| --accent-success | `colorSuccess` | #10b981 |
| --accent-warning | `colorWarning` | #f59e0b |
| --accent-danger | `colorError` | #ef4444 |

### 11.2 ConfigProvider 完整配置

```typescript
import { ConfigProvider, theme } from 'antd';

const darkTheme = {
  algorithm: theme.darkAlgorithm,
  token: {
    // 全局基础色
    colorPrimary: '#3b82f6',
    colorSuccess: '#10b981',
    colorWarning: '#f59e0b',
    colorError: '#ef4444',
    colorInfo: '#06b6d4',

    // 背景层级（映射设计概念）
    colorBgLayout: '#0a0e1a',       // 页面主背景
    colorBgContainer: '#111827',    // 卡片/面板背景
    colorBgElevated: '#1f2937',     // 悬浮/选中状态

    // 文字层级
    colorText: '#f0f9ff',
    colorTextSecondary: '#94a3b8',
    colorTextTertiary: '#64748b',

    // 边框
    colorBorder: 'rgba(148, 163, 184, 0.2)',
    colorBorderSecondary: 'rgba(148, 163, 184, 0.1)',

    // 圆角与字体
    borderRadius: 8,
    fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif',
    fontSize: 14,

    // 动画（复用 AntD Motion Token，不手写 CSS transition）
    motionDurationMid: '0.2s',      // 微交互 hover
    motionDurationSlow: '0.3s',     // 状态变化
  },
  components: {
    Layout: {
      headerBg: '#111827',           // 正确的 v5 Token 名
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

### 11.3 组件中获取 Token 的方式

```tsx
import { theme } from 'antd';

function MyComponent() {
  const { token } = theme.useToken();
  // 使用 token.colorBgContainer 而非 CSS 变量
  // 使用 token.motionDurationMid 而非手写 '0.2s'
  return <div style={{ background: token.colorBgContainer }} />;
}
```

### 11.4 图表暗黑模式适配

项目使用了 ECharts 和 @ant-design/charts，需要确保图表主题与深色 UI 融合。

**ECharts 暗黑主题：**

```typescript
import * as echarts from 'echarts';

// 注册自定义工业深色主题
echarts.registerTheme('industrialDark', {
  backgroundColor: 'transparent',              // 继承卡片背景
  textStyle: { color: '#94a3b8' },             // 对应 colorTextSecondary
  axisLine: { lineStyle: { color: 'rgba(148,163,184,0.2)' } },
  splitLine: { lineStyle: { color: 'rgba(148,163,184,0.1)' } },
  // ... 其他配置
});

// 初始化时使用
const chart = echarts.init(dom, 'industrialDark');
```

**Tooltip 背景融合：**

```typescript
tooltip: {
  backgroundColor: '#1f2937',       // 对应 colorBgElevated
  borderColor: 'rgba(148,163,184,0.2)',
  textStyle: { color: '#f0f9ff' },
}
```

**@ant-design/charts：** 使用其内置的 `theme` 属性传入暗黑配置，或通过 ConfigProvider 的 Token 自动继承。

### 11.5 数字滚动动画方案

**方案选择：** 为了减少外部依赖，使用自定义 `useCountUp` hook（基于 `requestAnimationFrame`），不引入 `react-countup`。

```typescript
function useCountUp(end: number, duration: number = 1500) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (end === 0) { setValue(0); return; }
    const startTime = performance.now();
    const animate = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // ease-out 缓动
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(Math.round(eased * end));
      if (progress < 1) requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  }, [end, duration]);
  return value;
}
```

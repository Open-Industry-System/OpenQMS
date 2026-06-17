# FMEA 管理页筛选功能设计

日期: 2026-06-17

## 背景与现状

FMEA 管理页（`frontend/src/pages/planning/fmea/FMEAListPage.tsx`）目前没有用户可操作的筛选 UI。后端 `list_fmeas` 已支持 `status`、`product_line`、`high_rpn` 三个筛选参数，其中 `product_line` 由全局 store 自动注入，`high_rpn` 仅通过预留的 URL 参数 `?risk=high` 触发（前端无入口），`status` 仅通过预留的 `?pending_approval=true` 触发。

grep 全前端确认：当前没有任何代码实际生成 `?risk=high` 或 `?pending_approval=true`，二者均为预留读取逻辑、无生产者。

表格列：文档编号、标题、类型、状态、版本、更新时间、操作。

## 目标

在 FMEA 管理页表格上方增加一行筛选栏，支持四个筛选维度，筛选状态同步到 URL（刷新保持、可分享），并兼容现有预留 URL 参数。

## 筛选维度

| 维度 | 控件 | 后端支持情况 |
|------|------|--------------|
| 状态 | Select（全部/草稿/审核中/已批准/返工/归档） | 已支持 `status` |
| 类型 | Select（全部/PFMEA/DFMEA） | **新增** `fmea_type` |
| 高风险 | Switch | 已支持 `high_rpn` |
| 关键词 | `Input.Search`（文档编号 + 标题模糊匹配） | **新增** `search` |

关键词匹配范围：文档编号 + 标题，不区分大小写模糊匹配。不含描述字段。

类型下拉选项与现有创建表单一致：PFMEA、DFMEA。

## UI 布局

顶部单行筛选栏，始终可见：

```
状态[全部▾] 类型[全部▾] 高风险[☐]  [🔍搜索关键词]  [重置]
─────────────────────────────────────────────────────
文档编号  标题  类型  状态  版本  时间  操作
...
```

关键词输入框采用 `Input.Search`，输入即搜（带防抖）+ 回车搜。

## 详细设计

### 1. 后端 — service 层

文件：`backend/app/services/fmea_service.py`，函数 `list_fmeas`

新增两个参数：
- `fmea_type: str | None = None`
- `search: str | None = None`

查询条件（同步加到 `query` 与 `count_query`）：
- `fmea_type` → `where(FMEADocument.fmea_type == fmea_type)`（精确匹配）
- `search` → `where(or_(FMEADocument.document_no.ilike(f"%{search}%"), FMEADocument.title.ilike(f"%{search}%")))`（不区分大小写）

`high_rpn` 分支会提前 return：该分支需在 Python 扫描 RPN **之前**先应用 `fmea_type` 与 `search` 的 where 条件（先 filter 再扫），避免对全表 500 条扫描后再丢弃。即把 `fmea_type`/`search` 的 where 应用到进入 `high_rpn` 分支前的 `query`。

### 2. 后端 — API 层

文件：`backend/app/api/fmea.py`，`list_fmeas` endpoint

新增两个 `Query` 参数：
- `fmea_type: str | None = None`
- `search: str | None = None`

透传给 service。

### 3. 前端 API client

文件：`frontend/src/api/fmea.ts`，`listFMEAs` 参数类型增加：
- `fmea_type?: string`
- `search?: string`

### 4. 前端页面

文件：`frontend/src/pages/planning/fmea/FMEAListPage.tsx`

#### 筛选栏控件
- 状态 Select：options 全部/草稿/审核中/已批准/返工/归档，value 对应 `""` / `draft` / `in_review` / `approved` / `rework` / `archived`
- 类型 Select：options 全部/PFMEA/DFMEA，value `""` / `PFMEA` / `DFMEA`
- 高风险 Switch
- 关键词 `Input.Search`，带防抖
- 重置按钮：清空所有筛选

#### 状态管理
- 筛选状态从 URL `searchParams` 初始化
- 任一筛选变化 → `setSearchParams` 写回 URL，参数名：`status`、`type`、`search`、`high_rpn`
- **兼容旧参数**（读取时一次性映射，不写回旧名）：
  - `risk=high` → `high_rpn=true`
  - `pending_approval=true` → `status=in_review`
- 任一筛选变化 → 重置到第 1 页并重新请求
- 保留现有 `product_line` 由全局 store 注入的逻辑

#### 请求组装
`fetchData` 从 URL 读取筛选值，组装 `listFMEAs` 调用：
- `status`：URL `status` 值或 undefined
- `fmea_type`：URL `type` 值或 undefined
- `high_rpn`：URL `high_rpn=true` 或旧 `risk=high`
- `search`：URL `search` 值或 undefined
- `product_line`：全局 store（不变）

#### 依赖触发
`useEffect` 监听 `productLine` 与 `searchParams`，变化时 `fetchData(1)`（保持现有结构）。

### 5. i18n

文件：`frontend/src/locales/zh-CN/fmea.json`（及对应 en）

新增 key（具体命名以现有 fmea.json 结构为准）：
- `filter.all` — 全部
- `filter.status` — 状态
- `filter.type` — 类型
- `filter.highRisk` — 高风险
- `filter.searchPlaceholder` — 搜索文档编号或标题
- `filter.reset` — 重置

状态/类型标签复用现有 `status.*` 与 `list.typeOption.*` key。

## 范围外

- 不改动表格列、创建表单、分页逻辑
- 不增加新的筛选维度（如时间范围、创建人）
- 不重构 `high_rpn` 的 Python 扫描实现（仅在它前面加 where 过滤）

## 验证

- 后端：`pytest tests/ -x` 相关 FMEA 测试通过
- 前端：`npm run build`（tsc --noEmit + vite build）通过
- 手动：状态/类型/关键词/高风险四维筛选各自生效；筛选变化 URL 同步；刷新保持筛选；从 `?risk=high` / `?pending_approval=true` 进入能正确映射；重置按钮清空全部筛选并回到第 1 页

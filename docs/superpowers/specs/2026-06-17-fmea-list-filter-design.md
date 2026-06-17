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

关键词匹配范围：文档编号 + 标题，不区分大小写模糊匹配。不含描述字段。`search` 入参先 `strip()`，为空字符串时不加 where 条件（避免生成 `ILIKE '%   %'` 这类无意义查询）。

类型下拉选项与现有创建表单一致：PFMEA、DFMEA。

## UI 布局

顶部单行筛选栏，始终可见：

```
状态[全部▾] 类型[全部▾] 高风险[☐]  [🔍搜索关键词]  [重置]
─────────────────────────────────────────────────────
文档编号  标题  类型  状态  版本  时间  操作
...
```

关键词输入框采用 `Input.Search`，通过 `onSearch` 回调触发（回车键 / 点击搜索按钮），**不**用 `onChange` 防抖——与项目其他列表页（如 `PLMPartsPage`）的 `Input.Search` 用法一致，避免新增防抖逻辑、减少后端压力。输入过程不触发请求。

## 详细设计

### 1. 后端 — service 层

文件：`backend/app/services/fmea_service.py`，函数 `list_fmeas`

> 前置：该文件当前 `from sqlalchemy import func, select`，未导入 `or_`，需补 import：`from sqlalchemy import func, or_, select`。

新增两个参数：
- `fmea_type: str | None = None`
- `search: str | None = None`

查询条件（同步加到 `query` 与 `count_query`）：
- `fmea_type` → `where(FMEADocument.fmea_type == fmea_type)`（精确匹配）
- `search` → 先 `search = search.strip()`；非空时转义 SQL 通配符再 ilike。注意：现有代码库所有 `ilike` 用法（spc/customer_audit/iqc 等 10+ 处）均未转义 `%`/`_`，属项目级遗留；本功能作为新增，率先修正：
  ```python
  import re
  safe = re.sub(r"([%_\\])", r"\\\1", search)
  query = query.where(or_(
      FMEADocument.document_no.ilike(f"%{safe}%", escape="\\"),
      FMEADocument.title.ilike(f"%{safe}%", escape="\\"),
  ))
  ```
  空字符串跳过，不加条件（避免 `ILIKE '%   %'`）。`re` 在文件顶部导入。

`high_rpn` 分支会提前 return：该分支需在 Python 扫描 RPN **之前**先应用 `fmea_type` 与 `search` 的 where 条件（先 filter 再扫），避免对全表 500 条扫描后再丢弃。具体位置：`fmea_service.py` 现有结构为 L30-44 依次追加 status/product_line/allowed_pls/factory_id 的 where，L46 `if high_rpn:` —— `fmea_type` 与 `search` 的 where 应追加在 L44 之后、L46 之前，这样两个分支（high_rpn 提前 return / 正常分页）都能带上这两个过滤。

### 2. 后端 — API 层

文件：`backend/app/api/fmea.py`，`list_fmeas` endpoint

新增两个 `Query` 参数：
- `fmea_type: Literal["PFMEA", "DFMEA"] | None = None` —— 用 `Literal` 而非裸 `str`，非法值（如 `fmea_type=foo`）由 FastAPI 直接返回 422，而非静默空结果。`Literal` 从 `typing` 导入。
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
- 关键词 `Input.Search`，`onSearch` 触发（见 UI 布局节）
- 重置按钮：清空所有筛选

#### 状态管理
现有页面只用 `const [searchParams] = useSearchParams()` 读取、未持有 `setSearchParams`，且旧参数 `risk` / `pending_approval` 仅在请求组装阶段读取。改造需同时处理受控控件的初始化与 URL 写回：

- 引入 `setSearchParams`：`const [searchParams, setSearchParams] = useSearchParams()`
- **统一读取函数**（受控控件初始值 + 请求组装共用同一来源），避免"请求生效但控件显示为未筛选"：
  - `status`：`searchParams.get("status")`，若无则回退旧参数 `pending_approval === "true"` → `in_review`
  - `high_rpn`：`searchParams.get("high_rpn") === "true"`，若无则回退旧参数 `risk === "high"`
  - `fmea_type`：`searchParams.get("type")`
  - `search`：`searchParams.get("search")`
- 受控控件（Select 的 `value`、Switch 的 `checked`、Input 的 `value`）初始值与变更值都从上述读取函数取，保证旧 URL 进入时控件也正确显示筛选态
- 任一筛选变化 → `setSearchParams` 写回 URL（参数名：`status`、`type`、`search`、`high_rpn`；**空值/关闭态一律剔除该参数，不写空串也不写 `false`**，保持 URL 简洁）+ **同时 `setPage(1)`**，再触发请求
- **兼容旧参数**：仅在读取时一次性映射，写回时一律用新参数名（`risk` / `pending_approval` 不再写回）
- **重置按钮**：清空 `status`/`type`/`search`/`high_rpn` 全部新参数，**并同时剔除残留的旧参数 `risk` / `pending_approval`**（防止从 `?risk=high` 进入后点重置仍残留），`setPage(1)` 并触发请求
- 保留现有 `product_line` 由全局 store 注入的逻辑

> 注意分页状态：现有 `useEffect` 只调用 `fetchData(1)` 不调用 `setPage(1)`，导致分页器 `current: page` 停在旧页、与实际第一页数据不一致。筛选变更时必须同时 `setPage(1)`。分页本身**不纳入 URL**（保持简单，仅筛选维度进 URL）。

#### 请求组装
`fetchData` 从上述统一读取函数取筛选值，组装 `listFMEAs` 调用。注意 URL 参数名与 API 参数名的映射（`type` → `fmea_type` 是唯一需重命名的一处）：

| URL 参数 | API 参数 | 备注 |
|----------|----------|------|
| `status` | `status` | 直传，含旧参数 `pending_approval` 回退 |
| `type` | `fmea_type` | **需映射重命名** |
| `search` | `search` | 直传 |
| `high_rpn` | `high_rpn` | 直传，含旧参数 `risk` 回退 |

`product_line` 由全局 store 注入（不变）。所有筛选值为空/未设时不传该参数。

#### 空状态与无障碍
- 搜索/筛选返回 0 条时，复用 Ant Design `Table` 默认空状态（`locale.emptyText`），不额外实现。
- 高风险 `Switch` 加 `aria-label`（i18n `filter.highRisk`），筛选栏用语义化容器包裹。不引入额外 a11y 改造。

#### 依赖触发
`useEffect` 监听 `productLine` 与 `searchParams`，变化时 `setPage(1)` + `fetchData(1)`。

### 5. i18n

文件：`frontend/src/locales/zh-CN/fmea.json` 与 `frontend/src/locales/en-US/fmea.json`（locale 目录为 `zh-CN` / `en-US`，非 `en`）。

新增 `filter` 命名空间下的 key（中 / 英）：

| key | zh-CN | en-US |
|-----|-------|-------|
| `filter.all` | 全部 | All |
| `filter.status` | 状态 | Status |
| `filter.type` | 类型 | Type |
| `filter.highRisk` | 高风险 | High Risk |
| `filter.searchPlaceholder` | 搜索文档编号或标题 | Search document no. or title |
| `filter.reset` | 重置 | Reset |

状态/类型标签复用现有 `status.*` 与 `list.typeOption.*` key。

## 范围外

- 不改动表格列、创建表单、分页大小与分页器交互（仅在筛选变更时 `setPage(1)` 回到首页，见状态管理节）
- 不增加新的筛选维度（如时间范围、创建人）
- 不重构 `high_rpn` 的 Python 扫描实现（仅在它前面加 where 过滤）

## 验证

- 后端：`cd backend && SECRET_KEY=test-secret-key pytest tests/test_fmea_state.py tests/test_spc_fmea_match.py -x`（仓库无根 `tests/`，后端测试在 `backend/tests/`；导入 `app.main` 需 `SECRET_KEY`，参考其他测试文件 `os.environ.setdefault` 写法）通过
- 前端类型检查/构建：`cd frontend && npm run build`（tsc --noEmit + vite build）通过
- 前端单测：新增 `frontend/src/pages/planning/fmea/FMEAListPage.test.tsx`（Vitest + Testing Library，仓库已配 `vitest` 命令且有多处 `*.test.tsx` 先例）。至少覆盖：
  - 从 `?risk=high` 进入 → 高风险 Switch 显示开启、请求带 `high_rpn`
  - 从 `?pending_approval=true` 进入 → 状态 Select 显示"审核中"、请求带 `status=in_review`
  - 改变某筛选 → URL 同步写入新参数、分页重置到第 1 页
  - 点重置 → 所有筛选清空、URL 参数剔除、回到第 1 页
- 运行前端测试：`cd frontend && npx vitest run src/pages/planning/fmea/FMEAListPage.test.tsx`
- 手动：状态/类型/关键词/高风险四维筛选各自生效；筛选变化 URL 同步；刷新保持筛选；从 `?risk=high` / `?pending_approval=true` 进入能正确映射；重置按钮清空全部筛选并回到第 1 页

# 8D / CAPA 模块 — 用户手册

> 最后更新: 2026-06-13 | 适用版本: OpenQMS v1.0

---

## 1. 功能概述

8D / CAPA（Corrective and Preventive Action）模块提供基于八步法 (Eight Disciplines) 的问题解决全流程管理，从团队组建到关闭归档，覆盖完整的 8D 报告生命周期。

核心能力：

| 能力 | 说明 |
|------|------|
| 8D 报告全流程 | D1 团队组建 → D2 问题描述 → D3 临时措施 → D4 根因分析 → D5 永久措施 → D6 实施验证 → D7 预防复发 → D8 关闭 |
| 状态流转控制 | 严格按序推进，D7/D8 需经理或管理员审批 |
| FMEA 关联 | 报告可关联到 FMEA 文档及具体失效节点，实现风险追溯 |
| AI 智能推荐 | D4/D5/D7 步骤可从关联 FMEA 图谱自动推荐根因、纠正措施和预防措施 |
| AI 草稿生成 | D2–D8 各步骤支持 AI 辅助内容草拟 |
| 经验教训检索 | 新建报告时可检索历史 CAPA / FMEA 的经验教训 |
| SCAR 联动 | 供应商导致的 CAPA 可通过 SCAR 模块向供应商发起纠正措施要求 |
| 产品线隔离 | 数据按产品线和工厂隔离，用户仅可见授权范围内的报告 |

**前端路由：**

| 页面 | 路由 | 说明 |
|------|------|------|
| 8D 报告列表 | `/capa` | 列表、筛选、新建 |
| 8D 报告详情 | `/capa/:id` | 步骤编辑、推进、FMEA 关联 |

---

## 2. 适用角色与权限

权限模型采用 **ModuleKey × PermissionLevel × 角色** 三级结构。CAPA 模块的 ModuleKey 为 `capa`。

PermissionLevel 含义：0 = NONE（不可见）、1 = VIEW（只读）、2 = CREATE（可新建）、3 = EDIT（可编辑内容）、4 = APPROVE（可审批 D7/D8 推进）、5 = ADMIN（完全控制）。

| ModuleKey | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|-----------|:-----:|:-------:|:--------:|:-----------:|:-----------:|:-----------:|:------:|
| capa | 5 | 4 | 3 | 1 | 2 | 2 | 1 |

**操作与最低权限对照：**

| 操作 | 所需 PermissionLevel | 说明 |
|------|---------------------|------|
| 查看 8D 列表/详情 | VIEW (1) | viewer、customer_qe、planning_qe 可查看 |
| 新建 8D 报告 | CREATE (2) | supplier_qe、customer_qe 及以上可新建 |
| 编辑报告内容 | EDIT (3) | field_qe 及以上可编辑各步骤字段 |
| 推进 D1–D6 步骤 | EDIT (3) | field_qe 及以上 |
| 推进 D7 → D8 | APPROVE (4) | manager、admin |
| 推进 D8 → 归档 | APPROVE (4) | manager、admin |
| 关联/更换 FMEA | EDIT (3) | field_qe 及以上 |
| AI 草稿生成 | EDIT (3) | field_qe 及以上 |
| D4/D5/D7 AI 推荐 | VIEW (1) + FMEA VIEW | 需同时拥有 CAPA VIEW 和 FMEA VIEW |

> 注意：`planning_qe` 仅有 VIEW 权限，无法编辑或推进报告。`supplier_qe` 和 `customer_qe` 可创建和编辑，但无法审批 D7/D8 推进。

---

## 3. 8D 流程详解

8D 方法论将问题解决过程分为八个标准步骤，每一步都有明确的目的和输入输出要求。OpenQMS 严格按此顺序控制流转。

### 3.1 D1 — 团队组建 (D1_TEAM)

**目的：** 组建跨职能团队，明确各成员职责，确保问题解决所需的技能和授权到位。

**状态：** `D1_TEAM`（报告创建后的初始状态）

**界面操作：**

- 以表格形式展示团队成员，每行包含 **成员姓名** 和 **项目职责**
- 职责选项：质量工程师、工艺工程师、研发工程师、项目经理、生产主管
- 点击「添加成员」按钮新增，点击行尾删除按钮移除

**数据结构：** `d1_team` 为 JSONB 数组，格式示例：

```json
[
  {"name": "张三", "role": "质量工程师"},
  {"name": "李四", "role": "工艺工程师"}
]
```

**流转条件：** 至少添加一名团队成员后，点击「推进下一步」进入 D2。

### 3.2 D2 — 问题描述 (D2_DESCRIPTION)

**目的：** 用 5W2H 方法准确描述问题：What（什么问题）、Who（谁发现/受影响）、When（何时发生）、Where（何地发生）、Why（为什么是问题）、How（如何发生）、How many（影响数量）。

**界面操作：**

- 文本编辑区（多行 TextArea），支持 5W2H 格式
- AI 草拟按钮：基于问题描述上下文，AI 可生成 D2 草稿
- 内容在 `onBlur` 时自动保存

**数据字段：** `d2_description` (Text)

### 3.3 D3 — 临时遏制措施 (D3_INTERIM)

**目的：** 在根因尚未明确之前，采取临时遏制措施 (Interim Containment Action) 防止问题扩大，保护客户和生产流程。

**典型内容：** 隔离不良品、100% 加检、临时切换替代供应商等。

**界面操作：**

- 文本编辑区（多行 TextArea）
- AI 草拟按钮：基于 D2 问题描述生成临时措施建议
- 内容在 `onBlur` 时自动保存

**数据字段：** `d3_interim` (Text)

### 3.4 D4 — 根因分析 (D4_ROOT_CAUSE)

**目的：** 通过 5Why、鱼骨图等方法找到问题的根本原因 (Root Cause)，区分技术原因和管理原因。

**界面操作：**

- **D4 AI 推荐面板** (`D4RecPanel`)：基于关联 FMEA 图谱和历史 CAPA，自动推荐可能的失效原因
  - 推荐来源包括：关联 FMEA 节点匹配、关键词匹配、语义搜索、历史 CAPA 相似案例
  - 点击「采纳」可将推荐文本追加到根因分析区域
- 文本编辑区（多行 TextArea），标注 "根因分析 (5Why / 鱼骨图)"
- AI 草拟按钮：基于上下文生成 D4 草稿
- 内容在 `onBlur` 时自动保存

**数据字段：** `d4_root_cause` (Text)

**D4 推荐接口：** `GET /api/capa/{report_id}/d4-fmea-recommendations`
- 需同时拥有 CAPA VIEW 和 FMEA VIEW 权限
- 返回字段：失效原因名称、描述、匹配来源、置信度、来源 CAPA 标识

### 3.5 D5 — 永久纠正措施 (D5_CORRECTION)

**目的：** 针对根因制定永久纠正措施 (Permanent Corrective Action)，彻底消除问题根因，而非仅控制症状。

**界面操作：**

- **D5 AI 推荐面板** (`D5RecPanel`)：基于关联 FMEA 图谱推荐两类内容
  - **已有控制措施**（来自 FMEA 预防/探测控制），可直接采纳
  - **通用建议**（AI 生成的预防措施、探测措施、纠正措施），含置信度
- 文本编辑区（多行 TextArea）
- AI 草拟按钮
- 内容在 `onBlur` 时自动保存

**数据字段：** `d5_correction` (Text)

**D5 推荐接口：** `GET /api/capa/{report_id}/d5-fmea-recommendations`
- 返回分为 `existing_controls`（FMEA 已有控制）和 `general_suggestions`（AI 建议措施）

### 3.6 D6 — 实施验证 (D6_VERIFICATION)

**目的：** 验证 D5 永久措施是否有效实施并消除了问题，确认改进前后数据对比。

**典型内容：** 措施实施日期、验证方法（数据对比、过程审核、客户反馈）、验证结论。

**界面操作：**

- 文本编辑区（多行 TextArea），标注 "效果验证"
- AI 草拟按钮
- 内容在 `onBlur` 时自动保存

**数据字段：** `d6_verification` (Text)

### 3.7 D7 — 预防复发 (D7_PREVENTION)

**目的：** 将 D5/D6 中验证有效的措施系统化、标准化，防止同类问题在其他产品线、工序或场景中复发。

**典型内容：** 更新 FMEA、修改控制计划、修订作业指导书、培训人员、更新检验标准。

**界面操作：**

- 文本编辑区（多行 TextArea），标注 "预防复发措施"
- **D7 FMEA 节点推荐面板** (`D7RecPanel`)：列出需更新的 FMEA 失效节点
  - 每个节点可标记为 "已更新" 或 "无需更新"
  - 只有全部推荐节点被确认后，「推进下一步」按钮才直接可用
  - 若存在未确认节点，系统弹出跳过确认对话框，要求填写跳过理由
- AI 草拟按钮
- 内容在 `onBlur` 时自动保存

**数据字段：** `d7_prevention` (Text)

**D7 推荐接口：** `GET /api/capa/{report_id}/d7-fmea-recommendations`
- 推荐来源：关联 FMEA 节点匹配 + 关键词匹配
- 返回字段：失效模式节点 ID/名称、失效原因节点 ID/名称、预防控制节点、匹配来源、建议预防措施

**D7 软门禁 (Soft Gate)：** 推进到 D8 之前，系统检查所有 D7 推荐的 FMEA 节点是否已确认。若存在未确认节点，需填写跳过理由后才能推进。跳过理由以审计日志记录 (`D7_SKIP_CONFIRMATION`)。

> D7 推进需要 APPROVE 权限（经理或管理员）。

### 3.8 D8 — 关闭 (D8_CLOSURE)

**目的：** 团队负责人确认所有措施有效、文件归档、团队解散，正式关闭 8D 报告。

**界面操作：**

- 文本编辑区（多行 TextArea），标注 "关闭确认"
- AI 草拟按钮
- 内容在 `onBlur` 时自动保存

**数据字段：** `d8_closure` (Text)

**特殊行为：**

- 报告进入 D8_CLOSURE 状态后，系统自动关闭关联的供应商风险预警 (`SupplierRiskAlert.status → "closed"`)
- D8 推进到 ARCHIVED 需要 APPROVE 权限

---

## 4. 状态流转

### 4.1 状态定义

| 状态值 | 中文标签 | 步骤序号 | 说明 |
|--------|----------|:--------:|------|
| `D1_TEAM` | D1 团队组建 | 0 | 初始状态，新建报告后进入 |
| `D2_DESCRIPTION` | D2 问题描述 | 1 | — |
| `D3_INTERIM` | D3 临时措施 | 2 | — |
| `D4_ROOT_CAUSE` | D4 根因分析 | 3 | — |
| `D5_CORRECTION` | D5 永久措施 | 4 | — |
| `D6_VERIFICATION` | D6 实施验证 | 5 | — |
| `D7_PREVENTION` | D7 预防复发 | 6 | 需经理或管理员审批推进 |
| `D8_CLOSURE` | D8 关闭 | 7 | 需经理或管理员审批推进 |
| `ARCHIVED` | 已归档 | 8 | 终态，不可回退 |

### 4.2 合法流转路径

```
D1_TEAM ──→ D2_DESCRIPTION ──→ D3_INTERIM ──→ D4_ROOT_CAUSE
                                              │         ↑
                                              │         │
                                              ↓         │
                                    D5_CORRECTION      │
                                              │         │
                                              ↓         │
                                    D6_VERIFICATION ──→ D5_CORRECTION（回退）
                                              │
                                              ↓
                                    D7_PREVENTION
                                              │
                                              ↓
                                    D8_CLOSURE
                                              │
                                              ↓
                                        ARCHIVED
```

**正向流转（默认）：** D1 → D2 → D3 → D4 → D5 → D6 → D7 → D8 → ARCHIVED

**允许的回退流转：**

| 当前状态 | 可回退到 |
|----------|----------|
| D2_DESCRIPTION | D1_TEAM |
| D4_ROOT_CAUSE | D3_INTERIM |
| D6_VERIFICATION | D5_CORRECTION |

回退操作通过 `PUT /api/capa/{report_id}` 更新状态字段实现（仅 D2→D1、D4→D3、D6→D5 有合法路径）。

### 4.3 权限门禁

| 推进操作 | 最低权限要求 | 后端校验逻辑 |
|----------|-------------|-------------|
| D1 → D2 | EDIT (3) | `advance_capa` — 正常推进 |
| D2 → D3 | EDIT (3) | `advance_capa` — 正常推进 |
| D3 → D4 | EDIT (3) | `advance_capa` — 正常推进 |
| D4 → D5 | EDIT (3) | `advance_capa` — 正常推进 |
| D5 → D6 | EDIT (3) | `advance_capa` — 正常推进 |
| D6 → D7 | EDIT (3) | `advance_capa` — 正常推进 |
| D7 → D8 | **APPROVE (4)** | `require_close_permission` 中间件拦截，检查 `user.role in [admin, manager]` |
| D8 → ARCHIVED | **APPROVE (4)** | 同上 |

> 前端按钮控制：当报告状态为 D7_PREVENTION 或 D8_CLOSURE 时，仅 `canApprove('capa')` 为 true 的用户可见「推进下一步」按钮。

### 4.4 推进 API

**请求：** `POST /api/capa/{report_id}/advance`

**请求体（可选）：**

```json
{
  "d7_skip_reasons": [
    {
      "fmea_id": "uuid",
      "node_id": "string",
      "reason": "跳过理由"
    }
  ]
}
```

- `d7_skip_reasons` 仅在 D7→D8 推进且存在未确认 FMEA 节点时使用
- 每次推进自动生成 `TRANSITION` 类型审计日志，记录旧状态和新状态

---

## 5. FMEA 关联

### 5.1 关联目的

将 8D 报告关联到 FMEA 文档（及具体失效节点），实现：

1. **D4/D5/D7 智能推荐** — 系统从关联的 FMEA 图谱中提取失效原因、控制措施和需更新的节点
2. **风险追溯** — 从 FMEA 报告可查看关联的 CAPA 报告
3. **D7 软门禁** — 推进到 D8 前确认相关 FMEA 节点已更新

### 5.2 关联操作

**前端操作：**

1. 在 8D 报告详情页右侧信息栏点击「关联 FMEA」按钮
2. 从下拉列表中选择 FMEA 文档（支持搜索）
3. 关联成功后页面显示绿色标签「已关联 FMEA」
4. 如需更换，点击「更换 FMEA 关联」重新选择

**后端 API：**

- 关联：`POST /api/capa/{report_id}/link-fmea?fmea_id={fmea_id}&fmea_node_id={node_id}`
  - 需要 CAPA EDIT 权限
  - 目标 FMEA 必须存在于用户可访问的工厂范围内
  - 关联操作记录 `LINK_FMEA` 审计日志
- 查询关联：`GET /api/capa/{report_id}/related-fmea`
  - 返回 `fmea_id`、`document_no`、`fmea_node_id`
- 按 FMEA 节点查询 CAPA：`GET /api/capa/by-fmea-node/{fmea_id}?fmea_node_id={node_id}`

### 5.3 数据字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `fmea_ref_id` | UUID (nullable) | 关联的 FMEA 文档 ID，外键指向 `fmea_documents.fmea_id` |
| `fmea_node_id` | String (nullable) | 关联的具体失效节点 ID，用于 D7 推荐精确定位 |

---

## 6. SCAR 联动

### 6.1 概述

当 8D 报告的根因指向供应商问题时，可通过 SCAR（Supplier Corrective Action Request）模块向供应商发起正式的纠正措施要求。SCAR 与 CAPA 通过 `capa_ref_id` 外键实现双向关联。

### 6.2 SCAR 关联 CAPA

**后端 API：** `POST /api/scars/{scar_id}/link-capa`

**请求体：**

```json
{
  "capa_ref_id": "uuid-of-capa-report"
}
```

- 需要 SCAR 模块的 CREATE 权限
- 关联后 SCAR 详情页显示关联的 8D 报告编号和链接

### 6.3 SCAR 状态流转

| 当前状态 | 操作 | 目标状态 | 所需权限 |
|----------|------|----------|----------|
| open | start | in_progress | CREATE (2) |
| in_progress | respond | responded | CREATE (2) |
| responded | verify | verified | APPROVE (4) |
| responded | reject | open | APPROVE (4) |
| verified | close | closed | APPROVE (4) |
| verified | reopen | in_progress | APPROVE (4) |

### 6.4 SCAR 发起来源

SCAR 可从以下来源自动或手动发起：

| 来源 | source_type | 说明 |
|------|-------------|------|
| IQC 不良 | `iqc` | 来料检验发现批次不良 |
| 客诉 | `complaint` | 客户投诉指向供应商责任 |
| RMA 退货 | `rma` | 退货分析指向供应商问题 |
| 手动 | `manual` | 直接在 SCAR 模块创建 |

### 6.5 CAPA 关闭时的 SCAR 联动

当 8D 报告状态推进到 `D8_CLOSURE` 时，系统自动关闭所有关联的、状态非 `closed` 的供应商风险预警：

```python
# capa_service.update_capa 内部逻辑
if capa.status == "D8_CLOSURE":
    await db.execute(
        update(SupplierRiskAlert)
        .where(SupplierRiskAlert.linked_capa_id == capa.report_id)
        .where(SupplierRiskAlert.status != "closed")
        .values(status="closed", handled_at=func.now())
    )
```

---

## 7. AI 辅助功能

### 7.1 AI 草稿生成

8D 报告的 D2–D8 各步骤支持 AI 辅助内容草拟，减少手动编写工作量。

**功能入口：** 每个步骤文本框右上角显示「AI 草拟」按钮

**操作流程：**

1. 点击「AI 草拟」按钮，选择草稿格式
2. 系统调用 `POST /api/capa/{report_id}/draft/{step}` 生成草稿
3. 草稿在预览面板中展示
4. 用户可选择「替换」或「追加」将 AI 草稿写入编辑区
5. 支持「撤销修改」回退到 AI 写入前的内容

**可草拟步骤：**

| 步骤 | API 路径 | 上下文输入 |
|------|----------|-----------|
| D2 | `/draft/d2` | 问题描述大纲 |
| D3 | `/draft/d3` | D2 内容 |
| D4 | `/draft/d4` | D2 + D3 内容 |
| D5 | `/draft/d5` | D4 根因 |
| D6 | `/draft/d6` | D5 纠正措施 |
| D7 | `/draft/d7` | D5 + D6 内容 |
| D8 | `/draft/d8` | 全流程摘要 |

**权限：** 需要 CAPA EDIT 权限

**能力查询：** `GET /api/capa/{report_id}/draft/capabilities`
- 返回 `{ ai_draft_enabled: bool, llm_provider: string | null }`
- D1_TEAM 和 ARCHIVED 状态不可用草拟功能

### 7.2 经验教训检索

新建 8D 报告后，系统自动弹出经验教训推荐面板 (`LessonsLearnedModal`)，从历史 CAPA 和 FMEA 中检索相似案例和经验。

**触发时机：** 从列表页创建报告后跳转到详情页时自动触发（携带 `problemDescription` 参数）

**API：** `POST /api/capa/{report_id}/lessons-learned`

**权限：** 需要 CAPA VIEW 权限；FMEA 来源数据需额外 FMEA VIEW 权限

### 7.3 D4/D5/D7 AI 推荐

详见各步骤章节中的推荐面板说明。三个推荐接口均需同时拥有 CAPA VIEW 和 FMEA VIEW 权限。

---

## 8. 报告列表与筛选

### 8.1 列表页

**路由：** `/capa`

**列表字段：**

| 列名 | 字段 | 说明 |
|------|------|------|
| 报告编号 | `document_no` | 格式：`8D-YYYY-NNN` |
| 标题 | `title` | — |
| 当前步骤 | `status` | 以 Tag 标签显示中文步骤名 |
| 严重等级 | `severity` | 彩色标签：致命(红)、严重(橙)、一般(蓝)、轻微(灰) |
| 期限 | `due_date` | 日期或"-" |
| 更新时间 | `updated_at` | — |

**严重等级配色：**

| 等级 | 颜色 |
|------|------|
| 致命 | red |
| 严重 | orange |
| 一般 | blue |
| 轻微 | default（灰色） |

### 8.2 筛选与排序

**API：** `GET /api/capa`

| 参数 | 类型 | 说明 |
|------|------|------|
| `page` | int | 页码（默认 1） |
| `page_size` | int | 每页数量（默认 20，最大 1000） |
| `status` | string | 按状态筛选 |
| `product_line` | string | 按产品线筛选 |
| `overdue` | bool | 仅显示逾期报告（到期日早于今天且未关闭/未归档） |
| `pending_action` | bool | 仅显示待处理报告（状态非 D8_CLOSURE/ARCHIVED） |

**产品线隔离：** 用户只能查看其授权产品线范围内的报告。若用户无可授权产品线，返回空列表。

### 8.3 新建报告

**弹窗表单字段：**

| 字段 | 必填 | 说明 |
|------|:----:|------|
| 标题 | 是 | 报告标题 |
| 报告编号 | 是 | 格式建议 `8D-YYYY-NNN`，需全局唯一 |
| 严重等级 | 否 | 默认 `一般`，可选：致命、严重、一般、轻微 |
| 到期日期 | 否 | 期望完成日期 |

**API：** `POST /api/capa`

**权限：** CAPA CREATE (2)

---

## 9. 常见问题

### Q1: 报告推进时提示"审批权限不足"

D7（预防复发）和 D8（关闭）步骤的推进需要 APPROVE (4) 级权限，即 `manager` 或 `admin` 角色。`field_qe`、`supplier_qe`、`customer_qe` 角色无法推进这两步。请联系经理或管理员操作。

### Q2: D7 推进时弹出"未确认 FMEA 节点"对话框

这是 D7 软门禁机制。当系统检测到关联 FMEA 中有待确认的失效节点时，会阻止直接推进。您需要：

1. 在 D7 推荐面板中逐个确认每个 FMEA 节点（标记为"已更新"或"无需更新"），或
2. 填写跳过理由后点击「确认跳过并推进」

跳过理由会记录在审计日志中。

### Q3: 如何将 CAPA 关联到 FMEA？

在 8D 报告详情页右侧信息栏点击「关联 FMEA」按钮，从下拉列表中选择 FMEA 文档。关联后可进一步指定具体的失效节点 (`fmea_node_id`)。若需更换关联，点击「更换 FMEA 关联」。

### Q4: 报告编号格式要求

`document_no` 需全局唯一。建议使用 `8D-YYYY-NNN` 格式（如 `8D-2026-001`）。重复编号会返回 400 错误。

### Q5: AI 草拟按钮灰色/不可用？

AI 草拟功能需要后端配置 LLM Provider。可通过 `GET /api/capa/{report_id}/draft/capabilities` 检查功能状态。若 `ai_draft_enabled` 为 `false`，表示未配置 LLM Provider。D1_TEAM 和 ARCHIVED 状态下也不可用。

### Q6: 产品线筛选不生效？

列表页按产品线筛选受权限控制。如果用户仅被授权部分产品线（`pl_scope.mode = EXPLICIT`），则只能看到这些产品线下的报告。若用户无任何产品线授权（`pl_scope.mode = NONE`），列表返回空。

### Q7: 如何从供应商问题发起 SCAR？

SCAR 不是从 CAPA 模块发起的。需要进入供应商管理模块（`/scars`），创建 SCAR 时指定 `source_type`（如 `complaint`、`iqc`、`rma`），然后通过 `POST /api/scars/{scar_id}/link-capa` 将 SCAR 关联到 CAPA 报告。详见 SCAR 模块文档。

### Q8: D8 关闭后关联的风险预警如何处理？

当 8D 报告推进到 D8_CLOSURE 状态时，系统自动将所有关联的、未关闭的供应商风险预警 (`SupplierRiskAlert`) 标记为 `closed`。此操作由后端自动完成，无需手动干预。

### Q9: 如何回退到上一步？

8D 流程支持有限的回退：

- D2 → D1
- D4 → D3
- D6 → D5

回退通过 `PUT /api/capa/{report_id}` 更新 `status` 字段实现。前端目前未提供回退按钮，需通过 API 调用。

### Q10: 审计日志记录了哪些操作？

每次操作均自动创建审计日志 (`audit_logs` 表，`table_name = capa_eightd`)：

| action | 说明 |
|--------|------|
| CREATE | 新建 8D 报告 |
| UPDATE | 编辑报告内容 |
| TRANSITION | 状态推进，记录 `old_status` 和 `new_status` |
| LINK_FMEA | 关联/更换 FMEA，记录 `old_fmea_ref_id` 和 `new_fmea_ref_id` |
| D7_SKIP_CONFIRMATION | D7 跳过未确认 FMEA 节点，记录 `skipped_nodes` |

---

## 附录：数据模型

### CAPAEightD 表 (`capa_eightd`)

| 字段 | 类型 | 说明 |
|------|------|------|
| `report_id` | UUID (PK) | 报告唯一标识 |
| `document_no` | String(50) | 报告编号，全局唯一 |
| `title` | String(200) | 报告标题 |
| `product_line_code` | String(20) | 产品线编码，默认 `DC-DC-100` |
| `factory_id` | UUID (FK) | 所属工厂 |
| `status` | String(20) | 当前状态，默认 `D1_TEAM` |
| `severity` | String(20) | 严重等级，默认 `一般` |
| `d1_team` | JSONB | 团队成员数组 `[{name, role}]` |
| `d2_description` | Text | 问题描述 |
| `d3_interim` | Text | 临时遏制措施 |
| `d4_root_cause` | Text | 根因分析 |
| `d5_correction` | Text | 永久纠正措施 |
| `d6_verification` | Text | 效果验证 |
| `d7_prevention` | Text | 预防复发措施 |
| `d8_closure` | Text | 关闭确认 |
| `fmea_ref_id` | UUID (FK, nullable) | 关联 FMEA 文档 |
| `fmea_node_id` | String(36, nullable) | 关联 FMEA 失效节点 |
| `due_date` | Date (nullable) | 到期日期 |
| `created_by` | UUID (FK, nullable) | 创建人 |
| `created_at` | DateTime(TZ) | 创建时间 |
| `updated_at` | DateTime(TZ) | 更新时间 |

### API 端点汇总

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/capa` | VIEW | 列表（支持分页、筛选） |
| POST | `/api/capa` | CREATE | 新建报告 |
| GET | `/api/capa/{id}` | VIEW | 报告详情 |
| PUT | `/api/capa/{id}` | EDIT | 更新报告内容 |
| POST | `/api/capa/{id}/advance` | D1-D6: EDIT, D7-D8: APPROVE | 推进到下一步 |
| POST | `/api/capa/{id}/link-fmea` | EDIT | 关联 FMEA |
| GET | `/api/capa/{id}/related-fmea` | VIEW | 查询关联的 FMEA |
| GET | `/api/capa/by-fmea-node/{fmea_id}` | VIEW | 按 FMEA 节点查询 CAPA |
| GET | `/api/capa/{id}/d4-fmea-recommendations` | VIEW + FMEA VIEW | D4 AI 推荐 |
| GET | `/api/capa/{id}/d5-fmea-recommendations` | VIEW + FMEA VIEW | D5 AI 推荐 |
| GET | `/api/capa/{id}/d7-fmea-recommendations` | VIEW + FMEA VIEW | D7 FMEA 节点推荐 |
| GET | `/api/capa/{id}/draft/capabilities` | VIEW | AI 草拟能力查询 |
| POST | `/api/capa/{id}/draft/{step}` | EDIT | 生成 AI 草稿 |
| GET | `/api/capa/capabilities` | VIEW | 模块 AI 能力查询 |
| POST | `/api/capa/{id}/lessons-learned` | VIEW | 经验教训检索 |
# FMEA/CP 版本管理设计文档

**日期**: 2026-05-25
**状态**: 设计阶段
**优先级**: P1

---

## 概述

为 FMEA 和控制计划（Control Plan）添加版本管理功能，支持版本历史追溯、变更对比、版本回退，以及 FMEA-CP 之间的版本强关联。

### 业务目标

- **审计追溯**：满足 IATF 16949 对 FMEA/CP 变更记录的要求
- **回退能力**：允许回退到历史版本以纠正错误变更
- **变更审核**：管理层可在审批前查看版本差异
- **知识保留**：保留历史版本供未来参考和学习

---

## 核心决策

| 决策项 | 选择 |
|--------|------|
| 版本触发时机 | 仅重大操作（提交审批、批准通过、手动标记） |
| 存储方式 | 全量快照存储 |
| 回退方式 | Git revert 模式（创建新版本） |
| 对比展示 | 并排对比视图（左右分屏） |
| FMEA-CP 关联 | 强关联（FMEA 变更时提醒 CP 同步更新） |
| 架构方案 | 独立版本表（非统一表） |

---

## 数据模型设计

### 新增表

#### `fmea_versions`

| 字段 | 类型 | 说明 |
|------|------|------|
| version_id | UUID PK | 版本记录 ID |
| fmea_id | UUID FK → fmea_documents | 关联的 FMEA 文档 |
| version_no | Integer | 版本号（与文档 version 字段同步） |
| snapshot | JSONB | 完整 graph_data 快照 |
| change_summary | Text | 变更摘要（手动填写或系统生成） |
| change_type | VARCHAR(20) | 触发类型：`submit`/`approve`/`manual`/`rollback` |
| created_by | UUID FK → users | 创建此版本的用户 |
| created_at | DateTime | 版本创建时间 |

索引：
- `(fmea_id, version_no)` UNIQUE — 同一 FMEA 的版本号唯一
- `(fmea_id, created_at DESC)` — 按时间倒序查询版本历史

#### `control_plan_versions`

| 字段 | 类型 | 说明 |
|------|------|------|
| version_id | UUID PK | 版本记录 ID |
| cp_id | UUID FK → control_plans | 关联的 CP 文档 |
| version_no | Integer | 版本号 |
| header_snapshot | JSONB | CP 头部字段快照（title, phase, part_no 等） |
| items_snapshot | JSONB | 完整 items 列表快照 |
| source_fmea_version_no | Integer NULL | 基于哪个 FMEA 版本生成 |
| change_summary | Text | 变更摘要 |
| change_type | VARCHAR(20) | 触发类型：`submit`/`approve`/`manual`/`rollback`/`fmea_sync` |
| created_by | UUID FK → users | 创建者 |
| created_at | DateTime | 创建时间 |

索引：
- `(cp_id, version_no)` UNIQUE
- `(cp_id, created_at DESC)`

### 现有表变更

#### `control_plans`

新增字段：
- `source_fmea_version_no` Integer NULL — 记录当前 CP 基于 FMEA 哪个版本生成
- `sync_pending` Boolean DEFAULT FALSE — 是否需要从关联 FMEA 同步更新

### 版本号规则

- 版本号从 1 开始，线性递增
- 回退操作也递增版本号（Git revert 模式）
- `change_type=rollback` 时，`change_summary` 包含 `rollback_from_version` 信息

---

## 服务层与 API 设计

### 版本创建触发点

| 触发时机 | change_type | 说明 |
|----------|-------------|------|
| FMEA 提交审批 | `submit` | 草稿 → 提交时自动创建快照 |
| FMEA 审批通过 | `approve` | 审批通过时创建快照，检查关联 CP 发出同步提醒 |
| FMEA 手动标记版本 | `manual` | 编辑界面"创建版本"按钮 |
| FMEA 回退 | `rollback` | 回退操作创建新版本 |
| CP 提交审批 | `submit` | 同 FMEA |
| CP 审批通过 | `approve` | 同 FMEA |
| CP 手动标记版本 | `manual` | 同 FMEA |
| CP 回退 | `rollback` | 同 FMEA |
| CP 从 FMEA 同步更新 | `fmea_sync` | FMEA 变更后 CP 执行同步，记录关联版本 |

### API 端点

#### FMEA 版本

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/api/fmea/{id}/versions` | 获取版本历史列表（倒序） | viewer+ |
| GET | `/api/fmea/{id}/versions/{version_no}` | 获取指定版本详情（完整快照） | viewer+ |
| POST | `/api/fmea/{id}/versions` | 手动创建版本 | engineer+ |
| POST | `/api/fmea/{id}/versions/{version_no}/rollback` | 回退到指定版本 | manager+ |
| GET | `/api/fmea/{id}/versions/compare?v1={n}&v2={m}` | 对比两个版本差异 | viewer+ |

请求/响应示例：

```python
# POST /api/fmea/{id}/versions — 手动创建版本
{
  "change_summary": "更新了过程步骤3的RPN值，增加了探测措施"
}

# Response
{
  "version_id": "uuid",
  "version_no": 3,
  "change_type": "manual",
  "change_summary": "...",
  "created_by": {...},
  "created_at": "2026-05-25T10:00:00Z"
}

# GET /api/fmea/{id}/versions/compare?v1=2&v2=3
{
  "v1": { "version_no": 2, "snapshot": {...} },
  "v2": { "version_no": 3, "snapshot": {...} },
  "diff": {
    "added_nodes": [...],
    "deleted_nodes": [...],
    "modified_nodes": [
      {
        "node_id": "node-123",
        "changes": [
          { "field": "severity", "old": 5, "new": 7 },
          { "field": "detection", "old": 3, "new": 2 }
        ]
      }
    ]
  },
  "summary": {
    "added": 0,
    "deleted": 0,
    "modified": 1
  }
}
```

#### CP 版本

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/api/control-plans/{id}/versions` | 版本历史列表 | viewer+ |
| GET | `/api/control-plans/{id}/versions/{version_no}` | 指定版本详情 | viewer+ |
| POST | `/api/control-plans/{id}/versions` | 手动创建版本 | engineer+ |
| POST | `/api/control-plans/{id}/versions/{version_no}/rollback` | 回退 | manager+ |
| GET | `/api/control-plans/{id}/versions/compare?v1={n}&v2={m}` | 对比差异 | viewer+ |

### FMEA-CP 强关联逻辑

FMEA 审批通过时（产生新版本）：
1. 查询所有 `fmea_ref_id` 指向该 FMEA 的 CP
2. 检查 CP 的 `source_fmea_version_no` 是否小于当前 FMEA 版本
3. 若是，设置 CP 的 `sync_pending = True`
4. 前端 CP 详情页展示同步提醒横幅
5. 用户点击"从 FMEA 同步"时：
   - 执行同步逻辑（复用现有 PFMEA → CP 生成逻辑）
   - 更新 CP 内容
   - 创建 `change_type=fmea_sync` 的版本
   - 更新 `source_fmea_version_no` 为当前 FMEA 版本
   - 清除 `sync_pending` 标记

---

## 前端设计

### 版本历史页面

在现有 FMEA/CP 详情页增加"版本历史" Tab（与编辑器 Tab 并列）：

**版本列表（左侧时间轴）**
- 每节点显示：
  - 版本号（如 v3）
  - 变更类型标签（颜色区分：`submit` 蓝色、`approve` 绿色、`manual` 灰色、`rollback` 橙色、`fmea_sync` 紫色）
  - 变更摘要文本
  - 操作人头像 + 姓名
  - 创建时间（相对时间 + hover 显示绝对时间）
- 每节点操作按钮：
  - "查看快照" — 新 Tab 打开只读快照视图
  - "对比" — 进入对比视图
  - "回退" — 仅最新版本且 manager/admin 权限可见

**手动创建版本**
- 时间轴顶部"创建版本"按钮
- 点击弹出 Modal：
  - 变更摘要（Textarea，必填）
  - 确认/取消按钮

### 并排对比视图

**布局**
- 顶部：版本选择器（两个下拉框，选择 v1 和 v2）
- 中部：左右分屏对比区域
- 底部：差异统计摘要栏

**FMEA 对比**
- 将两个版本的 `graph_data` 转换为表格行（复用 `fmeaTable.ts` 的 `graphToRows` 逻辑）
- 按 `nodeId` 对齐行
- 颜色规则：
  - 新增节点：绿色背景（`#f6ffed`）
  - 删除节点：红色背景 + 删除线（`#fff1f0`）
  - 修改节点：黄色背景（`#fffbe6`），具体变更字段高亮标注
- 差异高亮：
  - 修改单元格内显示："旧值 → 新值"格式
  - 如 severity 单元格显示："5 → 7"

**CP 对比**
- 按 `step_no` + `characteristic_no` 对齐 items 行
- 同样的颜色规则
- Header 字段（title, phase, part_no 等）在顶部单独区域对比

**差异统计**
- 顶部摘要栏显示："新增 0 项 / 修改 3 项 / 删除 0 项"
- 点击统计数字可跳转到对应类型的第一条差异

### FMEA-CP 同步提醒

**CP 详情页同步横幅**
- 位置：页面顶部，固定 Alert 横幅
- 样式：黄色警告样式（Ant Design Alert with type="warning"）
- 内容："关联的 FMEA 已更新至 v3（当前 CP 基于 FMEA v1），建议同步更新"
- 按钮：
  - "立即同步" — 跳转到同步预览页面
  - "忽略" — 关闭横幅，记录到版本历史

**同步预览页面**
- 展示 FMEA v1 → v3 的差异对比
- 展示同步后的 CP 预览（标记新增/修改/删除的 items）
- 确认/取消按钮

### 权限控制

| 操作 | viewer | engineer | manager | admin |
|------|--------|----------|---------|-------|
| 查看版本历史 | ✅ | ✅ | ✅ | ✅ |
| 查看版本对比 | ✅ | ✅ | ✅ | ✅ |
| 手动创建版本 | ❌ | ✅ | ✅ | ✅ |
| 执行回退 | ❌ | ❌ | ✅ | ✅ |
| FMEA-CP 同步 | ❌ | ✅ | ✅ | ✅ |

---

## 边界情况与约束

### 版本创建防护规则

1. **草稿状态才允许回退**
   - 已提交/已批准的文档需先撤回至草稿才能执行回退
   - API 层校验文档 `status == "draft"`

2. **回退需填写原因**
   - 确认 Modal 中 `change_summary` 必填
   - 格式：`"回退原因：{用户输入}。从 v{N} 回退"`

3. **回退不可链式**
   - 回退后的新版本需正常编辑后再创建下一版本
   - 不允许连续执行多次回退（防止版本号跳跃混乱）

4. **审批时自动创建版本不可跳过**
   - 即使文档没有实质性修改，提交审批也会创建快照
   - 保证审计完整性

### FMEA-CP 同步约束

- CP `sync_pending` 标记在执行同步后自动清除
- 同步时自动生成 `change_summary`："基于 FMEA v{N} 同步更新"
- 允许用户忽略同步提醒（关闭横幅），但在版本历史中记录"已忽略同步"事件
- 忽略后可手动重新触发同步

### 性能考量

- 版本列表 API 仅返回元数据，不返回 `snapshot` 字段
- 快照只在查看具体版本或对比时按需加载
- 预期版本数量：每个文档 10-50 个版本
- 快照大小：单条 10KB-500KB（FMEA graph_data 通常 50-200KB，CP items 通常 10-50KB）
- 总存储可控，无需分区或归档策略

---

## 实现路径

### 阶段一：数据层（后端）
1. 创建 `fmea_versions` 和 `control_plan_versions` 表（Alembic 迁移）
2. 修改 `control_plans` 表增加 `source_fmea_version_no` 和 `sync_pending` 字段
3. 创建 ORM 模型与 Pydantic schemas

### 阶段二：服务层（后端）
1. 实现版本创建逻辑（自动触发 + 手动触发）
2. 实现版本查询 API（列表、详情、对比）
3. 实现回退逻辑（包含防护规则校验）
4. 实现 FMEA-CP 强关联逻辑（审批通过时设置 `sync_pending`）
5. 实现 CP 同步逻辑（从 FMEA 更新 items）

### 阶段三：前端基础功能
1. 版本历史 Tab 与时间轴列表
2. 手动创建版本 Modal
3. 版本快照只读视图

### 阶段四：前端高级功能
1. 并排对比视图（FMEA 表格对比）
2. 并排对比视图（CP 表格对比）
3. 差异高亮与统计

### 阶段五：FMEA-CP 同步功能
1. CP 详情页同步提醒横幅
2. 同步预览页面
3. 同步执行与版本创建

---

## 测试要点

### 功能测试
- 版本自动创建（提交审批、审批通过）
- 版本手动创建（必填变更摘要）
- 版本回退（草稿状态、权限校验、原因记录）
- 版本对比（FMEA 节点增删改、CP items 增删改）
- FMEA-CP 同步（提醒触发、同步执行、版本记录）

### 权限测试
- viewer 无法创建版本或回退
- engineer 可创建版本但无法回退
- manager/admin 可执行所有操作

### 边界测试
- 回退非草稿文档（应拒绝）
- 回退到不存在的版本号（应拒绝）
- 对比相同版本号（应显示无差异）
- FMEA 无关联 CP 时的同步逻辑（应跳过）

### 性能测试
- 版本列表查询（50+ 版本的分页性能）
- 大型 FMEA 快照加载（500KB+ JSONB）
- 复杂版本对比（100+ 节点的差异计算）

---

## 验收标准

- [ ] FMEA 提交审批和审批通过时自动创建版本快照
- [ ] CP 提交审批和审批通过时自动创建版本快照
- [ ] 用户可手动创建版本并填写变更摘要
- [ ] 版本历史列表展示所有版本（倒序）
- [ ] 可查看任意版本的完整快照
- [ ] 可并排对比任意两个版本的差异（颜色标注增删改）
- [ ] manager/admin 可回退到历史版本（创建新版本）
- [ ] FMEA 审批通过时关联 CP 显示同步提醒
- [ ] CP 可执行 FMEA 同步并创建 `fmea_sync` 类型版本
- [ ] 所有版本操作记录到审计日志（AuditLog）
- [ ] 权限控制正确（viewer/engineer/manager/admin 分级）

---

## 未来扩展

- 版本备注标签（如 "量产前版本"、"客户审核版本"）
- 版本锁定（防止误删重要版本）
- 版本导出（PDF/Word 格式）
- 版本对比报告生成（用于管理评审）

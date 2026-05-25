# FMEA/CP 版本管理设计文档

**日期**: 2026-05-25
**状态**: 设计评审修订版
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
| 存储方式 | 全量快照存储 + SHA-256 防篡改校验 |
| 回退方式 | Git revert 模式（创建新版本）+ UUID 幂等性 Upsert |
| 对比展示 | 并排对比视图 + Diff 过滤器 + 影响链可视化 |
| FMEA-CP 关联 | 强关联（FMEA 变更时提醒 CP 同步更新）+ 字段级合并策略 |
| 版本号方案 | Major.Minor 双轨制（审批通过递增主版本，草稿操作递增副版本） |
| 架构方案 | 独立版本表 + Version UUID 强外键关联 |

---

## 数据模型设计

### 新增表

#### `fmea_versions`

| 字段 | 类型 | 说明 |
|------|------|------|
| version_id | UUID PK | 版本记录 ID |
| fmea_id | UUID FK → fmea_documents ON DELETE CASCADE | 关联的 FMEA 文档 |
| major_no | Integer NOT NULL | 主版本号（审批通过时递增） |
| minor_no | Integer NOT NULL DEFAULT 0 | 副版本号（提交/手动/回退时递增） |
| snapshot | JSONB NOT NULL | 完整 graph_data 快照 |
| sha256_hash | VARCHAR(64) NOT NULL | 快照防篡改校验哈希 |
| change_summary | Text NOT NULL | 变更摘要（手动填写或系统生成） |
| change_type | VARCHAR(20) NOT NULL | 触发类型：`submit`/`approve`/`manual`/`rollback` |
| created_by | UUID FK → users NOT NULL | 创建此版本的用户 |
| created_at | DateTime NOT NULL DEFAULT now() | 版本创建时间 |

索引：
- `(fmea_id, major_no, minor_no)` UNIQUE — 同一 FMEA 的版本号唯一
- `(fmea_id, created_at DESC)` — 按时间倒序查询版本历史

#### `control_plan_versions`

| 字段 | 类型 | 说明 |
|------|------|------|
| version_id | UUID PK | 版本记录 ID |
| cp_id | UUID FK → control_plans ON DELETE CASCADE | 关联的 CP 文档 |
| major_no | Integer NOT NULL | 主版本号 |
| minor_no | Integer NOT NULL DEFAULT 0 | 副版本号 |
| header_snapshot | JSONB NOT NULL | CP 头部字段快照（title, phase, part_no 等） |
| items_snapshot | JSONB NOT NULL | 完整 items 列表快照（保留原始 item_id UUID） |
| sha256_hash | VARCHAR(64) NOT NULL | 快照防篡改校验哈希 |
| source_fmea_version_id | UUID FK → fmea_versions.version_id ON DELETE SET NULL | 基于哪个 FMEA 版本生成（强外键） |
| change_summary | Text NOT NULL | 变更摘要 |
| change_type | VARCHAR(20) NOT NULL | 触发类型：`submit`/`approve`/`manual`/`rollback`/`fmea_sync` |
| created_by | UUID FK → users NOT NULL | 创建者 |
| created_at | DateTime NOT NULL DEFAULT now() | 创建时间 |

索引：
- `(cp_id, major_no, minor_no)` UNIQUE
- `(cp_id, created_at DESC)`

### 现有表变更

#### `control_plans`

新增字段：
- `source_fmea_version_id` UUID FK → fmea_versions.version_id ON DELETE SET NULL — 当前 CP 基于哪个 FMEA 版本生成
- `sync_pending` Boolean DEFAULT FALSE — 是否需要从关联 FMEA 同步更新

#### `control_plan_items`

新增字段：
- `item_source` VARCHAR(20) DEFAULT 'fmea' — 来源类型：`fmea`（由 FMEA 同步生成）或 `custom`（CP 界面手工创建）

### Major.Minor 双轨版本号规则

```
[v1.0 已发布] ──创建新草稿──> 变更 [v1.1 草稿] ──> 提交审批 [v1.2 草稿]
   ──> 审批通过 ──> [v2.0 已发布] ──> 修改提交 [v2.1 草稿] ──> 驳回修改 [v2.2 草稿]
   ──> 再次审批通过 ──> [v3.0 已发布]
```

- **主版本号（major_no）**：仅 `approve`（审批通过）时递增，对应 IATF 审计的正式发布版本
- **副版本号（minor_no）**：`submit`/`manual`/`rollback` 时递增，记录草稿阶段的修改历程
- **双轨优势**：审计视图只看 major 版本线（v1.0, v2.0, v3.0）极其干净；需要时展开 minor 版本追溯修改过程
- 版本列表默认只显示 major 版本，提供"展开所有版本"开关

### SHA-256 防篡改校验

创建版本快照时：
1. 将 snapshot JSONB 序列化为确定性字符串（sorted keys）
2. 计算 SHA-256 哈希并存入 `sha256_hash` 字段
3. 查看历史版本时，重新计算哈希与存储值比对
4. 不匹配则拒绝展示并记录安全告警到 AuditLog

---

## 服务层与 API 设计

### 版本创建触发点

| 触发时机 | change_type | 版本号变化 | 说明 |
|----------|-------------|------------|------|
| FMEA 提交审批 | `submit` | minor_no +1 | 草稿 → 提交时自动创建快照 |
| FMEA 审批通过 | `approve` | major_no +1, minor_no = 0 | 创建正式发布版本，检查关联 CP 发出同步提醒 |
| FMEA 手动标记版本 | `manual` | minor_no +1 | 编辑界面"创建版本"按钮 |
| FMEA 回退 | `rollback` | minor_no +1 | 回退操作创建新版本 |
| CP 提交审批 | `submit` | minor_no +1 | 同 FMEA |
| CP 审批通过 | `approve` | major_no +1, minor_no = 0 | 同 FMEA |
| CP 手动标记版本 | `manual` | minor_no +1 | 同 FMEA |
| CP 回退 | `rollback` | minor_no +1 | 同 FMEA |
| CP 从 FMEA 同步更新 | `fmea_sync` | minor_no +1 | 合并同步，记录关联 FMEA 版本 |

### API 端点

#### FMEA 版本

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/api/fmea/{id}/versions` | 版本历史列表（支持 `?major_only=true` 过滤） | viewer+ |
| GET | `/api/fmea/{id}/versions/{major}/{minor}` | 获取指定版本详情（含快照） | viewer+ |
| POST | `/api/fmea/{id}/versions` | 手动创建版本 | engineer+ |
| POST | `/api/fmea/{id}/versions/{major}/{minor}/rollback` | 回退到指定版本 | manager+ |
| GET | `/api/fmea/{id}/versions/compare?major1={m1}&minor1={n1}&major2={m2}&minor2={n2}` | 对比两个版本差异 | viewer+ |
| GET | `/api/fmea/{id}/versions/{major}/{minor}/verify` | 校验快照完整性（SHA-256） | manager+ |

#### CP 版本

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/api/control-plans/{id}/versions` | 版本历史列表 | viewer+ |
| GET | `/api/control-plans/{id}/versions/{major}/{minor}` | 指定版本详情 | viewer+ |
| POST | `/api/control-plans/{id}/versions` | 手动创建版本 | engineer+ |
| POST | `/api/control-plans/{id}/versions/{major}/{minor}/rollback` | 回退 | manager+ |
| GET | `/api/control-plans/{id}/versions/compare?...` | 对比差异 | viewer+ |
| GET | `/api/control-plans/{id}/versions/{major}/{minor}/verify` | 校验快照完整性 | manager+ |
| POST | `/api/control-plans/{id}/sync-from-fmea` | 执行 FMEA-CP 同步 | engineer+ |
| GET | `/api/control-plans/{id}/sync-preview` | 预览同步差异（不写入） | engineer+ |

请求/响应示例：

```python
# POST /api/fmea/{id}/versions — 手动创建版本
{
  "change_summary": "更新了过程步骤3的RPN值，增加了探测措施"
}

# Response
{
  "version_id": "uuid",
  "major_no": 2,
  "minor_no": 1,
  "change_type": "manual",
  "change_summary": "...",
  "sha256_hash": "a1b2c3...",
  "created_by": {...},
  "created_at": "2026-05-25T10:00:00Z"
}

# GET /api/fmea/{id}/versions/compare?major1=1&minor1=0&major2=2&minor2=0
{
  "v1": { "major_no": 1, "minor_no": 0, "snapshot": {...} },
  "v2": { "major_no": 2, "minor_no": 0, "snapshot": {...} },
  "diff": {
    "added_nodes": [...],
    "deleted_nodes": [...],
    "modified_nodes": [
      {
        "node_id": "node-123",
        "changes": [
          { "field": "severity", "old": 5, "new": 7 },
          { "field": "detection", "old": 3, "new": 2 }
        ],
        "impact_chain": [
          "RPN: 120 → 168"
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

### UUID 幂等性回退引擎（CP）

CP 回退时**必须保留 item_id UUID 不变**，防止下游模块（SPC、MSA、分层审核）的外键失效：

```python
async def rollback_control_plan(db: AsyncSession, cp_id: UUID, target_major: int, target_minor: int, user_id: UUID, reason: str):
    cp = await db.get(ControlPlan, cp_id)
    if cp.status != "draft":
        raise HTTPException(400, "只有草稿状态才允许回退")

    version = await db.execute(
        select(ControlPlanVersion).filter_by(cp_id=cp_id, major_no=target_major, minor_no=target_minor)
    )
    target = version.scalar_one()
    header_snap = target.header_snapshot
    items_snap = target.items_snapshot  # 含原始 item_id UUID

    # 更新头表（排除不可变字段）
    for key, val in header_snap.items():
        if hasattr(cp, key) and key not in ("cp_id", "created_at"):
            setattr(cp, key, val)

    # UUID 幂等性 Upsert：保留原始 item_id
    current_items = {item.item_id: item for item in cp.items}
    snap_items = {UUID(item["item_id"]): item for item in items_snap}

    # A. 删除快照中不存在的 items（外键约束会安全拦截）
    for item_id, item in current_items.items():
        if item_id not in snap_items:
            await db.delete(item)

    # B. 更新或重新插入，保留原始 UUID
    for item_id, snap_data in snap_items.items():
        if item_id in current_items:
            item = current_items[item_id]
            for field, val in snap_data.items():
                if hasattr(item, field) and field != "item_id":
                    setattr(item, field, val)
        else:
            new_item = ControlPlanItem(
                item_id=item_id, cp_id=cp_id,
                **{k: v for k, v in snap_data.items() if k != "item_id"}
            )
            db.add(new_item)

    # C. 递增副版本号，创建 rollback 版本记录
    cp.version += 1
    # ... 写入新版本记录
```

---

## FMEA-CP 强关联与合并同步策略

### 核心原则：字段级合并，非覆盖同步

CP 不是 FMEA 的影子。CP 中包含大量手工维护的字段（控制方法、检验频次、反应计划等），同步时必须按字段类别区分处理。

### `item_source` 字段区分来源

- `fmea`：该行由 FMEA 同步生成，可被后续同步覆盖
- `custom`：该行在 CP 界面手工创建，同步时完全保留不参与合并

### 字段级合并规则表

| 字段类别 | 数据来源 | 同步合并策略 |
|----------|----------|-------------|
| 过程步骤 / 产品特性 / 过程特性 / 关键分类 | 源自 FMEA | FMEA 变更时自动同步更新，界面高亮提示 |
| 设备 / 控制方法 / 样本容量 & 频次 / 反应计划 | CP 独有 | **绝对保留**，不被 FMEA 同步覆盖 |
| 特性编号（characteristic_no） | 混合 | 若 CP 用户已手动重编，保留 CP 编号 |
| 手工创建的行（`item_source=custom`） | CP 手工录入 | **完全保留**，不参与 FMEA 同步 |

### 对齐算法

同步或对比时，通过以下优先级对齐行：
1. **`source_fmea_node_id`**（对于从 FMEA 导入的行）— 精确匹配
2. **`item_id`**（对于已在 CP 中稳定存在的行）— 兜底匹配

### 同步流程

FMEA 审批通过时：
1. 查询所有 `fmea_ref_id` 指向该 FMEA 的 CP
2. 检查 CP 的 `source_fmea_version_id` 是否指向旧版本
3. 若是，设置 CP 的 `sync_pending = True`
4. 前端 CP 详情页展示同步提醒横幅

用户触发同步时：
1. **GET sync-preview** — 返回三向对比预览（CP 当前值 / FMEA 新增量 / 合并结果预览）
2. 用户在 Drawer 中逐项确认：`[✔ 接受同步]` 或 `[✖ 保持本地]`
3. **POST sync-from-fmea** — 执行确认后的合并写入
4. 创建 `change_type=fmea_sync` 的版本，记录 `source_fmea_version_id`
5. 更新 CP 的 `source_fmea_version_id` 指向新 FMEA 版本
6. 清除 `sync_pending` 标记

---

## 前端设计

### 版本历史页面

在现有 FMEA/CP 详情页增加"版本历史" Tab（与编辑器 Tab 并列）：

**版本列表（左侧时间轴）**
- 每节点显示：
  - 版本号（如 v2.0 或 v2.3）
  - 主版本标签：绿色"已发布"徽章（major 版本）
  - 副版本标签：灰色"草稿"徽章（minor 版本）
  - 变更类型标签（颜色区分：`submit` 蓝色、`approve` 绿色、`manual` 灰色、`rollback` 橙色、`fmea_sync` 紫色）
  - 变更摘要文本
  - 操作人头像 + 姓名
  - 创建时间（相对时间 + hover 显示绝对时间）
- 每节点操作按钮：
  - "查看快照" — 新 Tab 打开只读快照视图
  - "对比" — 进入对比视图
  - "回退" — 仅草稿状态 + manager/admin 权限可见
- "展开所有版本" 开关：默认只显示 major 版本线，展开后显示全部 minor 版本

**手动创建版本**
- 时间轴顶部"创建版本"按钮
- 点击弹出 Modal：变更摘要（Textarea，必填）+ 确认/取消按钮

### 并排对比视图

**布局**
- 顶部：版本选择器（两个下拉框，选择 v1 和 v2）
- 过滤器栏：`[只看修改项] [只看新增项] [只看删除项] [显示全部]`
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
- **影响链可视化**：修改严重度/频度/探测度时，显示级联影响："RPN: 120 → 168"

**CP 对比**
- 按 `source_fmea_node_id`（优先）或 `item_id` 对齐 items 行
- 同样的颜色规则
- Header 字段（title, phase, part_no 等）在顶部单独区域对比
- `item_source=custom` 的行标记为"手工行"，与 FMEA 同步行视觉区分

**差异统计**
- 顶部摘要栏显示："新增 0 项 / 修改 3 项 / 删除 0 项"
- 过滤器按钮可快速过滤只看特定类型的差异
- 点击统计数字可跳转到对应类型的第一条差异

### FMEA-CP 三向同步 Drawer

**同步提醒横幅**
- 位置：CP 详情页顶部，固定 Alert（type="warning"）
- 内容："关联的 FMEA 已更新至 v3.0（当前 CP 基于 FMEA v1.0），建议同步更新"
- 按钮："立即同步" / "忽略"

**三向合并 Drawer**
点击"立即同步"后从右侧滑出 Drawer：
1. **左侧列**：CP 当前值
2. **中间列**：FMEA 新版带来的增量变更项
3. **右侧列**：系统合并后的 CP 预览效果
- 每行可独立操作：`[✔ 接受同步]` 或 `[✖ 保持本地]`
- FMEA 源字段默认"接受同步"，CP 独有字段默认"保持本地"
- 底部确认按钮执行写入

### 权限控制

| 操作 | viewer | engineer | manager | admin |
|------|--------|----------|---------|-------|
| 查看版本历史 | ✅ | ✅ | ✅ | ✅ |
| 查看版本对比 | ✅ | ✅ | ✅ | ✅ |
| 手动创建版本 | ❌ | ✅ | ✅ | ✅ |
| 执行回退 | ❌ | ❌ | ✅ | ✅ |
| FMEA-CP 同步 | ❌ | ✅ | ✅ | ✅ |
| 校验快照完整性 | ❌ | ❌ | ✅ | ✅ |

---

## 边界情况与约束

### 版本创建防护规则

1. **草稿状态才允许回退**
   - 已提交/已批准的文档需先撤回至草稿才能执行回退
   - API 层校验文档 `status == "draft"`

2. **回退需填写原因**
   - 确认 Modal 中 `change_summary` 必填
   - 格式：`"回退原因：{用户输入}。从 v{M}.{N} 回退"`

3. **回退不可链式**
   - 回退后的新版本需正常编辑后再创建下一版本
   - 不允许连续执行多次回退

4. **审批时自动创建版本不可跳过**
   - 即使文档没有实质性修改，提交审批也会创建快照
   - 保证审计完整性

### FMEA-CP 同步约束

- CP `sync_pending` 标记在执行同步后自动清除
- 同步时自动生成 `change_summary`："基于 FMEA v{M}.{N} 同步更新"
- 允许用户忽略同步提醒（关闭横幅），版本历史中记录"已忽略同步"
- `item_source=custom` 的行在任何同步操作中完全保留
- 同步后 `source_fmea_version_id` 指向最新 FMEA 版本的 `version_id`

### 数据完整性

- **SHA-256 校验**：每次查看历史版本时校验快照哈希，不匹配则拒绝展示并告警
- **UUID 幂等性**：CP 回退时保留原有 item_id，通过 Upsert 而非 delete+insert 实现
- **强外键关联**：`source_fmea_version_id` 使用 UUID FK 直接关联 `fmea_versions.version_id`，FMEA 版本删除时 SET NULL
- **回退前引用检查**：FMEA 回退前检查是否有 CP 或其他模块引用当前 FMEA 的 graph 节点 ID。若存在活跃引用（`source_fmea_node_id`），在 API 响应中返回受影响的 CP 清单，要求用户确认后方可执行回退
- **快照存储上限**：每个文档保留最多 50 个版本快照。超出上限时，最早的 minor 版本（非 major 发布版本）自动归档为压缩存储（仅保留元数据 + 变更摘要，snapshot 字段清空），major 版本永久保留

### 性能考量

- 版本列表 API 仅返回元数据，不返回 `snapshot` 字段
- 快照只在查看具体版本或对比时按需加载
- `?major_only=true` 参数过滤只返回主版本线，减少数据量
- 预期版本数量：每个文档 10-50 个版本
- 快照大小：单条 10KB-500KB
- 当版本数超过 50 时，自动归档最早的 minor 版本（保留 major 发布版本），归档版本的 snapshot 字段清空仅保留元数据
- 总存储可控，无需分区或归档策略

---

## 实现路径

### 阶段一：数据层（后端）
1. 创建 `fmea_versions` 表（Alembic 迁移）
2. 创建 `control_plan_versions` 表（Alembic 迁移）
3. 修改 `control_plans` 表增加 `source_fmea_version_id` 和 `sync_pending` 字段
4. 修改 `control_plan_items` 表增加 `item_source` 字段
5. 创建 ORM 模型与 Pydantic schemas

### 阶段二：版本核心服务（后端）
1. 实现快照创建逻辑（含 SHA-256 哈希计算）
2. 实现版本查询 API（列表、详情、对比）
3. 实现版本对比 diff 算法（FMEA graph 节点对比 + CP items 对比）
4. 在现有 FMEA/CP 状态流转中集成自动版本创建（submit/approve 触发点）

### 阶段三：回退引擎（后端）
1. 实现 FMEA 回退逻辑（graph_data 整体替换）
2. 实现 CP UUID 幂等性 Upsert 回退引擎
3. 实现回退防护规则（状态校验、原因必填、链式回退拦截）
4. 实现快照完整性校验端点

### 阶段四：前端基础功能
1. 版本历史 Tab 与时间轴列表（含 major/minor 展开/折叠）
2. 手动创建版本 Modal
3. 版本快照只读视图

### 阶段五：前端高级功能
1. 并排对比视图（FMEA 表格对比 + Diff 过滤器）
2. 并排对比视图（CP 表格对比 + item_source 视觉区分）
3. 影响链可视化（RPN 级联变更提示）
4. 差异高亮与统计

### 阶段六：FMEA-CP 同步功能
1. 后端：同步预览 API（三向对比数据生成）
2. 后端：字段级合并同步执行逻辑
3. 前端：CP 详情页同步提醒横幅
4. 前端：三向合并 Drawer（逐项确认交互）
5. FMEA 审批通过时自动设置关联 CP 的 `sync_pending`

---

## 测试要点

### 功能测试
- 版本自动创建（提交审批 → minor+1，审批通过 → major+1）
- 版本手动创建（必填变更摘要）
- 版本回退（草稿状态、权限校验、原因记录）
- 版本对比（FMEA 节点增删改、CP items 增删改、影响链计算）
- 快照完整性校验（正常校验通过、篡改检测告警）
- major_only 过滤（列表只显示主版本线）

### 同步测试
- FMEA 审批通过 → 关联 CP 自动标记 `sync_pending`
- 同步预览生成三向对比数据
- 字段级合并：FMEA 源字段同步更新，CP 独有字段保留
- `item_source=custom` 行完全保留不受同步影响
- 同步后 `source_fmea_version_id` 正确指向新 FMEA 版本

### 回退安全性测试
- CP 回退保留 item_id UUID（下游 SPC/MSA 外键不断裂）
- 回退非草稿文档（应拒绝）
- 回退到不存在版本（应拒绝）
- 对比相同版本（应显示无差异）
- 无关联 CP 时的同步逻辑（应跳过）

### 权限测试
- viewer 无法创建版本、回退、同步
- engineer 可创建版本和同步但无法回退
- manager/admin 可执行所有操作
- viewer 无法调用校验端点

### 性能测试
- 版本列表查询（50+ 版本 + major_only 过滤）
- 大型 FMEA 快照加载（500KB+ JSONB）
- 复杂版本对比（100+ 节点的差异计算）
- 三向同步预览（50+ items 的合并预览生成）

---

## 验收标准

- [ ] FMEA 提交审批时自动创建 minor 版本快照
- [ ] FMEA 审批通过时自动创建 major 版本快照
- [ ] CP 提交审批和审批通过时自动创建对应版本快照
- [ ] 用户可手动创建版本并填写变更摘要
- [ ] 版本历史列表支持 major/minor 双轨展示（默认只显示 major，可展开）
- [ ] 可查看任意版本的完整快照（含 SHA-256 完整性校验）
- [ ] 可并排对比任意两个版本的差异（颜色标注增删改 + Diff 过滤器）
- [ ] 修改 S/O/D 值时显示 RPN 影响链
- [ ] manager/admin 可回退到历史版本（创建新版本，CP 保留 item_id UUID）
- [ ] FMEA 审批通过时关联 CP 显示同步提醒横幅
- [ ] CP 三向合并 Drawer 支持逐项确认同步/保留
- [ ] 同步时 FMEA 源字段更新、CP 独有字段保留、custom 行完全不受影响
- [ ] 所有版本操作记录到审计日志（AuditLog）
- [ ] 权限控制正确（viewer/engineer/manager/admin 分级）

---

## 未来扩展

- 版本备注标签（如 "量产前版本"、"客户审核版本"）
- 版本锁定（防止误删重要版本）
- 版本导出（PDF/Word 格式）
- 版本对比报告生成（用于管理评审）
- 电子签名集成（21 CFR Part 11 合规）

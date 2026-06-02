# 多人协同编辑模块设计文档

**日期:** 2026-06-02  
**范围:** 全文档类型（FMEA、Control Plan、CAPA 8D、APQP 等）  
**方案:** 乐观锁冲突提示（B）+ 轻量在线状态（D），短轮询 MVP，后续可升级 WebSocket  

---

## 1. 设计目标

- 解决多人同时编辑同一文档时的保存冲突问题
- 提供轻量在线状态，显示谁正在查看/编辑文档及具体编辑区域
- 不阻断编辑（非强制只读），让用户自主决定如何处理冲突
- 通用化设计，所有文档类型复用同一套协同基础设施
- 为未来升级到实时协同预留扩展点

## 2. 核心决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 协同模式 | 乐观锁 + 在线状态 | FMEA 是结构化图数据，实时协同需要业务规则支撑冲突合并，复杂度高风险大 |
| 数据传输 | 短轮询 MVP（15s），预留 WebSocket 升级路径 | 快速验证需求，后续可平滑替换传输层 |
| 编辑区域提示 | 行/字段级（FMEA 行 key + 字段名） | 精确到用户正在编辑的位置，帮助其他人避让 |
| 冲突处理 | 差异预览 + 用户选择覆盖/放弃 | 让用户了解对方修改内容后再做决定，避免盲目覆盖 |
| 覆盖范围 | 所有文档编辑器 | 通用组件，后续扩展只需"打开开关" |

## 3. 数据库模型

### 3.1 新增表 `collaboration_sessions`

```sql
CREATE TABLE collaboration_sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_type VARCHAR(30) NOT NULL,        -- 'fmea', 'control_plan', 'capa', etc.
    document_id UUID NOT NULL,                 -- 对应文档的 PK
    user_id UUID REFERENCES users(user_id),
    user_name VARCHAR(50),                     -- 冗余，避免 JOIN
    action VARCHAR(20) DEFAULT 'viewing',      -- 'viewing' | 'editing' | 'idle'
    editing_area JSONB DEFAULT NULL,           -- 灵活存储编辑区域
    last_activity TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    UNIQUE(document_type, document_id, user_id)
);

CREATE INDEX idx_collab_doc ON collaboration_sessions(document_type, document_id);
CREATE INDEX idx_collab_activity ON collaboration_sessions(last_activity);
```

### 3.2 设计说明

- **`document_type` + `document_id`**：通用主键，适用于所有文档类型
- **`editing_area` JSONB**：灵活存储不同文档类型的"编辑区域"
  - FMEA: `{ "row_key": "row_xxx", "field": "severity", "node_id": "n123" }`
  - CAPA: `{ "section": "d4_root_cause" }`
  - Control Plan: `{ "row_id": "cp_001", "column": "control_method" }`
- **冗余 `user_name`**：在线用户列表只读场景，避免每次查询 JOIN users 表
- **心跳驱动**：前端定期 POST `/heartbeat`，后端更新 `last_activity`

### 3.3 会话清理

- **定时清理**：后端每 60 秒删除 `last_activity < now() - interval '60 seconds'` 的记录
- **主动清理**：前端页面卸载时（`beforeunload`）发送同步 DELETE 请求立即移除会话
- **唯一约束**：同一用户同一文档只有一个会话（多标签页时后者覆盖前者）

## 4. API 设计

### 4.1 心跳上报

```
POST /api/collaboration/heartbeat
Authorization: Bearer <token>
Content-Type: application/json

{
  "document_type": "fmea",
  "document_id": "uuid",
  "action": "editing",
  "editing_area": {
    "row_key": "row_func_fm",
    "field": "severity",
    "node_id": "n123"
  }
}
```

**响应:** `204 No Content`

**行为:**
- `document_type` + `document_id` + `user_id` 唯一，UPSERT 模式
- 更新 `last_activity` 和 `editing_area`
- 如果 `action` 从 `editing` 变为 `viewing`，清空 `editing_area`

### 4.2 获取在线用户（短轮询）

```
GET /api/collaboration/{document_type}/{document_id}/active-users
Authorization: Bearer <token>
```

**响应:**

```json
{
  "users": [
    {
      "user_id": "uuid",
      "user_name": "张三",
      "action": "editing",
      "editing_area": {
        "row_key": "row_func_fm",
        "field": "severity"
      }
    }
  ],
  "total": 1
}
```

**轮询策略:**
- 正常状态：每 15 秒轮询
- 用户正在编辑：缩短到 8 秒
- 页面失焦（`document.hidden`）：延长到 30 秒
- 页面重新聚焦：立即轮询一次

### 4.3 保存冲突响应增强

复用现有 `lock_version` 乐观锁机制，冲突时返回额外信息：

```json
// 409 Conflict
{
  "detail": "Document has been modified by another user.",
  "conflict": {
    "saved_by": "张三",
    "saved_at": "2026-06-02T14:30:00+08:00",
    "their_changes_summary": {
      "nodes_added": 1,
      "nodes_modified": 2,
      "nodes_deleted": 0,
      "modified_fields": ["severity", "occurrence"]
    }
  }
}
```

### 4.4 差异对比端点

```
GET /api/fmea/{id}/diff?base_version={lock_version}&their_version={latest_version}
Authorization: Bearer <token>
```

**响应:**

```json
{
  "their_changes": [
    {
      "type": "node_modified",
      "node_id": "n123",
      "field": "severity",
      "old_value": 7,
      "new_value": 8
    },
    {
      "type": "node_added",
      "node_id": "n456",
      "node_type": "FailureMode",
      "name": "新失效模式"
    },
    {
      "type": "edge_added",
      "source": "n123",
      "target": "n456",
      "edge_type": "CAUSE_OF"
    }
  ]
}
```

> **注:** 差异对比使用 `lock_version` 字段作为版本标识。后端在保存成功时自动递增 `lock_version`，并记录每个版本的 snapshot（可复用现有 `fmea_versions` 机制或新增轻量版本记录）。

### 4.5 WebSocket 升级路径（预留）

```
GET /ws/collaboration/{document_type}/{document_id}
```

后续升级时，心跳和在线用户推送全部走 WebSocket，`/active-users` 轮询端点保留作为 fallback。

### 4.6 新增后端文件

```
backend/app/
  models/
    collaboration_session.py    # CollaborationSession 模型
  schemas/
    collaboration.py            # HeartbeatRequest, ActiveUserResponse, etc.
  api/
    collaboration.py            # 路由（heartbeat, active-users）
  services/
    collaboration_service.py    # 业务逻辑 + 会话清理定时任务
```

## 5. 前端组件架构

### 5.1 `useCollaboration(docType, docId)` Hook

```typescript
export interface EditingArea {
  row_key?: string;
  field?: string;
  node_id?: string;
  section?: string;
  column?: string;
}

export interface ActiveUser {
  user_id: string;
  user_name: string;
  action: 'viewing' | 'editing' | 'idle';
  editing_area: EditingArea | null;
}

export interface CollaborationState {
  activeUsers: ActiveUser[];
  currentUserEditing: boolean;
  isSyncing: boolean;      // 轮询是否正常工作
  startEditing: (area: EditingArea) => void;
  stopEditing: () => void;
}

export function useCollaboration(
  documentType: string,
  documentId: string
): CollaborationState;
```

**职责:**
- 管理心跳轮询（动态间隔）
- 管理本地 `editing_area` 状态
- 页面卸载时发送同步 DELETE 清理会话
- 返回在线用户列表和同步状态

### 5.2 `CollaborationBar` 组件

顶部在线用户列表，显示：
- 在线用户头像组（`Avatar.Group`）
- 编辑中用户绿色边框高亮
- 在线人数统计
- 同步状态指示器（轮询正常/失败）

### 5.3 `ActiveUserIndicator` 组件

行/字段级编辑提示：
- 接收 `row_key`、`field`、`activeUsers`
- 筛选出正在编辑该区域的用户
- 显示 `"某某正在编辑"` 标签
- 无编辑者时返回 `null`

### 5.4 `ConflictResolutionModal` 组件

冲突处理弹窗：
- 显示冲突信息（谁、何时保存）
- 显示差异摘要（新增/修改/删除统计）
- 可选：展开显示详细差异列表
- 两个操作按钮：
  - **放弃我的更改，刷新页面**：重新加载最新版本
  - **强制保存（覆盖对方更改）**：使用最新 `lock_version` 重新提交

### 5.5 各编辑器集成方式

以 FMEA 为例，需要修改：

1. **页面顶部**添加 `<CollaborationBar />`
2. **表格单元格**添加 `onFocus`/`onBlur` 驱动心跳：
   ```tsx
   <InputNumber
     onFocus={() => startEditing({ row_key: row.key, field: 'severity' })}
     onBlur={stopEditing}
   />
   ```
3. **单元格内**添加 `<ActiveUserIndicator />`
4. **保存逻辑**增强：捕获 409 错误，弹出 `<ConflictResolutionModal />`

**集成工作量:**

| 编辑器 | 预估行数 | 说明 |
|--------|---------|------|
| FMEA | ~30 行 | 最复杂，Table 每列需加 onFocus/onBlur |
| Control Plan | ~20 行 | 类似 FMEA，列数较少 |
| CAPA 8D | ~15 行 | 分区块编辑，editing_area 用 section |
| 其他模块 | ~10 行/个 | 简单表单，只需顶部 CollaborationBar |

### 5.6 新增前端文件

```
frontend/src/
  components/collaboration/
    CollaborationBar.tsx
    ActiveUserIndicator.tsx
    ConflictResolutionModal.tsx
    index.ts
  hooks/
    useCollaboration.ts
    useConflictResolution.ts   # 封装冲突检测 + 差异获取
  api/
    collaboration.ts           # heartbeat, getActiveUsers
  types/
    collaboration.ts           # 协同相关类型定义
```

## 6. 数据流

```
用户 A（编辑中）          后端                    用户 B（查看中）
    |                      |                         |
    |-- onFocus(severity) -|-------------------------|
    |-- POST /heartbeat --->| 更新 session            |
    |<--- 204 --------------|                         |
    |                      |<-- GET /active-users ----|
    |                      |  返回 A 的 editing_area |
    |                      |--- 200 ----------------->|
    |                      |                         |
    |                      |                         |-- 渲染 ActiveUserIndicator
    |                      |                         |   "张三 正在编辑 severity"
    |                      |                         |
    |-- onBlur() ----------|-------------------------|
    |-- POST /heartbeat --->| 清除 editing_area       |
    |<--- 204 --------------|                         |
    |                      |                         |
    |-- save() ------------|-------------------------|
    |-- PUT /fmea/{id} ---->| lock_version=5          |
    |                      |                         |
    |                      |  同时 B 也保存了！        |
    |                      |  lock_version 已变为 6    |
    |                      |                         |
    |<--- 409 Conflict -----|                         |
    |    {conflict: {...}} |                         |
    |                      |                         |
    |-- GET /diff?v=5,6 --->|                         |
    |<--- diff 结果 --------|                         |
    |                      |                         |
    |-- 弹出 ConflictModal -|-------------------------|
    |   用户选择覆盖/放弃    |                         |
```

## 7. 错误处理

| 场景 | 行为 |
|------|------|
| 心跳失败（网络抖动） | 静默重试 3 次，超过后标记为离线，不阻断编辑 |
| 轮询失败 | 同上，UI 显示"协同状态同步失败"但不阻断编辑操作 |
| 保存冲突（409） | 弹出 `ConflictResolutionModal`，用户必须选择处理方案 |
| 强制覆盖保存 | 使用最新 `lock_version` 重新提交，成功后刷新本地状态 |
| 后端会话清理延迟 | 用户关闭页面后最多 60 秒仍在在线列表（可接受） |
| 同一用户多标签页 | 后者覆盖前者，`UNIQUE` 约束保证单一会话 |
| 用户未登录/token 过期 | 心跳/轮询返回 401，前端跳转到登录页 |

## 8. 数据库迁移

```python
"""add collaboration_sessions table

Revision ID: xxx
Revises: 上一个 revision
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():
    op.create_table(
        'collaboration_sessions',
        sa.Column('session_id', sa.UUID(), nullable=False),
        sa.Column('document_type', sa.String(30), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('user_name', sa.String(50), nullable=True),
        sa.Column('action', sa.String(20), server_default='viewing'),
        sa.Column('editing_area', postgresql.JSONB(), nullable=True),
        sa.Column('last_activity', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('session_id'),
        sa.UniqueConstraint('document_type', 'document_id', 'user_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
    )
    op.create_index('idx_collab_doc', 'collaboration_sessions', ['document_type', 'document_id'])
    op.create_index('idx_collab_activity', 'collaboration_sessions', ['last_activity'])


def downgrade():
    op.drop_index('idx_collab_activity', table_name='collaboration_sessions')
    op.drop_index('idx_collab_doc', table_name='collaboration_sessions')
    op.drop_table('collaboration_sessions')
```

## 9. 性能与扩展

### 9.1 性能估算

- **心跳 QPS**：假设 50 并发用户 × (1/15s) ≈ **3.3 QPS**，极低负载
- **轮询 QPS**：假设 50 并发文档 × 平均 2 人在线 × (1/15s) ≈ **6.7 QPS**
- **数据库写入**：仅心跳时 UPSERT，读远大于写
- **内存占用**：`collaboration_sessions` 表记录数 ≈ 在线用户数，通常 < 100 条

### 9.2 Redis 扩展路径

项目已配置 Redis 但未使用。如需扩展：
- 将 `collaboration_sessions` 缓存到 Redis（Hash 结构，key = `{doc_type}:{doc_id}`）
- 设置 TTL = 60s，自然过期无需手动清理
- 心跳改为 Redis HSET，轮询改为 Redis HGETALL
- 大幅降低数据库压力

### 9.3 WebSocket 升级路径

1. 新增 `/ws/collaboration` WebSocket 端点
2. 连接建立时：发送当前文档的在线用户列表快照
3. 心跳改为 WebSocket message
4. 用户状态变更时：服务器主动 push 给同一文档的所有连接
5. 轮询端点保留作为 fallback（检测 WebSocket 不可用时降级）

## 10. 验收标准

- [ ] 打开 FMEA 编辑器，顶部显示在线用户列表
- [ ] 另一用户打开同一 FMEA，双方都能看到对方在线
- [ ] 用户点击编辑某单元格，对方在同一行看到"某某正在编辑"提示
- [ ] 用户 A 保存后，用户 B 保存时收到 409 冲突响应
- [ ] 冲突弹窗显示对方修改摘要和详细差异
- [ ] 用户 B 选择"放弃并刷新"后，页面重新加载最新数据
- [ ] 用户 B 选择"强制保存"后，成功覆盖并更新 lock_version
- [ ] 用户关闭页面后，60 秒内从在线列表消失
- [ ] Control Plan、CAPA 等其他编辑器同样支持协同状态显示
- [ ] 构建和 lint 无错误

## 11. 后续扩展方向

1. **WebSocket 实时推送**：降低延迟，减少轮询开销
2. **Redis 缓存层**：支撑更大并发量
3. **操作日志**：记录每次编辑的详细变更（谁、何时、改了什么字段），支持审计和回滚
4. **评论/批注**：在特定行/字段添加评论，@提及同事
5. **编辑锁定申请**：用户可申请某区域的排他编辑权，其他人自动只读

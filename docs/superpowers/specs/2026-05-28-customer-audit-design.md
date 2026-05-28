# 客户审核管理模块设计规格

**日期**: 2026-05-28
**关联功能**: ROADMAP Phase 2 P1 - 客户审核管理
**架构方案**: 扩展现有审核表结构（方案 B）

---

## 1. 概述

客户审核管理模块用于管理客户对供应商（我方）的质量审核活动，包括审核计划、执行、发现项记录、整改跟踪和客户确认闭环。

### 1.1 适用范围

- **现场审核**：客户到我方工厂进行实地审核
- **远程审核**：客户通过文件审查、视频会议等方式进行审核
- **客户类型**：OEM客户、Tier 1客户、Tier 2客户等（不绑定具体客户档案）

### 1.2 与现有模块关系

```
┌─────────────────────────────────────────────────────────────┐
│                    客户审核管理模块                          │
├─────────────────────────────────────────────────────────────┤
│  客户审核计划 ──→ 审核执行 ──→ 发现项 ──→ 整改闭环         │
│       │                                    │                │
│       ▼                                    ▼                │
│  客户类型管理                          CAPA 联动            │
│       │                                    │                │
│       ▼                                    ▼                │
│  审核日程                              客户确认             │
│       │                                    │                │
│       ▼                                    ▼                │
│  整改跟踪                              附件凭证             │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 数据模型设计

### 2.1 扩展现有表结构

#### `audit_plans` 表新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `audit_category` | VARCHAR(20), DEFAULT 'internal' | 审核类别：`internal`(内部) / `customer`(客户) |
| `customer_type` | VARCHAR(50), nullable | 客户类型：`OEM` / `Tier 1` / `Tier 2` / `其他` |
| `audit_mode` | VARCHAR(20), nullable | 审核方式：`on_site`(现场) / `remote`(远程) |
| `customer_confirmation_doc` | JSONB, DEFAULT '[]' | 客户确认函附件列表 |

#### `audit_findings` 表新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `audit_category` | VARCHAR(20), DEFAULT 'internal' | 审核类别：`internal` / `customer` |
| `customer_confirmed` | BOOLEAN, DEFAULT FALSE | 客户是否确认整改完成 |
| `customer_confirmation_date` | DATE, nullable | 客户确认日期 |
| `customer_confirmation_attachments` | JSONB, DEFAULT '[]' | 客户确认附件列表 |

### 2.2 编号规则

客户审核计划编号：`CA-YYYY-NNN`
- `CA` = Customer Audit
- `YYYY` = 年份
- `NNN` = 序号（001 起）

### 2.3 状态机

#### 客户审核计划状态

```
planned ──→ in_progress ──→ completed
   │              │              │
   └──────────────┴──→ cancelled  │
                                  │
   (发现项未关闭时禁止完成)        │
```

- `planned`: 已计划
- `in_progress`: 审核进行中
- `completed`: 审核完成（所有发现项已关闭且客户已确认）
- `cancelled`: 已取消

#### 发现项状态（复用现有）

```
open ──→ in_progress ──→ closed
  │            │
  └────────────┘
```

- `open`: 已开立
- `in_progress`: 整改中
- `closed`: 已关闭（需要客户确认 + CAPA 完成）

### 2.4 发现项严重度（复用现有）

- `major_nc`: 严重不符合
- `minor_nc`: 一般不符合
- `ofi`: 改进机会
- `observation`: 观察项

---

## 3. API 设计

### 3.1 扩展现有路由

#### GET /api/audit-plans

新增查询参数：
- `audit_category`: 过滤 `internal` / `customer`
- `customer_type`: 过滤客户类型
- `audit_mode`: 过滤审核方式

#### POST /api/audit-plans

请求体新增可选字段：
```json
{
  "audit_category": "customer",
  "customer_type": "OEM",
  "audit_mode": "on_site",
  ...
}
```

### 3.2 客户审核专用路由

#### POST /api/audit-plans/{audit_id}/customer-confirm

客户确认整改完成

请求体：
```json
{
  "confirmation_date": "2026-05-28",
  "attachments": [
    {
      "file_name": "客户确认函.pdf",
      "file_url": "/uploads/confirm-001.pdf",
      "uploaded_at": "2026-05-28T10:00:00Z"
    }
  ]
}
```

响应：
```json
{
  "message": "Customer confirmation recorded",
  "audit_id": "...",
  "customer_confirmed": true,
  "customer_confirmation_date": "2026-05-28"
}
```

### 3.3 发现项路由扩展

#### POST /api/audit-findings/{finding_id}/customer-confirm

确认单个发现项的客户整改确认

请求体：
```json
{
  "confirmation_date": "2026-05-28",
  "attachments": [...]
}
```

### 3.4 客户审核统计

#### GET /api/audit-plans/customer-stats

```json
{
  "total_customer_audits": 10,
  "planned": 2,
  "in_progress": 3,
  "completed": 5,
  "open_findings": 4,
  "major_nc_count": 1,
  "customer_confirmed": 3,
  "pending_confirmation": 2
}
```

---

## 4. 业务逻辑

### 4.1 创建客户审核计划

1. 验证 `audit_category` = 'customer' 时，`customer_type` 必填
2. 生成编号：`CA-YYYY-NNN`
3. 状态初始化为 `planned`

### 4.2 审核完成条件

客户审核计划标记为 `completed` 的条件：
1. 所有关联发现项状态为 `closed`
2. 所有关联发现项 `customer_confirmed` = TRUE
3. 或者审核计划级别有客户确认附件

### 4.3 发现项关闭条件

客户审核发现项关闭条件：
1. 根本原因分析已完成
2. 纠正措施已制定
3. CAPA 已完成（如有 CAPA 关联）
4. **客户已确认整改完成**（`customer_confirmed` = TRUE）

### 4.4 客户确认流程

1. 整改完成后，审核负责人在系统中上传客户确认函
2. 系统记录确认日期和附件
3. 自动检查是否满足关闭条件
4. 如满足，可关闭发现项

---

## 5. 前端设计

### 5.1 页面结构

```
客户审核管理
├── 客户审核列表页 (/customer-audits)
│   ├── 统计卡片（计划/进行中/已完成/待确认）
│   ├── 搜索/过滤栏
│   └── 审核计划表格
│       ├── 操作按钮：查看/编辑/开始/完成/取消
│       └── 状态标签
├── 客户审核详情页 (/customer-audits/:id)
│   ├── 审核基本信息卡片
│   ├── 发现项标签页
│   │   ├── 发现项表格
│   │   └── 操作：创建发现项/编辑/关闭/客户确认
│   ├── 整改跟踪标签页
│   │   ├── CAPA 关联信息
│   │   └── 客户确认状态
│   └── 客户确认标签页
│       ├── 确认函上传
│       └── 确认历史
└── 创建/编辑模态框
```

### 5.2 关键交互

- **客户类型选择**：下拉选择（OEM / Tier 1 / Tier 2 / 其他）
- **审核方式选择**：单选按钮（现场 / 远程）
- **客户确认上传**：拖拽上传区域，支持 PDF/图片
- **发现项状态看板**：可视化展示整改进度

### 5.3 权限控制

| 功能 | Admin | Manager | Engineer | Viewer |
|------|:-----:|:-------:|:--------:|:------:|
| 查看客户审核 | ✅ | ✅ | ✅ | ✅ |
| 创建/编辑审核 | ✅ | ✅ | ✅ | ❌ |
| 开始/完成审核 | ✅ | ✅ | ❌ | ❌ |
| 创建发现项 | ✅ | ✅ | ✅ | ❌ |
| 客户确认 | ✅ | ✅ | ❌ | ❌ |
| 关闭发现项 | ✅ | ✅ | ❌ | ❌ |

---

## 6. 数据库迁移

### Migration 009: Add Customer Audit Fields

```sql
-- audit_plans 表新增字段
ALTER TABLE audit_plans 
ADD COLUMN audit_category VARCHAR(20) DEFAULT 'internal',
ADD COLUMN customer_type VARCHAR(50),
ADD COLUMN audit_mode VARCHAR(20),
ADD COLUMN customer_confirmation_doc JSONB DEFAULT '[]';

-- audit_findings 表新增字段
ALTER TABLE audit_findings 
ADD COLUMN audit_category VARCHAR(20) DEFAULT 'internal',
ADD COLUMN customer_confirmed BOOLEAN DEFAULT FALSE,
ADD COLUMN customer_confirmation_date DATE,
ADD COLUMN customer_confirmation_attachments JSONB DEFAULT '[]';

-- 索引
CREATE INDEX idx_audit_plans_category ON audit_plans(audit_category);
CREATE INDEX idx_audit_plans_customer_type ON audit_plans(customer_type);
CREATE INDEX idx_audit_findings_category ON audit_findings(audit_category);
CREATE INDEX idx_audit_findings_confirmed ON audit_findings(customer_confirmed);
```

---

## 7. 测试要点

### 7.1 单元测试

- 客户审核计划 CRUD
- 发现项创建/更新/关闭
- 客户确认逻辑
- 状态转换验证

### 7.2 集成测试

- 审核完成条件检查
- 发现项关闭条件（含客户确认）
- CAPA 联动
- 附件上传

### 7.3 边界条件

- 无客户确认不允许关闭发现项
- 未关闭发现项不允许完成审核
- 客户类型必填验证
- 附件格式/大小限制

---

## 8. 验收标准

- [ ] 客户审核计划 CRUD 完整可用
- [ ] 支持现场和远程审核类型
- [ ] 支持 OEM/Tier 1/Tier 2 客户类型
- [ ] 发现项记录与内部审核一致
- [ ] 整改闭环支持 CAPA 联动
- [ ] 客户确认功能可用（上传确认函）
- [ ] 统计看板展示正确
- [ ] 权限控制符合 RBAC 设计
- [ ] 前端页面交互流畅
- [ ] 所有测试通过

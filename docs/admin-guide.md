# 管理员指南

本文档面向 OpenQMS 系统管理员，涵盖用户管理、权限配置、工厂/产品线分配和审计日志。

---

## 1. 用户管理

### 1.1 创建用户

使用 `admin` 账号登录后：

1. 进入 **用户管理** 页面（需 `user_mgmt` 模块 ADMIN 权限）。
2. 点击"新建用户"按钮。
3. 填写用户名、显示名、邮箱、密码，选择角色。
4. 保存后，新用户可立即登录。

### 1.2 重置密码

管理员可直接编辑用户信息修改密码。系统暂不支持自助密码重置。

### 1.3 禁用/启用用户

在用户列表中点击"禁用"按钮，被禁用用户无法登录但数据保留。

---

## 2. 角色与权限配置

### 2.1 角色列表

系统预设 7 个角色：

| 角色 | role_key | 说明 |
|------|----------|------|
| 系统管理员 | `admin` | 完全控制，不可修改 |
| 质量经理 | `manager` | 审批权限，可编辑大部分模块 |
| 只读用户 | `viewer` | 仅查看，不可创建/编辑 |
| 客户质量工程师 | `customer_qe` | 客诉/客户审核/SCAR 编辑 |
| 供应商质量工程师 | `supplier_qe` | 供应商/IQC/SCAR 编辑 |
| 现场质量工程师 | `field_qe` | FMEA/SPC/MSA 编辑 |
| 前期策划质量工程师 | `planning_qe` | FMEA/控制计划/PPAP/特殊特性编辑 |

### 2.2 权限配置

进入 **权限管理** 页面（需 `permission_mgmt` 模块 ADMIN 权限）：

1. 选择角色。
2. 为每个模块设置权限等级（NONE / VIEW / CREATE / EDIT / APPROVE / ADMIN）。
3. 保存后立即生效。

> ⚠️ `admin` 和 `viewer` 角色标记为 `is_system=True`，不建议修改其权限。

### 2.3 权限等级说明

| 等级 | 常量 | 含义 |
|:----:|------|------|
| 0 | NONE | 无权限，模块菜单隐藏 |
| 1 | VIEW | 只读，可查看列表和详情 |
| 2 | CREATE | 可创建新记录 |
| 3 | EDIT | 可编辑已有记录 |
| 4 | APPROVE | 可审批、关闭、归档 |
| 5 | ADMIN | 完全控制，包含删除和配置 |

---

## 3. 工厂与产品线分配

### 3.1 工厂管理

进入 **集团管理 → 工厂管理** 页面（需 `group` 模块 ADMIN 权限）：

1. 新建工厂：填写工厂编码、名称、地址。
2. 编辑/禁用工厂。
3. 分配用户到工厂：在用户编辑页面选择用户可访问的工厂。

### 3.2 产品线

产品线是工厂下的逻辑分组：

- 每个产品线属于一个工厂。
- 用户可被分配到多个产品线。
- 列表页默认按当前产品线过滤数据。

### 3.3 多工厂数据隔离

系统通过 `factory_scope` 实现数据隔离：

- 普通用户只能看到自己所属工厂的数据。
- 集团管理员可跨工厂查看数据。
- 产品线过滤在工厂范围内生效。

---

## 4. 审计日志

所有 CRUD 操作自动记录审计日志，包含：

| 字段 | 说明 |
|------|------|
| `table_name` | 操作的表名 |
| `record_id` | 记录 UUID |
| `action` | CREATE / UPDATE / DELETE / TRANSITION |
| `changed_fields` | 变更字段及新旧值（JSON） |
| `operated_by` | 操作人 UUID |
| `operated_at` | 操作时间 |

审计日志不可修改、不可删除。

---

## 5. 备份与恢复建议

### 5.1 数据库备份

```bash
# PostgreSQL 逻辑备份
docker compose exec db pg_dump -U qms qms > backup_$(date +%Y%m%d).sql

# 恢复
docker compose exec -T db psql -U qms qms < backup_20260613.sql
```

### 5.2 Neo4j 备份（知识图谱）

```bash
# Neo4j 逻辑备份
docker compose exec neo4j neo4j-admin database dump neo4j --output-path=/data/backup.dump

# 恢复（需先停止 neo4j）
docker compose exec neo4j neo4j-admin database load neo4j --from-path=/data/backup.dump
```

### 5.3 定期备份建议

- 生产环境建议每日自动备份 PostgreSQL 和 Neo4j。
- 备份文件保留至少 30 天。
- 定期测试备份恢复流程。
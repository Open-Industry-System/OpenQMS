# 供应商风险智能预警 — 设计规格

**日期**: 2026-06-11
**状态**: 草案
**路线图**: Phase 4 — 供应商风险智能预警 (P3)

---

## 1. 概述

在现有供应商质量数据（IQC 检验、SCAR、供应商评价、资质证书、ERP 交付）基础上，构建规则驱动的风险评分引擎，持续评估供应商风险状态。高风险自动推送预警通知（系统内 + 邮件 + Webhook），并提供风险看板和预警处置闭环（确认/忽略/创建 SCAR/CAPA）。

### 核心价值

- **主动发现**：从被动查看指标变为主动推送风险预警
- **综合评估**：多维指标加权评分，而非单一阈值判断
- **闭环处置**：预警可直接创建 SCAR/CAPA，跟踪到底

---

## 2. 架构

```
数据层（现有）          规则引擎              预警层                通知层
┌──────────┐      ┌──────────────┐      ┌──────────────┐      ┌───────────┐
│ IQC 检验  │─────▶│ 10 条规则    │─────▶│ 风险评分计算  │─────▶│ 系统内列表 │
│ SCAR      │      │ (指标采集    │      │ (加权综合分)  │      │ 邮件通知   │
│ 供应商评价 │      │  阈值判断)   │      │ 预警记录生成  │      │ Webhook   │
│ 证书      │      └──────────────┘      └──────────────┘      └───────────┘
│ ERP 交付  │                                              ↓
└──────────┘                                    确认/忽略/创建SCAR
```

与项目已有的 `cp_validation/rule_engine` 模式保持一致：规则是纯函数，接收数据返回结果，不直接访问数据库。

---

## 3. 风险规则引擎

### 3.1 规则定义

10 条规则，分三类：

| 规则 ID | 名称 | 类别 | 输入 | 触发条件 | 默认权重 |
|---------|------|------|------|----------|----------|
| R01 | PPM 超标 | 质量 | IQC 检验记录 | 供应商 PPM > 阈值（默认 1000） | 15 |
| R02 | 批次合格率下降 | 质量 | IQC 检验记录 | 合格率 < 阈值（默认 90%）或环比下降 > 比例（默认 10%） | 12 |
| R03 | 连续拒收 | 质量 | IQC 检验记录 | 连续 N 批（默认 3）拒收 | 18 |
| R04 | SCAR 超期未关闭 | 质量 | SCAR 记录 | 开放 SCAR 超过 N 天（默认 30） | 10 |
| R05 | SCAR 频发 | 质量 | SCAR 记录 | 时间窗口（默认 90 天）内 SCAR 数量 > 阈值（默认 3） | 12 |
| R06 | 交付准时率下降 | 交付 | 供应商评价 | delivery_score < 阈值（默认 70）或环比下降 > 比例（默认 15%） | 12 |
| R07 | 评级降级 | 交付 | 供应商评价 | 最近评级从 A/B 降为 C/D | 10 |
| R08 | 证书即将过期 | 合规 | 资质证书 | 证书在 30/60/90 天内过期 | 8 |
| R09 | 评价分数下滑 | 合规 | 供应商评价 | 总评分环比下降 > 阈值（默认 15 分） | 8 |
| R10 | 安全缺陷检测 | 合规 | IQC 检验记录 | 缺陷描述包含安全关键词 | 15 |

### 3.2 规则执行模式

规则是纯函数：`(supplier_data) -> (list[RuleResult])`

```python
@dataclass
class RuleResult:
    rule_id: str
    triggered: bool
    score: float          # 0-100，未触发为 0
    detail: str           # 人类可读的触发原因描述
    category: str         # "quality" | "delivery" | "compliance"
```

- 每条规则独立执行，互不影响
- 规则异常不中断其他规则（catch + 记录 failed_rule_id）
- 触发的规则贡献评分，未触发的贡献 0 分

### 3.3 风险评分计算

```
quality_score   = Σ(R01..R05 triggered scores × weights) / Σ(R01..R05 weights) × 100
delivery_score  = Σ(R06..R07 triggered scores × weights) / Σ(R06..R07 weights) × 100
compliance_score = Σ(R08..R10 triggered scores × weights) / Σ(R08..R10 weights) × 100

综合分 = quality_score × 0.50 + delivery_score × 0.30 + compliance_score × 0.20
```

映射到四级风险：

| 等级 | 分数范围 | 颜色 | 行动 |
|------|----------|------|------|
| 低风险 | 0-30 | 🟢 绿色 | 无需行动 |
| 中风险 | 31-60 | 🟡 黄色 | 关注，定期复查 |
| 高风险 | 61-80 | 🟠 橙色 | 立即确认，考虑创建 SCAR |
| 极高风险 | 81-100 | 🔴 红色 | 紧急处置，创建 SCAR/CAPA |

---

## 4. 数据模型

### 4.1 新增表

#### `supplier_risk_alerts` — 预警记录

| 列名 | 类型 | 说明 |
|------|------|------|
| alert_id | UUID PK | 预警 ID |
| supplier_id | UUID FK → suppliers | 供应商 |
| risk_level | VARCHAR(10) | low/medium/high/critical |
| risk_score | FLOAT | 综合风险分 0-100 |
| quality_score | FLOAT | 质量维度分 |
| delivery_score | FLOAT | 交付维度分 |
| compliance_score | FLOAT | 合规维度分 |
| rule_results | JSONB | 各规则执行结果快照 |
| alert_type | VARCHAR(30) | 首次/升级/定期复查 |
| status | VARCHAR(20) | open/acknowledged/action_taken/ignored/closed |
| handled_by | UUID FK → users | 处置人 |
| handled_at | TIMESTAMP | 处置时间 |
| handle_action | VARCHAR(20) | acknowledge/ignore/create_scar/create_capa |
| handle_note | TEXT | 处置备注 |
| linked_scar_id | UUID FK → supplier_scars | 关联 SCAR |
| linked_capa_id | UUID FK → capa_eightd | 关联 CAPA |
| snapshot_date | DATE | 快照日期（用于去重） |
| product_line_code | VARCHAR(20) | 产品线 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

唯一约束：`(supplier_id, snapshot_date)` — 每个供应商每天最多一条预警。

#### `supplier_risk_configs` — 规则配置

| 列名 | 类型 | 说明 |
|------|------|------|
| config_id | UUID PK | 配置 ID |
| rule_id | VARCHAR(10) | 规则 ID（R01-R10） |
| enabled | BOOLEAN | 是否启用 |
| thresholds | JSONB | 阈值参数（如 ppm_limit, days_window） |
| weight | FLOAT | 权重 |
| supplier_id | UUID FK → suppliers NULL | 供应商级覆盖（NULL=全局默认） |
| category | VARCHAR(20) | quality/delivery/compliance |
| product_line_code | VARCHAR(20) | 产品线 |
| updated_by | UUID FK → users | 更新人 |
| updated_at | TIMESTAMP | 更新时间 |

唯一约束：`(rule_id, supplier_id, product_line_code)` — 全局默认为 supplier_id=NULL。

#### `supplier_risk_notification_channels` — 通知渠道配置

| 列名 | 类型 | 说明 |
|------|------|------|
| channel_id | UUID PK | 渠道 ID |
| channel_type | VARCHAR(20) | email/webhook |
| config | JSONB | 渠道配置（email: addresses[]; webhook: url, secret） |
| min_risk_level | VARCHAR(10) | 最低触发风险等级（high/critical） |
| enabled | BOOLEAN | 是否启用 |
| supplier_id | UUID FK → suppliers NULL | 供应商级覆盖 |
| product_line_code | VARCHAR(20) | 产品线 |
| created_by | UUID FK → users | 创建人 |
| created_at | TIMESTAMP | 创建时间 |

### 4.2 权限注册

在 `Module` 枚举中新增 `SUPPLIER_RISK = "supplier_risk"`，并在权限种子中为 4 个角色分配：

| 角色 | 权限级别 |
|------|----------|
| admin | ADMIN (5) |
| manager | APPROVE (4) |
| quality_engineer | EDIT (3) |
| viewer | VIEW (1) |

---

## 5. 服务层

### 5.1 模块结构

```
services/supplier_risk/
├── __init__.py          # 对外接口
├── rule_engine.py       # 10 条规则（纯函数）
├── scorer.py            # 风险评分计算
├── service.py           # 主服务（协调规则引擎 + 评分 + 预警生成）
├── notifier.py          # 通知分发（邮件 + Webhook）
└── config.py            # 配置管理
```

### 5.2 核心服务接口

```python
# service.py
async def evaluate_supplier_risk(db, supplier_id, product_line_code) -> RiskEvaluation
async def evaluate_all_suppliers(db, product_line_code) -> list[RiskEvaluation]
async def handle_alert(db, alert_id, action, note, user_id) -> SupplierRiskAlert
async def create_scar_from_alert(db, alert_id, user_id) -> SupplierSCAR
async def create_capa_from_alert(db, alert_id, user_id) -> CAPAEightD

# config.py
async def get_rule_configs(db, product_line_code, supplier_id=None) -> list[RuleConfig]
async def update_rule_config(db, config_id, updates, user_id) -> RuleConfig

# notifier.py
async def send_notifications(db, alert, product_line_code) -> None
```

### 5.3 触发机制

| 触发方式 | 时机 | 说明 |
|----------|------|------|
| 定时全量扫描 | 每日凌晨 2:00 | 后台协程遍历所有活跃供应商 |
| 事件增量评估 | IQC 判定完成、SCAR 状态变更 | 仅评估相关供应商 |
| 手动触发 | 用户点击"立即评估" | 单个供应商 |

定时任务使用 `asyncio.create_task` + 后台协程，与项目已有的 MES 生命周期服务模式一致。

### 5.4 预警去重与升级

- 同一供应商同一天仅生成一条预警（唯一约束）
- 如果供应商风险等级升级（中→高、高→极高），更新已有预警的 `alert_type` 为 `escalated`，保留历史 `rule_results` 快照
- 降级不自动关闭预警，需人工确认

### 5.5 通知渠道

**邮件**：
- 使用 `aiosmtplib` 异步发送
- 邮件模板：供应商名称 + 风险等级 + 触发规则摘要 + 链接
- 发送失败仅记录日志，不阻塞流程

**Webhook**：
- HTTP POST JSON payload 到用户配置的 URL
- 包含 `X-Signature` HMAC 签名（用配置的 secret）
- 超时 5 秒，重试 1 次

**系统内**：
- 预警列表页自动展示
- 供应商详情页风险 Tab

---

## 6. 预警处置流程

```
open ──→ acknowledged ──→ action_taken ──→ closed
  │           │                │
  │           │                ├─ 创建 SCAR（自动关联）
  │           │                └─ 创建 CAPA（自动关联）
  │           │
  └──→ ignored（需填理由，写入 handle_note）
```

- `acknowledged`：确认已知晓，正在调查
- `action_taken`：已采取行动（创建 SCAR 或 CAPA）
- `closed`：SCAR/CAPA 关闭后自动关闭预警（或人工关闭）
- `ignored`：误报或不需处置，需填理由

权限要求：
- 确认/忽略：engineer 及以上
- 创建 SCAR/CAPA：engineer 及以上
- 关闭预警：manager 及以上

---

## 7. API 路由

路由文件：`backend/app/api/supplier_risk.py`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/supplier-risk/alerts` | 预警列表（分页+过滤） | VIEW |
| GET | `/supplier-risk/alerts/{alert_id}` | 预警详情 | VIEW |
| POST | `/supplier-risk/alerts/{alert_id}/handle` | 处置预警 | EDIT |
| POST | `/supplier-risk/alerts/{alert_id}/scar` | 从预警创建 SCAR | EDIT |
| POST | `/supplier-risk/alerts/{alert_id}/capa` | 从预警创建 CAPA | EDIT |
| POST | `/supplier-risk/evaluate/{supplier_id}` | 手动评估单个供应商 | EDIT |
| POST | `/supplier-risk/evaluate` | 手动全量评估 | APPROVE |
| GET | `/supplier-risk/dashboard` | 风险看板数据 | VIEW |
| GET | `/supplier-risk/configs` | 规则配置列表 | VIEW |
| PUT | `/supplier-risk/configs/{config_id}` | 更新规则配置 | APPROVE |
| GET | `/supplier-risk/channels` | 通知渠道列表 | VIEW |
| POST | `/supplier-risk/channels` | 创建通知渠道 | APPROVE |
| PUT | `/supplier-risk/channels/{channel_id}` | 更新通知渠道 | APPROVE |
| DELETE | `/supplier-risk/channels/{channel_id}` | 删除通知渠道 | APPROVE |

---

## 8. 前端

### 8.1 页面

在"供应商质量"菜单组下新增：

```
供应商质量
├── 供应商管理
├── 供货质量看板
├── 供应商风险预警  ← 新增
└── SCAR 管理
```

**风险预警页面** (`/supplier-risk`)：
- 顶部 KPI 卡片：高风险供应商数、极高风险数、开放预警数、平均风险分
- 风险矩阵散点图：X=质量分, Y=交付分, 气泡大小=合规分, 颜色=风险等级
- 预警列表：Ant Design Table，支持按风险等级/状态/供应商过滤
- 点击预警行展开处置面板（确认/忽略/创建SCAR/创建CAPA）

**风险配置** (`/supplier-risk/config`)：
- 规则配置表：每条规则一行，开关、阈值编辑、权重滑块
- 通知渠道管理：添加/编辑/删除邮件和 Webhook 渠道

### 8.2 供应商详情嵌入

在现有供应商详情页新增"风险"Tab，展示：
- 当前风险等级和评分
- 风险趋势图（近 6 个月）
- 历史预警列表

### 8.3 前端文件

```
pages/supplierRisk/
├── SupplierRiskPage.tsx          # 风险预警主页面
├── RiskConfigPage.tsx            # 风险配置页面
├── components/
│   ├── RiskMatrixChart.tsx       # 风险矩阵散点图
│   ├── AlertTable.tsx            # 预警列表
│   ├── HandleAlertDrawer.tsx     # 处置抽屉
│   ├── RuleConfigTable.tsx       # 规则配置表
│   ├── ChannelConfigTable.tsx    # 通知渠道配置表
│   └── RiskTrendChart.tsx        # 风险趋势图（嵌入供应商详情）
```

API 客户端：`frontend/src/api/supplierRisk.ts`
类型定义：扩展 `frontend/src/types/index.ts`

---

## 9. 数据库迁移

Alembic 迁移文件：`033_add_supplier_risk_tables.py`

3 张新表：
1. `supplier_risk_alerts` — 预警记录
2. `supplier_risk_configs` — 规则配置
3. `supplier_risk_notification_channels` — 通知渠道

权限种子：为 `SUPPLIER_RISK` 模块注册 4 个角色的权限级别。

---

## 10. 测试

### 后端测试

规则引擎纯函数测试（18 个）：
- R01: PPM 超标 / 未超标
- R02: 合格率低于阈值 / 环比下降 / 正常
- R03: 连续拒收 3 批 / 2 批不触发
- R04: SCAR 超期 / 未超期
- R05: SCAR 频发 / 未频发
- R06: 交付分数低 / 环比下降 / 正常
- R07: 评级降级 / 未降级
- R08: 证书 30/60/90 天过期 / 未过期
- R09: 总评分下滑 / 未下滑
- R10: 安全关键词匹配 / 不匹配

评分计算测试（4 个）：
- 全部低风险 = 低
- 部分触发 = 中
- 多维度高 = 高
- 全部触发 = 极高

预警处置流测试（4 个）：
- 确认预警
- 忽略预警
- 从预警创建 SCAR
- 从预警创建 CAPA

配置管理测试（2 个）：
- 全局默认配置读取
- 供应商级覆盖

总计：28 个测试

### 前端

无测试框架（项目现状），手动验证页面功能。

---

## 11. 与现有模块集成

| 集成点 | 说明 |
|--------|------|
| IQC 检验 | 判定完成时触发增量评估；R01/R02/R03/R10 读取 IQC 数据 |
| SCAR | 状态变更时触发增量评估；R04/R05 读取 SCAR 数据；预警可创建 SCAR |
| 供应商评价 | 评价完成后触发增量评估；R06/R07/R09 读取评价数据 |
| 供应商证书 | R08 读取证书过期数据 |
| CAPA | 预警可创建 CAPA；CAPA 关闭后可自动关闭关联预警 |
| 供货质量看板 | 风险看板复用部分 PPM/合格率查询逻辑 |
| 权限系统 | 新增 SUPPLIER_RISK 模块，复用 require_permission 机制 |

---

## 12. 安全与性能

- **数据隔离**：所有查询加 `product_line_code` 过滤
- **权限控制**：API 路由使用 `require_permission(Module.SUPPLIER_RISK, ...)`
- **Webhook 签名**：HMAC-SHA256 签名验证 payload 完整性
- **邮件配置**：通过环境变量配置 SMTP，不硬编码
- **性能**：全量扫描使用批量查询，避免 N+1；规则引擎纯函数无 I/O
- **去重**：唯一约束防止同天重复预警

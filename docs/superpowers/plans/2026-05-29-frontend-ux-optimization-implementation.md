# 前端 UX 综合优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重组前端导航、重设计仪表盘、建立模块间交叉引用，提升 OpenQMS 前端 UX。

**Architecture:** 5 阶段递进 — 导航分组 → 仪表盘重设计 → 后端关联 API → 前端关联组件 → 目录迁移。每阶段独立可交付，不破坏现有功能。

**Tech Stack:** React 18 + TypeScript 5.6 + Ant Design 5.21 + FastAPI + SQLAlchemy 2.0 + PostgreSQL 15 + Alembic

**Spec:** `docs/superpowers/specs/2026-05-29-frontend-ux-optimization-design.md`

---

## Phase 1: 侧边栏导航分组重构

### Task 1: 重构 AppLayout 菜单为 SubMenu 分组

**Files:**
- Modify: `frontend/src/components/layout/AppLayout.tsx`

- [ ] **Step 1: 替换 menuItems 为分组结构**

将 `AppLayout.tsx:31-67` 的 `menuItems` 替换为 SubMenu 分组结构。添加 `ROUTE_GROUP_MAP` 和 `getSelectedMenuKey` 函数：

```tsx
// 所有菜单 key 列表（用于最长前缀匹配）
const MENU_KEYS = [
  "/dashboard",
  "/fmea", "/control-plans", "/apqp", "/ppap",
  "/special-characteristics", "/special-characteristics/matrix", "/special-characteristics/traceability",
  "/spc", "/msa/gauges", "/msa/studies", "/quality-goals",
  "/internal-audits", "/management-reviews",
  "/customer-quality", "/customer-audits", "/capa",
  "/suppliers", "/suppliers/quality",
  "/iqc/inspections", "/iqc/materials", "/scars",
];

// 菜单 key → 所属分组 key（精确匹配每个叶子菜单项）
const MENU_KEY_TO_GROUP: Record<string, string> = {
  "/fmea": "grp:planning",
  "/control-plans": "grp:planning",
  "/apqp": "grp:planning",
  "/ppap": "grp:planning",
  "/special-characteristics": "grp:planning",
  "/special-characteristics/matrix": "grp:planning",
  "/special-characteristics/traceability": "grp:planning",
  "/spc": "grp:shopfloor",
  "/msa/gauges": "grp:shopfloor",
  "/msa/studies": "grp:shopfloor",
  "/quality-goals": "grp:shopfloor",
  "/internal-audits": "grp:shopfloor",
  "/management-reviews": "grp:shopfloor",
  "/customer-quality": "grp:customer",
  "/customer-audits": "grp:customer",
  "/capa": "grp:customer",
  "/suppliers": "grp:supplier",
  "/suppliers/quality": "grp:supplier",
  "/iqc/inspections": "grp:supplier",
  "/iqc/materials": "grp:supplier",
  "/scars": "grp:supplier",
};

function getSelectedMenuKey(pathname: string): string {
  const matched = MENU_KEYS
    .filter((key) => pathname === key || pathname.startsWith(key + "/"))
    .sort((a, b) => b.length - a.length);
  return matched[0] || "/dashboard";
}

const menuItems = [
  { key: "/dashboard", icon: <DashboardOutlined />, label: "仪表盘" },
  {
    key: "grp:planning",
    icon: <ExperimentOutlined />,
    label: "前期质量策划",
    children: [
      { key: "/fmea", icon: <FileTextOutlined />, label: "FMEA 管理" },
      { key: "/control-plans", icon: <FileTextOutlined />, label: "控制计划" },
      { key: "/apqp", icon: <ProjectOutlined />, label: "APQP 质量策划" },
      { key: "/ppap", icon: <FileProtectOutlined />, label: "PPAP" },
      { key: "/special-characteristics", icon: <SafetyCertificateOutlined />, label: "特殊特性" },
    ],
  },
  {
    key: "grp:shopfloor",
    icon: <ToolOutlined />,
    label: "现场质量管理",
    children: [
      { key: "/spc", icon: <BarChartOutlined />, label: "SPC 控制图" },
      {
        key: "grp:msa",
        icon: <ToolOutlined />,
        label: "MSA 分析",
        children: [
          { key: "/msa/gauges", label: "量具管理" },
          { key: "/msa/studies", label: "研究管理" },
        ],
      },
      { key: "/quality-goals", icon: <AimOutlined />, label: "质量目标" },
      { key: "/internal-audits", icon: <SafetyOutlined />, label: "内部审核" },
      { key: "/management-reviews", icon: <TeamOutlined />, label: "管理评审" },
    ],
  },
  {
    key: "grp:customer",
    icon: <CustomerServiceOutlined />,
    label: "客户质量",
    children: [
      { key: "/customer-quality", icon: <CustomerServiceOutlined />, label: "客诉/RMA" },
      { key: "/customer-audits", icon: <AuditOutlined />, label: "客户审核" },
      { key: "/capa", icon: <BugOutlined />, label: "8D/CAPA" },
    ],
  },
  {
    key: "grp:supplier",
    icon: <ShopOutlined />,
    label: "供应商质量",
    children: [
      { key: "/suppliers", icon: <ShopOutlined />, label: "供应商管理" },
      { key: "/suppliers/quality", icon: <BarChartOutlined />, label: "供货质量看板" },
      { key: "/scars", icon: <AlertOutlined />, label: "SCAR 管理" },
      {
        key: "grp:iqc",
        icon: <ExperimentOutlined />,
        label: "来料检验",
        children: [
          { key: "/iqc/inspections", label: "检验单" },
          { key: "/iqc/materials", label: "物料管理" },
        ],
      },
    ],
  },
];
```

- [ ] **Step 2: 更新 AppLayout 函数体中的 selectedKeys 和 openKeys 逻辑**

替换 `AppLayout.tsx:79` 的 `selectedKey` 计算，添加状态化的 `openKeys`：

```tsx
// 替换原来的：
// const selectedKey = "/" + location.pathname.split("/")[1];

// 改为：
const selectedKey = getSelectedMenuKey(location.pathname);
const currentGroup = MENU_KEY_TO_GROUP[selectedKey];

// openKeys：路由变化时自动展开当前分组，同时保留用户手动操作
const [openKeys, setOpenKeys] = useState<string[]>(
  currentGroup ? [currentGroup] : []
);

// 路由变化时，确保当前分组在 openKeys 中
useEffect(() => {
  if (currentGroup && !openKeys.includes(currentGroup)) {
    setOpenKeys((prev) => [...prev, currentGroup]);
  }
}, [currentGroup]);
```

在 `<Menu>` 组件上使用受控 `openKeys` + `onOpenChange`：

```tsx
<Menu
  mode="inline"
  selectedKeys={[selectedKey]}
  openKeys={openKeys}
  onOpenChange={setOpenKeys}
  items={menuItems}
  onClick={({ key }) => {
    if (key.startsWith("grp:")) return;
    navigate(key);
  }}
  style={{ borderRight: 0 }}
/>
```

这样路由变化时自动展开当前分组，用户也可以手动展开/收起其他分组。

- [ ] **Step 3: 验证编译通过**

Run: `cd frontend && npm run build`
Expected: 编译成功，无 TS 错误

- [ ] **Step 4: 手动验证**

Run: `cd frontend && npm run dev`
- 访问 `http://localhost:5173/dashboard`，确认仪表盘高亮
- 访问 `http://localhost:5173/fmea`，确认"前期质量策划"分组展开，FMEA 高亮
- 访问 `http://localhost:5173/suppliers/quality`，确认"供应商质量"分组展开，供货质量看板高亮（不是供应商管理）
- 访问 `http://localhost:5173/iqc/inspections`，确认 IQC 子菜单高亮
- 折叠侧边栏，hover 各分组图标，确认弹出子菜单

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/AppLayout.tsx
git commit -m "feat(nav): reorganize sidebar into 5 business groups with SubMenu"
```

---

## Phase 2: 仪表盘重设计

### Task 2: 扩展后端 dashboard API — 新增 summary 和 alerts

**Files:**
- Modify: `backend/app/services/dashboard_service.py`
- Modify: `backend/app/api/dashboard.py`

- [ ] **Step 1: 在 dashboard_service.py 中新增 get_summary 函数**

在 `dashboard_service.py` 末尾添加：

```python
async def get_summary(db: AsyncSession, product_line: str | None = None) -> dict:
    now = datetime.now(timezone.utc)

    # 待办：待审批 FMEA + 待推进 CAPA + 未关闭客诉
    fmea_pending = select(func.count(FMEADocument.fmea_id)).where(
        FMEADocument.status.in_(["draft", "in_review"])
    )
    if product_line:
        fmea_pending = fmea_pending.where(FMEADocument.product_line_code == product_line)
    fmea_pending_count = await db.scalar(fmea_pending) or 0

    capa_pending = select(func.count(CAPAEightD.report_id)).where(
        CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"])
    )
    if product_line:
        capa_pending = capa_pending.where(CAPAEightD.product_line_code == product_line)
    capa_pending_count = await db.scalar(capa_pending) or 0

    from app.models.customer_quality import CustomerComplaint
    complaint_pending = select(func.count(CustomerComplaint.complaint_id)).where(
        CustomerComplaint.status == "open"
    )
    if product_line:
        complaint_pending = complaint_pending.where(
            CustomerComplaint.product_line_code == product_line
        )
    complaint_pending_count = await db.scalar(complaint_pending) or 0

    pending_actions = fmea_pending_count + capa_pending_count + complaint_pending_count

    # 超期任务
    overdue_capa_q = select(func.count(CAPAEightD.report_id)).where(
        CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"]),
        CAPAEightD.due_date < now.date(),
    )
    if product_line:
        overdue_capa_q = overdue_capa_q.where(CAPAEightD.product_line_code == product_line)
    overdue_tasks = await db.scalar(overdue_capa_q) or 0

    # 高风险项 — 从现有 get_dashboard 复用 RPN 计算逻辑
    from app.utils.fmea_graph import build_rpn_rows
    fmea_query = select(FMEADocument.fmea_id, FMEADocument.graph_data)
    if product_line:
        fmea_query = fmea_query.where(FMEADocument.product_line_code == product_line)
    result = await db.execute(fmea_query)
    all_docs = result.all()

    high_risk_items = 0
    for _doc_id, graph_data in all_docs:
        if not graph_data:
            continue
        nodes = graph_data.get("nodes", []) if isinstance(graph_data, dict) else []
        edges = graph_data.get("edges", []) if isinstance(graph_data, dict) else []
        rows = build_rpn_rows(nodes, edges)
        for row in rows:
            s = row.get("severity", 0)
            o = row.get("occurrence", 0)
            d = row.get("detection", 0)
            if s > 0 and o > 0 and d > 0:
                rpn = s * o * d
                if rpn >= 100:
                    high_risk_items += 1

    # 本月趋势
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)

    this_month = select(func.count(FMEADocument.fmea_id)).where(
        FMEADocument.created_at >= month_start
    )
    last_month = select(func.count(FMEADocument.fmea_id)).where(
        FMEADocument.created_at >= prev_month_start,
        FMEADocument.created_at < month_start,
    )
    if product_line:
        this_month = this_month.where(FMEADocument.product_line_code == product_line)
        last_month = last_month.where(FMEADocument.product_line_code == product_line)

    this_count = await db.scalar(this_month) or 0
    last_count = await db.scalar(last_month) or 0

    return {
        "pending_actions": pending_actions,
        "overdue_tasks": overdue_tasks,
        "high_risk_items": high_risk_items,
        "month_trend": this_count - last_count,
    }
```

- [ ] **Step 2: 在 dashboard_service.py 中新增 get_alerts 函数**

```python
async def get_alerts(db: AsyncSession, product_line: str | None = None) -> dict:
    from app.utils.fmea_graph import build_rpn_rows
    from app.models.supplier import Supplier

    now = datetime.now(timezone.utc)

    # 高 RPN FMEA — top 5
    fmea_query = select(FMEADocument.fmea_id, FMEADocument.document_no, FMEADocument.graph_data)
    if product_line:
        fmea_query = fmea_query.where(FMEADocument.product_line_code == product_line)
    result = await db.execute(fmea_query)
    all_docs = result.all()

    high_rpn_items = []
    for doc_id, doc_no, graph_data in all_docs:
        if not graph_data:
            continue
        nodes = graph_data.get("nodes", []) if isinstance(graph_data, dict) else []
        edges = graph_data.get("edges", []) if isinstance(graph_data, dict) else []
        rows = build_rpn_rows(nodes, edges)
        for row in rows:
            s = row.get("severity", 0)
            o = row.get("occurrence", 0)
            d = row.get("detection", 0)
            if s > 0 and o > 0 and d > 0:
                rpn = s * o * d
                if rpn >= 100:
                    high_rpn_items.append({
                        "fmea_id": str(doc_id),
                        "document_no": doc_no,
                        "node_name": row.get("failure_mode", ""),
                        "rpn": rpn,
                    })

    high_rpn_items.sort(key=lambda x: x["rpn"], reverse=True)
    high_rpn_items = high_rpn_items[:5]

    # 超期 CAPA — top 5
    capa_query = (
        select(
            CAPAEightD.report_id,
            CAPAEightD.document_no,
            CAPAEightD.due_date,
        )
        .where(
            CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"]),
            CAPAEightD.due_date < now.date(),
        )
        .order_by(CAPAEightD.due_date)
        .limit(5)
    )
    if product_line:
        capa_query = capa_query.where(CAPAEightD.product_line_code == product_line)
    capa_result = await db.execute(capa_query)
    overdue_capas = [
        {
            "report_id": str(row.report_id),
            "document_no": row.document_no,
            "overdue_days": (now.date() - row.due_date).days,
        }
        for row in capa_result.all()
    ]

    # PPM 超标供应商 — top 5
    # PPM 从 IQC 检验数据计算（defects / lot_qty * 1M）
    # 阈值：customers.ppm_target，默认 500
    from app.models.customer_quality import Customer
    from app.models.iqc_inspection import IqcInspection
    from app.models.supplier import Supplier

    ppm_target_q = select(func.min(Customer.ppm_target))
    ppm_threshold = await db.scalar(ppm_target_q) or 500.0
    if ppm_threshold is None or ppm_threshold <= 0:
        ppm_threshold = 500.0

    # 按供应商聚合 IQC 检验数据计算 PPM
    ppm_query = (
        select(
            IqcInspection.supplier_id,
            func.sum(IqcInspection.defect_qty).label("total_defects"),
            func.sum(IqcInspection.lot_qty).label("total_lots"),
        )
        .where(IqcInspection.supplier_id.isnot(None))
        .group_by(IqcInspection.supplier_id)
    )
    if product_line:
        ppm_query = ppm_query.where(IqcInspection.product_line_code == product_line)
    ppm_result = await db.execute(ppm_query)

    high_ppm_suppliers = []
    for row in ppm_result.all():
        if row.total_lots and row.total_lots > 0:
            ppm = (row.total_defects / row.total_lots) * 1_000_000
            if ppm > ppm_threshold:
                # 查供应商名称
                supp = await db.get(Supplier, row.supplier_id)
                if supp:
                    high_ppm_suppliers.append({
                        "supplier_id": str(row.supplier_id),
                        "supplier_name": supp.name,
                        "ppm": round(ppm, 1),
                    })

    high_ppm_suppliers.sort(key=lambda x: x["ppm"], reverse=True)
    high_ppm_suppliers = high_ppm_suppliers[:5]

    return {
        "high_rpn_fmeas": high_rpn_items,
        "overdue_capas": overdue_capas,
        "high_ppm_suppliers": high_ppm_suppliers,
    }
```

- [ ] **Step 3: 在 dashboard_service.py 中新增 get_recent_actions 函数**

```python
async def get_recent_actions(
    db: AsyncSession, user_id: str, limit: int = 5
) -> list[dict]:
    from app.models.audit import AuditLog

    query = (
        select(AuditLog)
        .where(AuditLog.operated_by == user_id)
        .order_by(AuditLog.operated_at.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    logs = result.scalars().all()

    # 从 table_name + record_id 查文档编号
    actions = []
    for log in logs:
        entity_no = ""
        if log.table_name == "fmea_documents":
            q = select(FMEADocument.document_no).where(
                FMEADocument.fmea_id == log.record_id
            )
            entity_no = await db.scalar(q) or ""
        elif log.table_name == "capa_eightd":
            q = select(CAPAEightD.document_no).where(
                CAPAEightD.report_id == log.record_id
            )
            entity_no = await db.scalar(q) or ""

        actions.append({
            "record_id": str(log.record_id),
            "table_name": log.table_name,
            "entity_no": entity_no,
            "action": log.action,
            "operated_at": log.operated_at.isoformat(),
        })

    return actions
```

- [ ] **Step 4: 在 dashboard API router 中注册新端点，替换现有 alerts 端点**

现有 `backend/app/api/dashboard.py` 已有 `@router.get("/alerts")`（L41-48），它从 `get_dashboard` 返回的 `data["alerts"]` 取数据（当前为空列表）。**替换**该端点实现，同时新增 `/summary` 和 `/recent-actions`：

```python
@router.get("/summary")
async def get_summary(
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await dashboard_service.get_summary(db, product_line)


# 替换现有的 /alerts 端点实现
@router.get("/alerts")
async def get_alerts(
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await dashboard_service.get_alerts(db, product_line)


@router.get("/recent-actions")
async def get_recent_actions(
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await dashboard_service.get_recent_actions(db, user.user_id)
```

- [ ] **Step 5: 验证后端编译**

Run: `cd backend && python -c "from app.api.dashboard import router; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/dashboard_service.py backend/app/api/dashboard.py
git commit -m "feat(dashboard): add summary/alerts/recent-actions API endpoints"
```

### Task 3: 更新前端 DashboardData 类型和 API 客户端

**Files:**
- Modify: `frontend/src/types/index.ts:130-153`
- Modify: `frontend/src/api/dashboard.ts`

- [ ] **Step 1: 扩展 DashboardData 类型**

替换 `frontend/src/types/index.ts:130-153`：

```typescript
export interface DashboardData {
  kpi: {
    total_fmea: number;
    approved_fmea: number;
    total_capa: number;
    open_capa: number;
    overdue_capa: number;
    avg_rpn: number;
    high_rpn_count: number;
    total_safety: number;
    pending_safety_approval: number;
    safety_suggestions: number;
    management_review: {
      total_reviews: number;
      closed_reviews: number;
      total_outputs: number;
      verified_outputs: number;
      pending_verification: number;
      completion_rate: number;
    };
  };
  trends: Record<string, unknown>;
  alerts: unknown[];
}

export interface DashboardSummary {
  pending_actions: number;
  overdue_tasks: number;
  high_risk_items: number;
  month_trend: number;
}

export interface DashboardAlerts {
  high_rpn_fmeas: Array<{
    fmea_id: string;
    document_no: string;
    node_name: string;
    rpn: number;
  }>;
  overdue_capas: Array<{
    report_id: string;
    document_no: string;
    overdue_days: number;
  }>;
  high_ppm_suppliers: Array<{
    supplier_id: string;
    supplier_name: string;
    ppm: number;
  }>;
}

export interface DashboardRecentAction {
  record_id: string;
  table_name: string;
  entity_no: string;
  action: string;
  operated_at: string;
}
```

- [ ] **Step 2: 扩展 dashboard API 客户端**

替换 `frontend/src/api/dashboard.ts`：

```typescript
import client from "./client";
import type { DashboardData, DashboardSummary, DashboardAlerts, DashboardRecentAction } from "../types";

export async function getDashboard(productLine?: string): Promise<DashboardData> {
  const resp = await client.get("/dashboard", { params: { product_line: productLine || undefined } });
  return resp.data;
}

export async function getDashboardSummary(productLine?: string): Promise<DashboardSummary> {
  const resp = await client.get("/dashboard/summary", { params: { product_line: productLine || undefined } });
  return resp.data;
}

export async function getDashboardAlerts(productLine?: string): Promise<DashboardAlerts> {
  const resp = await client.get("/dashboard/alerts", { params: { product_line: productLine || undefined } });
  return resp.data;
}

export async function getDashboardRecentActions(): Promise<DashboardRecentAction[]> {
  const resp = await client.get("/dashboard/recent-actions");
  return resp.data;
}
```

- [ ] **Step 3: 验证编译**

Run: `cd frontend && npm run build`
Expected: 编译成功

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/dashboard.ts
git commit -m "feat(dashboard): add TypeScript types and API client for new endpoints"
```

### Task 4: 重写仪表盘前端页面

**Files:**
- Modify: `frontend/src/pages/dashboard/DashboardPage.tsx`

- [ ] **Step 1: 重写 DashboardPage 为三层布局**

替换整个 `DashboardPage.tsx`：

```tsx
import { useEffect, useState } from "react";
import { Row, Col, Card, List, Button, Tag, Typography, Space, Statistic } from "antd";
import {
  AlertOutlined,
  ClockCircleOutlined,
  WarningOutlined,
  RiseOutlined,
  PlusOutlined,
  FileTextOutlined,
  BugOutlined,
  CustomerServiceOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import {
  getDashboardSummary,
  getDashboardAlerts,
  getDashboardRecentActions,
} from "../../api/dashboard";
import type { DashboardSummary, DashboardAlerts, DashboardRecentAction } from "../../types";
import { useProductLineStore } from "../../store/productLineStore";

const { Title, Text } = Typography;

export default function DashboardPage() {
  const navigate = useNavigate();
  const productLine = useProductLineStore((s) => s.selected);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [alerts, setAlerts] = useState<DashboardAlerts | null>(null);
  const [recentActions, setRecentActions] = useState<DashboardRecentAction[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      getDashboardSummary(productLine || undefined),
      getDashboardAlerts(productLine || undefined),
      getDashboardRecentActions(),
    ])
      .then(([s, a, r]) => {
        setSummary(s);
        setAlerts(a);
        setRecentActions(r);
      })
      .finally(() => setLoading(false));
  }, [productLine]);

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>
        质量仪表盘
      </Title>

      {/* 顶部指标卡 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable onClick={() => navigate("/capa?pending_action=true")}>
            <Statistic
              title="待办事项"
              value={summary?.pending_actions ?? 0}
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: (summary?.pending_actions ?? 0) > 0 ? "#FAAD14" : "#52C41A" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable onClick={() => navigate("/capa?overdue=true")}>
            <Statistic
              title="超期任务"
              value={summary?.overdue_tasks ?? 0}
              prefix={<AlertOutlined />}
              valueStyle={{ color: (summary?.overdue_tasks ?? 0) > 0 ? "#FF4D4F" : "#52C41A" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable onClick={() => navigate("/fmea?risk=high")}>
            <Statistic
              title="高风险项"
              value={summary?.high_risk_items ?? 0}
              prefix={<WarningOutlined />}
              valueStyle={{ color: (summary?.high_risk_items ?? 0) > 0 ? "#FF4D4F" : "#52C41A" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="本月趋势"
              value={summary?.month_trend ?? 0}
              prefix={<RiseOutlined />}
              valueStyle={{
                color: (summary?.month_trend ?? 0) >= 0 ? "#52C41A" : "#FF4D4F",
              }}
            />
          </Card>
        </Col>
      </Row>

      {/* 风险预警区 */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={8}>
          <Card title="高 RPN FMEA" size="small" loading={loading}>
            <List
              dataSource={alerts?.high_rpn_fmeas ?? []}
              locale={{ emptyText: "无高风险项" }}
              renderItem={(item) => (
                <List.Item
                  style={{ cursor: "pointer" }}
                  onClick={() => navigate(`/fmea/${item.fmea_id}`)}
                >
                  <List.Item.Meta
                    title={item.document_no}
                    description={item.node_name}
                  />
                  <Tag color="error">RPN={item.rpn}</Tag>
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="超期 CAPA" size="small" loading={loading}>
            <List
              dataSource={alerts?.overdue_capas ?? []}
              locale={{ emptyText: "无超期任务" }}
              renderItem={(item) => (
                <List.Item
                  style={{ cursor: "pointer" }}
                  onClick={() => navigate(`/capa/${item.report_id}`)}
                >
                  <List.Item.Meta
                    title={item.document_no}
                    description={`超期 ${item.overdue_days} 天`}
                  />
                  <Tag color="error">{item.overdue_days}天</Tag>
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="PPM 超标供应商" size="small" loading={loading}>
            <List
              dataSource={alerts?.high_ppm_suppliers ?? []}
              locale={{ emptyText: "无超标供应商" }}
              renderItem={(item) => (
                <List.Item
                  style={{ cursor: "pointer" }}
                  onClick={() => navigate(`/suppliers/${item.supplier_id}`)}
                >
                  <List.Item.Meta
                    title={item.supplier_name}
                    description={`PPM: ${item.ppm}`}
                  />
                  <Tag color="warning">PPM={item.ppm}</Tag>
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>

      {/* 底部：最近操作 + 快速入口 */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={16}>
          <Card title="最近操作" size="small" loading={loading}>
            <List
              dataSource={recentActions}
              locale={{ emptyText: "暂无操作记录" }}
              renderItem={(item) => {
                const typeMap: Record<string, { label: string; path: string }> = {
                  fmea_documents: { label: "FMEA", path: "/fmea" },
                  capa_eightd: { label: "CAPA", path: "/capa" },
                };
                const info = typeMap[item.table_name] || {
                  label: item.table_name,
                  path: "/",
                };
                return (
                  <List.Item
                    style={{ cursor: "pointer" }}
                    onClick={() => navigate(`${info.path}/${item.record_id}`)}
                  >
                    <List.Item.Meta
                      title={`${info.label} - ${item.entity_no}`}
                      description={`${item.action} · ${new Date(item.operated_at).toLocaleString("zh-CN")}`}
                    />
                  </List.Item>
                );
              }}
            />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="快速入口" size="small">
            <Space direction="vertical" style={{ width: "100%" }}>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                block
                onClick={() => navigate("/fmea")}
              >
                新建 FMEA
              </Button>
              <Button
                icon={<PlusOutlined />}
                block
                onClick={() => navigate("/capa")}
              >
                新建 CAPA
              </Button>
              <Button
                icon={<PlusOutlined />}
                block
                onClick={() => navigate("/customer-quality")}
              >
                新建客诉
              </Button>
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
```

- [ ] **Step 2: 验证编译**

Run: `cd frontend && npm run build`
Expected: 编译成功

- [ ] **Step 3: 手动验证**

Run: `cd frontend && npm run dev`
- 访问仪表盘，确认三层布局
- 确认顶部 4 个指标卡正确显示
- 确认风险预警区 3 个列表正确显示
- 点击指标卡确认跳转正确
- 确认最近操作和快速入口区域

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/dashboard/DashboardPage.tsx
git commit -m "feat(dashboard): redesign to three-tier layout with alerts and recent actions"
```

---

## Phase 3: 跨模块关联 — 数据库 + API

### Task 5: Alembic 迁移 — 新增 fmea_node_id 和 supplier_id 字段

**Files:**
- Create: `backend/alembic/versions/008_add_cross_module_links.py`

- [ ] **Step 1: 创建迁移文件**

```python
"""add cross-module link fields

Revision ID: 026_add_cross_module_links
Revises: 025_add_customer_audit_fields
Create Date: 2026-05-29
"""

from alembic import op
import sqlalchemy as sa

revision = "026_add_cross_module_links"
down_revision = "025_add_customer_audit_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CAPA → FMEA 失效模式节点级关联
    op.add_column(
        "capa_eightd",
        sa.Column("fmea_node_id", sa.String(36), nullable=True),
    )

    # 客诉 → 供应商关联
    op.add_column(
        "customer_complaints",
        sa.Column(
            "supplier_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.supplier_id"),
            nullable=True,
        ),
    )

    # 特殊特性引用位置表
    op.create_table(
        "special_characteristic_links",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sc_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("special_characteristics.sc_id"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("source_item_id", sa.String(36), nullable=False),
    )
    op.create_unique_constraint(
        "uq_sc_link",
        "special_characteristic_links",
        ["sc_id", "source_type", "source_id", "source_item_id"],
    )


def downgrade() -> None:
    op.drop_table("special_characteristic_links")
    op.drop_column("customer_complaints", "supplier_id")
    op.drop_column("capa_eightd", "fmea_node_id")
```

- [ ] **Step 2: 验证迁移语法**

Run: `cd backend && python -c "import alembic.config; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/008_add_cross_module_links.py
git commit -m "feat(db): add cross-module link fields (fmea_node_id, supplier_id, sc_links)"
```

### Task 6: 更新后端模型 — CAPA 和 CustomerComplaint

**Files:**
- Modify: `backend/app/models/capa.py`
- Modify: `backend/app/models/customer_quality.py`
- Create: `backend/app/models/special_characteristic_link.py`

- [ ] **Step 1: 在 CAPAEightD 模型中添加 fmea_node_id**

在 `backend/app/models/capa.py:30` 的 `fmea_ref_id` 之后添加：

```python
fmea_node_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
```

- [ ] **Step 2: 在 CustomerComplaint 模型中添加 supplier_id**

在 `backend/app/models/customer_quality.py:79` 的 `scar_ref_id` 之后添加：

```python
supplier_id: Mapped[uuid.UUID | None] = mapped_column(
    UUID(as_uuid=True), ForeignKey("suppliers.supplier_id"), nullable=True
)
```

并添加 relationship：

```python
supplier = relationship("Supplier", foreign_keys=[supplier_id])
```

- [ ] **Step 3: 创建 SpecialCharacteristicLink 模型**

创建 `backend/app/models/special_characteristic_link.py`：

```python
import uuid

from sqlalchemy import String, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SpecialCharacteristicLink(Base):
    __tablename__ = "special_characteristic_links"
    __table_args__ = (
        UniqueConstraint(
            "sc_id", "source_type", "source_id", "source_item_id",
            name="uq_sc_link",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("special_characteristics.sc_id"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_item_id: Mapped[str] = mapped_column(String(36), nullable=False)
```

- [ ] **Step 4: 验证模型导入**

Run: `cd backend && python -c "from app.models.special_characteristic_link import SpecialCharacteristicLink; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/capa.py backend/app/models/customer_quality.py backend/app/models/special_characteristic_link.py
git commit -m "feat(models): add cross-module link fields and SpecialCharacteristicLink model"
```

### Task 7: 新增跨模块关联 API — CAPA↔FMEA

**Files:**
- Modify: `backend/app/schemas/capa.py`
- Modify: `backend/app/services/capa_service.py`
- Modify: `backend/app/api/capa.py`

- [ ] **Step 1: 在 CAPA schema 中添加 fmea_node_id 字段**

在 `backend/app/schemas/capa.py` 的 CAPA 相关 schema 中添加 `fmea_node_id: str | None = None`。

- [ ] **Step 2: 在 capa_service 中添加关联 FMEA 节点的方法**

```python
async def link_fmea_node(
    db: AsyncSession, report_id: str, fmea_id: str, fmea_node_id: str
) -> None:
    from app.models.capa import CAPAEightD
    q = select(CAPAEightD).where(CAPAEightD.report_id == report_id)
    capa = (await db.execute(q)).scalar_one_or_none()
    if not capa:
        raise ValueError("CAPA not found")
    capa.fmea_ref_id = fmea_id
    capa.fmea_node_id = fmea_node_id
    await db.commit()


async def get_capas_by_fmea_node(
    db: AsyncSession, fmea_id: str, fmea_node_id: str | None = None
) -> list[dict]:
    from app.models.capa import CAPAEightD
    q = select(CAPAEightD).where(CAPAEightD.fmea_ref_id == fmea_id)
    if fmea_node_id:
        q = q.where(CAPAEightD.fmea_node_id == fmea_node_id)
    result = await db.execute(q)
    return [
        {
            "report_id": str(c.report_id),
            "document_no": c.document_no,
            "title": c.title,
            "status": c.status,
        }
        for c in result.scalars().all()
    ]
```

- [ ] **Step 3: 在 CAPA API router 中添加端点**

```python
@router.get("/{report_id}/related-fmea")
async def get_related_fmea(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    from app.models.capa import CAPAEightD
    from app.models.fmea import FMEADocument

    capa = (
        await db.execute(
            select(CAPAEightD).where(CAPAEightD.report_id == report_id)
        )
    ).scalar_one_or_none()
    if not capa:
        raise HTTPException(status_code=404, detail="CAPA not found")
    if not capa.fmea_ref_id:
        return {"fmea_id": None, "document_no": None, "fmea_node_id": None}

    fmea = (
        await db.execute(
            select(FMEADocument).where(FMEADocument.fmea_id == capa.fmea_ref_id)
        )
    ).scalar_one_or_none()

    return {
        "fmea_id": str(capa.fmea_ref_id),
        "document_no": fmea.document_no if fmea else None,
        "fmea_node_id": capa.fmea_node_id,
    }


@router.get("/by-fmea-node/{fmea_id}")
async def get_capas_by_fmea_node(
    fmea_id: str,
    fmea_node_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await capa_service.get_capas_by_fmea_node(db, fmea_id, fmea_node_id)
```

- [ ] **Step 4: 验证编译**

Run: `cd backend && python -c "from app.api.capa import router; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/capa.py backend/app/services/capa_service.py backend/app/api/capa.py
git commit -m "feat(capa): add CAPA-FMEA node-level linking API"
```

### Task 8: 新增跨模块关联 API — 客诉→供应商

**Files:**
- Modify: `backend/app/schemas/customer_quality.py`
- Modify: `backend/app/services/customer_quality_service.py`
- Modify: `backend/app/api/customer_quality.py`

- [ ] **Step 1: 在客诉 schema 中添加 supplier_id 字段**

在 `backend/app/schemas/customer_quality.py` 的客诉相关 schema 中添加 `supplier_id: str | None = None`。

- [ ] **Step 2: 在客诉 service 中添加按供应商查询方法**

```python
async def get_complaints_by_supplier(
    db: AsyncSession, supplier_id: str
) -> list[dict]:
    from app.models.customer_quality import CustomerComplaint
    q = select(CustomerComplaint).where(
        CustomerComplaint.supplier_id == supplier_id
    )
    result = await db.execute(q)
    return [
        {
            "complaint_id": str(c.complaint_id),
            "complaint_no": c.complaint_no,
            "severity": c.severity,
            "status": c.status,
            "defect_desc": c.defect_desc,
        }
        for c in result.scalars().all()
    ]
```

- [ ] **Step 3: 在客诉 API router 中添加端点**

```python
@router.get("/by-supplier/{supplier_id}")
async def get_complaints_by_supplier(
    supplier_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await customer_quality_service.get_complaints_by_supplier(db, supplier_id)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/customer_quality.py backend/app/services/customer_quality_service.py backend/app/api/customer_quality.py
git commit -m "feat(customer-quality): add complaint-supplier linking API"
```

### Task 9: 新增跨模块关联 API — 特殊特性引用

**Files:**
- Modify: `backend/app/services/special_characteristic_service.py`
- Modify: `backend/app/api/special_characteristic.py`

- [ ] **Step 1: 在特殊特性 service 中添加引用查询方法**

```python
async def get_sc_references(
    db: AsyncSession, sc_id: str
) -> list[dict]:
    from app.models.special_characteristic_link import SpecialCharacteristicLink
    q = select(SpecialCharacteristicLink).where(
        SpecialCharacteristicLink.sc_id == sc_id
    )
    result = await db.execute(q)
    return [
        {
            "source_type": link.source_type,
            "source_id": str(link.source_id),
            "source_item_id": link.source_item_id,
        }
        for link in result.scalars().all()
    ]


async def add_sc_reference(
    db: AsyncSession,
    sc_id: str,
    source_type: str,
    source_id: str,
    source_item_id: str,
) -> None:
    from app.models.special_characteristic_link import SpecialCharacteristicLink
    link = SpecialCharacteristicLink(
        sc_id=sc_id,
        source_type=source_type,
        source_id=source_id,
        source_item_id=source_item_id,
    )
    db.add(link)
    await db.commit()
```

- [ ] **Step 2: 在特殊特性 API router 中添加端点**

```python
@router.get("/{sc_id}/references")
async def get_sc_references(
    sc_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await special_characteristic_service.get_sc_references(db, sc_id)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/special_characteristic_service.py backend/app/api/special_characteristic.py
git commit -m "feat(special-characteristic): add SC reference tracking API"
```

### Task 10: 新增跨模块关联 API — 供应商聚合

**Files:**
- Modify: `backend/app/services/supplier_service.py`
- Modify: `backend/app/api/supplier.py`

- [ ] **Step 1: 在供应商 service 中添加聚合查询方法**

```python
async def get_supplier_related(
    db: AsyncSession, supplier_id: str
) -> dict:
    from app.models.customer_quality import CustomerComplaint
    from app.models.iqc_inspection import IqcInspection
    from app.models.supplier import SupplierSCAR

    # 客诉
    complaints_q = select(CustomerComplaint).where(
        CustomerComplaint.supplier_id == supplier_id
    )
    complaints = (await db.execute(complaints_q)).scalars().all()

    # IQC 不合格
    iqc_q = select(IqcInspection).where(
        IqcInspection.supplier_id == supplier_id,
        IqcInspection.inspection_result == "reject",
    )
    iqc_rejects = (await db.execute(iqc_q)).scalars().all()

    # SCAR
    scar_q = select(SupplierSCAR).where(
        SupplierSCAR.supplier_id == supplier_id
    )
    scars = (await db.execute(scar_q)).scalars().all()

    return {
        "complaints": [
            {"id": str(c.complaint_id), "no": c.complaint_no, "status": c.status}
            for c in complaints
        ],
        "iqc_rejects": [
            {"id": str(i.inspection_id), "no": i.inspection_no, "result": i.result}
            for i in iqc_rejects
        ],
        "scars": [
            {"id": str(s.scar_id), "no": s.scar_no, "status": s.status}
            for s in scars
        ],
    }
```

- [ ] **Step 2: 在供应商 API router 中添加端点**

```python
@router.get("/{supplier_id}/related")
async def get_supplier_related(
    supplier_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await supplier_service.get_supplier_related(db, supplier_id)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/supplier_service.py backend/app/api/supplier.py
git commit -m "feat(supplier): add aggregated related data API (complaints, IQC, SCAR)"
```

---

## Phase 4: 跨模块关联 — 前端组件 + 集成

### Task 11: 创建前端跨模块关联组件

**Files:**
- Create: `frontend/src/components/cross-links/RelatedCAPAList.tsx`
- Create: `frontend/src/components/cross-links/RelatedFMEALink.tsx`
- Create: `frontend/src/components/cross-links/SupplierBadge.tsx`
- Create: `frontend/src/components/cross-links/APQPProgressCard.tsx`
- Create: `frontend/src/components/cross-links/SpecialCharacteristicTag.tsx`

- [ ] **Step 1: 创建 RelatedCAPAList 组件**

```tsx
// frontend/src/components/cross-links/RelatedCAPAList.tsx
import { useEffect, useState } from "react";
import { List, Tag, Typography } from "antd";
import { useNavigate } from "react-router-dom";
import client from "../../api/client";

interface RelatedCAPA {
  report_id: string;
  document_no: string;
  title: string;
  status: string;
}

export default function RelatedCAPAList({
  fmeaId,
  fmeaNodeId,
}: {
  fmeaId: string;
  fmeaNodeId?: string;
}) {
  const navigate = useNavigate();
  const [items, setItems] = useState<RelatedCAPA[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const params: Record<string, string> = {};
    if (fmeaNodeId) params.fmea_node_id = fmeaNodeId;
    client
      .get(`/capa/by-fmea-node/${fmeaId}`, { params })
      .then((r) => setItems(r.data))
      .finally(() => setLoading(false));
  }, [fmeaId, fmeaNodeId]);

  if (!items.length && !loading) return null;

  return (
    <List
      size="small"
      header={<Typography.Text strong>关联 CAPA</Typography.Text>}
      loading={loading}
      dataSource={items}
      renderItem={(item) => (
        <List.Item
          style={{ cursor: "pointer" }}
          onClick={() => navigate(`/capa/${item.report_id}`)}
        >
          <List.Item.Meta
            title={item.document_no}
            description={item.title}
          />
          <Tag>{item.status}</Tag>
        </List.Item>
      )}
    />
  );
}
```

- [ ] **Step 2: 创建 RelatedFMEALink 组件**

```tsx
// frontend/src/components/cross-links/RelatedFMEALink.tsx
import { useEffect, useState } from "react";
import { Tag, Space } from "antd";
import { useNavigate } from "react-router-dom";
import client from "../../api/client";

interface FMEAInfo {
  fmea_id: string;
  document_no: string;
}

export default function RelatedFMEALink({
  fmeaRefId,
  fmeaNodeId,
}: {
  fmeaRefId: string | null;
  fmeaNodeId?: string | null;
}) {
  const navigate = useNavigate();
  const [fmea, setFmea] = useState<FMEAInfo | null>(null);

  useEffect(() => {
    if (!fmeaRefId) return;
    client.get(`/fmea/${fmeaRefId}`).then((r) => {
      setFmea({ fmea_id: r.data.fmea_id, document_no: r.data.document_no });
    });
  }, [fmeaRefId]);

  if (!fmea) return null;

  const handleClick = () => {
    const url = fmeaNodeId
      ? `/fmea/${fmea.fmea_id}?node=${fmeaNodeId}`
      : `/fmea/${fmea.fmea_id}`;
    navigate(url);
  };

  return (
    <Tag color="blue" style={{ cursor: "pointer" }} onClick={handleClick}>
      {fmea.document_no}
      {fmeaNodeId && " (失效模式)"}
    </Tag>
  );
}
```

- [ ] **Step 3: 创建 SupplierBadge 组件**

```tsx
// frontend/src/components/cross-links/SupplierBadge.tsx
import { useEffect, useState } from "react";
import { Tag } from "antd";
import { useNavigate } from "react-router-dom";
import client from "../../api/client";

export default function SupplierBadge({
  supplierId,
}: {
  supplierId: string | null;
}) {
  const navigate = useNavigate();
  const [name, setName] = useState<string>("");

  useEffect(() => {
    if (!supplierId) return;
    client.get(`/suppliers/${supplierId}`).then((r) => {
      setName(r.data.name);
    });
  }, [supplierId]);

  if (!supplierId) return null;

  return (
    <Tag
      color="green"
      style={{ cursor: "pointer" }}
      onClick={() => navigate(`/suppliers/${supplierId}`)}
    >
      {name || "供应商"}
    </Tag>
  );
}
```

- [ ] **Step 4: 创建 APQPProgressCard 组件**

```tsx
// frontend/src/components/cross-links/APQPProgressCard.tsx
import { Card, Steps } from "antd";
import { useNavigate } from "react-router-dom";

interface SubModule {
  type: "fmea" | "control_plan" | "ppap";
  id: string;
  status: string;
  label: string;
}

export default function APQPProgressCard({
  subModules,
}: {
  subModules: SubModule[];
}) {
  const navigate = useNavigate();

  const pathMap: Record<string, string> = {
    fmea: "/fmea",
    control_plan: "/control-plans",
    ppap: "/ppap",
  };

  return (
    <Card title="子模块进度" size="small">
      <Steps
        direction="vertical"
        size="small"
        current={subModules.filter((m) => m.status === "approved").length}
        items={subModules.map((m) => ({
          title: m.label,
          description: m.status,
          style: { cursor: "pointer" },
          onClick: () => navigate(`${pathMap[m.type]}/${m.id}`),
        }))}
      />
    </Card>
  );
}
```

- [ ] **Step 5: 创建 SpecialCharacteristicTag 组件**

```tsx
// frontend/src/components/cross-links/SpecialCharacteristicTag.tsx
import { useEffect, useState } from "react";
import { Tag } from "antd";
import { useNavigate } from "react-router-dom";
import client from "../../api/client";

export default function SpecialCharacteristicTag({
  scId,
}: {
  scId: string | null;
}) {
  const navigate = useNavigate();
  const [code, setCode] = useState<string>("");

  useEffect(() => {
    if (!scId) return;
    client.get(`/special-characteristics/${scId}`).then((r) => {
      setCode(r.data.sc_code);
    });
  }, [scId]);

  if (!scId) return null;

  return (
    <Tag
      color="purple"
      style={{ cursor: "pointer" }}
      onClick={() => navigate(`/special-characteristics/${scId}`)}
    >
      {code || "SC"}
    </Tag>
  );
}
```

- [ ] **Step 6: 验证编译**

Run: `cd frontend && npm run build`
Expected: 编译成功

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/cross-links/
git commit -m "feat(components): add cross-module link components (RelatedCAPAList, RelatedFMEALink, SupplierBadge, APQPProgressCard, SpecialCharacteristicTag)"
```

### Task 12: 在 CAPA 详情页集成跨模块关联

**Files:**
- Modify: `frontend/src/pages/capa/CAPADetailPage.tsx`

- [ ] **Step 1: 在 CAPA 详情页顶部添加关联 FMEA 卡片**

在 CAPADetailPage 的详情区域添加：

```tsx
import RelatedFMEALink from "../../components/cross-links/RelatedFMEALink";
import SupplierBadge from "../../components/cross-links/SupplierBadge";

// 在详情页顶部添加：
<Card size="small" style={{ marginBottom: 16 }}>
  <Space>
    <Typography.Text strong>关联 FMEA：</Typography.Text>
    <RelatedFMEALink
      fmeaRefId={capa.fmea_ref_id}
      fmeaNodeId={capa.fmea_node_id}
    />
  </Space>
</Card>
```

- [ ] **Step 2: 验证编译**

Run: `cd frontend && npm run build`
Expected: 编译成功

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/capa/CAPADetailPage.tsx
git commit -m "feat(capa): integrate RelatedFMEALink in CAPA detail page"
```

### Task 13: 在客诉详情页集成跨模块关联

**Files:**
- Modify: `frontend/src/pages/customerQuality/ComplaintDetailPage.tsx`

- [ ] **Step 1: 在客诉详情页添加供应商关联**

```tsx
import SupplierBadge from "../../components/cross-links/SupplierBadge";
import RelatedFMEALink from "../../components/cross-links/RelatedFMEALink";

// 在客诉详情页添加：
<Space style={{ marginBottom: 16 }}>
  <Typography.Text strong>关联供应商：</Typography.Text>
  <SupplierBadge supplierId={complaint.supplier_id} />
  <Typography.Text strong>关联 FMEA：</Typography.Text>
  <RelatedFMEALink fmeaRefId={complaint.fmea_ref_id} />
</Space>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/customerQuality/ComplaintDetailPage.tsx
git commit -m "feat(customer-quality): integrate SupplierBadge and RelatedFMEALink in complaint detail"
```

### Task 14: 在供应商详情页集成聚合数据

**Files:**
- Modify: `frontend/src/pages/supplier/SupplierDetailPage.tsx`

- [ ] **Step 1: 在供应商详情页添加客诉/IQC/SCAR tabs**

```tsx
import { Tabs, List, Tag } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import client from "../../api/client";

// 在供应商详情页添加 tabs：
const [relatedData, setRelatedData] = useState<{
  complaints: Array<{id: string; no: string; status: string}>;
  iqc_rejects: Array<{id: string; no: string; result: string}>;
  scars: Array<{id: string; no: string; status: string}>;
}>({ complaints: [], iqc_rejects: [], scars: [] });

useEffect(() => {
  if (!supplierId) return;
  client.get(`/suppliers/${supplierId}/related`).then((r) => setRelatedData(r.data));
}, [supplierId]);

<Tabs items={[
  // ... 现有 tabs ...
  {
    key: "complaints",
    label: `客诉 (${relatedData.complaints.length})`,
    children: (
      <List
        dataSource={relatedData.complaints}
        renderItem={(item) => (
          <List.Item
            style={{ cursor: "pointer" }}
            onClick={() => navigate(`/customer-quality/complaints/${item.id}`)}
          >
            {item.no} <Tag>{item.status}</Tag>
          </List.Item>
        )}
      />
    ),
  },
  {
    key: "iqc",
    label: `IQC 不合格 (${relatedData.iqc_rejects.length})`,
    children: (
      <List
        dataSource={relatedData.iqc_rejects}
        renderItem={(item) => (
          <List.Item
            style={{ cursor: "pointer" }}
            onClick={() => navigate(`/iqc/inspections/${item.id}`)}
          >
            {item.no} <Tag color="error">{item.result}</Tag>
          </List.Item>
        )}
      />
    ),
  },
  {
    key: "scars",
    label: `SCAR (${relatedData.scars.length})`,
    children: (
      <List
        dataSource={relatedData.scars}
        renderItem={(item) => (
          <List.Item
            style={{ cursor: "pointer" }}
            onClick={() => navigate(`/scars/${item.id}`)}
          >
            {item.no} <Tag>{item.status}</Tag>
          </List.Item>
        )}
      />
    ),
  },
]} />
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/supplier/SupplierDetailPage.tsx
git commit -m "feat(supplier): add complaint/IQC/SCAR tabs to supplier detail page"
```

### Task 15: 在 FMEA 编辑器集成关联 CAPA 和 URL 参数定位

**Files:**
- Modify: `frontend/src/pages/fmea/FMEAEditorPage.tsx`

- [ ] **Step 1: 添加 URL 参数 node 解析和高亮逻辑**

```tsx
import { useSearchParams } from "react-router-dom";

// 在 FMEAEditorPage 组件内：
const [searchParams] = useSearchParams();
const highlightNodeId = searchParams.get("node");
const [highlightedRowKey, setHighlightedRowKey] = useState<string | null>(null);

// 在 rows 计算后，找到高亮行：
useEffect(() => {
  if (highlightNodeId && rows.length > 0) {
    const targetRow = rows.find(
      (r) => r.failureModeNodeId === highlightNodeId
    );
    if (targetRow) {
      setHighlightedRowKey(targetRow.key);
      // 滚动到目标行
      setTimeout(() => {
        const el = document.querySelector(`[data-row-key="${targetRow.key}"]`);
        el?.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 300);
    }
  }
}, [highlightNodeId, rows]);
```

- [ ] **Step 2: 在 Table 的 rowClassName 中添加高亮样式**

```tsx
<Table
  // ... 现有 props ...
  rowClassName={(record) =>
    record.key === highlightedRowKey ? "highlighted-row" : ""
  }
/>

// 在页面的 <style> 或 CSS 中添加：
// .highlighted-row { background-color: #fffbe6 !important; }
```

- [ ] **Step 3: 添加"关联 CAPA"tab**

在 FMEA 编辑器的 tab 区域添加：

```tsx
import RelatedCAPAList from "../../components/cross-links/RelatedCAPAList";

// 在 tabs 中添加：
{
  key: "related-capa",
  label: "关联 CAPA",
  children: selectedFunctionId ? (
    <RelatedCAPAList
      fmeaId={fmea!.fmea_id}
      fmeaNodeId={selectedFunctionId}
    />
  ) : (
    <Typography.Text type="secondary">请先选择一个失效模式行</Typography.Text>
  ),
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/fmea/FMEAEditorPage.tsx
git commit -m "feat(fmea): add URL node定位, row高亮, and 关联CAPA tab"
```

### Task 16: 在列表页支持 query 参数筛选

**Files:**
- Modify: `frontend/src/pages/fmea/FMEAListPage.tsx`
- Modify: `frontend/src/pages/capa/CAPAListPage.tsx`
- Modify: `frontend/src/pages/customerQuality/CustomerQualityPage.tsx`

- [ ] **Step 1: FMEA 列表页支持 ?risk=high 参数**

```tsx
import { useSearchParams } from "react-router-dom";

const [searchParams] = useSearchParams();
const riskFilter = searchParams.get("risk");

// 在加载列表数据时，如果 risk=high，添加筛选条件
useEffect(() => {
  const params: Record<string, string> = {};
  if (riskFilter === "high") params.high_rpn = "true";
  // 传给 API 调用
}, [riskFilter]);
```

- [ ] **Step 2: CAPA 列表页支持 ?overdue=true 和 ?pending_action=true 参数**

```tsx
const [searchParams] = useSearchParams();
const overdueFilter = searchParams.get("overdue");
const pendingFilter = searchParams.get("pending_action");

// 在加载列表数据时应用筛选
```

- [ ] **Step 3: 客诉列表页支持 ?status=open 参数**

```tsx
const [searchParams] = useSearchParams();
const statusFilter = searchParams.get("status");

// 在加载列表数据时应用筛选
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/fmea/FMEAListPage.tsx frontend/src/pages/capa/CAPAListPage.tsx frontend/src/pages/customerQuality/CustomerQualityPage.tsx
git commit -m "feat(lists): add query param filtering for dashboard drill-down"
```

---

## Phase 5: 目录重构

### Task 17: 逐模块迁移页面文件到新目录结构

**Files:**
- Modify: `frontend/src/App.tsx` (所有 import 路径)

- [ ] **Step 1: 迁移 planning 组（FMEA、控制计划、APQP、PPAP、特殊特性）**

```bash
mkdir -p frontend/src/pages/planning/{fmea,control-plan,apqp,ppap,special-characteristic}
mv frontend/src/pages/fmea/* frontend/src/pages/planning/fmea/
mv frontend/src/pages/control-plan/* frontend/src/pages/planning/control-plan/
mv frontend/src/pages/apqp/* frontend/src/pages/planning/apqp/
mv frontend/src/pages/ppap/* frontend/src/pages/planning/ppap/
mv frontend/src/pages/special-characteristic/* frontend/src/pages/planning/special-characteristic/
rmdir frontend/src/pages/fmea frontend/src/pages/control-plan frontend/src/pages/apqp frontend/src/pages/ppap frontend/src/pages/special-characteristic
```

更新 `App.tsx` 中的 import 路径，例如：
```tsx
// 旧：import FMEAListPage from "./pages/fmea/FMEAListPage";
// 新：import FMEAListPage from "./pages/planning/fmea/FMEAListPage";
```

Run: `cd frontend && npm run build`
Expected: 编译成功

- [ ] **Step 2: 迁移 shopfloor 组（SPC、MSA、质量目标、内部审核、管理评审）**

```bash
mkdir -p frontend/src/pages/shopfloor/{spc,msa,quality-goal,internal-audit,management-review}
mv frontend/src/pages/spc/* frontend/src/pages/shopfloor/spc/
mv frontend/src/pages/msa/* frontend/src/pages/shopfloor/msa/
mv frontend/src/pages/qualityGoal/* frontend/src/pages/shopfloor/quality-goal/
mv frontend/src/pages/internalAudit/* frontend/src/pages/shopfloor/internal-audit/
mv frontend/src/pages/managementReview/* frontend/src/pages/shopfloor/management-review/
rmdir frontend/src/pages/spc frontend/src/pages/msa frontend/src/pages/qualityGoal frontend/src/pages/internalAudit frontend/src/pages/managementReview
```

更新 App.tsx import 路径。

Run: `cd frontend && npm run build`
Expected: 编译成功

- [ ] **Step 3: 迁移 customer 组（客诉、客户审核、CAPA）**

```bash
mkdir -p frontend/src/pages/customer/{quality,audit,capa}
mv frontend/src/pages/customerQuality/* frontend/src/pages/customer/quality/
mv frontend/src/pages/customerAudit/* frontend/src/pages/customer/audit/
mv frontend/src/pages/capa/* frontend/src/pages/customer/capa/
rmdir frontend/src/pages/customerQuality frontend/src/pages/customerAudit frontend/src/pages/capa
```

更新 App.tsx import 路径。

Run: `cd frontend && npm run build`
Expected: 编译成功

- [ ] **Step 4: 迁移 supplier 组（供应商、SCAR、IQC）**

```bash
mkdir -p frontend/src/pages/supplier/{management,dashboard,scar,iqc}
# 移动供应商相关文件（注意 components 子目录）
mv frontend/src/pages/supplier/SupplierListPage.tsx frontend/src/pages/supplier/management/
mv frontend/src/pages/supplier/SupplierDetailPage.tsx frontend/src/pages/supplier/management/
mv frontend/src/pages/supplier/SupplierQualityPage.tsx frontend/src/pages/supplier/dashboard/
mv frontend/src/pages/supplier/components/* frontend/src/components/supplier/
rmdir frontend/src/pages/supplier/components
mv frontend/src/pages/scar/* frontend/src/pages/supplier/scar/
mv frontend/src/pages/iqc/* frontend/src/pages/supplier/iqc/
rmdir frontend/src/pages/scar frontend/src/pages/iqc
```

更新 App.tsx import 路径。

Run: `cd frontend && npm run build`
Expected: 编译成功

- [ ] **Step 5: 更新所有模块内部的相对 import 路径**

每个模块内的文件有相对 import（如 `../../api/fmea`、`../../types`）。迁移后路径深度变了，需要逐一修正。

**planning/fmea/** — 文件从 `pages/fmea/` 移到 `pages/planning/fmea/`（多一层），所有 `../../` 改为 `../../../`：
- `FMEAListPage.tsx`: `../../api/fmea` → `../../../api/fmea`, `../../types` → `../../../types`
- `FMEAEditorPage.tsx`: `../../api/fmea` → `../../../api/fmea`, `../../types` → `../../../types`, `../../utils/fmeaTable` → `../../../utils/fmeaTable`, `../../utils/fmea` → `../../../utils/fmea`, `../../store/authStore` → `../../../store/authStore`, `../../components/dfmea/` → `../../../components/dfmea/`

**planning/control-plan/** — 同理多一层：
- `ControlPlanListPage.tsx`: `../../api/controlPlan` → `../../../api/controlPlan`, `../../types` → `../../../types`
- `ControlPlanEditorPage.tsx`: `../../api/controlPlan` → `../../../api/controlPlan`, `../../types` → `../../../types`, `../../store/authStore` → `../../../store/authStore`, `../../components/control-plan/` → `../../../components/control-plan/`

**planning/apqp/** — 多一层：
- `APQPListPage.tsx`: `../../api/apqp` → `../../../api/apqp`, `../../types` → `../../../types`
- `APQPDetailPage.tsx`: `../../api/apqp` → `../../../api/apqp`, `../../types` → `../../../types`

**planning/ppap/** — 多一层：
- `PPAPListPage.tsx`: `../../api/ppap` → `../../../api/ppap`, `../../types` → `../../../types`
- `PPAPDetailPage.tsx`: `../../api/ppap` → `../../../api/ppap`, `../../types` → `../../../types`

**planning/special-characteristic/** — 多一层：
- `SCListPage.tsx`: `../../api/specialCharacteristic` → `../../../api/specialCharacteristic`, `../../types` → `../../../types`
- `SCDetailPage.tsx`: `../../api/specialCharacteristic` → `../../../api/specialCharacteristic`, `../../types` → `../../../types`
- `SCMatrixPage.tsx`: `../../api/specialCharacteristic` → `../../../api/specialCharacteristic`, `../../types` → `../../../types`
- `TraceabilityPage.tsx`: `../../api/specialCharacteristic` → `../../../api/specialCharacteristic`, `../../types` → `../../../types`

**shopfloor/spc/** — 多一层：
- `SPCListPage.tsx`: `../../api/spc` → `../../../api/spc`, `../../types` → `../../../types`
- `SPCDetailPage.tsx`: `../../api/spc` → `../../../api/spc`, `../../types` → `../../../types`, `../../types/spc` → `../../../types/spc`
- `VersionPanel.tsx`: `../../api/spc` → `../../../api/spc`, `../../types` → `../../../types`

**shopfloor/msa/** — 多一层：
- `GaugeListPage.tsx`: `../../api/msa` → `../../../api/msa`, `../../types` → `../../../types`
- `GaugeDetailPage.tsx`: `../../api/msa` → `../../../api/msa`, `../../types` → `../../../types`
- `MsaStudyListPage.tsx`: `../../api/msa` → `../../../api/msa`, `../../types` → `../../../types`
- `StudyDetailPage.tsx`: `../../api/msa` → `../../../api/msa`, `../../types` → `../../../types`

**shopfloor/quality-goal/** — 多一层：
- `QualityGoalListPage.tsx`: `../../api/qualityGoal` → `../../../api/qualityGoal`, `../../types` → `../../../types`

**shopfloor/internal-audit/** — 多一层：
- `InternalAuditListPage.tsx`: `../../api/audit` → `../../../api/audit`, `../../types` → `../../../types`
- `InternalAuditDetailPage.tsx`: `../../api/audit` → `../../../api/audit`, `../../types` → `../../../types`

**shopfloor/management-review/** — 多一层：
- `ManagementReviewListPage.tsx`: `../../api/managementReview` → `../../../api/managementReview`, `../../types` → `../../../types`
- `ManagementReviewDetailPage.tsx`: `../../api/managementReview` → `../../../api/managementReview`, `../../types` → `../../../types`

**customer/quality/** — 多一层（从 `pages/customerQuality/` 到 `pages/customer/quality/`）：
- `CustomerQualityPage.tsx`: `../../api/customerQuality` → `../../../api/customerQuality`, `../../types` → `../../../types`
- `ComplaintDetailPage.tsx`: `../../api/customerQuality` → `../../../api/customerQuality`, `../../types` → `../../../types`
- `RMADetailPage.tsx`: `../../api/customerQuality` → `../../../api/customerQuality`, `../../types` → `../../../types`

**customer/audit/** — 多一层（从 `pages/customerAudit/` 到 `pages/customer/audit/`）：
- `CustomerAuditListPage.tsx`: `../../api/audit` → `../../../api/audit`, `../../types` → `../../../types`
- `CustomerAuditDetailPage.tsx`: `../../api/audit` → `../../../api/audit`, `../../types` → `../../../types`

**customer/capa/** — 多一层（从 `pages/capa/` 到 `pages/customer/capa/`）：
- `CAPAListPage.tsx`: `../../api/capa` → `../../../api/capa`, `../../types` → `../../../types`
- `CAPADetailPage.tsx`: `../../api/capa` → `../../../api/capa`, `../../types` → `../../../types`

**supplier/management/** — 多一层（从 `pages/supplier/` 到 `pages/supplier/management/`）：
- `SupplierListPage.tsx`: `../../api/supplier` → `../../../api/supplier`, `../../types` → `../../../types`
- `SupplierDetailPage.tsx`: `../../api/supplier` → `../../../api/supplier`, `../../types` → `../../../types`

**supplier/dashboard/** — 多一层：
- `SupplierQualityPage.tsx`: `../../api/supplier` → `../../../api/supplier`, `../../types` → `../../../types`

**supplier/scar/** — 多一层（从 `pages/scar/` 到 `pages/supplier/scar/`）：
- `SCARListPage.tsx`: `../../api/scar` → `../../../api/scar`, `../../types` → `../../../types`
- `SCARDetailPage.tsx`: `../../api/scar` → `../../../api/scar`, `../../types` → `../../../types`

**supplier/iqc/** — 多一层（从 `pages/iqc/` 到 `pages/supplier/iqc/`）：
- `IqcInspectionListPage.tsx`: `../../api/iqc` → `../../../api/iqc`, `../../types` → `../../../types`
- `IqcInspectionDetailPage.tsx`: `../../api/iqc` → `../../../api/iqc`, `../../types` → `../../../types`
- `IqcMaterialListPage.tsx`: `../../api/iqc` → `../../../api/iqc`, `../../types` → `../../../types`

Run: `cd frontend && npm run build`
Expected: 编译成功

- [ ] **Step 6: Commit**

```bash
git add -A frontend/src/pages/ frontend/src/App.tsx frontend/src/components/supplier/
git commit -m "refactor(frontend): reorganize pages into business group directories"
```

---

## 完成检查

- [ ] 所有 5 个阶段完成
- [ ] `cd frontend && npm run build` 编译通过
- [ ] `cd backend && python -c "from app.main import app; print('OK')"` 后端启动正常
- [ ] 仪表盘三层布局正常显示
- [ ] 侧边栏分组正确，选中状态正确
- [ ] 跨模块关联跳转正常（CAPA↔FMEA、客诉→供应商、供应商聚合）
- [ ] 目录重构后所有页面功能正常

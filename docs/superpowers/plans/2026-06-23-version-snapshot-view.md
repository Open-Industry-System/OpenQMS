# FMEA / Control Plan 版本快照只读查看 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 FMEA 与 CP 编辑器「查看版本」按钮从占位 `message.info` 改为就地加载版本快照并以只读模式渲染（横幅 + 返回当前版本），同时隔离当前文档态控件、重置选择态、加协作 guard。

**Architecture:** 在每个编辑器新增 `viewingVersion` 状态；覆盖 `usePermission()` 的 `canEdit`/`canApprove`（`viewingVersion` 非空时强制 `false`）让全部 `disabled={!canEdit(...)}` 控件转只读；`onViewSnapshot` 调 `getFMEAVersion`/`getCPVersion` 加载快照填入现有 state；进入/退出时重置选择态与图谱缓存；顶部 `Alert` 横幅 + 「返回当前版本」；CP 隐藏 sync/stale/ValidationPanel 等当前文档态控件；`useCollaboration` 的 `startEditing` 加单点 guard。

**Tech Stack:** React 18 + TypeScript 5.6 + Ant Design 5.29 + react-i18next + Vitest + @testing-library/react

## Global Constraints

- 中文 UI（zh-CN）为主，en-US 同步；新 i18n key 必须同时加到 `frontend/src/locales/zh-CN/*.json` 与 `frontend/src/locales/en-US/*.json`。
- 错误处理沿用各编辑器现有内联风格 `err?.response?.data?.detail || t("...")`。**不得引入 `formatFMEAError`**（本 worktree 不存在）。
- **行号提示来自本 worktree**（`frontend/src/...` 相对 worktree 根）。代码定位以**内容锚点**（exact 字符串搜索）为准，行号仅为辅助；实现时若行号偏移以内容锚点为准。
- 所有改动须 `npm run lint` + `npm run build`（含 `tsc --noEmit`）通过；现有 FMEA 编辑器测试须全绿。
- 后端**无改动**：`GET /api/fmea/{id}/versions/{major}/{minor}` 返回 `FMEAVersionDetail`（`snapshot`+`sha256_hash`）；`GET /api/control-plans/{id}/versions/{major}/{minor}` 返回 `ControlPlanVersionDetail`（`header_snapshot`+`items_snapshot`+`sha256_hash`）；rollback 返回 `RollbackResponse`。
- 命名：FMEA 用 `canEdit`/`canApprove`（重命名 hook 返回为 `rawCanEdit`/`rawCanApprove`）；CP 用 `canEdit`（已有）+ 新增 `canApproveAllowed`。

---

## File Structure

- **Modify** `frontend/src/types/index.ts` — `VersionBase` nullable + `version_id`、`FMEAVersion`/`CPVersion`/`*Detail`/`CPVersionHeader`/`RollbackResponse`。
- **Modify** `frontend/src/api/version.ts` — 修正返回类型。
- **Modify** `frontend/src/components/version/VersionHistoryTab.tsx` — `getChangeTypeConfig` 接受 `string | null`。
- **Modify** `frontend/src/locales/{zh-CN,en-US}/fmea.json` + `controlPlan.json` — 新 i18n keys。
- **Modify** `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx` — viewingVersion、权限包装、load/exit（含选择态重置 + graphDataRef）、startEditing guard、横幅、Alert import、占位点。
- **Modify** `frontend/src/pages/planning/control-plan/ControlPlanEditorPage.tsx` — viewingVersion、canApproveAllowed、load/exit（含 versionHeader）、startEditing guard、快照态隔离、横幅、占位点。
- **Create** `frontend/src/pages/planning/fmea/FMEAVersionSnapshot.test.tsx` 与 `frontend/src/pages/planning/control-plan/CPVersionSnapshot.test.tsx`。

---

### Task 1: 修正类型定义 (types/index.ts)

**Files:**
- Modify: `frontend/src/types/index.ts`（`// --- Version Management ---` 块）

**Interfaces:**
- Produces: `VersionBase`（nullable + `version_id`）、`FMEAVersion`、`FMEAVersionDetail`、`CPVersion`（含 `source_fmea_version_id`）、`CPVersionDetail`、`CPVersionHeader`、`RollbackResponse`。

- [ ] **Step 1: 替换 Version Management 类型块**

打开 `frontend/src/types/index.ts`，定位 `// --- Version Management ---`，把 `VersionBase` 起到 `CPVersion` 的整块替换为：

```ts
export interface VersionBase {
  version_id: string;
  major_no: number;
  minor_no: number;
  change_type: string | null;
  change_summary: string | null;
  created_by: string | null;
  created_at: string;
}

export interface FMEAVersion extends VersionBase {
  fmea_id: string;
}

export interface FMEAVersionDetail extends FMEAVersion {
  snapshot: GraphData;
  sha256_hash: string;
}

export interface CPVersion extends VersionBase {
  cp_id: string;
  source_fmea_version_id: string | null;
}

export interface CPVersionHeader {
  document_no: string | null;
  title: string | null;
  fmea_ref_id: string | null;
  product_line_code: string | null;
  status: string | null;
  phase: string | null;
  part_no: string | null;
  part_name: string | null;
  contact_info: string | null;
  drawing_rev: string | null;
  org_factory: string | null;
  core_group: string | null;
}

export interface CPVersionDetail extends CPVersion {
  header_snapshot: CPVersionHeader;
  items_snapshot: ControlPlanItem[];
  sha256_hash: string;
}

export interface RollbackResponse {
  version_id: string;
  major_no: number;
  minor_no: number;
  change_type: string | null;
  change_summary: string | null;
  created_at: string;
}
```

> `GraphData` 与 `ControlPlanItem` 在本文件已存在。删除原 `FMEAVersion.graph_data` 与 `CPVersion.items` 字段。

- [ ] **Step 2: VersionHistoryTab.getChangeTypeConfig 接受 null**

打开 `frontend/src/components/version/VersionHistoryTab.tsx`，定位 `const getChangeTypeConfig = (changeType: string):`，改为：

```ts
  const getChangeTypeConfig = (changeType: string | null): { label: string; color: string } => {
    switch (changeType) {
      case "submit":
        return { label: t("history.changeTypes.submit"), color: "blue" };
      case "approve":
        return { label: t("history.changeTypes.approve"), color: "green" };
      case "manual":
        return { label: t("history.changeTypes.manual"), color: "default" };
      case "rollback":
        return { label: t("history.changeTypes.rollback"), color: "orange" };
      case "fmea_sync":
        return { label: t("history.changeTypes.fmea_sync"), color: "purple" };
      default:
        return { label: changeType ?? "", color: "default" };
    }
  };
```

- [ ] **Step 3: 检查受影响引用**

Run: `cd frontend && grep -rn "\.graph_data\|\.items\b" src/components/version src/components/version/*.tsx | grep -i version` 以及 `grep -rn "RollbackConfirmModal" src/components/version`

Expected: `VersionHistoryTab`/`VersionCompareView`/`RollbackConfirmModal` 对 `FMEAVersion`/`CPVersion` 仅访问 list item 字段。若 `RollbackConfirmModal` 用了 detail 字段，把其 props 类型改为对应 `*Detail`（预期无需改动）。

- [ ] **Step 4: 验证编译**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -40`

Expected: 无新增错误（`version.ts` 的返回类型错误由 Task 2 修）。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/components/version/VersionHistoryTab.tsx
git commit -m "refactor(types): align version types with backend (nullable, version_id, detail split)"
```

---

### Task 2: 修正 API 客户端返回类型 (api/version.ts)

**Files:**
- Modify: `frontend/src/api/version.ts`

**Interfaces:**
- Consumes: Task 1 类型。
- Produces: `getFMEAVersion(): Promise<FMEAVersionDetail>`、`getCPVersion(): Promise<CPVersionDetail>`，供 Task 4/6 调用。

- [ ] **Step 1: 更新 import 与返回类型**

打开 `frontend/src/api/version.ts`，把顶部 import 改为：

```ts
import client from "./client";
import type {
  FMEAVersion,
  FMEAVersionDetail,
  CPVersion,
  CPVersionDetail,
  VersionListResponse,
  FMEACompareResponse,
  CPCompareResponse,
  VerifyResponse,
  SyncPreviewResponse,
  RollbackResponse,
} from "../types";
```

把 `getFMEAVersion` 与 `createFMEAVersion` 返回类型改为 `Promise<FMEAVersionDetail>`；`rollbackFMEAVersion` 改为 `Promise<RollbackResponse>`。CP 同理：`getCPVersion`/`createCPVersion` → `Promise<CPVersionDetail>`，`rollbackCPVersion` → `Promise<RollbackResponse>`。

示例（rollbackFMEAVersion）：
```ts
export async function rollbackFMEAVersion(
  fmeaId: string,
  major: number,
  minor: number,
  data: { reason: string }
): Promise<RollbackResponse> {
  const resp = await client.post(
    `/fmea/${fmeaId}/versions/${major}/${minor}/rollback`,
    data
  );
  return resp.data;
}
```

- [ ] **Step 2: 验证编译**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -40`

Expected: 无错误（或仅剩 Task 4/6 编辑器内部错误）。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/version.ts
git commit -m "refactor(api): correct version client return types (detail vs rollback)"
```

---

### Task 3: FMEA i18n keys

**Files:**
- Modify: `frontend/src/locales/zh-CN/fmea.json` + `frontend/src/locales/en-US/fmea.json`

**Interfaces:**
- Produces: `messages.viewingVersion`、`actions.exitVersion`、`messages.loadVersionFailed`。

- [ ] **Step 1: zh-CN fmea.json**

在 `messages` 块内，把 `"viewSnapshot": "查看版本 v{{version}} 快照（功能开发中）",` 改为并在其后追加：
```json
    "viewSnapshot": "查看版本 v{{version}} 快照",
    "viewingVersion": "正在查看 v{{version}} 快照（只读）",
    "loadVersionFailed": "加载版本快照失败",
```
在 `actions` 块内（紧邻 `save` 之后）追加：
```json
    "exitVersion": "返回当前版本",
```

- [ ] **Step 2: en-US fmea.json**

同样位置：
```json
    "viewSnapshot": "View version v{{version}} snapshot",
    "viewingVersion": "Viewing v{{version}} snapshot (read-only)",
    "loadVersionFailed": "Failed to load version snapshot",
```
`actions`：
```json
    "exitVersion": "Return to current version",
```

- [ ] **Step 3: 验证 JSON**

Run: `cd frontend && node -e "JSON.parse(require('fs').readFileSync('src/locales/zh-CN/fmea.json','utf8')); JSON.parse(require('fs').readFileSync('src/locales/en-US/fmea.json','utf8')); console.log('ok')"`

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/locales/zh-CN/fmea.json frontend/src/locales/en-US/fmea.json
git commit -m "i18n(fmea): add version snapshot read-only banner keys"
```

---

### Task 4: FMEA 编辑器 — 快照只读模式

**Files:**
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`
- Test: `frontend/src/pages/planning/fmea/FMEAVersionSnapshot.test.tsx`

**Interfaces:**
- Consumes: Task 2 `getFMEAVersion`、Task 3 i18n、现有 `getFMEA`、`normalizeGraphData`、`graphDataRef`、`baseGraphRef`、各 selection setter。
- Produces: `viewingVersion`、`loadVersionSnapshot(major, minor)`、`exitVersionSnapshot()`、`canEdit`/`canApprove` 包装、`startEditing` guard。

**内容锚点（worktree 行号仅供参考）：**
- antd import：文件顶部 `import { Button, Space, Tag, Typography, Input, Select, Table, Tabs,` 块（约 `:3-6`），**未含 `Alert`**。
- `usePermission` 解构：`const { canEdit, canApprove } = usePermission();`（约 `:117`）。
- `useCollaboration` 解构：`const { activeUsers, startEditing, stopEditing, isSyncing } = useCollaboration("fmea", fmeaId);`（约 `:184`）。
- `graphDataRef`/`baseGraphRef`/`loadGraphData`：约 `:125`/`:187`/`:250`。
- 横幅插入点：`<Tabs activeKey={outerTab} onChange={setOuterTab} style={{ marginBottom: 16 }} items={[`（约 `:1274`，CollaborationBar 之后）。
- `VersionHistoryTab` 的 `onViewSnapshot`：`onViewSnapshot={(major, minor) => message.info(t("messages.viewSnapshot", { major, minor }))}`（约 `:1700`）。

- [ ] **Step 1: 写失败测试（含完整 mock）**

创建 `frontend/src/pages/planning/fmea/FMEAVersionSnapshot.test.tsx`：

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { App } from "antd";
import FMEAEditorPage from "./FMEAEditorPage";
import type { FMEADocument, GraphEdge, GraphNode } from "../../../types";

const mocks = vi.hoisted(() => ({
  getFMEA: vi.fn(),
  getFMEAVersion: vi.fn(),
  listFMEAVersions: vi.fn(),
  canEdit: vi.fn(),
  startEditing: vi.fn(),
}));

vi.mock("antd", async () => {
  const actual = await vi.importActual<typeof import("antd")>("antd");
  return {
    ...actual,
    App: Object.assign(
      ({ children }: { children: React.ReactNode }) => <>{children}</>,
      { useApp: () => ({ message: { warning: vi.fn(), success: vi.fn(), error: vi.fn() }, modal: {}, notification: {} }) }
    ),
  };
});

vi.mock("../../../api/fmea", () => ({
  getFMEA: mocks.getFMEA,
  updateFMEA: vi.fn(),
  transitionFMEA: vi.fn(),
}));
vi.mock("../../../api/version", () => ({
  getFMEAVersion: mocks.getFMEAVersion,
  listFMEAVersions: mocks.listFMEAVersions,
}));
vi.mock("../../../api/specialCharacteristic", () => ({
  syncFromFMEA: vi.fn(),
  getSeverityWarnings: vi.fn().mockResolvedValue({ warnings: [] }),
}));
vi.mock("../../../api/lessonsLearned", () => ({ getFMEALessons: vi.fn() }));
vi.mock("../../../api/graph", () => ({
  getImpactChain: vi.fn(),
  getCauseChain: vi.fn(),
  normalizeGraphData: vi.fn((nodes: unknown, edges: unknown) => ({ nodes, edges })),
}));
vi.mock("../../../api/changeImpact", () => ({ analyzeChangeImpact: vi.fn() }));
vi.mock("../../../store/authStore", () => ({
  useAuthStore: (selector: (s: { user: unknown }) => unknown) => selector({ user: { user_id: "u1", role_key: "admin" } }),
}));
vi.mock("../../../hooks/usePermission", () => ({
  usePermission: () => ({ canEdit: mocks.canEdit, canApprove: () => true }),
}));
vi.mock("../../../hooks/useCollaboration", () => ({
  useCollaboration: () => ({
    activeUsers: [],
    startEditing: mocks.startEditing,
    stopEditing: vi.fn(),
    isSyncing: false,
  }),
}));
vi.mock("../../../components/dfmea/SmartSuggestionDropdown", () => ({
  default: ({ value, disabled }: { value: string; disabled?: boolean }) => <input aria-label="smart-suggestion" value={value} disabled={disabled} readOnly />,
}));
vi.mock("../../../components/dfmea/StructureTree", () => ({ default: () => <div data-testid="dfmea-structure-tree" /> }));
vi.mock("../../../components/dfmea/ParameterDiagram", () => ({ default: () => <div data-testid="parameter-diagram" /> }));
vi.mock("../../../components/lessons/LessonsLearnedModal", () => ({ default: () => null }));
// 不 mock VersionHistoryTab — 用真实组件触发 onViewSnapshot
vi.mock("../../../components/version/CreateVersionModal", () => ({ default: () => null }));
vi.mock("../../../components/version/RollbackConfirmModal", () => ({ default: () => null }));
vi.mock("../../../components/version/VersionCompareView", () => ({ default: () => <div data-testid="version-compare" /> }));
vi.mock("../../../components/cross-links/RelatedCAPAList", () => ({ default: () => <div data-testid="related-capa" /> }));
vi.mock("../../../components/graph", () => ({
  GraphCanvas: () => <div data-testid="graph-canvas" />,
  GraphToolbar: () => <div data-testid="graph-toolbar" />,
  NodeDetailDrawer: () => null,
  GraphLegend: () => <div data-testid="graph-legend" />,
}));
vi.mock("../../../components/change-impact", () => ({ ImpactReportPanel: () => <div data-testid="impact-report" /> }));
vi.mock("../../../components/collaboration", () => ({
  CollaborationBar: () => <div data-testid="collaboration-bar" />,
  ActiveUserIndicator: () => <div data-testid="active-user" />,
  ConflictResolutionModal: () => null,
}));
vi.mock("../../../components/design", () => ({
  PageShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DataCard: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  StatusBadge: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const node = (id: string, type: string, name = id): GraphNode => ({ id, type, name, severity: 0, occurrence: 0, detection: 0 });

function makeDoc(nodes: GraphNode[], edges: GraphEdge[]): FMEADocument {
  return {
    fmea_id: "fmea-1", document_no: "PFMEA-1", title: "doc", fmea_type: "PFMEA",
    product_line_code: "DC-DC-100", status: "draft", version: 1,
    graph_data: { nodes, edges, wizardScope: { wizard_completed: true } },
    lock_version: 1, created_by: "u1", created_at: "2026-06-18T00:00:00Z",
    updated_at: "2026-06-18T00:00:00Z", approved_by: null, approved_at: null,
  };
}

function renderEditor() {
  return render(
    <App>
      <MemoryRouter initialEntries={["/fmea/fmea-1"]}>
        <Routes><Route path="/fmea/:id" element={<FMEAEditorPage />} /></Routes>
      </MemoryRouter>
    </App>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.canEdit.mockReturnValue(true);
  mocks.getFMEA.mockResolvedValue(makeDoc([node("f1", "Function", "当前功能")], []));
  mocks.listFMEAVersions.mockResolvedValue({
    items: [{ version_id: "v1", fmea_id: "fmea-1", major_no: 1, minor_no: 0, change_type: "approve", change_summary: "v1", created_by: "u1", created_at: "2026-06-18T00:00:00Z" }],
    total: 1, page: 1, page_size: 100,
  });
  mocks.getFMEAVersion.mockResolvedValue({
    version_id: "v1", fmea_id: "fmea-1", major_no: 1, minor_no: 0, change_type: "approve",
    change_summary: "v1", created_by: "u1", created_at: "2026-06-18T00:00:00Z",
    snapshot: { nodes: [node("f1", "Function", "快照功能")], edges: [] },
    sha256_hash: "abc",
  });
});

describe("FMEAEditorPage version snapshot", () => {
  it("loads version snapshot into read-only mode with banner", async () => {
    renderEditor();
    await waitFor(() => expect(mocks.getFMEA).toHaveBeenCalled());

    fireEvent.click(screen.getByText("tabs.versionHistory"));
    const viewBtn = await screen.findByRole("button", { name: "history.view" });
    fireEvent.click(viewBtn);

    await waitFor(() => expect(mocks.getFMEAVersion).toHaveBeenCalledWith("fmea-1", 1, 0));
    await waitFor(() => expect(screen.getByText(/messages.viewingVersion/)).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("快照功能")).toBeInTheDocument());
    // 只读态未触发协作事件
    expect(mocks.startEditing).not.toHaveBeenCalled();
  });

  it("returns to current version on exit", async () => {
    renderEditor();
    await waitFor(() => expect(mocks.getFMEA).toHaveBeenCalled());
    fireEvent.click(screen.getByText("tabs.versionHistory"));
    const viewBtn = await screen.findByRole("button", { name: "history.view" });
    fireEvent.click(viewBtn);
    await waitFor(() => expect(screen.getByText(/messages.viewingVersion/)).toBeInTheDocument());

    fireEvent.click(screen.getByText("actions.exitVersion"));
    await waitFor(() => expect(mocks.getFMEA.mock.calls.length).toBeGreaterThanOrEqual(2));
    await waitFor(() => expect(screen.queryByText(/messages.viewingVersion/)).not.toBeInTheDocument());
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAVersionSnapshot.test.tsx 2>&1 | tail -30`

Expected: FAIL — 横幅 `messages.viewingVersion` 未渲染（`onViewSnapshot` 仍是 `message.info`）。

- [ ] **Step 3: 添加 Alert import**

在 antd import 块 `import { Button, Space, Tag, Typography, Input, Select, Table, Tabs,` 的第二行加入 `Alert`：

```ts
import {
  Button, Space, Tag, Typography, Input, Select, Table, Tabs,
  Row, Col, App, Spin, Popconfirm, Empty, Tooltip, Alert,
  Divider, Modal, Radio, Form, Dropdown,
} from "antd";
```

- [ ] **Step 4: 添加 viewingVersion state 与权限包装**

定位 `const { canEdit, canApprove } = usePermission();`，替换为：

```ts
  const { canEdit: rawCanEdit, canApprove: rawCanApprove } = usePermission();
  const [viewingVersion, setViewingVersion] = useState<{ major: number; minor: number } | null>(null);
  const isViewingVersion = viewingVersion !== null;
  const canEdit = useCallback(
    (m: string) => rawCanEdit(m) && !isViewingVersion,
    [rawCanEdit, isViewingVersion]
  );
  const canApprove = useCallback(
    (m: string) => rawCanApprove(m) && !isViewingVersion,
    [rawCanApprove, isViewingVersion]
  );
```

- [ ] **Step 5: 添加 startEditing guard**

定位 `const { activeUsers, startEditing, stopEditing, isSyncing } = useCollaboration("fmea", fmeaId);`，替换为：

```ts
  const { activeUsers, startEditing: rawStartEditing, stopEditing, isSyncing } = useCollaboration("fmea", fmeaId);
  const startEditing = useCallback((...args: Parameters<typeof rawStartEditing>) => {
    if (isViewingVersion) return;
    rawStartEditing(...args);
  }, [rawStartEditing, isViewingVersion]);
```

> `isViewingVersion` 在 Step 4 已定义于同一组件作用域；若 `useCollaboration` 在 `viewingVersion` state 声明之前，把 state 声明上移到 `useCollaboration` 之前，或确保 `isViewingVersion` 可见（React hooks 顺序：state 声明通常在 hook 调用前，检查并调整顺序使 `isViewingVersion` 在 `startEditing` 定义时已声明）。

- [ ] **Step 6: 添加 getFMEAVersion import**

在 `import { getFMEA, updateFMEA, transitionFMEA } from "../../../api/fmea";` 之后添加：
```ts
import { getFMEAVersion } from "../../../api/version";
```

- [ ] **Step 7: 添加 loadVersionSnapshot 与 exitVersionSnapshot**

在 `loadGraphData` 定义之后添加：

```ts
  const loadVersionSnapshot = useCallback(async (major: number, minor: number) => {
    try {
      const v = await getFMEAVersion(fmeaId, major, minor);
      const snap = v.snapshot ?? { nodes: [], edges: [] };
      setNodes(snap.nodes || []);
      setEdges(snap.edges || []);
      graphDataRef.current = normalizeGraphData(
        snap.nodes as unknown as Array<Record<string, unknown>>,
        snap.edges as unknown as Array<Record<string, unknown>>,
      );
      setSelectedFunctionId(null);
      setSelectedStructureNode(null);
      setSelectedGraphNode(null);
      setDrawerVisible(false);
      setHighlightNodes([]);
      setViewingVersion({ major, minor });
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      message.error(e?.response?.data?.detail || t("messages.loadVersionFailed"));
    }
  }, [fmeaId, t]);

  const exitVersionSnapshot = useCallback(async () => {
    const doc = await getFMEA(fmeaId);
    setFmea(doc);
    setNodes(doc.graph_data?.nodes || []);
    setEdges(doc.graph_data?.edges || []);
    baseGraphRef.current = {
      nodes: JSON.parse(JSON.stringify(doc.graph_data?.nodes || [])),
      edges: JSON.parse(JSON.stringify(doc.graph_data?.edges || [])),
    };
    graphDataRef.current = null;
    setSelectedFunctionId(null);
    setSelectedStructureNode(null);
    setSelectedGraphNode(null);
    setDrawerVisible(false);
    setHighlightNodes([]);
    setViewingVersion(null);
  }, [fmeaId]);
```

> 各 setter（`setSelectedFunctionId`/`setSelectedStructureNode`/`setSelectedGraphNode`/`setDrawerVisible`/`setHighlightNodes`）已在 `:106-131` 声明。`getFMEA`/`setNodes`/`setEdges`/`setFmea`/`graphDataRef`/`baseGraphRef`/`normalizeGraphData`/`message`/`t` 均在作用域内。

- [ ] **Step 8: 替换占位点**

定位 `onViewSnapshot={(major, minor) => message.info(t("messages.viewSnapshot", { major, minor }))}`，替换为：
```tsx
            onViewSnapshot={loadVersionSnapshot}
```

- [ ] **Step 9: 添加只读横幅**

定位 `<Tabs activeKey={outerTab} onChange={setOuterTab} style={{ marginBottom: 16 }} items={[`，在其**之前**插入：

```tsx
      {viewingVersion && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message={t("messages.viewingVersion", { version: `${viewingVersion.major}.${viewingVersion.minor}` })}
          action={
            <Button size="small" onClick={exitVersionSnapshot}>
              {t("actions.exitVersion")}
            </Button>
          }
        />
      )}
```

- [ ] **Step 10: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAVersionSnapshot.test.tsx 2>&1 | tail -30`

Expected: PASS（2 个测试通过）。

- [ ] **Step 11: 全量 FMEA 测试 + lint**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/ 2>&1 | tail -20 && npm run lint 2>&1 | tail -20`

Expected: 全绿，lint 无错误。

- [ ] **Step 12: Commit**

```bash
git add frontend/src/pages/planning/fmea/FMEAEditorPage.tsx frontend/src/pages/planning/fmea/FMEAVersionSnapshot.test.tsx
git commit -m "feat(fmea): version snapshot read-only view with selection reset and collab guard"
```

---

### Task 5: CP i18n keys

**Files:**
- Modify: `frontend/src/locales/zh-CN/controlPlan.json` + `frontend/src/locales/en-US/controlPlan.json`

- [ ] **Step 1: zh-CN controlPlan.json**

在 `"message": {` 块内追加：
```json
    "viewingVersion": "正在查看 v{{version}} 快照（只读）",
    "loadVersionFailed": "加载版本快照失败",
```
在 `"button": {` 块内追加：
```json
    "exitVersion": "返回当前版本",
```

- [ ] **Step 2: en-US controlPlan.json**

同样位置：
```json
    "viewingVersion": "Viewing v{{version}} snapshot (read-only)",
    "loadVersionFailed": "Failed to load version snapshot",
```
```json
    "exitVersion": "Return to current version",
```

- [ ] **Step 3: 验证 JSON**

Run: `cd frontend && node -e "JSON.parse(require('fs').readFileSync('src/locales/zh-CN/controlPlan.json','utf8')); JSON.parse(require('fs').readFileSync('src/locales/en-US/controlPlan.json','utf8')); console.log('ok')"`

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/locales/zh-CN/controlPlan.json frontend/src/locales/en-US/controlPlan.json
git commit -m "i18n(controlPlan): add version snapshot read-only banner keys"
```

---

### Task 6: CP 编辑器 — 快照只读模式 + 状态隔离

**Files:**
- Modify: `frontend/src/pages/planning/control-plan/ControlPlanEditorPage.tsx`
- Test: `frontend/src/pages/planning/control-plan/CPVersionSnapshot.test.tsx`

**Interfaces:**
- Consumes: Task 2 `getCPVersion`、Task 5 i18n、现有 `getControlPlan`、`baseItemsRef`、`ValidationPanel`（已 import `:34`）。
- Produces: `viewingVersion`、`versionHeader`、`loadVersionSnapshot`、`exitVersionSnapshot`、`canApproveAllowed`、`startEditing` guard。

**内容锚点（worktree 行号）：**
- 权限解构 `const { canEdit: canEditPerm, canApprove } = usePermission();`（`:113`）与 `const canEdit = canEditPerm('planning') && !isApproved;`（`:115`）。
- `useCollaboration` 解构 `const { activeUsers, isSyncing, startEditing, stopEditing } = useCollaboration("control_plan", cpId);`（`:118`）。
- sync_pending 横幅 `{cp?.sync_pending && (`（`:699`）。
- checkStale 按钮 `{!isNew && (` 紧邻 `<Button icon={<ExclamationCircleOutlined />} onClick={handleCheckStale}>`（`:732`）。
- `<Tabs activeKey={outerTab} onChange={setOuterTab} items={[`（`:713`）。
- 审批按钮 `{!isNew && canApprove('planning') && currentStatus !== "approved" && (`（`:754`）。
- fmea_ref_id 显示 `value={cp?.fmea_ref_id || t("form.notAssociated")}`（`:858`）。
- ValidationPanel `{!isNew && id && (` 包裹 `<ValidationPanel cpId={id} />`（`:914`）。
- history tab `canCreate={canEditPerm('planning')}` / `canRollback={canApprove('planning')}` / `onViewSnapshot={(major, minor) => message.info(...)}`（`:901-904`）。
- PageShell subtitle `subtitle={\`${t("column.status")}：${statusLabels[currentStatus] || currentStatus}\`}`（`:676`）。

- [ ] **Step 1: 写失败测试（含完整 mock）**

创建 `frontend/src/pages/planning/control-plan/CPVersionSnapshot.test.tsx`：

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { App } from "antd";
import ControlPlanEditorPage from "./ControlPlanEditorPage";
import type { ControlPlan } from "../../../types";

const mocks = vi.hoisted(() => ({
  getControlPlan: vi.fn(),
  getCPVersion: vi.fn(),
  listCPVersions: vi.fn(),
  getCPSyncStatus: vi.fn(),
  startEditing: vi.fn(),
}));

vi.mock("antd", async () => {
  const actual = await vi.importActual<typeof import("antd")>("antd");
  return {
    ...actual,
    App: Object.assign(
      ({ children }: { children: React.ReactNode }) => <>{children}</>,
      { useApp: () => ({ message: { warning: vi.fn(), success: vi.fn(), error: vi.fn() }, modal: {}, notification: {} }) }
    ),
  };
});

vi.mock("../../../api/controlPlan", () => ({
  getControlPlan: mocks.getControlPlan,
  createControlPlan: vi.fn(),
  updateControlPlan: vi.fn(),
  checkStaleItems: vi.fn().mockResolvedValue({ stale_items: [] }),
  approveControlPlan: vi.fn(),
  syncCSRToControlPlan: vi.fn(),
}));
vi.mock("../../../api/version", () => ({
  getCPVersion: mocks.getCPVersion,
  listCPVersions: mocks.listCPVersions,
}));
vi.mock("../../../api/customerQuality", () => ({ listCustomers: vi.fn().mockResolvedValue([]) }));
vi.mock("../../../api/specialCharacteristic", () => ({
  getCPSyncStatus: mocks.getCPSyncStatus,
  syncToCP: vi.fn(),
}));
vi.mock("../../../store/authStore", () => ({
  useAuthStore: (selector: (s: { user: unknown }) => unknown) => selector({ user: { user_id: "u1", role_key: "admin" } }),
}));
vi.mock("../../../hooks/usePermission", () => ({
  usePermission: () => ({ canEdit: () => true, canApprove: () => true }),
}));
vi.mock("../../../hooks/useCollaboration", () => ({
  useCollaboration: () => ({
    activeUsers: [],
    startEditing: mocks.startEditing,
    stopEditing: vi.fn(),
    isSyncing: false,
  }),
}));
vi.mock("../../../components/collaboration", () => ({
  CollaborationBar: () => <div data-testid="collab" />,
  ActiveUserIndicator: () => <div data-testid="au" />,
  ConflictResolutionModal: () => null,
}));
vi.mock("../../../components/control-plan/ImportFromFMEAModal", () => ({ default: () => null }));
vi.mock("../../../components/control-plan/ValidationPanel", () => ({ default: () => <div data-testid="validation-panel" /> }));
vi.mock("../../../components/version/CreateVersionModal", () => ({ default: () => null }));
vi.mock("../../../components/version/RollbackConfirmModal", () => ({ default: () => null }));
vi.mock("../../../components/version/VersionCompareView", () => ({ default: () => <div data-testid="vc" /> }));
vi.mock("../../../components/design/PageShell", () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, tc: (key: string) => key }),
}));

function makeCP(): ControlPlan {
  return {
    cp_id: "cp-1", document_no: "CP-1", title: "当前CP", status: "draft",
    phase: "sample", part_no: "P1", part_name: "件名", product_line_code: "DC-DC-100",
    fmea_ref_id: null, contact_info: "", core_group: "", org_factory: "", drawing_rev: "",
    sync_pending: false, items: [], version: 1, lock_version: 1,
    created_by: "u1", created_at: "2026-06-18T00:00:00Z", updated_at: "2026-06-18T00:00:00Z",
  } as unknown as ControlPlan;
}

function renderEditor() {
  return render(
    <App>
      <MemoryRouter initialEntries={["/control-plans/cp-1"]}>
        <Routes><Route path="/control-plans/:id" element={<ControlPlanEditorPage />} /></Routes>
      </MemoryRouter>
    </App>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getControlPlan.mockResolvedValue(makeCP());
  mocks.getCPSyncStatus.mockResolvedValue({ items: [] });
  mocks.listCPVersions.mockResolvedValue({
    items: [{ version_id: "v1", cp_id: "cp-1", major_no: 1, minor_no: 0, source_fmea_version_id: null, change_type: "approve", change_summary: "v1", created_by: "u1", created_at: "2026-06-18T00:00:00Z" }],
    total: 1, page: 1, page_size: 100,
  });
  mocks.getCPVersion.mockResolvedValue({
    version_id: "v1", cp_id: "cp-1", major_no: 1, minor_no: 0, source_fmea_version_id: null,
    change_type: "approve", change_summary: "v1", created_by: "u1", created_at: "2026-06-18T00:00:00Z",
    header_snapshot: {
      document_no: "CP-1", title: "快照CP", fmea_ref_id: null, product_line_code: "DC-DC-100",
      status: "approved", phase: "sample", part_no: "P1", part_name: "快照件名",
      contact_info: "", drawing_rev: "", org_factory: "", core_group: "",
    },
    items_snapshot: [],
    sha256_hash: "abc",
  });
});

describe("ControlPlanEditorPage version snapshot", () => {
  it("loads version snapshot into read-only mode with banner", async () => {
    renderEditor();
    await waitFor(() => expect(mocks.getControlPlan).toHaveBeenCalled());

    fireEvent.click(screen.getByText("pageTitle.versionHistory"));
    const viewBtn = await screen.findByRole("button", { name: "history.view" });
    fireEvent.click(viewBtn);

    await waitFor(() => expect(mocks.getCPVersion).toHaveBeenCalledWith("cp-1", 1, 0));
    await waitFor(() => expect(screen.getByText(/message.viewingVersion/)).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("快照CP")).toBeInTheDocument());
    // 快照态隐藏 ValidationPanel
    await waitFor(() => expect(screen.queryByTestId("validation-panel")).not.toBeInTheDocument());
    expect(mocks.startEditing).not.toHaveBeenCalled();
  });

  it("returns to current version on exit", async () => {
    renderEditor();
    await waitFor(() => expect(mocks.getControlPlan).toHaveBeenCalled());
    fireEvent.click(screen.getByText("pageTitle.versionHistory"));
    const viewBtn = await screen.findByRole("button", { name: "history.view" });
    fireEvent.click(viewBtn);
    await waitFor(() => expect(screen.getByText(/message.viewingVersion/)).toBeInTheDocument());

    fireEvent.click(screen.getByText("button.exitVersion"));
    await waitFor(() => expect(mocks.getControlPlan.mock.calls.length).toBeGreaterThanOrEqual(2));
    await waitFor(() => expect(screen.queryByText(/message.viewingVersion/)).not.toBeInTheDocument());
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/pages/planning/control-plan/CPVersionSnapshot.test.tsx 2>&1 | tail -30`

Expected: FAIL — 横幅未渲染，`onViewSnapshot` 仍是 `message.info`。

- [ ] **Step 3: 添加 viewingVersion/versionHeader state 与权限包装**

定位：
```ts
  const { canEdit: canEditPerm, canApprove } = usePermission();
  const isApproved = cp?.status === "approved";
  const canEdit = canEditPerm('planning') && !isApproved;
```
替换为：
```ts
  const { canEdit: canEditPerm, canApprove: rawCanApprove } = usePermission();
  const isApproved = cp?.status === "approved";
  const [viewingVersion, setViewingVersion] = useState<{ major: number; minor: number } | null>(null);
  const [versionHeader, setVersionHeader] = useState<CPVersionHeader | null>(null);
  const isViewingVersion = viewingVersion !== null;
  const canEdit = canEditPerm('planning') && !isApproved && !isViewingVersion;
  const canApproveAllowed = (m: "planning") => rawCanApprove(m) && !isViewingVersion;
```

> 需 import `CPVersionHeader` 类型：在 `import type { ControlPlan, ControlPlanItem } from "../../../types";` 改为 `import type { ControlPlan, ControlPlanItem, CPVersionHeader } from "../../../types";`。

- [ ] **Step 4: 添加 startEditing guard**

定位 `const { activeUsers, isSyncing, startEditing, stopEditing } = useCollaboration("control_plan", cpId);`，替换为：
```ts
  const { activeUsers, isSyncing, startEditing: rawStartEditing, stopEditing } = useCollaboration("control_plan", cpId);
  const startEditing = useCallback((...args: Parameters<typeof rawStartEditing>) => {
    if (isViewingVersion) return;
    rawStartEditing(...args);
  }, [rawStartEditing, isViewingVersion]);
```

> 确保 `isViewingVersion` 在此 hook 调用前已声明（state 声明顺序：`viewingVersion` state 在 `useCollaboration` 之前；若顺序不符，调整 state 声明位置）。

- [ ] **Step 5: 添加 getCPVersion import 与 load/exit**

在 `import { getControlPlan, ... } from "../../../api/controlPlan";` 之后添加：
```ts
import { getCPVersion } from "../../../api/version";
```

在加载 CP 的 `useEffect` 之后添加：

```ts
  const loadVersionSnapshot = useCallback(async (major: number, minor: number) => {
    try {
      const v = await getCPVersion(id!, major, minor);
      const h = v.header_snapshot || {};
      setTitle(h.title || "");
      setDocumentNo(h.document_no || "");
      setPhase(h.phase || "sample");
      setPartNo(h.part_no || "");
      setPartName(h.part_name || "");
      setContactInfo(h.contact_info || "");
      setCoreGroup(h.core_group || "");
      setOrgFactory(h.org_factory || "");
      setDrawingRev(h.drawing_rev || "");
      setItems(v.items_snapshot || []);
      setVersionHeader(v.header_snapshot);
      setViewingVersion({ major, minor });
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      message.error(e?.response?.data?.detail || t("message.loadVersionFailed"));
    }
  }, [id, t]);

  const exitVersionSnapshot = useCallback(async () => {
    if (!id) return;
    try {
      const doc = await getControlPlan(id);
      setCp(doc);
      setTitle(doc.title);
      setDocumentNo(doc.document_no);
      setPhase(doc.phase || "sample");
      setPartNo(doc.part_no || "");
      setPartName(doc.part_name || "");
      setContactInfo(doc.contact_info || "");
      setCoreGroup(doc.core_group || "");
      setOrgFactory(doc.org_factory || "");
      setDrawingRev(doc.drawing_rev || "");
      setItems(doc.items || []);
      baseItemsRef.current = JSON.parse(JSON.stringify(doc.items || []));
      setVersionHeader(null);
      setViewingVersion(null);
    } catch {
      message.error(t("message.loadFailed"));
    }
  }, [id, t]);
```

- [ ] **Step 6: 快照态隔离 — 隐藏 sync/checkStale/ValidationPanel，fmea_ref_id 与 status 读快照**

(a) sync_pending 横幅：定位 `{cp?.sync_pending && (`，改为 `{cp?.sync_pending && !isViewingVersion && (`。

(b) checkStale 按钮：定位紧邻 `<Button icon={<ExclamationCircleOutlined />} onClick={handleCheckStale}>` 的 `{!isNew && (`，改为 `{!isNew && !isViewingVersion && (`。

(c) fmea_ref_id 显示：定位 `value={cp?.fmea_ref_id || t("form.notAssociated")}`，改为：
```tsx
                value={(isViewingVersion ? versionHeader?.fmea_ref_id : cp?.fmea_ref_id) || t("form.notAssociated")}
```

(d) ValidationPanel：定位 `{!isNew && id && (`（包裹 `<ValidationPanel cpId={id} />`），改为 `{!isNew && id && !isViewingVersion && (`。

(e) PageShell subtitle：定位 `subtitle={\`${t("column.status")}：${statusLabels[currentStatus] || currentStatus}\`}`，改为：
```tsx
      subtitle={`${t("column.status")}：${statusLabels[isViewingVersion ? (versionHeader?.status || "") : currentStatus] || (isViewingVersion ? (versionHeader?.status || "") : currentStatus)}`}
```

- [ ] **Step 7: 替换审批按钮与 history tab 权限/占位点**

(a) 审批按钮：定位 `{!isNew && canApprove('planning') && currentStatus !== "approved" && (`，把 `canApprove('planning')` 改为 `canApproveAllowed('planning')`：
```tsx
        {!isNew && canApproveAllowed('planning') && currentStatus !== "approved" && (
```

(b) history tab：定位
```tsx
            canCreate={canEditPerm('planning')}
            canRollback={canApprove('planning')}
            isDraft={currentStatus === "draft"}
            onViewSnapshot={(major, minor) => message.info(`${t("button.viewSnapshot")} v${major}.${minor}`)}
```
替换为：
```tsx
            canCreate={canEdit}
            canRollback={canApproveAllowed('planning')}
            isDraft={currentStatus === "draft"}
            onViewSnapshot={loadVersionSnapshot}
```

- [ ] **Step 8: 添加只读横幅**

定位 `<Tabs activeKey={outerTab} onChange={setOuterTab} items={[`（`:713`），在其**之前**插入：
```tsx
      {viewingVersion && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message={t("message.viewingVersion", { version: `${viewingVersion.major}.${viewingVersion.minor}` })}
          action={
            <Button size="small" onClick={exitVersionSnapshot}>
              {t("button.exitVersion")}
            </Button>
          }
        />
      )}
```

> `Alert` 与 `Button` 已 import。

- [ ] **Step 9: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/pages/planning/control-plan/CPVersionSnapshot.test.tsx 2>&1 | tail -30`

Expected: PASS（2 个测试通过）。

- [ ] **Step 10: 全量 lint + tsc + 测试**

Run: `cd frontend && npm run lint 2>&1 | tail -20 && npx tsc --noEmit 2>&1 | tail -20 && npx vitest run src/pages/planning/ 2>&1 | tail -20`

Expected: 无错误，全绿。

- [ ] **Step 11: Commit**

```bash
git add frontend/src/pages/planning/control-plan/ControlPlanEditorPage.tsx frontend/src/pages/planning/control-plan/CPVersionSnapshot.test.tsx
git commit -m "feat(controlPlan): version snapshot read-only view with state isolation and collab guard"
```

---

### Task 7: 全量验证与收尾

- [ ] **Step 1: 全量构建**

Run: `cd frontend && npm run build 2>&1 | tail -20`

Expected: 构建成功。

- [ ] **Step 2: 全量测试**

Run: `cd frontend && npx vitest run 2>&1 | tail -20`

Expected: 全绿（原有测试 + 4 个新增快照测试）。

- [ ] **Step 3: 手动验证（可选，需 Docker）**

`docker compose up`，登录 engineer，打开有版本的 FMEA → 版本历史 → 「查看」→ 确认横幅 + 只读 + 图谱显示快照 + drawer/高亮已清 → 「返回当前版本」。CP 同理，并确认快照态无 sync/checkStale/ValidationPanel。

- [ ] **Step 4: 收尾 commit（若有遗漏）**

```bash
git status
git add -A && git commit -m "chore: version snapshot view final cleanup"
```

---

## Self-Review

**1. Spec coverage:**
- §3.1–3.6（FMEA state/权限/加载/返回/占位/横幅）→ Task 4 ✓
- §3.7 图谱 graphDataRef 同步 → Task 4 Step 7（load 设、exit 清）✓
- §3.8 选择态重置 + startEditing guard → Task 4 Step 5/7 + 测试断言 `startEditing` 未调用 ✓
- §4.2 CP canApproveAllowed + history tab 权限 → Task 6 Step 3/7 ✓
- §4.3–4.6 CP 加载/返回/占位/横幅 → Task 6 ✓
- §4.7 CP 快照态隔离（sync/checkStale/ValidationPanel/fmea_ref_id/status + startEditing guard）→ Task 6 Step 4/6 + 测试断言 ValidationPanel 隐藏 & startEditing 未调用 ✓
- §5 类型（nullable + version_id + source_fmea_version_id + RollbackResponse + getChangeTypeConfig null）→ Task 1 ✓
- §5 API 返回类型（detail vs RollbackResponse）→ Task 2 ✓
- §6 i18n → Task 3/5 ✓
- §7 协作 guard → Task 4/6 单点 guard + 测试断言 ✓

**2. Placeholder scan:** 无 TBD/TODO；所有代码块完整。`listFMEAVersions`/`listCPVersions` mock 均在 Step 1 即提供，使首测失败聚焦功能未实现。`CPVersionHeader` 类型 import 在 Task 6 Step 3 说明。

**3. Type consistency:** `getFMEAVersion`→`FMEAVersionDetail`、`getCPVersion`→`CPVersionDetail`、`rollback*Version`→`RollbackResponse`（Task 1 定义、Task 2 修正、Task 4/6 使用）。`canApproveAllowed`（Task 6 Step 3/7 一致）、`loadVersionSnapshot`/`exitVersionSnapshot`/`viewingVersion`/`versionHeader`（Task 4/6 一致）、`isViewingVersion`（两编辑器一致）。`startEditing` guard 模式（`rawStartEditing` + `useCallback` 包装）在 FMEA/CP 一致。

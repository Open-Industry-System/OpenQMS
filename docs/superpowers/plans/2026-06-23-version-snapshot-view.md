# FMEA / Control Plan 版本快照只读查看 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 FMEA 与 CP 编辑器「查看版本」按钮从占位 `message.info` 改为就地加载版本快照并以只读模式渲染（横幅 + 返回当前版本）。

**Architecture:** 在每个编辑器新增 `viewingVersion` 状态；通过覆盖 `usePermission()` 返回的 `canEdit`/`canApprove`（`viewingVersion` 非空时强制 `false`）让全部已有 `disabled={!canEdit(...)}` 控件自动转只读；`onViewSnapshot` 调用已有 `getFMEAVersion`/`getCPVersion` 加载快照填入现有 state；顶部 `Alert` 横幅 + 「返回当前版本」按钮重新拉取当前文档复位。

**Tech Stack:** React 18 + TypeScript 5.6 + Ant Design 5.29 + react-i18next + Vitest + @testing-library/react

## Global Constraints

- 中文 UI（zh-CN）为主，en-US 同步；新 i18n key 必须同时加到 `frontend/src/locales/zh-CN/*.json` 与 `frontend/src/locales/en-US/*.json`。
- FMEA 编辑器错误处理沿用现有内联风格 `err?.response?.data?.detail || t("...")`（见 `FMEAEditorPage.tsx:415`）。**不得引入 `formatFMEAError`**（该工具在本 worktree 不存在）。
- 所有改动须 `npm run lint` + `npm run build`（含 `tsc --noEmit`）通过；现有 FMEA 编辑器测试须全绿。
- 后端**无改动**：`GET /api/fmea/{id}/versions/{major}/{minor}` 返回 `FMEAVersionDetail`（含 `snapshot`+`sha256_hash`）；`GET /api/control-plans/{id}/versions/{major}/{minor}` 返回 `ControlPlanVersionDetail`（含 `header_snapshot`+`items_snapshot`+`sha256_hash`）；rollback 端点返回 `RollbackResponse`（非 detail）。
- 命名：FMEA 用 `canEdit`/`canApprove`（重命名原 hook 返回为 `rawCanEdit`/`rawCanApprove` 后包装）；CP 用 `canEdit`（已有）+ 新增 `canApproveAllowed`。
- 触碰文件须遵循现有风格（中文注释、antd 组件、`useTranslation` namespace）。

---

## File Structure

- **Modify** `frontend/src/types/index.ts` — 修正 `FMEAVersion`/`CPVersion` list 类型，新增 `FMEAVersionDetail`/`CPVersionDetail`/`CPVersionHeader`。
- **Modify** `frontend/src/api/version.ts` — 修正 `getFMEAVersion`/`getCPVersion`/`createFMEAVersion`/`createCPVersion` 返回类型为 `*Detail`，`rollback*Version` 为 `RollbackResponse`。
- **Modify** `frontend/src/locales/zh-CN/fmea.json` + `frontend/src/locales/en-US/fmea.json` — 新增 viewing/exit/loadFailed key，删除 viewSnapshot 占位 key。
- **Modify** `frontend/src/locales/zh-CN/controlPlan.json` + `frontend/src/locales/en-US/controlPlan.json` — 同上（CP namespace）。
- **Modify** `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx` — `viewingVersion` state、canEdit/canApprove 包装、load/exit、graphDataRef 同步、横幅、占位点替换。
- **Modify** `frontend/src/pages/planning/control-plan/ControlPlanEditorPage.tsx` — 同上（CP 版本：canApproveAllowed、history tab 权限改用包装后权限）。
- **Create** `frontend/src/pages/planning/fmea/FMEAVersionSnapshot.test.tsx` — 快照加载/只读/返回测试。
- **Create** `frontend/src/pages/planning/control-plan/CPVersionSnapshot.test.tsx` — 同上（CP）。

---

### Task 1: 修正类型定义 (types/index.ts)

**Files:**
- Modify: `frontend/src/types/index.ts:561-579`

**Interfaces:**
- Produces: `FMEAVersion`（list item，无 `graph_data`）、`FMEAVersionDetail`（含 `snapshot`+`sha256_hash`）、`CPVersion`（list item，无 `items`）、`CPVersionDetail`（含 `header_snapshot`+`items_snapshot`+`sha256_hash`）、`CPVersionHeader`。供 Task 2 的 API 客户端与 Task 3/4 的编辑器使用。

- [ ] **Step 1: 替换 Version Management 类型块**

打开 `frontend/src/types/index.ts`，定位到 `// --- Version Management ---`（约 561 行起），将 `VersionBase` 之后的 `FMEAVersion` 与 `CPVersion` 定义替换并新增 detail 类型：

```ts
export interface FMEAVersion extends VersionBase {
  fmea_id: string;
}

export interface FMEAVersionDetail extends FMEAVersion {
  snapshot: GraphData;
  sha256_hash: string;
}

export interface CPVersion extends VersionBase {
  cp_id: string;
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
```

> 删除原 `FMEAVersion.graph_data` 与 `CPVersion.items` 字段（list 端点不返回它们）。`GraphData` 与 `ControlPlanItem` 类型在本文件已存在，无需新增 import。

- [ ] **Step 2: 检查并修正受影响引用**

Run: `grep -rn "\.graph_data" frontend/src --include="*.tsx" --include="*.ts" | grep -i version` 以及 `grep -rn "FMEAVersion\b\|CPVersion\b" frontend/src --include="*.tsx" --include="*.ts"`

Expected: `VersionHistoryTab.tsx`、`VersionCompareView.tsx`、`RollbackConfirmModal.tsx` 中对 `FMEAVersion`/`CPVersion` 的访问应仅限 `VersionBase` 字段（`major_no`/`minor_no`/`change_type`/`change_summary`/`created_by`/`created_at`）+ `fmea_id`/`cp_id`。若发现访问 `.graph_data` 或 `.items`，改为对应 `*Detail` 类型或删除该访问（这些组件只用 list item 字段，预期无需改动；若 `RollbackConfirmModal` 用了 detail，则把其 props 类型改为 `*Detail`）。

- [ ] **Step 3: 验证编译**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -40`

Expected: 无新增类型错误（若 `version.ts` 因返回类型报错，Task 2 会修；本步聚焦 types 自身）。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "refactor(types): split FMEA/CP version list vs detail types"
```

---

### Task 2: 修正 API 客户端返回类型 (api/version.ts)

**Files:**
- Modify: `frontend/src/api/version.ts:1-156`

**Interfaces:**
- Consumes: Task 1 的 `FMEAVersionDetail`/`CPVersionDetail`/`FMEAVersion`/`CPVersion`/`RollbackResponse`。
- Produces: `getFMEAVersion(fmeaId, major, minor): Promise<FMEAVersionDetail>`、`getCPVersion(...): Promise<CPVersionDetail>`，供 Task 3/4 调用。

- [ ] **Step 1: 更新 import**

打开 `frontend/src/api/version.ts`，把第 2-10 行的 import 改为：

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

> `RollbackResponse` 类型若 `types/index.ts` 中尚不存在，先确认：`grep -n "RollbackResponse" frontend/src/types/index.ts`。若不存在，在 Task 1 的 Version Management 块末尾追加 `export interface RollbackResponse { version_id: string; major_no: number; minor_no: number; change_type: string | null; change_summary: string | null; created_at: string; }`（对齐 `backend/app/schemas/version.py:84-92`）。若已存在则跳过。

- [ ] **Step 2: 修正各函数返回类型**

把 `getFMEAVersion`（约 26 行）返回类型 `Promise<FMEAVersion>` → `Promise<FMEAVersionDetail>`：
```ts
export async function getFMEAVersion(
  fmeaId: string,
  major: number,
  minor: number
): Promise<FMEAVersionDetail> {
  const resp = await client.get(
    `/fmea/${fmeaId}/versions/${major}/${minor}`
  );
  return resp.data;
}
```

把 `createFMEAVersion`（约 37 行）返回类型 → `Promise<FMEAVersionDetail>`。

把 `rollbackFMEAVersion`（约 48 行）返回类型 → `Promise<RollbackResponse>`：
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

CP 同理：`getCPVersion` → `Promise<CPVersionDetail>`，`createCPVersion` → `Promise<CPVersionDetail>`，`rollbackCPVersion` → `Promise<RollbackResponse>`。

- [ ] **Step 3: 验证编译**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -40`

Expected: 无错误（或仅剩 Task 3/4 即将处理的编辑器内部错误）。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/version.ts frontend/src/types/index.ts
git commit -m "refactor(api): correct version client return types (detail vs rollback)"
```

---

### Task 3: FMEA 编辑器 — i18n keys

**Files:**
- Modify: `frontend/src/locales/zh-CN/fmea.json:238` 与 `frontend/src/locales/en-US/fmea.json:238`
- Modify: 对应 `actions` 块

**Interfaces:**
- Produces: `messages.viewingVersion`、`actions.exitVersion`、`messages.loadVersionFailed`（zh + en）。供 Task 4 使用。

- [ ] **Step 1: 修改 zh-CN fmea.json**

打开 `frontend/src/locales/zh-CN/fmea.json`。在 `messages` 块中，把第 238 行 `"viewSnapshot": "查看版本 v{{version}} 快照（功能开发中）",` 改为（去掉「功能开发中」并保留作为通用查看提示，但实际不再用 message.info 调用）：

```json
    "viewSnapshot": "查看版本 v{{version}} 快照",
    "viewingVersion": "正在查看 v{{version}} 快照（只读）",
    "loadVersionFailed": "加载版本快照失败",
```

在 `actions` 块中新增（找到 `"actions": {` 块内任意位置，建议紧邻 `save` 之后）：
```json
    "exitVersion": "返回当前版本",
```

- [ ] **Step 2: 修改 en-US fmea.json**

打开 `frontend/src/locales/en-US/fmea.json`，同样位置：
```json
    "viewSnapshot": "View version v{{version}} snapshot",
    "viewingVersion": "Viewing v{{version}} snapshot (read-only)",
    "loadVersionFailed": "Failed to load version snapshot",
```
`actions` 块新增：
```json
    "exitVersion": "Return to current version",
```

- [ ] **Step 3: 验证 JSON 合法**

Run: `cd frontend && node -e "JSON.parse(require('fs').readFileSync('src/locales/zh-CN/fmea.json','utf8')); JSON.parse(require('fs').readFileSync('src/locales/en-US/fmea.json','utf8')); console.log('ok')"`

Expected: 输出 `ok`。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/locales/zh-CN/fmea.json frontend/src/locales/en-US/fmea.json
git commit -m "i18n(fmea): add version snapshot read-only banner keys"
```

---

### Task 4: FMEA 编辑器 — 快照只读模式

**Files:**
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`（state 约 280-285、加载逻辑、横幅约 1515、占位点 1882）
- Test: `frontend/src/pages/planning/fmea/FMEAVersionSnapshot.test.tsx`

**Interfaces:**
- Consumes: Task 2 的 `getFMEAVersion`、Task 3 的 i18n keys、现有 `getFMEA`、`normalizeGraphData`（已 import 于 `:55`）、`graphDataRef`（`:125`）、`baseGraphRef`（`:355`）。
- Produces: `loadVersionSnapshot(major, minor)`、`exitVersionSnapshot()`、`viewingVersion` state。

- [ ] **Step 1: 写失败测试 — 快照加载与只读横幅**

创建 `frontend/src/pages/planning/fmea/FMEAVersionSnapshot.test.tsx`。复用 `FMEAEditorDragSort.test.tsx` 的 mock 模式，但**不 mock `VersionHistoryTab`**（改用一个调用 `onViewSnapshot` 的桩），并 mock `getFMEAVersion`：

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
  canEdit: vi.fn(),
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
  usePermission: () => ({
    canEdit: mocks.canEdit,
    canApprove: () => true,
  }),
}));
vi.mock("../../../hooks/useCollaboration", () => ({
  useCollaboration: () => ({ activeUsers: [], startEditing: vi.fn(), stopEditing: vi.fn(), isSyncing: false }),
}));
vi.mock("../../../components/dfmea/SmartSuggestionDropdown", () => ({
  default: ({ value, disabled }: { value: string; disabled?: boolean }) => <input aria-label="smart-suggestion" value={value} disabled={disabled} readOnly />,
}));
vi.mock("../../../components/dfmea/StructureTree", () => ({ default: () => <div data-testid="dfmea-structure-tree" /> }));
vi.mock("../../../components/dfmea/ParameterDiagram", () => ({ default: () => <div data-testid="parameter-diagram" /> }));
vi.mock("../../../components/lessons/LessonsLearnedModal", () => ({ default: () => null }));
// NOTE: 不 mock VersionHistoryTab — 用真实组件触发 onViewSnapshot
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
  const cur = makeDoc([node("f1", "Function", "当前功能")], []);
  mocks.getFMEA.mockResolvedValue(cur);
  mocks.getFMEAVersion.mockResolvedValue({
    fmea_id: "fmea-1", major_no: 1, minor_no: 0, change_type: "approve",
    change_summary: "v1", created_by: "u1", created_at: "2026-06-18T00:00:00Z",
    snapshot: { nodes: [node("f1", "Function", "快照功能")], edges: [] },
    sha256_hash: "abc",
  });
});

describe("FMEAEditorPage version snapshot", () => {
  it("loads version snapshot into read-only mode with banner", async () => {
    renderEditor();
    await waitFor(() => expect(mocks.getFMEA).toHaveBeenCalled());

    // 切到版本历史 Tab
    fireEvent.click(screen.getByText("tabs.versionHistory"));
    await waitFor(() => expect(mocks.getFMEAVersion).toBeDefined());

    // 点击「查看」按钮（VersionHistoryTab 真实渲染，按钮文案来自 t("history.view")）
    const viewBtn = await screen.findByRole("button", { name: "history.view" });
    fireEvent.click(viewBtn);

    // 快照加载
    await waitFor(() => expect(mocks.getFMEAVersion).toHaveBeenCalledWith("fmea-1", 1, 0));
    // 只读横幅出现
    await waitFor(() => expect(screen.getByText(/messages.viewingVersion/)).toBeInTheDocument());
    // 快照功能名渲染（结构树/表格中）
    await waitFor(() => expect(screen.getByText("快照功能")).toBeInTheDocument());
  });

  it("returns to current version on exit", async () => {
    renderEditor();
    await waitFor(() => expect(mocks.getFMEA).toHaveBeenCalled());
    fireEvent.click(screen.getByText("tabs.versionHistory"));
    const viewBtn = await screen.findByRole("button", { name: "history.view" });
    fireEvent.click(viewBtn);
    await waitFor(() => expect(screen.getByText(/messages.viewingVersion/)).toBeInTheDocument());

    // 点击「返回当前版本」
    fireEvent.click(screen.getByText("actions.exitVersion"));
    // 重新拉取当前文档（至少 2 次：初始 + exit）
    await waitFor(() => expect(mocks.getFMEA.mock.calls.length).toBeGreaterThanOrEqual(2));
    // 横幅消失
    await waitFor(() => expect(screen.queryByText(/messages.viewingVersion/)).not.toBeInTheDocument());
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAVersionSnapshot.test.tsx 2>&1 | tail -30`

Expected: FAIL — 横幅 `messages.viewingVersion` 未渲染（因为 `onViewSnapshot` 仍是 `message.info`）。

- [ ] **Step 3: 添加 viewingVersion state 与权限包装**

打开 `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`。

定位 `:280` `const { canEdit, canApprove } = usePermission();`，替换为：

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

> `useCallback` 已从 react import（`:1`）。`useState` 同样已 import。

- [ ] **Step 4: 添加 loadVersionSnapshot 与 exitVersionSnapshot**

在 `loadGraphData` 附近（约 `:418` `loadGraphData` 定义之后）添加：

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
    setViewingVersion(null);
  }, [fmeaId]);
```

在文件顶部 import 区（`:19` `import { getFMEA, updateFMEA, transitionFMEA } from "../../../api/fmea";` 之后）添加：
```ts
import { getFMEAVersion } from "../../../api/version";
```

> `getFMEA`、`setNodes`、`setEdges`、`setFmea`、`graphDataRef`、`baseGraphRef`、`normalizeGraphData`、`message`、`t` 均已在作用域内。

- [ ] **Step 5: 替换占位点**

定位 `:1882`：
```tsx
            onViewSnapshot={(major, minor) => message.info(t("messages.viewSnapshot", { major, minor }))}
```
替换为：
```tsx
            onViewSnapshot={loadVersionSnapshot}
```

- [ ] **Step 6: 添加只读横幅**

定位 `:1514` `<Tabs activeKey={outerTab} onChange={setOuterTab}...`（在 CollaborationBar 之后、Tabs 之前）。在 `<Tabs` 之前插入：

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

> `Alert` 已从 antd import（确认 `:3-12` 的 antd import 含 `Alert`；若不含则加入）。

- [ ] **Step 7: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAVersionSnapshot.test.tsx 2>&1 | tail -30`

Expected: PASS（2 个测试通过）。若失败，检查 `VersionHistoryTab` 真实渲染时 `listFMEAVersions` 是否被 mock（本测试未 mock `../../../api/version` 的 `listFMEAVersions`，会导致版本列表加载失败 → 「查看」按钮不渲染）。

**修正：** 在 Step 1 的 `vi.mock("../../../api/version", ...)` 中补上 `listFMEAVersions`：
```ts
vi.mock("../../../api/version", () => ({
  getFMEAVersion: mocks.getFMEAVersion,
  listFMEAVersions: vi.fn().mockResolvedValue({
    items: [{ fmea_id: "fmea-1", major_no: 1, minor_no: 0, change_type: "approve", change_summary: "v1", created_by: "u1", created_at: "2026-06-18T00:00:00Z" }],
    total: 1, page: 1, page_size: 100,
  }),
}));
```

- [ ] **Step 8: 运行全部 FMEA 测试与 lint**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/ 2>&1 | tail -20 && npm run lint 2>&1 | tail -20`

Expected: 所有测试通过，lint 无错误。

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/planning/fmea/FMEAEditorPage.tsx frontend/src/pages/planning/fmea/FMEAVersionSnapshot.test.tsx
git commit -m "feat(fmea): version snapshot read-only view in editor"
```

---

### Task 5: CP 编辑器 — i18n keys

**Files:**
- Modify: `frontend/src/locales/zh-CN/controlPlan.json` + `frontend/src/locales/en-US/controlPlan.json`

**Interfaces:**
- Produces: CP namespace 的 `message.viewingVersion`、`button.exitVersion`、`message.loadVersionFailed`。供 Task 6 使用。

- [ ] **Step 1: 修改 zh-CN controlPlan.json**

打开 `frontend/src/locales/zh-CN/controlPlan.json`。在 `"message": {` 块（约 145 行）内新增（紧邻 `loadFailed` 之类）：
```json
    "viewingVersion": "正在查看 v{{version}} 快照（只读）",
    "loadVersionFailed": "加载版本快照失败",
```
在 `"button": {` 块（约 10 行）内新增：
```json
    "exitVersion": "返回当前版本",
```

- [ ] **Step 2: 修改 en-US controlPlan.json**

同样位置：
```json
    "viewingVersion": "Viewing v{{version}} snapshot (read-only)",
    "loadVersionFailed": "Failed to load version snapshot",
```
`button` 块：
```json
    "exitVersion": "Return to current version",
```

- [ ] **Step 3: 验证 JSON 合法**

Run: `cd frontend && node -e "JSON.parse(require('fs').readFileSync('src/locales/zh-CN/controlPlan.json','utf8')); JSON.parse(require('fs').readFileSync('src/locales/en-US/controlPlan.json','utf8')); console.log('ok')"`

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/locales/zh-CN/controlPlan.json frontend/src/locales/en-US/controlPlan.json
git commit -m "i18n(controlPlan): add version snapshot read-only banner keys"
```

---

### Task 6: CP 编辑器 — 快照只读模式

**Files:**
- Modify: `frontend/src/pages/planning/control-plan/ControlPlanEditorPage.tsx`（权限 113-115、审批按钮 754、history tab 898-908、横幅 713 前、占位点 904）
- Test: `frontend/src/pages/planning/control-plan/CPVersionSnapshot.test.tsx`

**Interfaces:**
- Consumes: Task 2 的 `getCPVersion`、Task 5 的 i18n keys、现有 `getControlPlan`、`useCollaboration` 的 `startEditing`/`stopEditing`。
- Produces: `loadVersionSnapshot(major, minor)`、`exitVersionSnapshot()`、`viewingVersion` state、`canApproveAllowed`。

- [ ] **Step 1: 写失败测试**

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
  getCPSyncStatus: vi.fn(),
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
  listCPVersions: vi.fn().mockResolvedValue({
    items: [{ cp_id: "cp-1", major_no: 1, minor_no: 0, change_type: "approve", change_summary: "v1", created_by: "u1", created_at: "2026-06-18T00:00:00Z" }],
    total: 1, page: 1, page_size: 100,
  }),
}));
vi.mock("../../../api/customerQuality", () => ({ listCustomers: vi.fn().mockResolvedValue([]) }));
vi.mock("../../../api/specialCharacteristic", () => ({
  getCPSyncStatus: mocks.getCPSyncStatus.mockResolvedValue({ items: [] }),
  syncToCP: vi.fn(),
}));
vi.mock("../../../store/authStore", () => ({
  useAuthStore: (selector: (s: { user: unknown }) => unknown) => selector({ user: { user_id: "u1", role_key: "admin" } }),
}));
vi.mock("../../../hooks/usePermission", () => ({
  usePermission: () => ({
    canEdit: () => true,
    canApprove: () => true,
  }),
}));
vi.mock("../../../hooks/useCollaboration", () => ({
  useCollaboration: () => ({ activeUsers: [], startEditing: vi.fn(), stopEditing: vi.fn(), isSyncing: false }),
}));
vi.mock("../../../components/collaboration", () => ({
  CollaborationBar: () => <div data-testid="collab" />,
  ActiveUserIndicator: () => <div data-testid="au" />,
  ConflictResolutionModal: () => null,
}));
vi.mock("../../../components/control-plan/ImportFromFMEAModal", () => ({ default: () => null }));
vi.mock("../../../components/version/CreateVersionModal", () => ({ default: () => null }));
vi.mock("../../../components/version/RollbackConfirmModal", () => ({ default: () => null }));
vi.mock("../../../components/version/VersionCompareView", () => ({ default: () => <div data-testid="vc" /> }));
vi.mock("../../../components/design/PageShell", () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, t: (key: string) => key }),
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
  mocks.getCPVersion.mockResolvedValue({
    cp_id: "cp-1", major_no: 1, minor_no: 0, change_type: "approve",
    change_summary: "v1", created_by: "u1", created_at: "2026-06-18T00:00:00Z",
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
    // 快照标题渲染
    await waitFor(() => expect(screen.getByText("快照CP")).toBeInTheDocument());
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

> 注意 `vi.mock("react-i18next")` 中重复的 `t` 键是非法语法 — 改为 `useTranslation: () => ({ t: (key: string) => key })` 单一 `t`。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/pages/planning/control-plan/CPVersionSnapshot.test.tsx 2>&1 | tail -30`

Expected: FAIL（横幅未渲染，`onViewSnapshot` 仍是 `message.info`）。

- [ ] **Step 3: 添加 viewingVersion state 与权限包装**

打开 `frontend/src/pages/planning/control-plan/ControlPlanEditorPage.tsx`。

定位 `:113-115`：
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
  const isViewingVersion = viewingVersion !== null;
  const canEdit = canEditPerm('planning') && !isApproved && !isViewingVersion;
  const canApproveAllowed = (m: "planning") => rawCanApprove(m) && !isViewingVersion;
```

> `useState` 已 import（`:1`）。

- [ ] **Step 4: 添加 loadVersionSnapshot 与 exitVersionSnapshot**

在 `useEffect`（加载 CP，约 `:146`）之后添加：

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
      setViewingVersion(null);
    } catch {
      message.error(t("message.loadFailed"));
    }
  }, [id, t]);
```

在 import 区（`:14` `import { getControlPlan, ... } from "../../../api/controlPlan";` 之后）添加：
```ts
import { getCPVersion } from "../../../api/version";
```

> `useCallback`、`getControlPlan`、`message`、`t`、`baseItemsRef`、各 setter 均在作用域内。

- [ ] **Step 5: 替换审批按钮与 history tab 权限**

定位 `:754`：
```tsx
        {!isNew && canApprove('planning') && currentStatus !== "approved" && (
```
替换 `canApprove('planning')` → `canApproveAllowed('planning')`：
```tsx
        {!isNew && canApproveAllowed('planning') && currentStatus !== "approved" && (
```

定位 `:898-908` 的 `VersionHistoryTab`，把：
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

- [ ] **Step 6: 添加只读横幅**

定位 `:713` `<Tabs activeKey={outerTab}...`（在 sync pending banner 之后）。在 `<Tabs` 之前插入：

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

> `Alert` 已 import（`:5`）。`Button` 已 import。

- [ ] **Step 7: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/pages/planning/control-plan/CPVersionSnapshot.test.tsx 2>&1 | tail -30`

Expected: PASS（2 个测试通过）。

- [ ] **Step 8: 全量 lint + build + 测试**

Run: `cd frontend && npm run lint 2>&1 | tail -20 && npx tsc --noEmit 2>&1 | tail -20 && npx vitest run src/pages/planning/ 2>&1 | tail -20`

Expected: lint 无错误，tsc 无错误，所有 planning 测试通过。

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/planning/control-plan/ControlPlanEditorPage.tsx frontend/src/pages/planning/control-plan/CPVersionSnapshot.test.tsx
git commit -m "feat(controlPlan): version snapshot read-only view in editor"
```

---

### Task 7: 全量验证与收尾

**Files:** 无新增；运行整体验证。

- [ ] **Step 1: 全量前端构建**

Run: `cd frontend && npm run build 2>&1 | tail -20`

Expected: 构建成功（`tsc --noEmit` + `vite build` 均通过）。

- [ ] **Step 2: 全量前端测试**

Run: `cd frontend && npx vitest run 2>&1 | tail -20`

Expected: 所有测试通过（含原有 28 个 FMEA 编辑器测试 + 4 个新增快照测试）。

- [ ] **Step 3: 手动验证（可选，需 Docker）**

若要真人验证：`docker compose up`，登录 engineer，打开一个有版本的 FMEA → 版本历史 → 点「查看」→ 确认横幅 + 只读 + 图谱 Tab 显示快照 → 点「返回当前版本」。CP 同理。

- [ ] **Step 4: 最终 commit（若有未提交改动）**

```bash
git status
# 若有遗漏改动：
git add -A && git commit -m "chore: version snapshot view final cleanup"
```

---

## Self-Review

**1. Spec coverage:**
- §3.1 viewingVersion state → Task 4 Step 3 / Task 6 Step 3 ✓
- §3.2 canEdit/canApprove 包装（重命名 rawCanEdit）→ Task 4 Step 3 ✓
- §3.3 加载快照（含 graphDataRef 设置）→ Task 4 Step 4 ✓
- §3.4 返回（含 graphDataRef=null）→ Task 4 Step 4 ✓
- §3.5 占位点替换 → Task 4 Step 5 ✓
- §3.6 横幅 → Task 4 Step 6 ✓
- §3.7 图谱 graphDataRef 同步 → Task 4 Step 4（load 设、exit 清）✓
- §4.2 CP canApproveAllowed + history tab 权限 → Task 6 Step 3/5 ✓
- §4.3 CP 加载快照 → Task 6 Step 4 ✓
- §4.4 CP 返回 → Task 6 Step 4 ✓
- §4.5 CP 占位点 → Task 6 Step 5 ✓
- §4.6 CP 横幅 → Task 6 Step 6 ✓
- §5 类型修正（含 rollback=RollbackResponse）→ Task 1/2 ✓
- §6 i18n（FMEA + CP，删除 viewSnapshot 占位提示路径）→ Task 3/5 ✓
- §7 协作 guard（测试覆盖）→ Task 4/6 测试含 startEditing mock ✓
- §8 测试 → Task 4/6 新增 + Task 7 全量 ✓

**2. Placeholder scan:** 无 TBD/TODO；所有代码块完整。Task 6 Step 1 中 `vi.mock("react-i18next")` 的重复 `t` 键已在同步骤说明修正。`RollbackResponse` 类型存在性的条件分支已在 Task 2 Step 1 说明。

**3. Type consistency:** `getFMEAVersion` → `FMEAVersionDetail`（Task 1 定义、Task 2 修正、Task 4 使用）；`getCPVersion` → `CPVersionDetail`；`canApproveAllowed` 命名在 Task 6 Step 3/5 一致；`loadVersionSnapshot`/`exitVersionSnapshot` 命名在 Task 4/6 一致。

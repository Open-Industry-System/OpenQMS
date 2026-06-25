# FMEA / Control Plan 版本快照只读查看 — 设计文档

**日期**: 2026-06-23
**分支**: worktree-version-snapshot-view
**范围**: FMEA + Control Plan 两个编辑器的「查看版本」功能（当前为占位符 `message.info(...)`）

## 1. 背景与现状

用户在版本历史中点击「查看版本」时，FMEA 编辑器 (`FMEAEditorPage.tsx:1882`) 与 CP 编辑器 (`ControlPlanEditorPage.tsx:904`) 的 `onViewSnapshot` 都只是弹出 `message.info` 提示「功能开发中」。本设计完成该功能：以就地只读模式展示所选版本的快照内容。

### 后端（已完成，无需改动）
- `GET /api/fmea/{fmea_id}/versions/{major}/{minor}` → `FMEAVersionDetail`，含 `snapshot: dict`（建版本时的完整 `graph_data` = `{nodes, edges}`）与 `sha256_hash`。
- `GET /api/control-plans/{cp_id}/versions/{major}/{minor}` → `ControlPlanVersionDetail`，含 `header_snapshot: dict` 与 `items_snapshot: list[dict]`。
- 字段定义见 `backend/app/schemas/version.py` 与 `backend/app/services/version_service.py`。

### 前端现状
- API 客户端 `getFMEAVersion` / `getCPVersion` 已存在（`frontend/src/api/version.ts`）但**未被调用**，且返回类型与后端实际字段不符。
- 两个编辑器所有可编辑控件统一由 `canEdit(...)` / `canApprove(...)` 门控（`usePermission()` hook）。

## 2. 关键设计决策

**就地只读模式**（用户已选定）：在编辑器内加载版本快照的 state，通过覆盖 `canEdit` 让全部已有可编辑控件自动转只读，顶部显示只读横幅，提供「返回当前版本」按钮。

### 支点：覆盖 canEdit
两个编辑器的 30+ 处可编辑控件均已 `disabled={!canEdit('fmea')}`（CP 为 `disabled={!canEdit}`）。因此**只需把 `canEdit` 在 `viewingVersion` 非空时强制返回 `false`**，即可让全部输入框/Select/增删/保存/转交按钮进入只读，无需逐个改动。`canApprove` 同理覆盖。

## 3. FMEA 编辑器改动 (`frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`)

### 3.1 State
新增 `viewingVersion: { major: number; minor: number } | null`。

### 3.2 覆盖权限
现有 `const { canEdit, canApprove } = usePermission();`（`:280`，直接解构，无别名）。必须重命名为 `rawCanEdit` / `rawCanApprove` 后再包本地 `canEdit` / `canApprove`，**避免同名冲突**：

```ts
const { canEdit: rawCanEdit, canApprove: rawCanApprove } = usePermission();
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
> ⚠️ 现有 `canEdit`/`canApprove` 来自 `usePermission()`（已 `useCallback` 稳定化）。替换为本地包装函数后，须确认所有依赖 `canEdit` 的 `useMemo`/`useCallback` 依赖数组仍正确（如 `columns` 的 deps），避免 stale closure。

### 3.3 加载快照
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
```

> 错误处理沿用本编辑器现有风格（`FMEAEditorPage.tsx:415` 的 `err?.response?.data?.detail || t("messages.operationFailed")`）。**不引入 `formatFMEAError`** —— 该工具在本 worktree 不存在（`frontend/src/utils/fmeaError.ts` 缺失，`FMEAEditorPage.tsx` 也未导入），主工作区虽有但不应作为本实现的依赖。

### 3.4 返回当前版本
```ts
const exitVersionSnapshot = useCallback(async () => {
  const doc = await getFMEA(fmeaId);
  setFmea(doc);
  setNodes(doc.graph_data?.nodes || []);
  setEdges(doc.graph_data?.edges || []);
  baseGraphRef.current = {
    nodes: JSON.parse(JSON.stringify(doc.graph_data?.nodes || [])),
    edges: JSON.parse(JSON.stringify(doc.graph_data?.edges || [])),
  };
  graphDataRef.current = null; // 清空快照图谱缓存，使下次切到图谱 Tab 时 loadGraphData 重拉当前文档
  setViewingVersion(null);
}, [fmeaId]);
```
重新拉取当前文档（而非缓存当前 state）以避免 stale / 冲突检测基线错乱。`graphDataRef.current = null` 与 §3.7 退出要求一致（对应 `:332` 保存后清空）。

### 3.5 占位点替换
`FMEAEditorPage.tsx:1882` 的 `onViewSnapshot={(major, minor) => message.info(...)}` 改为 `onViewSnapshot={loadVersionSnapshot}`。

### 3.6 横幅
在 `<Tabs activeKey={outerTab}>` 之前渲染：
```tsx
{viewingVersion && (
  <Alert
    type="warning"
    showIcon
    style={{ marginBottom: 16 }}
    message={t("messages.viewingVersion", { version: `${viewingVersion.major}.${viewingVersion.minor}` })}
    action={<Button size="small" onClick={exitVersionSnapshot}>{t("actions.exitVersion")}</Button>}
  />
)}
```

### 3.7 图谱 Tab 数据源（已核实）
`GraphCanvas` 本身不拉 API，它读 `graphDataRef.current`（`FMEAEditorPage.tsx:125`，渲染于 `:1562-1567`）。但 `loadGraphData()`（`:250`）在 `graphDataRef.current` 为空时调用 `getFMEA(id)` 拉取**当前**文档：

```ts
const loadGraphData = useCallback(async () => {
  if (!id || graphDataRef.current) return;   // ← ref 非空则跳过
  const doc = await getFMEA(id);
  graphDataRef.current = normalizeGraphData(rawNodes, rawEdges);
  ...
}, [id]);
```

关键：`loadGraphData` 有 `if (!id || graphDataRef.current) return` 的早退 —— 只要 ref 已设值就不会重新拉取。因此：

- **进入快照**：`loadVersionSnapshot` 中必须显式设置 `graphDataRef.current = normalizeGraphData(snapshot.nodes, snapshot.edges)`，使图谱 Tab 显示快照数据而非当前文档。
- **退出快照**：`exitVersionSnapshot` 中必须 `graphDataRef.current = null`（与 `:332` 保存后清空一致），使下次切到图谱 Tab 时 `loadGraphData` 重新拉取当前文档。

注意 `normalizeGraphData` 入参类型需与现有 `:257` 的强转写法一致（`rawNodes as unknown as Array<Record<string, unknown>>`）。

### 3.8 选择态与协作 guard（进入/退出快照时重置）
加载快照仅替换 nodes/edges/graphDataRef，但页面还有 `selectedFunctionId`、`selectedStructureNode`、`selectedGraphNode`、`drawerVisible`、`highlightNodes` 等选择/高亮态（`FMEAEditorPage.tsx:106-131`）。若不清空，快照切换后 drawer 仍指向已不存在的节点、图谱高亮残留。因此：

- **进入快照** (`loadVersionSnapshot`)：`setSelectedFunctionId(null)`、`setSelectedStructureNode(null)`、`setSelectedGraphNode(null)`、`setDrawerVisible(false)`、`setHighlightNodes([])`。
- **退出快照** (`exitVersionSnapshot`)：同样清空上述五项。

**协作 guard**：`startEditing` 在 severity/occurrence/detection Select 的 `onFocus` 中调用，这些 Select 已 `disabled={!canEdit('fmea')}`。为提供业务层保护（非仅依赖 UI 假设），在 `useCollaboration` 解构处加单点 guard：

```ts
const { activeUsers, startEditing: rawStartEditing, stopEditing, isSyncing } = useCollaboration("fmea", fmeaId);
const startEditing = useCallback((...args: Parameters<typeof rawStartEditing>) => {
  if (isViewingVersion) return;
  rawStartEditing(...args);
}, [rawStartEditing, isViewingVersion]);
```

测试须断言：进入快照态后 `startEditing`（mock spy）未被调用。

## 4. CP 编辑器改动 (`frontend/src/pages/planning/control-plan/ControlPlanEditorPage.tsx`)

### 4.1 State
新增 `viewingVersion: { major: number; minor: number } | null`。

### 4.2 覆盖权限
当前 CP 编辑器**没有本地 `canApprove` 包装**：`const { canEdit: canEditPerm, canApprove } = usePermission();`（`:113`），审批按钮直接用 `canApprove('planning')`（`:754`），版本历史 Tab 也用原始权限 `canCreate={canEditPerm('planning')}` / `canRollback={canApprove('planning')}`（`:901-902`）。因此「canApprove 同理覆盖」在 CP 不成立，需新增本地包装：

```ts
const { canEdit: canEditPerm, canApprove: rawCanApprove } = usePermission();
const isViewingVersion = viewingVersion !== null;
const canEdit = canEditPerm('planning') && !isApproved && !isViewingVersion;
const canApproveAllowed = (m: string) => rawCanApprove(m) && !isViewingVersion;
```

然后将：
- 审批按钮 `:754` 的 `canApprove('planning')` → `canApproveAllowed('planning')`。
- 版本历史 Tab `:901-902` 的 `canCreate={canEditPerm('planning')}` → `canCreate={canEdit}`，`canRollback={canApprove('planning')}` → `canRollback={canApproveAllowed('planning')}`。

> 这样查看快照时审批/创建版本/回滚按钮一并隐藏，避免在只读态误操作。

### 4.3 加载快照
```ts
const loadVersionSnapshot = useCallback(async (major: number, minor: number) => {
  try {
    const v = await getCPVersion(id!, major, minor);
    setTitle(v.header_snapshot.title || "");
    setDocumentNo(v.header_snapshot.document_no || "");
    setPhase(v.header_snapshot.phase || "sample");
    setPartNo(v.header_snapshot.part_no || "");
    setPartName(v.header_snapshot.part_name || "");
    setContactInfo(v.header_snapshot.contact_info || "");
    setCoreGroup(v.header_snapshot.core_group || "");
    setOrgFactory(v.header_snapshot.org_factory || "");
    setDrawingRev(v.header_snapshot.drawing_rev || "");
    setItems(v.items_snapshot || []);
    setViewingVersion({ major, minor });
  } catch (err) {
    message.error(/* ... */);
  }
}, [id]);
```

### 4.4 返回当前版本
重新 `getControlPlan(id)`，按现有 `useEffect` 中的赋值逻辑复位全部 header 字段与 `setItems`，清空 `viewingVersion`。

### 4.5 占位点替换
`ControlPlanEditorPage.tsx:904` 改为 `onViewSnapshot={loadVersionSnapshot}`。

### 4.6 横幅
同 FMEA，在编辑器主区域顶部渲染只读 Alert + 「返回当前版本」。

### 4.7 快照态隔离（隐藏当前文档态控件）
加载快照只设置 header 字段与 items，但 `cp` state 未更新，导致以下控件在只读态仍显示**当前文档**状态/动作，须在 `isViewingVersion` 时隐藏或改读快照值：

- **sync_pending 横幅**（`ControlPlanEditorPage.tsx:699` `{cp?.sync_pending && ...}`）：加 `&& !isViewingVersion` 隐藏。
- **checkStale 按钮**（`:732` `{!isNew && (...)}`，未受 `canEdit` 门控）：加 `&& !isViewingVersion` 隐藏。
- **ValidationPanel**（`:914` `{!isNew && id && (<ValidationPanel cpId={id} />)}`）：加 `&& !isViewingVersion` 隐藏（历史版本不做校验）。
- **fmea_ref_id 显示**（`:858` `value={cp?.fmea_ref_id || ...}`）与 **PageShell 状态副标题**（`:676` 用 `currentStatus`）：新增 `versionHeader: CPVersionHeader | null` state，`loadVersionSnapshot` 中 `setVersionHeader(v.header_snapshot)`，`exitVersionSnapshot` 中 `setVersionHeader(null)`；显示值改为 `isViewingVersion ? (versionHeader?.fmea_ref_id || t("form.notAssociated")) : (cp?.fmea_ref_id || t("form.notAssociated"))`，副标题状态同理用 `versionHeader?.status`。

**协作 guard**：CP 的 `startEditing` 在 7 处 `onFocus`（items 表各列）。与 FMEA 同理，在 `useCollaboration` 解构处（`:118`）加单点 guard：

```ts
const { activeUsers, isSyncing, startEditing: rawStartEditing, stopEditing } = useCollaboration("control_plan", cpId);
const startEditing = useCallback((...args: Parameters<typeof rawStartEditing>) => {
  if (isViewingVersion) return;
  rawStartEditing(...args);
}, [rawStartEditing, isViewingVersion]);
```

## 5. 类型与 API 客户端修正

### `frontend/src/types/index.ts`
后端 list 端点返回 `FMEAVersionListItem`（无 snapshot），detail 端点返回 `FMEAVersionDetail`（含 `snapshot` + `sha256_hash`）。当前前端 `VersionBase`/`FMEAVersion`/`CPVersion` 类型与后端不符（字段不可为空却应是 `| null`，且缺 `version_id`、CP 缺 `source_fmea_version_id`）。修正方案：

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

export interface CPVersionHeader { /* 字段对齐 header_snapshot，见 version_service.py:236-249，各字段 string | null */ }

export interface CPVersionDetail extends CPVersion {
  header_snapshot: CPVersionHeader;
  items_snapshot: ControlPlanItem[];
  sha256_hash: string;
}
```

`VersionHistoryTab.getChangeTypeConfig(changeType: string)` 参数改为 `string | null`，default 分支 `label: changeType ?? ""` 以避免渲染 `null`。`change_summary` 的 `{v.change_summary && ...}` 已是真值判断，null 安全。

### `frontend/src/api/version.ts` 返回类型
- `getFMEAVersion` / `createFMEAVersion` → `FMEAVersionDetail`（detail 与 create 端点均返回 `FMEAVersionDetail`，`api/version.py:97-114`）。
- `getCPVersion` / `createCPVersion` → `CPVersionDetail`（`api/version.py:226-243`）。
- `rollbackFMEAVersion` / `rollbackCPVersion` → **`RollbackResponse`**（rollback 端点返回 `RollbackResponse`，`api/version.py:115` 与 `:244`，**非** `*Detail`）。
- 排查所有 `FMEAVersion`/`CPVersion` 引用（`VersionHistoryTab`、`VersionCompareView`、`RollbackConfirmModal`），确保仅访问 list item 字段。

## 6. i18n

### `frontend/src/locales/zh-CN/fmea.json`（及 en-US）
- `messages.viewSnapshot` 当前 locale 用 `{{version}}`，但 `:1882` 调用传的是 `{ major, minor }` —— 不匹配。该提示路径将被 `loadVersionSnapshot` 取代，**删除 `:1882` 的 `message.info` 调用与该 key**（或改为加载中提示并统一插值为 `{ version: \`${major}.${minor}\` }`，二选一，倾向删除）。
- 新增 `messages.viewingVersion`: `"正在查看 v{{version}} 快照（只读）"`（插值传 `{ version: \`${major}.${minor}\` }`）。
- 新增 `actions.exitVersion`: `"返回当前版本"`。
- 新增 `messages.loadVersionFailed`: `"加载版本快照失败"`。
- CP locale：`ControlPlanEditorPage` 现用 `button.viewSnapshot`（`:904`），同样删除该 `message.info` 调用，新增与 FMEA 对应的 viewing/exit/loadFailed key（确认 CP 的 i18n namespace 后补，见实现计划）。

## 7. 边界与风险

- **协作 `useCollaboration`**：查看期间 `canEdit` 为 false → 可编辑控件 disabled，通常不触发 focus。除此外，在 `useCollaboration` 解构处加单点 `startEditing` guard（`isViewingVersion` 时 no-op，见 §3.8/§4.7）作为业务保护层；只读测试断言进入快照态后 `startEditing`（mock spy）未被调用。
- **版本历史 Tab 内操作**：FMEA 的 `canCreate={canEdit(...)}` / `canRollback={canApprove(...)}` 在只读时自动变 false；CP 须按 §4.2 把 history tab 改用 `canEdit` / `canApproveAllowed`。创建/回滚按钮隐藏，避免误操作。对比弹窗独立，不受影响。
- **冲突检测基线 `baseGraphRef`**：查看时不触碰；返回时重新拉取重置。
- **向导重定向**：查看快照仅 setState 不导航；返回重新拉取时，若当前为草稿 DFMEA 未完成向导则走原重定向逻辑（可接受边界）。
- **图谱 Tab**：见 3.7，进入/退出快照时同步设置/清空 `graphDataRef.current`。

## 8. 测试

- 现有 28 个 FMEA 编辑器测试须全绿。
- 新增测试（`FMEAEditorPage` 测试文件）：
  1. 点击「查看版本」→ 调用 `getFMEAVersion`，state 被快照填充，横幅渲染。
  2. 只读态下 `canEdit` 被覆盖（保存/提交按钮 disabled 或隐藏）。
  3. 点「返回当前版本」→ 调用 `getFMEA`，恢复当前文档 state，横幅消失。
- CP 编辑器新增对应测试（若有测试文件）。

## 9. 实现顺序

1. 类型与 API 客户端修正（types + version.ts）。
2. FMEA 编辑器：state + canEdit/canApprove 包装（重命名避免冲突）+ 加载/返回（含 `graphDataRef` 同步）+ 横幅 + 占位点替换。
3. CP 编辑器：同上。
4. i18n。
5. 测试：跑现有测试 + 新增。
6. `npm run lint` + `npm run build`（tsc --noEmit）验证。

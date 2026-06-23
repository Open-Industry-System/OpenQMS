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
    setViewingVersion({ major, minor });
  } catch (err) {
    message.error(formatFMEAError(err, t("messages.loadVersionFailed")));
  }
}, [fmeaId, t]);
```

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
  setViewingVersion(null);
}, [fmeaId]);
```
重新拉取当前文档（而非缓存当前 state）以避免 stale / 冲突检测基线错乱。

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

### 3.7 图谱 Tab 风险点
`GraphCanvas` 可能从 API 重新拉取**当前**文档的图谱而非 state。需在实现阶段验证：
- 若 `GraphCanvas` 读 state → 自然显示快照数据，无需处理。
- 若 `GraphCanvas` 读 API → 查看快照时图谱会显示当前文档（错数据）。处理方式：在只读时让图谱复用快照数据（传 prop），或隐藏图谱 Tab。

## 4. CP 编辑器改动 (`frontend/src/pages/planning/control-plan/ControlPlanEditorPage.tsx`)

### 4.1 State
新增 `viewingVersion: { major: number; minor: number } | null`。

### 4.2 覆盖权限
现有 `const canEdit = canEditPerm('planning') && !isApproved;` → `... && !isApproved && viewingVersion === null;`。`canApprove` 同理覆盖。

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

## 5. 类型与 API 客户端修正

### `frontend/src/types/index.ts`
后端 list 端点返回 `FMEAVersionListItem`（无 snapshot），detail 端点返回 `FMEAVersionDetail`（含 `snapshot` + `sha256_hash`）。当前前端 `FMEAVersion` 类型带 `graph_data: GraphData` 字段是错误的（list 不含此字段）。修正方案：

- 重定义 `FMEAVersion`（= list item）去掉 `graph_data`：`{ fmea_id, major_no, minor_no, change_type, change_summary, created_by, created_at }`（继承 `VersionBase`）。
- 新增 `FMEAVersionDetail extends FMEAVersion { snapshot: GraphData; sha256_hash: string; }`。
- CP 同理：`CPVersion`（list item）已含 `items: ControlPlanItem[]` —— 但 list 端点同样不返回 items，故应去掉 `items`，改为 `CPVersionDetail extends CPVersion { header_snapshot: CPVersionHeader; items_snapshot: ControlPlanItem[]; sha256_hash: string; }`，并新增 `CPVersionHeader` 接口（字段对齐 `header_snapshot`，见 `version_service.py:236-249`）。
- 修正 `getFMEAVersion` / `getCPVersion` / `createFMEAVersion` / `createCPVersion` / `rollbackFMEAVersion` / `rollbackCPVersion` 的返回类型为对应 `*Detail`。
- `VersionListResponse<T>` 的 `T` 保持为 list item 类型。
- 排查所有 `FMEAVersion`/`CPVersion` 引用（`VersionHistoryTab`、`VersionCompareView`、`RollbackConfirmModal` 等），确保仅访问 list item 字段。

## 6. i18n

### `frontend/src/locales/zh-CN/fmea.json`（及 en-US）
- `messages.viewSnapshot` 去掉「（功能开发中）」后缀（保留作为加载提示或移除）。
- 新增 `messages.viewingVersion`: `"正在查看 v{{version}} 快照（只读）"`
- 新增 `actions.exitVersion`: `"返回当前版本"`
- 新增 `messages.loadVersionFailed`: `"加载版本快照失败"`
- CP locale 同步对应 key（视 `ControlPlanEditorPage` 的 namespace 而定，确认后补）。

## 7. 边界与风险

- **协作 `useCollaboration`**：查看期间 `canEdit` 为 false → 不触发 `startEditing`；协作栏保留展示，不主动隐藏。
- **版本历史 Tab 内操作**：`canCreate={canEdit(...)}` 与 `canRollback={canApprove(...)}` 在只读时自动变 false → 创建/回滚按钮隐藏，避免误操作。对比弹窗独立，不受影响。
- **冲突检测基线 `baseGraphRef`**：查看时不触碰；返回时重新拉取重置。
- **向导重定向**：查看快照仅 setState 不导航；返回重新拉取时，若当前为草稿 DFMEA 未完成向导则走原重定向逻辑（可接受边界）。
- **图谱 Tab**：见 3.7，实现阶段验证并处理。

## 8. 测试

- 现有 28 个 FMEA 编辑器测试须全绿。
- 新增测试（`FMEAEditorPage` 测试文件）：
  1. 点击「查看版本」→ 调用 `getFMEAVersion`，state 被快照填充，横幅渲染。
  2. 只读态下 `canEdit` 被覆盖（保存/提交按钮 disabled 或隐藏）。
  3. 点「返回当前版本」→ 调用 `getFMEA`，恢复当前文档 state，横幅消失。
- CP 编辑器新增对应测试（若有测试文件）。

## 9. 实现顺序

1. 类型与 API 客户端修正（types + version.ts）。
2. FMEA 编辑器：state + canEdit 包装 + 加载/返回 + 横幅 + 占位点替换；验证图谱 Tab。
3. CP 编辑器：同上。
4. i18n。
5. 测试：跑现有测试 + 新增。
6. `npm run lint` + `npm run build`（tsc --noEmit）验证。

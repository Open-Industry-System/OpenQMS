# US-E2E-01 8D 全程闭环 — Spec A：D4 根因验证 + AI 采纳/动作审计（D4/D5 采纳 + D7 节点动作）

**状态**：设计稿（待评审）
**日期**：2026-07-03
**关联**：`docs/user-stories/US-E2E-01-capa-8d-closed-loop.md`（v6 定稿）、`PROGRESS.md` 特性缺口清单 P0-1 / P0-4
**分支**：`worktree-us-e2e-01-8d-closed-loop`（从 `fix/dashboard-admin-pages` head 切出）

## 背景与范围

US-E2E-01 故事要求 8D 全程闭环可审计：根因必须经现场验证才可确认（D4→D5 阻断），AI 推荐采纳 + 根因验证记录留痕含来源。`PROGRESS.md` 缺口审计识别出两个数据模型缺口：

- **P0-1 D4 现场根因验证子流程**：当前 `capa_eightd.d4_root_cause` 是单个 `Text` 列，无方法/结果/证据字段、无附件关联、无 D4→D5 阻断校验。
- **P0-4 AI 采纳审计留痕**：D4/D5 推荐面板已有「采纳」按钮（`D4RecPanel.tsx:83` / `D5RecPanel.tsx:54,107`），但采纳只把文本**追加**到 d-step 字段，未记录"采纳了哪条推荐、来自哪个源、什么时间"。注：`PROGRESS.md` 缺口清单原文把 D7 也列入，但 `D7RecPanel` 实际无采纳按钮（它是 confirm/skip/自动回填流程，见决策 2），Spec A 仅覆盖 D4/D5 采纳。

本 spec 是 B 路线三阶段分解的**第一阶段**，仅交付 P0-1 + P0-4 两个数据模型缺口。编排器、DAG 面板、provenance UI、SPC/IQC 新源属 Spec B；故事级 E2E spec 属 Spec C。三阶段依赖顺序：A → B → C。

### 不在本 spec 范围

- 12 阶段推荐编排器与 DAG 可视化面板（P0-2，Spec B）
- 推荐来源 provenance 标签 UI + testid（P0-3，Spec B；本 spec 仅埋采纳/验证元素的 testid）
- SPC / IQC / MES / 供货 / 同类型产品 / lessons 新推荐源（P1-5~10，Spec B）
- 故事级 E2E spec `capa-story-closed-loop.spec.ts`（P2-11，Spec C）
- `stage_index` 字段的实际填充——本 spec 仅建可空列，编排器上线后透传（见下"决策"）

## 关键决策（已与用户确认）

1. **stage_index 可空，P0-2 后补**：`capa_ai_adoption.stage_index` 建为可空列，现阶段写 `None`。P0-2 编排器上线后在推荐响应里返回 `stage_index`，前端采纳时回传，服务层透传——届时只改服务层一处。历史采纳记录不回填。Spec C 故事 spec 只断言 P0-2 后创建的采纳记录的 stage_index。

2. **采纳统一端点 + 落库 + 审计（追加语义）**：新增 `POST /api/capa/{report_id}/adopt-recommendation`，服务层一次事务内：①插 `capa_ai_adoption` 记录；②写 `ADOPT_RECOMMENDATION` AuditLog；③把 `adopted_text` **追加**到对应 d-step 字段——`new = f"{current}\n{adopted_text}" if current else adopted_text`，与现有 `CAPADetailPage.tsx:501-506/527-532` 的 `onAdopt` 行为完全一致（`current ? \`${current}\n${text}\` : text`），保留用户已输入或之前采纳的多条根因/措施。前端采纳按钮改调此端点，删除原 `onAdopt` 父组件回调；采纳后前端 refetch CAPA 拿最新 d-step 回显。
   - **未保存输入保护**：TextArea 本地值若 dirty，前端在调采纳端点前先 `await handleUpdate(field, localValue)` flush 到 DB，避免采纳追加到旧 DB 值后 refetch 冲掉本地未保存输入（与现有 `onAdopt` 用 `localData` 拼接的行为等价）。
   - **范围**：D4 / D5 文本采纳走统一采纳端点。D7RecPanel 没有"采纳"按钮（它是 confirm/skip/自动回填到 FMEA 的流程，`D7RecPanel.tsx`），但其 confirm/skip/自动回填是**等价的"对推荐的动作"**，故事验收同样要求"留痕含来源"——现有 `updateFMEA` 只写 `fmea_documents` 的 graph_data UPDATE，无法回溯"哪条 CAPA D7 推荐触发了哪个节点动作"。Spec A **新增 D7 节点动作审计**（独立表 + 端点，不与 D4/D5 文本采纳混用），见决策 6。

3. **证据附件 = JSONB 元数据，不引入文件存储管道**：`capa_root_cause_verification.evidence_attachments` 用 JSONB list 存 `[{filename, size, content_ref}]`，沿用 `audit_finding.customer_confirmation_attachments` 惯例。前端用 Ant `Upload beforeUpload={false}` 捕获文件元数据，不真实上传。

4. **验证记录一对多、无 DELETE**：一个 CAPA 可有多条验证记录（对应多次候选根因尝试，故事 5.d「验证不通过 → 选另一条或新增根因，再次验证」）。不提供 DELETE——验证不通过的记录留作历史。

5. **D4→D5 闸口**：`advance_capa` 在 `D4_ROOT_CAUSE → D5_CORRECTION` 转换前校验 `count(is_verified=true) ≥ 1`，不通过抛 `ValueError` → API 400。

6. **D7 节点动作审计（独立模型，不与 D4/D5 文本采纳混用）**：新增表 `capa_d7_node_action` + 3 个端点，记录工程师对 D7 推荐的 confirm / skip / auto-fill 动作，带 CAPA + FMEA + 节点 + 来源 + 控制措施前后名。自动回填**移到后端**（`POST /d7-auto-fill` 一次事务内更新 FMEA graph_data + 写 FMEA UPDATE audit + 写 `capa_d7_node_action` + 写 `D7_AUTO_FILLED_FMEA` CAPA audit），前端不再直接 `updateFMEA`。顺带修复 D7 confirm/skip 现状只在内存、刷新即丢的隐患（持久化到表，UI 经 `GET` 重载）。

7. **采纳返回值（Finding 2）**：`adopt_recommendation` 服务层返回 `(adoption, new_value)` 元组，handler 用 `new_value` 组装 `AdoptResponse.field_value`，避免实现时漏掉 `field_value`。

8. **未保存输入保护接口（Finding 3）**：D4/D5 RecPanel 不直接知道 TextArea 状态（dirty + `handleUpdate` 在 `CAPADetailPage`）。父组件传 `beforeAdopt?: () => Promise<void>`，RecPanel 采纳前 `await beforeAdopt?.()` flush 本地 d-step 字段，再调采纳端点。

9. **D7 改判语义（Finding 5）**：D7 动作按"当前裁决"建模（一行 per capa+fmea+fm+fc，可改判），匹配现有 UI 可在 updated/skipped 间切换的行为：
   - `record_d7_action`（confirm/skip）= **upsert**：无既有行 → insert + `D7_NODE_CONFIRMED`/`D7_NODE_SKIPPED` audit；有既有行且 `action != "auto_filled"` → 更新 `action`/`reason`/`acted_by`/`acted_at` + `D7_NODE_ACTION_CHANGED` audit（带 `old_action`/`new_action`）；既有行 `action == "auto_filled"` → 400 "已自动回填，不可改判"（前端禁用 confirm/skip 按钮并显示已锁定）。
   - `auto_fill_d7`：无既有行 → insert `auto_filled` + 图改 + audits；既有行 `action == "auto_filled"` → 409 幂等拒绝（前端应禁用 auto-fill 按钮）；既有行 `action in {confirmed, skipped}` → 升级为 `auto_filled`（做图改 + 更新行 + `D7_NODE_ACTION_CHANGED` + `D7_AUTO_FILLED_FMEA` audits）。
   - 唯一索引见数据模型（`COALESCE` 表达式索引）。

## 数据模型

### 新表 `capa_root_cause_verification`

```python
class CapaRootCauseVerification(Base):
    __tablename__ = "capa_root_cause_verification"
    verification_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    capa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False)
    root_cause_text: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str | None] = mapped_column(Text)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    evidence_attachments: Mapped[list] = mapped_column(JSONB, default=lambda: [])
    source_ref: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    # 索引：ix_capa_rcv_capa_id (capa_id), ix_capa_rcv_factory (factory_id)
```

`source_ref` 为 JSONB：来自 AI 推荐时 `{match_source, fmea_id, failure_cause_node_id, item_ref}`；工程师手填「新增根因」时为 `null`。

### 新表 `capa_ai_adoption`

```python
class CapaAIAdoption(Base):
    __tablename__ = "capa_ai_adoption"
    adoption_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    capa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False)
    d_step: Mapped[str] = mapped_column(String(8), nullable=False)        # "d4"|"d5"（D7 不走采纳端点，见决策 2）
    adopted_text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)       # match_source 值
    stage_index: Mapped[int | None] = mapped_column(Integer, nullable=True)  # P0-2 后填
    item_ref: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    adopted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    adopted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # 索引：ix_capa_adopt_capa_step (capa_id, d_step), ix_capa_adopt_factory (factory_id)
```

### 新表 `capa_d7_node_action`（决策 6）

```python
class CapaD7NodeAction(Base):
    __tablename__ = "capa_d7_node_action"
    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    capa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)        # "confirmed"|"skipped"|"auto_filled"
    fmea_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id"), nullable=False)
    failure_mode_node_id: Mapped[str] = mapped_column(String(36), nullable=False)
    failure_cause_node_id: Mapped[str | None] = mapped_column(String(36))
    match_source: Mapped[str] = mapped_column(String(40), nullable=False)  # "linked"|"keyword"
    prevention_control_node_id: Mapped[str | None] = mapped_column(String(36))  # auto_filled 才有
    prevention_control_name_before: Mapped[str | None] = mapped_column(Text)     # auto_filled：改动前控制名
    prevention_control_name_after: Mapped[str | None] = mapped_column(Text)      # auto_filled：改动后（= d5_correction）
    reason: Mapped[str | None] = mapped_column(Text)                            # skip 原因
    acted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    acted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # 索引：ix_capa_d7_capa (capa_id), ix_capa_d7_factory (factory_id)
```

- 一个 CAPA 一条 FMEA 节点只记一条 action 行（当前裁决，可改判，见决策 9）；用**表达式唯一索引** `CREATE UNIQUE INDEX ix_capa_d7_node_unique ON capa_d7_node_action (capa_id, fmea_id, failure_mode_node_id, COALESCE(failure_cause_node_id, ''))` 防重复——Postgres 普通 UNIQUE 允许多个 NULL，`failure_cause_node_id` 可空，故用 `COALESCE(...,'')` 收口（Finding 4）。
- `auto_filled` 时 `prevention_control_name_after = capa.d5_correction`，`before` = 改动前该控制节点 name（若有），便于审计"把控制措施从 X 改成了 Y"。

### 迁移

`backend/alembic/versions/20260703_add_capa_verification_adoption.py`，`down_revision` 取当前 head（实施时确认），手写 `op.create_table` ×3（`capa_root_cause_verification` / `capa_ai_adoption` / `capa_d7_node_action`）+ 普通索引（`capa_id`/`factory_id` 等）。`capa_d7_node_action` 的去重用**表达式唯一索引**（Finding 4，普通 UNIQUE 约束无法表达 `COALESCE`）：

```python
op.execute("CREATE UNIQUE INDEX ix_capa_d7_node_unique ON capa_d7_node_action "
           "(capa_id, fmea_id, failure_mode_node_id, COALESCE(failure_cause_node_id, ''))")
```

遵循 ADR-0013（UUID `as_uuid=True`）、ADR-0001（Python 端 `uuid4`）。`downgrade()` 反向 drop（先 drop 表达式索引，再 drop 表）。

## API

新增 7 个端点，挂在现有 `backend/app/api/capa.py` 的 `router = APIRouter(prefix="/api/capa")`。

| 方法 | 路径 | 权限 | 作用 |
|---|---|---|---|
| POST | `/api/capa/{report_id}/adopt-recommendation` | CAPA EDIT | D4/D5 文本采纳：插 adoption + ADOPT_RECOMMENDATION audit + 追加 d-step 字段，单事务 |
| POST | `/api/capa/{report_id}/root-cause-verifications` | CAPA EDIT | 新建验证记录 + ROOT_CAUSE_VERIFICATION audit |
| GET | `/api/capa/{report_id}/root-cause-verifications` | CAPA VIEW | 列出该 CAPA 全部验证记录（按 created_at desc） |
| PATCH | `/api/capa/{report_id}/root-cause-verifications/{vid}` | CAPA EDIT | 更新（翻 is_verified、补 method/result/evidence）；写 audit |
| POST | `/api/capa/{report_id}/d7-node-actions` | CAPA EDIT | 记录 D7 节点 confirm/skip + D7_NODE_CONFIRMED/D7_NODE_SKIPPED audit |
| GET | `/api/capa/{report_id}/d7-node-actions` | CAPA VIEW | 列出该 CAPA 全部 D7 节点动作（UI 持久化 confirm/skip 状态） |
| POST | `/api/capa/{report_id}/d7-auto-fill` | CAPA EDIT | 后端自动回填：更新 FMEA graph_data + FMEA UPDATE audit + capa_d7_node_action(auto_filled) + D7_AUTO_FILLED_FMEA audit，单事务 |

每个端点 handler 模式（沿用 `api/capa.py` 现有 thin handler 写法）：
1. `level = await get_user_permission(scope.user, Module.CAPA, db)`；`< EDIT`（或 VIEW）→ 403
2. `capa = await capa_service.get_capa(db, report_id)`；None → 404
3. `check_factory_access(capa.factory_id, scope)` → 跨工厂 403
4. 调服务层；异常映射：`ValueError` → 400；`LookupError` → 404（PATCH 归属不匹配 / verification 不属于该 CAPA / D7 目标 FMEA 不存在 / auto_fill 重复幂等拒绝）；`PermissionError` → 403（D7 目标 FMEA 跨工厂）。D7 端点额外：`d7-node-actions` 需 `Module.FMEA` ≥ VIEW；`d7-auto-fill` 需 `Module.FMEA` ≥ EDIT。

**`d7-node-actions`（confirm/skip）额外校验（Finding 3）**：`record_d7_action` 也接收 `fmea_id` 并落库，必须 fetch 目标 FMEA，校验：存在（None → 404）、与 CAPA 同工厂（`check_factory_access(fmea.factory_id, scope)` → 跨工厂 403）、用户对该 FMEA 有 VIEW 权限（`Module.FMEA` ≥ VIEW → 403）。防止记录"对不存在 / 跨工厂 FMEA 节点的动作"。

**`d7-auto-fill` 额外校验**：需 FMEA EDIT 权限（`Module.FMEA` ≥ EDIT，因为后端要改 FMEA graph_data）；`capa.d5_correction` 为空 → 400 "D5 永久措施为空，无法自动回填"；目标 FMEA 必须与 CAPA 同工厂（`check_factory_access(fmea.factory_id, scope)`）。

**PATCH 归属安全（Finding 3）**：`update_verification` 在服务层用 `verification_id=vid AND capa_id=capa.report_id AND factory_id=capa.factory_id` 联合查询，不匹配返回 None → API 404。前端无法用"有权限的 CAPA A 的 URL"改"CAPA B / 别的工厂"的验证记录。`create` / `list` / `d7-node-actions` 的 `list` 同样始终带 `capa_id + factory_id` 过滤，绝不裸按 `verification_id` / `action_id` 查。

### Schemas（`backend/app/schemas/capa_verification.py` 新建）

```python
class AdoptRequest(BaseModel):
    d_step: Literal["d4", "d5"]             # D7 不走采纳端点（见决策 2）
    adopted_text: str
    source: str                              # match_source 值，见下方"source/item_ref 映射"
    item_ref: dict | None = None
    # stage_index 不进 Spec A 请求——模型列已建为可空，Spec B 编排器上线后
    # 扩展本 schema 加 stage_index 字段 + 服务层透传（单点改动）

class AdoptResponse(BaseModel):
    adoption_id: UUID
    d_step: str
    field_value: str                  # 落库后 d-step 字段值回显

class VerificationCreate(BaseModel):
    root_cause_text: str
    method: str | None = None
    result: str | None = None
    is_verified: bool = False
    evidence_attachments: list[dict] = []
    source_ref: dict | None = None

class VerificationUpdate(BaseModel):
    method: str | None = None
    result: str | None = None
    is_verified: bool | None = None
    evidence_attachments: list[dict] | None = None

class VerificationResponse(BaseModel):
    verification_id: UUID
    capa_id: UUID
    root_cause_text: str
    method: str | None
    result: str | None
    is_verified: bool
    evidence_attachments: list[dict]
    source_ref: dict | None
    verified_by: UUID | None
    verified_at: datetime | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class D7NodeActionCreate(BaseModel):
    action: Literal["confirmed", "skipped"]
    fmea_id: UUID
    failure_mode_node_id: str
    failure_cause_node_id: str | None = None
    match_source: str                       # "linked"|"keyword"
    reason: str | None = None               # skip 原因

class D7AutoFillRequest(BaseModel):
    fmea_id: UUID
    failure_mode_node_id: str
    failure_cause_node_id: str              # auto-fill 必须有 cause 节点
    match_source: str

class D7AutoFillResponse(BaseModel):
    action_id: UUID
    prevention_control_node_id: str         # 命中/新建的控制节点 id
    prevention_control_name_after: str      # = capa.d5_correction
    is_new_control: bool                    # 新建 vs 更新既有

class D7NodeActionResponse(BaseModel):
    action_id: UUID
    capa_id: UUID
    action: str
    fmea_id: UUID
    failure_mode_node_id: str
    failure_cause_node_id: str | None
    match_source: str
    prevention_control_node_id: str | None
    prevention_control_name_before: str | None
    prevention_control_name_after: str | None
    reason: str | None
    acted_by: UUID
    acted_at: datetime
    model_config = ConfigDict(from_attributes=True)
```

## 服务层

### `backend/app/services/capa_verification_service.py`（新建）

```python
FIELD_MAP = {"d4": "d4_root_cause", "d5": "d5_correction"}   # D7 不走采纳（见决策 2）

async def adopt_recommendation(db, capa, req: AdoptRequest, user) -> tuple[CapaAIAdoption, str]:
    field = FIELD_MAP[req.d_step]
    current = getattr(capa, field) or ""
    new_value = f"{current}\n{req.adopted_text}" if current else req.adopted_text  # 追加，与现有 onAdopt 一致
    setattr(capa, field, new_value)
    adoption = CapaAIAdoption(capa_id=capa.report_id, factory_id=capa.factory_id,
                              d_step=req.d_step, adopted_text=req.adopted_text,
                              source=req.source, stage_index=None,  # 现阶段硬 None
                              item_ref=req.item_ref, adopted_by=user.user_id)
    db.add(adoption)
    db.add(AuditLog(table_name="capa_eightd", record_id=capa.report_id,
                    action="ADOPT_RECOMMENDATION",
                    changed_fields={"d_step": req.d_step, "source": req.source,
                                    "stage_index": None, "adopted_text": req.adopted_text,
                                    "item_ref": req.item_ref},
                    operated_by=user.user_id))
    if field in capa_service.EMBEDDING_FIELDS:                  # d4/d5 在集合内（d2/d7 同）
        await enqueue_embedding(db, "capa", capa.report_id, capa.product_line_code, capa.factory_id)
    await db.commit(); await db.refresh(adoption)
    return adoption, new_value   # handler 用 new_value 组装 AdoptResponse.field_value（Finding 2）

async def create_verification(db, capa, req: VerificationCreate, user) -> CapaRootCauseVerification:
    rec = CapaRootCauseVerification(capa_id=capa.report_id, factory_id=capa.factory_id,
                                    root_cause_text=req.root_cause_text, method=req.method,
                                    result=req.result, is_verified=req.is_verified,
                                    evidence_attachments=req.evidence_attachments,
                                    source_ref=req.source_ref,
                                    verified_by=user.user_id if req.is_verified else None,
                                    verified_at=func.now() if req.is_verified else None)
    db.add(rec)
    db.add(AuditLog(..., action="ROOT_CAUSE_VERIFICATION",
                    changed_fields={"verification_id": ..., "is_verified": req.is_verified,
                                    "root_cause_text": req.root_cause_text, "source_ref": req.source_ref}, ...))
    await db.commit(); await db.refresh(rec)
    return rec

async def list_verifications(db, capa) -> list[CapaRootCauseVerification]:
    # WHERE capa_id=capa.report_id AND factory_id=capa.factory_id ORDER BY created_at DESC
    ...

async def update_verification(db, capa, vid, req: VerificationUpdate, user) -> CapaRootCauseVerification:
    # 联合归属过滤：verification_id=vid AND capa_id=capa.report_id AND factory_id=capa.factory_id
    # 不匹配 → None → API 404（防止用可访问 CAPA 的 URL 改另一条 CAPA/工厂的记录，见 Finding 3）
    rec = await db.scalar(select(CapaRootCauseVerification).where(
        CapaRootCauseVerification.verification_id == vid,
        CapaRootCauseVerification.capa_id == capa.report_id,
        CapaRootCauseVerification.factory_id == capa.factory_id))
    if rec is None:
        raise LookupError("verification not found")  # → API 404
    # 应用非 None 字段；is_verified 翻转时同步 verified_by/verified_at（见 Finding 4）：
    if req.is_verified is not None and req.is_verified != rec.is_verified:
        if req.is_verified:                       # false→true
            rec.is_verified = True
            rec.verified_by = user.user_id
            rec.verified_at = func.now()
        else:                                     # true→false
            rec.is_verified = False
            rec.verified_by = None
            rec.verified_at = None
    if req.method is not None: rec.method = req.method
    if req.result is not None: rec.result = req.result
    if req.evidence_attachments is not None: rec.evidence_attachments = req.evidence_attachments
    db.add(AuditLog(..., action="ROOT_CAUSE_VERIFICATION",
                    changed_fields={"verification_id": vid, "is_verified": rec.is_verified,
                                    "method": req.method, "result": req.result}, ...))
    await db.commit(); await db.refresh(rec)
    return rec
```

### source / item_ref 映射（Finding 5）

`AdoptRequest.source` 必填，但当前 `RecommendationCandidate.to_d5_suggestion_schema`（`recommendation_types.py:69`）仅对 `historical_capa` 设 `match_source`，其他 D5 general suggestion 缺失 → 前端发不出合法 `source`。Spec A 顺带修：让 `to_d5_suggestion_schema` **始终**输出 `match_source`（镜像 `to_d4_schema` 的模式），并按下表给前端 `item_ref`：

| 推荐类型 | 内部 `source` | 外部 `match_source` | `item_ref` |
|---|---|---|---|
| D4 根因 | `fmea_graph` | `fmea_graph` | `{failure_cause_node_id, fmea_id, failure_mode_node_id}` |
| D4 根因 | `semantic_search` | `semantic_search` | `{failure_cause_node_id, fmea_id}` |
| D4 根因 | `historical_capa` | `historical_capa` | `{historical_capa_id, document_no}` |
| D4 根因 | `rule_engine` | `rule` | `{}` |
| D5 existing_control | `fmea_graph` | `fmea_graph` | `{control_node_id, failure_cause_node_id, fmea_id}` |
| D5 general_suggestion | `rule_engine_measure` | `rule` | `{}` |
| D5 general_suggestion | `historical_capa` | `historical_capa` | `{historical_capa_id, document_no}` |
| D5 general_suggestion | `semantic_search` | `semantic_search` | `{failure_cause_node_id, fmea_id}`（若有节点引用） |
| D4/D5 LLM 融合 | `llm` | `llm` | `{}` |

`to_d5_suggestion_schema` 修改（`recommendation_types.py:69`）：

```python
def to_d5_suggestion_schema(self) -> dict[str, Any]:
    result = {
        "content": self.content,
        "category": self.category or "预防措施",
        "basis": self.metadata.get("basis", ""),
        "confidence": round(self.confidence, 2),
        "match_reason": self.match_reason,
        "match_source": "rule" if self.source == "rule_engine_measure" else self.source,  # 始终输出
    }
    if self.source == "historical_capa":
        result["source_capa_id"] = self.metadata.get("historical_capa_id")
        result["source_capa_document_no"] = self.metadata.get("document_no")
    return result
```

前端 D4/D5 两处 RecPanel 采纳按钮按下表填 `source` + `item_ref`（D7 不在列）：

| 端点 d_step | 来源字段 | source 取值 | item_ref 取值 |
|---|---|---|---|
| d4 (D4RecPanel) | `item.match_source` | 同上表 | 从 `item` 取 `failure_cause_node_id`/`fmea_id` 等拼 dict |
| d5 existing_control (D5RecPanel) | `item.match_source` | 同上表 | 从 `item` 取 `control_node_id`/`failure_cause_node_id`/`fmea_id` |
| d5 general_suggestion (D5RecPanel) | `item.match_source` | 同上表（修复后必有） | 从 `item` 取可用节点引用，无则 `{}` |

- `ROOT_CAUSE_VERIFICATION` audit action 新增；`ADOPT_RECOMMENDATION` audit action 新增。两者沿用 ADR-0004 手写 AuditLog 模式。
- `stage_index` 在 `adopt_recommendation` 里现阶段硬写 `None`——`AdoptRequest` 不含该字段。待 P0-2 编排器落地后扩展 `AdoptRequest` 加 `stage_index` + 服务层透传（单点改动，plan 里标注 TODO）。

### `backend/app/services/capa_d7_action_service.py`（新建，决策 6/9）

```python
import copy
from sqlalchemy import select
from app.models.fmea import FMEADocument
from app.models.capa import CapaD7NodeAction
from app.models.audit import AuditLog
from app.services import fmea_service

NODE_KEY = lambda r: (r.capa_id, r.fmea_id, r.failure_mode_node_id, r.failure_cause_node_id or "")

async def _fetch_fmea_for_d7(db, capa, fmea_id) -> FMEADocument:
    """confirm/skip/auto-fill 共用：校验目标 FMEA 存在 + 同工厂（Finding 3）。FMEA VIEW/EDIT 权限在 handler 层查。"""
    fmea = await db.get(FMEADocument, fmea_id)
    if fmea is None:
        raise LookupError("目标 FMEA 不存在")  # → 404
    if fmea.factory_id != capa.factory_id:
        raise PermissionError("目标 FMEA 跨工厂")  # → 403
    return fmea

async def record_d7_action(db, capa, req: D7NodeActionCreate, user) -> CapaD7NodeAction:
    # Finding 3：fetch + 校验目标 FMEA 归属（FMEA VIEW 权限在 handler 层查）
    await _fetch_fmea_for_d7(db, capa, req.fmea_id)
    existing = await db.scalar(select(CapaD7NodeAction).where(
        CapaD7NodeAction.capa_id == capa.report_id,
        CapaD7NodeAction.fmea_id == req.fmea_id,
        CapaD7NodeAction.failure_mode_node_id == req.failure_mode_node_id,
        CapaD7NodeAction.failure_cause_node_id == req.failure_cause_node_id))
    if existing is not None:
        if existing.action == "auto_filled":
            raise ValueError("已自动回填，不可改判")  # → 400
        old_action = existing.action
        existing.action = req.action
        existing.reason = req.reason
        existing.acted_by = user.user_id
        existing.acted_at = func.now()
        db.add(AuditLog(table_name="capa_eightd", record_id=capa.report_id,
                        action="D7_NODE_ACTION_CHANGED",
                        changed_fields={"fmea_id": str(req.fmea_id),
                                        "failure_mode_node_id": req.failure_mode_node_id,
                                        "failure_cause_node_id": req.failure_cause_node_id,
                                        "old_action": old_action, "new_action": req.action},
                        operated_by=user.user_id))
        await db.commit(); await db.refresh(existing)
        return existing
    rec = CapaD7NodeAction(capa_id=capa.report_id, factory_id=capa.factory_id,
                           action=req.action, fmea_id=req.fmea_id,
                           failure_mode_node_id=req.failure_mode_node_id,
                           failure_cause_node_id=req.failure_cause_node_id,
                           match_source=req.match_source, reason=req.reason,
                           acted_by=user.user_id)
    db.add(rec)
    db.add(AuditLog(table_name="capa_eightd", record_id=capa.report_id,
                    action=f"D7_NODE_{req.action.upper()}",  # D7_NODE_CONFIRMED / D7_NODE_SKIPPED
                    changed_fields={"fmea_id": str(req.fmea_id),
                                    "failure_mode_node_id": req.failure_mode_node_id,
                                    "failure_cause_node_id": req.failure_cause_node_id,
                                    "match_source": req.match_source, "reason": req.reason},
                    operated_by=user.user_id))
    await db.commit(); await db.refresh(rec)
    return rec

async def list_d7_actions(db, capa) -> list[CapaD7NodeAction]:
    # WHERE capa_id=capa.report_id AND factory_id=capa.factory_id ORDER BY acted_at DESC
    ...

async def auto_fill_d7(db, capa, req: D7AutoFillRequest, user) -> tuple[CapaD7NodeAction, dict]:
    if not capa.d5_correction:
        raise ValueError("D5 永久措施为空，无法自动回填")  # → 400
    fmea = await _fetch_fmea_for_d7(db, capa, req.fmea_id)  # Finding 3
    # Finding 1：deepcopy graph 再改，避免原地改 JSONB 不被 SQLAlchemy 持久化
    graph = copy.deepcopy(fmea.graph_data or {"nodes": [], "edges": []})
    ctrl_node = None; name_before = None
    for e in graph["edges"]:
        if e["source"] == req.failure_cause_node_id and e["type"] == "PREVENTED_BY":
            for n in graph["nodes"]:
                if n["id"] == e["target"] and n["type"] == "PreventionControl":
                    ctrl_node = n; name_before = n.get("name"); break
    is_new = ctrl_node is None
    if is_new:
        ctrl_id = str(uuid.uuid4())
        graph["nodes"].append({"id": ctrl_id, "type": "PreventionControl",
                               "name": capa.d5_correction, "severity": 1, "occurrence": 1, "detection": 1})
        graph["edges"].append({"source": req.failure_cause_node_id, "target": ctrl_id, "type": "PREVENTED_BY"})
        ctrl_node = graph["nodes"][-1]
    else:
        ctrl_node["name"] = capa.d5_correction
    # Finding 2：调 fmea_service 无提交核心，复用 lock_version++/GraphSyncOutbox/缓存失效/embedding 全部副作用
    await fmea_service._apply_fmea_update(db, fmea, title=None, graph_data=graph,
                                           user_id=user.user_id)  # 不 commit
    # D7 节点动作 upsert（Finding 5）
    existing = await db.scalar(select(CapaD7NodeAction).where(
        CapaD7NodeAction.capa_id == capa.report_id,
        CapaD7NodeAction.fmea_id == req.fmea_id,
        CapaD7NodeAction.failure_mode_node_id == req.failure_mode_node_id,
        CapaD7NodeAction.failure_cause_node_id == req.failure_cause_node_id))
    if existing is not None:
        if existing.action == "auto_filled":
            raise LookupError("已自动回填")  # → 409 幂等拒绝
        old_action = existing.action
        existing.action = "auto_filled"
        existing.prevention_control_node_id = ctrl_node["id"]
        existing.prevention_control_name_before = name_before
        existing.prevention_control_name_after = capa.d5_correction
        existing.acted_by = user.user_id; existing.acted_at = func.now()
        rec = existing
        db.add(AuditLog(table_name="capa_eightd", record_id=capa.report_id,
                        action="D7_NODE_ACTION_CHANGED",
                        changed_fields={"old_action": old_action, "new_action": "auto_filled",
                                        "prevention_control_node_id": ctrl_node["id"]},
                        operated_by=user.user_id))
    else:
        rec = CapaD7NodeAction(capa_id=capa.report_id, factory_id=capa.factory_id,
                               action="auto_filled", fmea_id=req.fmea_id,
                               failure_mode_node_id=req.failure_mode_node_id,
                               failure_cause_node_id=req.failure_cause_node_id,
                               match_source=req.match_source,
                               prevention_control_node_id=ctrl_node["id"],
                               prevention_control_name_before=name_before,
                               prevention_control_name_after=capa.d5_correction,
                               acted_by=user.user_id)
        db.add(rec)
    db.add(AuditLog(table_name="capa_eightd", record_id=capa.report_id,
                    action="D7_AUTO_FILLED_FMEA",
                    changed_fields={"fmea_id": str(req.fmea_id),
                                    "failure_cause_node_id": req.failure_cause_node_id,
                                    "prevention_control_node_id": ctrl_node["id"],
                                    "name_before": name_before, "name_after": capa.d5_correction},
                    operated_by=user.user_id))
    await db.commit(); await db.refresh(rec)  # 单事务：FMEA 副作用 + D7 动作 + 两 audits 原子
    return rec, {"prevention_control_node_id": ctrl_node["id"],
                 "prevention_control_name_after": capa.d5_correction, "is_new_control": is_new}
```

### `fmea_service` 重构（Finding 2）

`fmea_service.update_fmea`（`fmea_service.py:196`）当前末尾 `await db.commit()`（L276）独立提交，且包含 FOR UPDATE 行锁 + `lock_version += 1` + `GraphSyncOutbox` + 推荐缓存失效 + `enqueue_embedding` 等副作用。Spec A 把它拆为：

- `_apply_fmea_update(db, fmea, title, graph_data, user_id, product_line_code=None, lock_version=None, confirmed_latest_lock_version=None) -> FMEADocument`：**不 commit、不 refresh**，保留 L206-275 全部副作用（行锁 / 乐观锁校验 / 变更检测 / `lock_version++` / FMEA UPDATE audit / `GraphSyncOutbox` / 缓存失效 / `enqueue_embedding`）。`graph_data` 由调用方传**新对象**（auto_fill_d7 已 deepcopy），`fmea.graph_data = graph_data` 重赋值确保持久化（Finding 1）。
- `update_fmea(...)` 改为 `fmea = await _apply_fmea_update(...); await db.commit(); await db.refresh(fmea); return fmea`——公开行为不变，既有调用方与测试零改动。

`auto_fill_d7` 调 `_apply_fmea_update`（不 commit）后追加 D7 动作 + audits，再单 `commit`，保证"FMEA 全部副作用 + D7 写入"原子。

- 新增 AuditLog action：`D7_NODE_CONFIRMED` / `D7_NODE_SKIPPED` / `D7_NODE_ACTION_CHANGED` / `D7_AUTO_FILLED_FMEA`（沿用 ADR-0004 手写模式）。

### `capa_service.advance_capa` 闸口改动（`backend/app/services/capa_service.py:257`）

在 `old_status = capa.status` 之前插入：

```python
if current == EightDState.D4_ROOT_CAUSE and next_state == EightDState.D5_CORRECTION:
    cnt = await db.scalar(select(func.count()).select_from(CapaRootCauseVerification)
        .where(CapaRootCauseVerification.capa_id == capa.report_id)
        .where(CapaRootCauseVerification.is_verified == True))
    if cnt < 1:
        raise ValueError("D4→D5 需至少 1 条已验证根因记录")
```

校验在事务内、写 TRANSITION audit 之前；不通过抛 `ValueError`，API 层 `advance_capa` handler 已有 `except ValueError → 400`。

## 前端

### 采纳按钮改调端点（`D4RecPanel.tsx` / `D5RecPanel.tsx`）

- D4/D5 RecPanel 删除 `onAdopt: (text) => void` props，改为 `onAdopted?: () => void`（刷新回调）+ `beforeAdopt?: () => Promise<void>`（flush 回调，见下）。
- 采纳按钮 `onClick`：①`await beforeAdopt?.()`（父组件 flush 本地 d-step 字段，见 Finding 3）；②`await adoptRecommendation(capaId, {d_step, adopted_text, source, item_ref})`（`source`/`item_ref` 按映射表填）；③成功 `message.success` + `onAdopted?.()` 拉最新 CAPA 回显。
- `CAPADetailPage.tsx:501,527` 的 `onAdopt` 回调删除，改为传：
  ```tsx
  beforeAdopt={async () => { if (localData.d4_root_cause !== capa.d4_root_cause)
                                await handleUpdate("d4_root_cause", localData.d4_root_cause); }}
  onAdopted={() => refreshCapa()}
  ```
  （`handleUpdate` 走现有 PUT flush；对比 `localData` vs `capa` 判断 dirty——`capa` 是上次 fetch 的快照。）
- `api/capa.ts` 新增 `adoptRecommendation(capaId, req): Promise<AdoptResponse>`。

### D7RecPanel 改造（决策 6/9）

- confirm/skip 按钮：从内存 `confirmedNodes` 改为调 `POST /api/capa/{report_id}/d7-node-actions`（upsert，可改判）；状态从 `GET /api/capa/{report_id}/d7-node-actions` 重载（修复刷新即丢的隐患）。`onConfirmationChange(allConfirmed, unconfirmedItems)` 改为从持久化动作派生。
- 已 `auto_filled` 的节点：confirm/skip 按钮禁用并显示"已自动回填"锁定态（后端已 400 拦截，前端先禁用避免误触）；auto-fill 按钮在已 `auto_filled` 时禁用（后端 409 幂等）。
- 自动回填按钮：删除 `handleAutoFill` 里的 `getFMEA` + 图改 + `updateFMEA`，改为调 `POST /api/capa/{report_id}/d7-auto-fill`，后端返回 `{prevention_control_node_id, prevention_control_name_after, is_new_control}`；成功后 `message.success` + 刷新推荐列表 + 重载 d7-node-actions。
- `api/capa.ts` 新增 `recordD7Action` / `listD7Actions` / `autoFillD7`。

### 新组件 `frontend/src/components/capa/D4VerificationCard.tsx`

放在 `CAPADetailPage` D4 区块、推荐面板下方：

- 列出该 CAPA 全部验证记录（`GET .../root-cause-verifications`），每条卡片显示根因/方法/结果/证据数/`is_verified` 徽标。
- 「+ 新增验证」表单：`root_cause_text`（默认填当前 `d4_root_cause`）、`method`、`result`、`is_verified`（Ant `Switch`）、`evidence_attachments`（Ant `Upload beforeUpload={false}` 捕 `{filename, size}` 进 state，不真实上传）。
- 单条记录可展开编辑（PATCH `is_verified` 等）。
- `api/capa.ts` 新增 `listVerifications` / `createVerification` / `updateVerification`。

### data-e2e 钩子（Spec A 仅埋采纳 + 验证元素；provenance tag 留 Spec B）

| 元素 | testid |
|---|---|
| D4 采纳按钮 | `d4-adopt` |
| D5 采纳按钮（existing_control / general_suggestion 各一） | `d5-adopt-control` / `d5-adopt-suggestion` |
| 验证卡 | `d4-verification-card` |
| 新增验证按钮 | `d4-verification-new` |
| 根因输入 | `verification-root-cause` |
| 方法/结果/证据 | `verification-method` / `verification-result` / `verification-evidence` |
| 验证状态开关 | `verification-is-verified` |
| 提交 | `verification-submit` |
| 验证记录项 | `verification-item-{n}`（内含 `verification-status`） |
| D7 确认按钮 | `d7-confirm` |
| D7 跳过按钮 | `d7-skip` |
| D7 自动回填按钮 | `d7-auto-fill` |
| D7 节点动作状态 | `d7-node-action-{n}`（内含 `d7-action-status`，`auto_filled` 时带 `locked`） |

## E2E / 测试兼容

### 现有 E2E 影响评估（已查证）

- `seed_e2e.py:119` 的 `8D-E2E-001` 未传 `status`，默认 `D1_TEAM`。
- `frontend/e2e/specs/m1-core/capa.spec.ts` 仅跑 D1→D2 冒烟（`PROGRESS.md` 记录 ~10% 覆盖）。
- → D4→D5 闸口在现有 E2E **不触发**，Spec A 对现有 E2E 安全，无需 fixture 回填。
- Spec C 故事 spec 才会越过 D4，届时由 Spec C 自建 `is_verified=true` 验证记录越过闸口。

### 后端 pytest（TDD，新建）

- `backend/tests/capa/test_capa_verification_service.py`：
  - `adopt_recommendation`：追加到 d-step 字段（已有 `current="A"` + adopt `"B"` → 字段为 `"A\nB"`；空字段 + adopt `"B"` → `"B"`），插 adoption + 写 ADOPT_RECOMMENDATION audit（assert 3 条落库）。**追加语义回归测试（Finding 1）**。
  - `adopt_recommendation`：`stage_index` 写 None（`AdoptRequest` 不含该字段）。
  - `adopt_recommendation` API：`d_step="d7"` 被 Pydantic `Literal["d4","d5"]` 拒绝 → 422（D7 不走采纳，Finding 2）。
  - `create_verification`：插记录 + ROOT_CAUSE_VERIFICATION audit；`is_verified=True` 时填 `verified_by/verified_at`，`False` 时两者为 None。
  - `list_verifications`：按 created_at desc、`capa_id + factory_id` 联合过滤。
  - `update_verification` 翻 `is_verified`：false→true 设 `verified_by=当前用户`、`verified_at=now()`；true→false 清空两者（Finding 4）。
  - `update_verification` **归属安全（Finding 3）**：用 CAPA A 的 `report_id` + CAPA B 的 `vid`（同工厂或跨工厂）→ 返回 None → API 404；不修改 CAPA B 的记录。
  - `advance_capa` D4→D5：无验证记录 → `ValueError`；有 ≥1 `is_verified=True` → 放行 + TRANSITION audit。
  - `factory_id` 隔离：跨工厂 list 验证记录为空。
- `backend/tests/capa/test_capa_api_verification.py`：4 端点权限矩阵（viewer 403 / engineer 200 / 跨工厂 403 / 404）。
- 现有 `backend/tests/capa/test_capa_*`：扫描任何 `advance_capa` 越过 D4 的用例，补"前置：创建已验证根因"fixture 保持绿（实施时 grep 确认，预期无需改——现有测试多停在 D2/D3 或用 mock 跳过状态机）。D7 既有 `D7_SKIP_CONFIRMATION`（`capa_service.py:302`，advance 时按 `d7_skip_reasons` 汇总写）保留不动——新 `D7_NODE_SKIPPED` 是点击时逐条写，二者并存（前者汇总、后者明细），不冲突。
- `backend/tests/recommendation/test_recommendation_types.py`（新增或既有）：`to_d5_suggestion_schema` 对 `rule_engine_measure` 输出 `match_source="rule"`、对 `historical_capa` 输出 `match_source="historical_capa"`（Finding 5 回归）。
- `backend/tests/capa/test_capa_d7_action_service.py`（新）：
  - `record_d7_action`：confirmed/skip 各插 `capa_d7_node_action` + 写 D7_NODE_CONFIRMED / D7_NODE_SKIPPED audit。
  - `record_d7_action` 改判（Finding 5）：confirmed→skip upsert 更新同一行 + D7_NODE_ACTION_CHANGED audit（带 old/new_action）；auto_filled 行 → ValueError。
  - `record_d7_action` FMEA 校验（Finding 3）：fmea_id 不存在 → LookupError(404)；跨工厂 FMEA → PermissionError(403)。
  - `list_d7_actions`：按 acted_at desc、`capa_id + factory_id` 联合过滤。
  - `auto_fill_d7`：d5_correction 空 → ValueError；目标 FMEA 跨工厂/不存在 → LookupError/PermissionError；既有控制 → `name_before` 捕获、`is_new_control=False`；无既有控制 → 新建节点+边、`is_new_control=True`。
  - `auto_fill_d7` 持久化（Finding 1）：commit 后**重新查询 FMEA**，断言 `graph_data` 已含新控制名（防原地改 JSONB 不持久化）；用 deepcopy 而非原对象引用。
  - `auto_fill_d7` FMEA 副作用（Finding 2）：断言 `fmea.lock_version` 递增、`GraphSyncOutbox` 有 `fmea.updated` 行、推荐缓存失效（或调用 spy）、`document_embeddings` enqueue——与 `update_fmea` 等价。
  - `auto_fill_d7` 原子性：四写（FMEA graph + FMEA UPDATE audit + capa_d7_node_action(auto_filled) + D7_AUTO_FILLED_FMEA audit）单 commit；中途模拟失败 → 全回滚。
  - `auto_fill_d7` 改判（Finding 5）：既有 confirmed 行 → 升级 auto_filled（图改 + 行更新 + D7_NODE_ACTION_CHANGED + D7_AUTO_FILLED_FMEA）；既有 auto_filled → LookupError(409)。
  - `factory_id` 隔离：跨工厂 list / auto-fill 拒绝。
- `backend/tests/fmea/test_fmea_service_update_core.py`（新或既有扩展）：`update_fmea` 公开行为不变（既有测试零改动）；`_apply_fmea_update` 不 commit，调用方可继续追加写入后单 commit。

### 前端 vitest（新建）

- `frontend/src/components/capa/D4VerificationCard.test.tsx`：表单提交调 `createVerification`、列表渲染、`is_verified` Switch PATCH `updateVerification`（false→true 后端填 verifier 前端回显）。
- `D4RecPanel.test.tsx`（既有）：更新——采纳按钮先 `await beforeAdopt()` 再调 `adoptRecommendation`（不再 `onAdopt` 回调）；`source`/`item_ref` 按映射表填。
- `D5RecPanel.test.tsx`（既有）：同上，existing_control 与 general_suggestion 两条采纳路径。
- `D7RecPanel.test.tsx`（既有，需改写）：confirm/skip 调 `recordD7Action`、状态从 `listD7Actions` 重载；auto-fill 调 `autoFillD7`（不再 `updateFMEA`）；`onConfirmationChange` 从持久化动作派生。

## 验收

- `capa_root_cause_verification` + `capa_ai_adoption` + `capa_d7_node_action` 三表通过 Alembic 迁移在干净库建出；`capa_d7_node_action` 的去重用 `COALESCE` 表达式唯一索引（R3-Finding 4）。
- 7 个新端点按权限矩阵工作；`advance_capa` D4→D5 闸口阻断/放行正确；PATCH 归属不匹配 → 404；`d7-auto-fill` 跨工厂 / d5 空 → 404/400；`d7-node-actions` 目标 FMEA 不存在/跨工厂 → 404/403（R3-Finding 3）。
- 采纳端点**追加**到 d-step 字段（不覆盖，保留已有内容）；单事务原子；服务层返回 `(adoption, new_value)`、handler 组装 `field_value`（R2-Finding 2）；D4/D5 RecPanel 采纳前 `await beforeAdopt()` flush 本地字段（R2-Finding 3）。
- `to_d5_suggestion_schema` 始终输出 `match_source`（R1-Finding 5）；前端 D4/D5 采纳按映射表填 `source`/`item_ref`。
- `update_verification` 翻 `is_verified` 时正确设/清 `verified_by`/`verified_at`（R1-Finding 4）。
- D7 confirm/skip/auto-fill 全部经新端点落 `capa_d7_node_action` + 对应 audit；**改判 upsert**（confirmed↔skip 更新同一行 + D7_NODE_ACTION_CHANGED audit；auto_filled 行锁定不可改判，前端禁用并显锁定态）（R3-Finding 5）。
- `auto_fill_d7` **deepcopy graph** 再改，commit 后重查 FMEA graph_data 已变化（持久化，R3-Finding 1）；通过 `_apply_fmea_update` 无提交核心**复用全部 FMEA 更新副作用**（lock_version++ / GraphSyncOutbox / 推荐缓存失效 / enqueue_embedding），且与 D7 写入单 commit 原子（R3-Finding 2）；`fmea_service.update_fmea` 公开行为不变、既有测试零改动。
- D7RecPanel 状态持久化（修复刷新即丢）；现有 `D7_SKIP_CONFIRMATION` 汇总审计保留不动。
- 后端新增 pytest 全绿（含 R1/R2/R3 全部 Finding 回归）；现有 capa/fmea 测试不退化；前端 vitest + `tsc --noEmit` + `npm run build` 绿；`make check` 绿。
- data-e2e 钩子就位（Spec C 故事 spec 可依赖）。
- `docs/` 同步：本 spec + `PROGRESS.md` 缺口清单 P0-1/P0-4 勾选；`CLAUDE.md` 无需改（无新命令/约定）。

## 参考

- 故事：`docs/user-stories/US-E2E-01-capa-8d-closed-loop.md`
- 缺口清单：`PROGRESS.md` §「US-E2E-01 8D 全程闭环 — 特性缺口清单」P0-1 / P0-4
- 现有代码：`backend/app/models/capa.py`、`backend/app/services/capa_service.py:257 advance_capa`、`backend/app/api/capa.py`、`frontend/src/components/capa/{D4,D5,D7}RecPanel.tsx`、`frontend/src/pages/capa/CAPADetailPage.tsx`
- 相关 ADR：ADR-0001（UUID v4）、ADR-0003（factory_id 行级隔离）、ADR-0004（手写 AuditLog）、ADR-0013（手写 Alembic）
- 后续 spec：Spec B（编排器 + DAG + provenance + SPC/IQC 源）、Spec C（故事级 E2E spec）
# US-E2E-01 8D 全程闭环 — Spec A：D4 现场根因验证 + AI 采纳审计

**状态**：设计稿（待评审）
**日期**：2026-07-03
**关联**：`docs/user-stories/US-E2E-01-capa-8d-closed-loop.md`（v6 定稿）、`PROGRESS.md` 特性缺口清单 P0-1 / P0-4
**分支**：`worktree-us-e2e-01-8d-closed-loop`（从 `fix/dashboard-admin-pages` head 切出）

## 背景与范围

US-E2E-01 故事要求 8D 全程闭环可审计：根因必须经现场验证才可确认（D4→D5 阻断），AI 推荐采纳 + 根因验证记录留痕含来源。`PROGRESS.md` 缺口审计识别出两个数据模型缺口：

- **P0-1 D4 现场根因验证子流程**：当前 `capa_eightd.d4_root_cause` 是单个 `Text` 列，无方法/结果/证据字段、无附件关联、无 D4→D5 阻断校验。
- **P0-4 AI 采纳审计留痕**：D4/D5/D7 推荐面板已有「采纳」按钮（`D4RecPanel.tsx:83` / `D5RecPanel.tsx:54,107` / `D7RecPanel`），但采纳只把文本写进 d-step 字段，未记录"采纳了哪条推荐、来自哪个源、什么时间"。

本 spec 是 B 路线三阶段分解的**第一阶段**，仅交付 P0-1 + P0-4 两个数据模型缺口。编排器、DAG 面板、provenance UI、SPC/IQC 新源属 Spec B；故事级 E2E spec 属 Spec C。三阶段依赖顺序：A → B → C。

### 不在本 spec 范围

- 12 阶段推荐编排器与 DAG 可视化面板（P0-2，Spec B）
- 推荐来源 provenance 标签 UI + testid（P0-3，Spec B；本 spec 仅埋采纳/验证元素的 testid）
- SPC / IQC / MES / 供货 / 同类型产品 / lessons 新推荐源（P1-5~10，Spec B）
- 故事级 E2E spec `capa-story-closed-loop.spec.ts`（P2-11，Spec C）
- `stage_index` 字段的实际填充——本 spec 仅建可空列，编排器上线后透传（见下"决策"）

## 关键决策（已与用户确认）

1. **stage_index 可空，P0-2 后补**：`capa_ai_adoption.stage_index` 建为可空列，现阶段写 `None`。P0-2 编排器上线后在推荐响应里返回 `stage_index`，前端采纳时回传，服务层透传——届时只改服务层一处。历史采纳记录不回填。Spec C 故事 spec 只断言 P0-2 后创建的采纳记录的 stage_index。

2. **采纳统一端点 + 落库 + 审计**：新增 `POST /api/capa/{report_id}/adopt-recommendation`，服务层一次事务内：①插 `capa_ai_adoption` 记录；②写 `ADOPT_RECOMMENDATION` AuditLog；③把 `adopted_text` **覆盖式**写到对应 d-step 字段（与现有 `onAdopt` 文本覆盖行为一致，非追加）。前端采纳按钮改调此端点，删除原 `onAdopt` 父组件回调。

3. **证据附件 = JSONB 元数据，不引入文件存储管道**：`capa_root_cause_verification.evidence_attachments` 用 JSONB list 存 `[{filename, size, content_ref}]`，沿用 `audit_finding.customer_confirmation_attachments` 惯例。前端用 Ant `Upload beforeUpload={false}` 捕获文件元数据，不真实上传。

4. **验证记录一对多、无 DELETE**：一个 CAPA 可有多条验证记录（对应多次候选根因尝试，故事 5.d「验证不通过 → 选另一条或新增根因，再次验证」）。不提供 DELETE——验证不通过的记录留作历史。

5. **D4→D5 闸口**：`advance_capa` 在 `D4_ROOT_CAUSE → D5_CORRECTION` 转换前校验 `count(is_verified=true) ≥ 1`，不通过抛 `ValueError` → API 400。

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
    d_step: Mapped[str] = mapped_column(String(8), nullable=False)        # "d4"|"d5"|"d7"
    adopted_text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)       # match_source 值
    stage_index: Mapped[int | None] = mapped_column(Integer, nullable=True)  # P0-2 后填
    item_ref: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    adopted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    adopted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # 索引：ix_capa_adopt_capa_step (capa_id, d_step), ix_capa_adopt_factory (factory_id)
```

### 迁移

`backend/alembic/versions/20260703_add_capa_verification_adoption.py`，`down_revision` 取当前 head（实施时确认），手写 `op.create_table` ×2 + 4 个索引，遵循 ADR-0013（UUID `as_uuid=True`）、ADR-0001（Python 端 `uuid4`）。`downgrade()` 反向 drop。

## API

新增 4 个端点，挂在现有 `backend/app/api/capa.py` 的 `router = APIRouter(prefix="/api/capa")`。

| 方法 | 路径 | 权限 | 作用 |
|---|---|---|---|
| POST | `/api/capa/{report_id}/adopt-recommendation` | CAPA EDIT | 采纳：插 adoption + ADOPT_RECOMMENDATION audit + 写 d-step 字段，单事务 |
| POST | `/api/capa/{report_id}/root-cause-verifications` | CAPA EDIT | 新建验证记录 + ROOT_CAUSE_VERIFICATION audit |
| GET | `/api/capa/{report_id}/root-cause-verifications` | CAPA VIEW | 列出该 CAPA 全部验证记录（按 created_at desc） |
| PATCH | `/api/capa/{report_id}/root-cause-verifications/{vid}` | CAPA EDIT | 更新（翻 is_verified、补 method/result/evidence）；写 audit |

每个端点 handler 模式（沿用 `api/capa.py` 现有 thin handler 写法）：
1. `level = await get_user_permission(scope.user, Module.CAPA, db)`；`< EDIT`（或 VIEW）→ 403
2. `capa = await capa_service.get_capa(db, report_id)`；None → 404
3. `check_factory_access(capa.factory_id, scope)` → 跨工厂 403
4. 调服务层；`ValueError` → 400

### Schemas（`backend/app/schemas/capa_verification.py` 新建）

```python
class AdoptRequest(BaseModel):
    d_step: Literal["d4", "d5", "d7"]
    adopted_text: str
    source: str
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
```

## 服务层

### `backend/app/services/capa_verification_service.py`（新建）

```python
FIELD_MAP = {"d4": "d4_root_cause", "d5": "d5_correction", "d7": "d7_prevention"}

async def adopt_recommendation(db, capa, req: AdoptRequest, user) -> CapaAIAdoption:
    field = FIELD_MAP[req.d_step]
    setattr(capa, field, req.adopted_text)                      # 覆盖式写 d-step
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
    if field in capa_service.EMBEDDING_FIELDS:                  # d2/d4/d5/d7
        await enqueue_embedding(db, "capa", capa.report_id, capa.product_line_code, capa.factory_id)
    await db.commit(); await db.refresh(adoption)
    return adoption

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

async def list_verifications(db, capa) -> list[CapaRootCauseVerification]: ...
async def update_verification(db, rec, req: VerificationUpdate, user) -> CapaRootCauseVerification: ...
```

- `ROOT_CAUSE_VERIFICATION` audit action 新增；`ADOPT_RECOMMENDATION` audit action 新增。两者沿用 ADR-0004 手写 AuditLog 模式。
- `stage_index` 在 `adopt_recommendation` 里现阶段硬写 `None`——`AdoptRequest` 不含该字段。待 P0-2 编排器落地后扩展 `AdoptRequest` 加 `stage_index` + 服务层透传（单点改动，plan 里标注 TODO）。

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

### 采纳按钮改调端点（`D4RecPanel.tsx` / `D5RecPanel.tsx` / `D7RecPanel.tsx`）

- 删除 `onAdopt: (text) => void` props，改为 `onAdopted?: () => void`（可选刷新回调）。
- 采纳按钮 `onClick` 内联 `await adoptRecommendation(capaId, {d_step, adopted_text, source, item_ref})`，成功 `message.success` + `onAdopted?.()`。
- `CAPADetailPage.tsx:501,527` 的 `onAdopt` 回调（写 PUT）删除，改为传 `onAdopted={() => refreshCapa()}` 拉最新 d-step 字段回显。
- `api/capa.ts` 新增 `adoptRecommendation(capaId, req): Promise<AdoptResponse>`。

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
| 验证卡 | `d4-verification-card` |
| 新增验证按钮 | `d4-verification-new` |
| 根因输入 | `verification-root-cause` |
| 方法/结果/证据 | `verification-method` / `verification-result` / `verification-evidence` |
| 验证状态开关 | `verification-is-verified` |
| 提交 | `verification-submit` |
| 验证记录项 | `verification-item-{n}`（内含 `verification-status`） |

## E2E / 测试兼容

### 现有 E2E 影响评估（已查证）

- `seed_e2e.py:119` 的 `8D-E2E-001` 未传 `status`，默认 `D1_TEAM`。
- `frontend/e2e/specs/m1-core/capa.spec.ts` 仅跑 D1→D2 冒烟（`PROGRESS.md` 记录 ~10% 覆盖）。
- → D4→D5 闸口在现有 E2E **不触发**，Spec A 对现有 E2E 安全，无需 fixture 回填。
- Spec C 故事 spec 才会越过 D4，届时由 Spec C 自建 `is_verified=true` 验证记录越过闸口。

### 后端 pytest（TDD，新建）

- `backend/tests/capa/test_capa_verification_service.py`：
  - `adopt_recommendation`：写 d-step 字段 + 插 adoption + 写 ADOPT_RECOMMENDATION audit（assert 3 条落库）。
  - `adopt_recommendation`：`stage_index` 写 None（即便 req 带也忽略）。
  - `create_verification`：插记录 + ROOT_CAUSE_VERIFICATION audit；`is_verified=True` 时填 `verified_by/verified_at`。
  - `list_verifications`：按 created_at desc、factory_id 隔离。
  - `update_verification`：翻 `is_verified` + audit。
  - `advance_capa` D4→D5：无验证记录 → `ValueError`；有 ≥1 `is_verified=True` → 放行 + TRANSITION audit。
  - `factory_id` 隔离：跨工厂读取验证记录为空。
- `backend/tests/capa/test_capa_api_verification.py`：4 端点权限矩阵（viewer 403 / engineer 200 / 跨工厂 403 / 404）。
- 现有 `backend/tests/capa/test_capa_*`：扫描任何 `advance_capa` 越过 D4 的用例，补"前置：创建已验证根因"fixture 保持绿（实施时 grep 确认，预期无需改——现有测试多停在 D2/D3 或用 mock 跳过状态机）。

### 前端 vitest（新建）

- `frontend/src/components/capa/D4VerificationCard.test.tsx`：表单提交调 `createVerification`、列表渲染、`is_verified` Switch PATCH `updateVerification`。
- `D4RecPanel.test.tsx`（既有）：更新——采纳按钮调 `adoptRecommendation` 而非 `onAdopt` 回调。

## 验收

- `capa_root_cause_verification` + `capa_ai_adoption` 两表通过 Alembic 迁移在干净库建出。
- 4 个新端点按权限矩阵工作；`advance_capa` D4→D5 闸口阻断/放行正确。
- 采纳按钮调端点落库 + 审计 + 写 d-step 字段，单事务原子；前端三处 RecPanel 不再走 `onAdopt` 回调。
- 后端新增 pytest 全绿；现有 capa 测试不退化；前端 vitest + `tsc --noEmit` + `npm run build` 绿；`make check` 绿。
- data-e2e 钩子就位（Spec C 故事 spec 可依赖）。
- `docs/` 同步：本 spec + `PROGRESS.md` 缺口清单 P0-1/P0-4 勾选；`CLAUDE.md` 无需改（无新命令/约定）。

## 参考

- 故事：`docs/user-stories/US-E2E-01-capa-8d-closed-loop.md`
- 缺口清单：`PROGRESS.md` §「US-E2E-01 8D 全程闭环 — 特性缺口清单」P0-1 / P0-4
- 现有代码：`backend/app/models/capa.py`、`backend/app/services/capa_service.py:257 advance_capa`、`backend/app/api/capa.py`、`frontend/src/components/capa/{D4,D5,D7}RecPanel.tsx`、`frontend/src/pages/capa/CAPADetailPage.tsx`
- 相关 ADR：ADR-0001（UUID v4）、ADR-0003（factory_id 行级隔离）、ADR-0004（手写 AuditLog）、ADR-0013（手写 Alembic）
- 后续 spec：Spec B（编排器 + DAG + provenance + SPC/IQC 源）、Spec C（故事级 E2E spec）
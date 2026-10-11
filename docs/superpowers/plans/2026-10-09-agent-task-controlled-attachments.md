# R4b-2 任务私有受控附件 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为目标绑定 AgentTask 提供默认关闭、租户隔离、实际 ClamAV 扫描门禁、受权下载与可恢复清理的私有附件基础。

**Architecture:** 附件元数据位于 tenant-local `agent_task_attachments`，文件只能在 backend 私有本地卷中暂存或 clean。上传先原子预留任务额度和全局 PostgreSQL advisory pipeline slot，再以低层 `python-multipart` 流式解析与 `clamd` newline `nINSTREAM` 扫描；仅经过 `scanning → promoting → available` 两阶段提升的对象可下载。跨文件系统/数据库崩溃由状态对账恢复，整代删除只能由平台层显式销毁记录授权。

**Tech Stack:** FastAPI 0.115 / Starlette 0.38.6、SQLAlchemy async 2.0、PostgreSQL 15 advisory locks、Alembic public + tenant migrations、已安装 `python-multipart`、ClamAV `clamd`、React 18 / TypeScript / Ant Design、Vitest、Playwright。

## Global Constraints

- 保持 `AGENT_TASK_RUNTIME_ENABLED=false` 与新 `AGENT_TASK_ATTACHMENTS_ENABLED=false` 默认关闭；关闭必须早于租户、认证、body、数据库和 scanner。
- 首片仅限私有本地卷与单一全局 pipeline slot；不添加 MinIO/S3、预签名 URL、对象存储抽象、文件预览、解析、OCR、embedding、搜索或插件/模型交付。
- 文件永远不接入 `CapaRootCauseVerification.evidence_attachments`，不成为 D4 验证证据、降敏结论或外发批准。
- 文件大小固定 20 MiB，multipart 总请求固定为 20 MiB + 64 KiB，单任务上限固定 5，上传总 deadline 120 秒，扫描 deadline 60 秒，保留期 168 小时。
- 允许扩展名仅 `.pdf`、`.png`、`.jpg`、`.jpeg`、`.txt`、`.csv`、`.docx`、`.xlsx`；下载永远 `application/octet-stream` + attachment + nosniff + no-store。
- ClamAV profile 固定 `StreamMaxLength`/`MaxFileSize`/`MaxScanSize=20M`、`MaxRecursion=10`、`MaxFiles=1000`、`MaxScanTime=60000`、`AlertExceedsMax=yes`、`AlertEncrypted=yes`、`MaxThreads=1`、`MaxQueue=1`。
- 附件创建时的 `origin_generation` 仅为存储代际与审计事实；普通维护、失败重试、暂停/停用后恢复不得使仍在保留期内的附件删除或永久不可读。
- 历史或未知 namespace 没有明确处置记录时只告警保留；整代清理仅接受精确的 `test_rebuild` 或 `tenant_destroyed` disposal record。
- 所有 CRUD/状态转换写最小 `AuditLog`，不记录文件内容、文件名、路径、storage key、恶意签名、原始 ClamAV 输出或自由异常文本。
- 不提交、暂存、push、merge、部署或启用用户环境，除非用户另行明确授权；本计划中的每个“检查点”取代 commit 步骤。
- 文档与代码同步更新；测试仅创建/清理本轮自有数据库、临时目录、Compose project、浏览器与进程资源。

---

## File Structure

| 文件 | 责任 |
|---|---|
| `backend/app/models/agent_task_attachment.py` | tenant-local 附件 ORM；状态/字段约束由 migration 保证 |
| `backend/app/models/tenant_attachment_disposal.py` | platform-local append-only 销毁授权 ORM |
| `backend/app/services/agent_runtime/attachment_storage.py` | 私有根校验、descriptor-relative I/O、staging/clean 原子移动与 digest 检查 |
| `backend/app/services/agent_runtime/clamav_scan.py` | 严格 newline `nVERSIONCOMMANDS`/`nINSTREAM` client 与固定扫描结论 |
| `backend/app/services/agent_runtime/task_attachments.py` | 授权、reservation、advisory slot、上传状态机、列表/下载/删除 |
| `backend/app/services/agent_runtime/attachment_recovery.py` | promoting/purging/scanning 对账、live orphan 和 disposal 处理 |
| `backend/app/api/agent_task_attachments.py` | 薄 HTTP 路由；早期受权后低层 streaming multipart 接线 |
| `backend/app/schemas/agent_attachment.py` | 严格 API 输出/availability DTO；不接收客户端归属或扫描字段 |
| `backend/app/cli/agent_task_attachments.py` | 受控 reconciliation/purge CLI，不暴露任意路径 |
| `docker/clamav/clamd.conf` | 受控 ClamAV 上限与 heuristic 拒绝配置 |
| `frontend/src/components/agent/AgentTaskAttachments.tsx` | 任务侧栏中的受限上传/状态/下载/删除区；无预览 |
| `frontend/src/api/agentTaskAttachments.ts` | 严格 response parser 与请求封装 |
| `frontend/src/types/agentAttachment.ts` | 附件 DTO/type 边界 |

## Task 1: 数据契约、双迁移链与默认关闭配置

**Files:**
- Create: `backend/app/models/agent_task_attachment.py`
- Create: `backend/app/models/tenant_attachment_disposal.py`
- Create: `backend/alembic/versions/20261009_agent_task_attachments.py`
- Create: `backend/alembic_tenant/versions/tv005_agent_task_attachments.py`
- Create: `backend/tests/migrations/test_agent_task_attachments_delta.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/config.py`
- Modify: `backend/alembic_tenant/__init__.py`
- Modify: `backend/alembic_tenant/snapshot/business_20260927.py`
- Modify: `backend/tests/migrations/test_tenant_schema_parity.py`
- Modify: `backend/tests/migrations/test_agent_task_core.py`

**Interfaces:**
- Produces `AgentTaskAttachment` with statuses `scanning|promoting|available|rejected_malware|rejected_scanner|failed_storage|purging|purged`.
- Produces `TenantAttachmentStorageDisposal` with exact unique `(tenant_id, origin_generation, storage_namespace)` and `reason in ('test_rebuild','tenant_destroyed')`.
- Produces strict settings `AGENT_TASK_ATTACHMENTS_ENABLED`, storage/scanner settings, all disabled/safe by default.

- [ ] **Step 1: Add migration RED tests.**

```python
async def test_agent_attachment_migrations_create_matching_tenant_tables(migrated_db):
    assert await has_table(migrated_db, "agent_task_attachments")
    assert await has_constraint(migrated_db, "agent_task_attachments", "ck_agent_task_attachment_status")
    assert await has_table(migrated_db, "tenant_attachment_storage_disposals", schema="public")

async def test_attachment_generation_pair_is_all_or_nothing(migrated_db):
    with pytest.raises(IntegrityError):
        await insert_attachment(tenant_id=uuid4(), origin_generation=None)
```

- [ ] **Step 2: Run the migration RED tests.**

Run: `cd backend && pytest tests/migrations/test_agent_task_attachments_delta.py -q`

Expected: FAIL because the migrations/models do not exist.

- [ ] **Step 3: Add models and public migration.**

Create public revision `20261009_agent_task_attachments` with `down_revision="20261001_agent_readonly_controls"`. Create `agent_task_attachments` with FK to `agent_tasks`, `factory_id`, `uploaded_by`, nullable `tenant_id`/`origin_generation` paired by check constraint, server-owned `storage_namespace` and `storage_key`, nullable pre-header fields, enum-like status checks, nonnegative size check, and indexes on `(task_id, status)` and `(expires_at, status)`. Create platform `tenant_attachment_storage_disposals` with no cross-schema FK and its precise uniqueness/check constraints.

- [ ] **Step 4: Add tenant migration and parity updates.**

Create `tv005_agent_task_attachments` with `down_revision="tv004_agent_readonly_controls"`; it creates only the tenant-local attachment table. Keep the frozen `tv001_business_snapshot` DDL and `business_20260927.py` unchanged: it is the irreversible baseline and already runs before every delta. Update `REVIEWED_REVISIONS`, the tenant head constants, and tv001→tv005 migration/parity tests so fresh tenant migration proves the final schema without duplicate table creation. Do not put the platform disposal table in the tenant snapshot.

- [ ] **Step 5: Add configuration/model imports.**

Add settings with defaults exactly matching Global Constraints and bounded validators. Import both models where Alembic metadata discovery requires them. Do not create storage or connect to ClamAV when the feature is disabled.

- [ ] **Step 6: Run GREEN migration/parity tests.**

Run: `cd backend && pytest tests/migrations/test_agent_task_attachments_delta.py tests/migrations/test_tenant_schema_parity.py tests/migrations/test_agent_task_core.py -q`

Expected: PASS; fresh public and tenant chains agree, invalid generation pairs and invalid statuses are rejected.

- [ ] **Step 7: Checkpoint.**

Record migration names, public/tenant heads, and test output in the execution ledger; do not commit.

## Task 2: Private storage and strict ClamAV protocol units

**Files:**
- Create: `backend/app/services/agent_runtime/attachment_storage.py`
- Create: `backend/app/services/agent_runtime/clamav_scan.py`
- Create: `backend/tests/services/agent_runtime/test_attachment_storage.py`
- Create: `backend/tests/services/agent_runtime/test_clamav_scan.py`
- Modify: `backend/app/services/agent_runtime/README.md`

**Interfaces:**

```python
@dataclass(frozen=True)
class AttachmentNamespace:
    tenant_id: UUID | None
    origin_generation: int | None
    storage_namespace: str

@dataclass(frozen=True)
class ScanResult:
    outcome: Literal["clean", "found", "unavailable"]
    scanner_version: str | None
    failure_code: str | None

class PrivateAttachmentStorage:
    def __init__(self, root: Path) -> None: ...
    def validate_root(self) -> None: ...
    def create_staging(self, namespace: AttachmentNamespace, attachment_id: UUID) -> BinaryIO: ...
    def promote(self, namespace: AttachmentNamespace, attachment_id: UUID, expected_sha256: str, expected_size: int) -> None: ...
    def open_clean(self, namespace: AttachmentNamespace, attachment_id: UUID, expected_sha256: str, expected_size: int) -> BinaryIO: ...
    def remove(self, namespace: AttachmentNamespace, attachment_id: UUID, area: Literal["staging", "clean"]) -> None: ...

async def scan_stream(reader: AsyncIterator[bytes], *, host: str, port: int, timeout_seconds: int) -> ScanResult: ...
```

- [ ] **Step 1: Write storage RED tests.**

```python
def test_storage_rejects_symlink_root_and_filename_paths(tmp_path):
    root = tmp_path / "root"; root.symlink_to(tmp_path)
    with pytest.raises(ValueError):
        PrivateAttachmentStorage(root).validate_root()

def test_promote_requires_exact_size_and_digest(tmp_path):
    storage = private_storage(tmp_path)
    handle = storage.create_staging(public_namespace(), attachment_id)
    handle.write(b"clean"); handle.close()
    with pytest.raises(AttachmentIntegrityError):
        storage.promote(public_namespace(), attachment_id, "0" * 64, 5)
```

- [ ] **Step 2: Write ClamAV framing RED tests with a strict local TCP fixture.**

```python
async def test_scan_stream_sends_zinstream_and_zero_terminator(strict_clamd):
    result = await scan_stream(chunks([b"abc"]), **strict_clamd.address)
    assert result.outcome == "clean"
    assert strict_clamd.frames == [b"abc", b""]

@pytest.mark.parametrize("reply", [b"stream: Heuristics.Limits.Exceeded FOUND\0", b"stream: Encrypted.Doc FOUND\0"])
async def test_scan_stream_rejects_all_found_replies(strict_clamd, reply):
    strict_clamd.reply = reply
    assert (await scan_stream(chunks([b"x"]), **strict_clamd.address)).outcome == "found"
```

- [ ] **Step 3: Run unit RED tests.**

Run: `cd backend && pytest tests/services/agent_runtime/test_attachment_storage.py tests/services/agent_runtime/test_clamav_scan.py -q`

Expected: FAIL because storage and scanner services are absent.

- [ ] **Step 4: Implement descriptor-safe storage.**

Use only server-generated UUID path components below a validated `0700` root; create staging with `0600`, reject symlinks, keep digest/size caller-provided and verify them before same-filesystem atomic promotion. `open_clean` must re-verify the metadata before returning a file descriptor. Never accept a filename, path, tenant identity, or storage key from HTTP.

- [ ] **Step 5: Implement strict ClamAV client.**

Open one bounded TCP connection for newline `nVERSIONCOMMANDS\n`, validate the version/capability response, close it, then open a fresh bounded connection for `nINSTREAM\n`. Send 4-byte big-endian lengths and a zero-length terminator, enforce 60 seconds on the whole exchange, and accept only strict single-result `OK`, `FOUND`, or `ERROR`. Map every `FOUND` to `found`, every malformed/error/timeout/connection error to `unavailable`; do not expose daemon text.

- [ ] **Step 6: Run GREEN units and focused regression.**

Run: `cd backend && pytest tests/services/agent_runtime/test_attachment_storage.py tests/services/agent_runtime/test_clamav_scan.py tests/services/agent_runtime/test_task_service.py -q`

Expected: PASS; existing task authority is unchanged.

- [ ] **Step 7: Checkpoint.**

Confirm no storage helper can return a static path or a client-derived path; do not commit.

## Task 3: Reservation, authorization, state machine, download and deletion service

**Files:**
- Create: `backend/app/services/agent_runtime/task_attachments.py`
- Create: `backend/tests/services/agent_runtime/test_task_attachments.py`
- Modify: `backend/app/services/agent_runtime/task_service.py`
- Modify: `backend/app/services/agent_runtime/task_updates.py`

**Interfaces:**

```python
async def reserve_upload(db: AsyncSession, scope: RequestScope, task_id: UUID) -> ReservedAttachment: ...
async def receive_and_scan(reservation: ReservedAttachment, chunks: AsyncIterator[bytes]) -> AttachmentView: ...
async def list_for_view(db: AsyncSession, scope: RequestScope, task_id: UUID) -> list[AttachmentView]: ...
async def open_download(db: AsyncSession, scope: RequestScope, task_id: UUID, attachment_id: UUID) -> DownloadHandle: ...
async def purge_for_owner(db: AsyncSession, scope: RequestScope, task_id: UUID, attachment_id: UUID) -> None: ...
```

- [ ] **Step 1: Write reservation/concurrency RED tests.**

```python
async def test_sixth_concurrent_reservation_is_rejected(owned_task, five_reservations):
    with pytest.raises(AttachmentCapacityError):
        await reserve_upload(owned_task.db, owned_task.scope, owned_task.task_id)

async def test_reservation_counts_scanning_promoting_and_available(owned_task):
    await seed_statuses(owned_task, ["scanning", "promoting", "available", "available", "available"])
    with pytest.raises(AttachmentCapacityError):
        await reserve_upload(owned_task.db, owned_task.scope, owned_task.task_id)

async def test_revocation_before_promotion_leaves_no_downloadable_blob(owned_task, revoke_capa_view):
    reservation = await reserve_upload(owned_task.db, owned_task.scope, owned_task.task_id)
    revoke_capa_view()
    with pytest.raises(AttachmentSourceChanged):
        await receive_and_scan(reservation, chunks([b"clean"]))
```

- [ ] **Step 2: Write state/download/delete RED tests.**

```python
async def test_only_available_attachment_can_open_download(owned_task):
    attachment = await seed_attachment(owned_task, status="rejected_malware")
    with pytest.raises(LookupError):
        await open_download(owned_task.db, owned_task.scope, owned_task.task_id, attachment.attachment_id)

async def test_delete_commits_purging_before_physical_delete(owned_task, storage_spy):
    attachment = await seed_attachment(owned_task, status="available")
    await purge_for_owner(owned_task.db, owned_task.scope, owned_task.task_id, attachment.attachment_id)
    assert storage_spy.states == ["purging", "purged"]
```

- [ ] **Step 3: Run service RED tests.**

Run: `cd backend && pytest tests/services/agent_runtime/test_task_attachments.py -q`

Expected: FAIL because reservation and attachment services do not exist.

- [ ] **Step 4: Implement the bounded state machine.**

Reuse `get_task_for_view` for all user operations. Under `AgentTask ... FOR UPDATE`, count only `scanning/promoting/available`, insert a 180-second `scanning` reservation, and commit before reading body. Enforce task status `ready|paused`. Use one dedicated session advisory lock acquired before the reservation; explicit `finally` release/invalidate behavior must follow the established `maintenance_connection` lock-safety pattern. The slot covers body receipt through terminal transition.

- [ ] **Step 5: Implement completion and safe response data.**

For clean scans: recheck captured request binding/current task/CAPA authorization, persist scan metadata with `scanning → promoting`, promote storage, then commit `promoting → available`. For `FOUND`, scanner failure, stream limit, cancellation, or I/O failure: remove staging, transition to the fixed terminal status, audit the fixed code, and release quota. Return only attachment ID, sanitized name, size, status, timestamps, and expiration.

- [ ] **Step 6: Implement list, direct download, and delete.**

List only records authorized by the same task check. Download requires `available`, unexpired metadata and successful storage re-verification; stream from an already-open descriptor with `Content-Disposition: attachment`, `application/octet-stream`, `nosniff`, and `no-store`. Delete transitions `available → purging → purged`; do not hard-delete rows. Add minimal audit actions for reserve/result/download/delete without file names or scanner output.

- [ ] **Step 7: Run GREEN services and existing runtime regressions.**

Run: `cd backend && pytest tests/services/agent_runtime/test_task_attachments.py tests/services/agent_runtime/test_task_service.py tests/services/agent_runtime/test_task_updates.py tests/services/agent_runtime/test_message_queue.py -q`

Expected: PASS; no attachment is emitted through message, result, checkpoint, or plugin paths.

- [ ] **Step 8: Checkpoint.**

Inspect audit payload fixtures for forbidden filename/content/path/signature strings; do not commit.

## Task 4: Recovery, tenant lifecycle and explicit disposal authority

**Files:**
- Create: `backend/app/services/agent_runtime/attachment_recovery.py`
- Create: `backend/app/cli/agent_task_attachments.py`
- Create: `backend/tests/services/agent_runtime/test_attachment_recovery.py`
- Modify: `backend/app/services/tenant_test_rebuild.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_multitenancy/test_test_tenant_rebuild.py`

**Interfaces:**

```python
async def reconcile_live_namespace(db: AsyncSession, namespace: AttachmentNamespace, storage: PrivateAttachmentStorage, *, now: datetime) -> ReconcileStats: ...
async def reconcile_disposed_namespace(platform_db: AsyncSession, disposal: TenantAttachmentStorageDisposal, storage: PrivateAttachmentStorage) -> ReconcileStats: ...
async def record_test_rebuild_disposal(connection: AsyncConnection, target: RebuildTarget) -> None: ...
```

- [ ] **Step 1: Write recovery RED tests.**

```python
async def test_promoting_clean_file_after_crash_becomes_available(owned_attachment):
    await crash_after_promote_before_status_commit(owned_attachment)
    await reconcile_live_namespace(...)
    assert await attachment_status(owned_attachment) == "available"

async def test_generation_increment_preserves_available_attachment(owned_attachment):
    await normal_maintenance_increment_generation(owned_attachment.tenant)
    assert await download_as_currently_authorized_user(owned_attachment) == b"clean"

async def test_rebuild_disposal_is_required_for_old_namespace_delete(old_namespace):
    await reconcile_unknown_namespace(old_namespace)
    assert old_namespace.exists()
    await record_exact_test_rebuild_disposal(...)
    await reconcile_disposed_namespace(...)
    assert not old_namespace.exists()
```

- [ ] **Step 2: Run recovery RED tests.**

Run: `cd backend && pytest tests/services/agent_runtime/test_attachment_recovery.py tests/test_multitenancy/test_test_tenant_rebuild.py -q`

Expected: FAIL because recovery/disposal functions are absent.

- [ ] **Step 3: Implement reconciliation rules.**

Under the same global pipeline advisory lock, complete `promoting` from verified staging/clean, complete `purging` whether the file is present or already absent, and fail only expired `scanning` reservations. Delete unreferenced objects only in a live namespace whose attachment table is queryable. For an unknown/historical namespace, write a safe maintenance warning and preserve bytes unless an exact disposal record authorizes removal.

- [ ] **Step 4: Integrate explicit test-rebuild disposal.**

After the test-only rebuild has successfully dropped the exact schema, insert the exact old `(tenant_id, origin_generation, storage_namespace, 'test_rebuild')` disposal record in the same committed destructive transaction. Do not write it for ordinary `begin_new_attempt`, migration, failed rebuild, suspended, or deactivated tenant states. Existing production deactivation remains preservation-only.

- [ ] **Step 5: Add startup and CLI recovery entrypoints.**

When attachments are enabled, run bounded reconciliation after settings/storage validation during lifespan; failure must leave attachments closed rather than deleting unknown data. Add `python -m app.cli.agent_task_attachments reconcile` that accepts no arbitrary filesystem path or tenant wildcard and reports aggregate safe counters only.

- [ ] **Step 6: Run GREEN lifecycle tests.**

Run: `cd backend && pytest tests/services/agent_runtime/test_attachment_recovery.py tests/test_multitenancy/test_test_tenant_rebuild.py tests/test_multitenancy/test_tenant_migrator.py -q`

Expected: PASS; maintenance generation increments preserve data and only explicit destructive rebuild authorizes old-generation cleanup.

- [ ] **Step 7: Checkpoint.**

Verify recovery uses platform/maintenance authority rather than uploaded-by identity, and never makes an orphan clean file downloadable; do not commit.

## Task 5: Content-safe HTTP API and early default-off gate

**Files:**
- Create: `backend/app/api/agent_task_attachments.py`
- Create: `backend/app/schemas/agent_attachment.py`
- Create: `backend/tests/api/test_agent_task_attachments.py`
- Modify: `backend/app/core/tenant_context.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/README.md`

**Interfaces:**

```python
GET    /api/agent/tasks/{task_id}/attachments/availability -> {"enabled": true}
POST   /api/agent/tasks/{task_id}/attachments -> AttachmentOut
GET    /api/agent/tasks/{task_id}/attachments -> AttachmentList
GET    /api/agent/tasks/{task_id}/attachments/{attachment_id}/download -> StreamingResponse
DELETE /api/agent/tasks/{task_id}/attachments/{attachment_id} -> 204
```

- [ ] **Step 1: Write API RED tests.**

```python
async def test_disabled_attachment_post_returns_404_before_body_and_tenant_lookup(client, monkeypatch):
    response = await client.post("/api/agent/tasks/not-a-uuid/attachments", content=b"x" * 1024)
    assert response.status_code == 404
    assert not tenant_lookup.called

async def test_chunked_over_limit_returns_constant_413_and_removes_staging(authorized_client, private_root):
    response = await stream_multipart_without_content_length(authorized_client, 20 * MIB + 65537)
    assert response.json() == {"detail": "ATTACHMENT_INPUT_LIMIT"}
    assert list(private_root.rglob("*")) == []
```

- [ ] **Step 2: Run API RED tests.**

Run: `cd backend && pytest tests/api/test_agent_task_attachments.py -q`

Expected: FAIL because the router and schemas are absent.

- [ ] **Step 3: Implement route and schema boundary.**

Mount a separate router in `main.py`, but route it under the existing `/api/agent/tasks/{task_id}/attachments` contract. Add exact middleware matching before the broader Agent runtime condition. The POST signature receives `Request`, `RequestScope`, and `AsyncSession`, never FastAPI `File`/`UploadFile`; it authorizes/reserves first, then passes `request.stream()` into Task 3's service/parser.

- [ ] **Step 4: Map errors without content leakage.**

Return only: `404 Not Found`, `413 ATTACHMENT_INPUT_LIMIT`, `422 ATTACHMENT_INPUT_INVALID|ATTACHMENT_TYPE_REJECTED|ATTACHMENT_MALWARE_REJECTED`, `503 ATTACHMENT_CAPACITY_BUSY|ATTACHMENT_SCANNER_UNAVAILABLE`, `409 ATTACHMENT_SOURCE_CHANGED`, and `500 ATTACHMENT_UNAVAILABLE`. Assert responses, logs and audit rows contain no file body/name/path/signature/scanner text.

- [ ] **Step 5: Run API GREEN and default-off regressions.**

Run: `cd backend && pytest tests/api/test_agent_task_attachments.py tests/api/test_agent_tasks.py tests/api/test_trial_peer.py -q`

Expected: PASS; old Agent runtime/API routes keep their existing default-off behavior.

- [ ] **Step 6: Checkpoint.**

Review route order and default-off tests for body parsing before authorization; do not commit.

## Task 6: Actual ClamAV Compose profile and non-mocked integration evidence

**Files:**
- Create: `docker/clamav/clamd.conf`
- Create: `backend/tests/e2e/test_agent_task_attachment_process.py`
- Modify: `docker-compose.yml`
- Modify: `Makefile`
- Modify: `backend/tests/e2e/agent_local_trial_harness.py`

**Interfaces:**

```text
make agent-attachment-e2e
# Starts only a uniquely named, attachment-scan Compose project and self-owned storage volume.
```

- [ ] **Step 1: Write actual-scanner RED harness assertions.**

```python
def test_actual_clamav_rejects_eicar_and_never_promotes_clean_file(actual_attachment_stack):
    result = actual_attachment_stack.upload(EICAR_BYTES, "eicar.txt")
    assert result.status_code == 422
    assert actual_attachment_stack.clean_objects() == []

def test_actual_clamav_rejects_encrypted_and_expansion_limit_samples(actual_attachment_stack):
    assert actual_attachment_stack.upload(ENCRYPTED_PDF, "encrypted.pdf").status_code == 422
    assert actual_attachment_stack.upload(OVERSIZED_EXPANSION_DOCX, "limit.docx").status_code == 422
```

- [ ] **Step 2: Run the actual-scanner RED harness.**

Run: `make agent-attachment-e2e`

Expected: FAIL before profile/configuration/services exist. Use only a self-owned random Compose project name, database, named volumes, port allocation, and private root.

- [ ] **Step 3: Add hardened ClamAV profile.**

Add a profile-only `clamav` service with no host port and a pinned image digest. Mount only a definitions volume and `docker/clamav/clamd.conf`; do not mount backend attachment storage. Add backend private volumes for storage/runtime only and supply attachment settings only to the profile test invocation. The health check uses `PING`/`VERSIONCOMMANDS`, not a fake-clean endpoint.

- [ ] **Step 4: Add real sample generation and end-to-end checks.**

Generate deterministic EICAR, encrypted permitted-format, and compressed-below-input-limit/expanded-over-scan-limit fixtures inside the self-owned e2e environment. Assert the daemon emits `FOUND` through the real protocol, the API maps it to the fixed error, no clean object exists, and a clean text/PDF fixture is the only downloadable path.

- [ ] **Step 5: Run GREEN actual-scanner evidence and cleanup.**

Run: `make agent-attachment-e2e`

Expected: PASS against the real pinned daemon; record image digest, scanner/definition version, tests, exit code, then remove the self-owned Compose project, database, volumes, temp root and child processes.

- [ ] **Step 6: Checkpoint.**

Confirm no test replaces ClamAV with an always-clean fake when claiming final scanner acceptance; do not commit.

## Task 7: Frontend controlled task attachment panel

**Files:**
- Create: `frontend/src/types/agentAttachment.ts`
- Create: `frontend/src/api/agentTaskAttachments.ts`
- Create: `frontend/src/api/agentTaskAttachments.test.ts`
- Create: `frontend/src/components/agent/AgentTaskAttachments.tsx`
- Create: `frontend/src/components/agent/AgentTaskAttachments.test.tsx`
- Modify: `frontend/src/components/agent/AgentSidebar.tsx`
- Modify: `frontend/src/components/agent/AgentSidebar.test.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/README.md`
- Modify: `frontend/src/components/README.md`
- Modify: `frontend/src/types/README.md`

**Interfaces:**

```ts
type AttachmentStatus = "scanning" | "promoting" | "available" | "rejected_malware" | "rejected_scanner" | "failed_storage" | "purging" | "purged";
interface AgentTaskAttachment { attachment_id: string; display_name: string | null; byte_size: number | null; status: AttachmentStatus; scanned_at: string | null; expires_at: string; }
async function getAttachmentAvailability(taskId: string, signal?: AbortSignal): Promise<{ enabled: true }>;
async function uploadTaskAttachment(taskId: string, file: File, signal?: AbortSignal): Promise<AgentTaskAttachment>;
```

- [ ] **Step 1: Write frontend API/component RED tests.**

```tsx
it("does not send multipart until availability succeeds", async () => {
  render(<AgentTaskAttachments taskId={taskId} identity="u1" />);
  expect(mockPost).not.toHaveBeenCalled();
});

it("clears selected file and rows on authorization loss", async () => {
  mockAvailabilityThenListThen403();
  render(<AgentTaskAttachments taskId={taskId} identity="u1" />);
  await screen.findByText("任务私有附件");
  await waitFor(() => expect(screen.queryByText("clean.pdf")).toBeNull());
});
```

- [ ] **Step 2: Run frontend RED tests.**

Run: `cd frontend && npm test -- --run src/api/agentTaskAttachments.test.ts src/components/agent/AgentTaskAttachments.test.tsx`

Expected: FAIL because attachment API/types/component are absent.

- [ ] **Step 3: Implement strict client DTO validation.**

Follow `agentTasks.ts` exact-key runtime validation. POST only `FormData` with `file`; never attach task/factory/tenant/scan fields. Downloads request the authenticated endpoint as a browser attachment response, not a constructed URL; do not create a preview, `FileReader`, blob URL, or persistent storage.

- [ ] **Step 4: Implement isolated panel and sidebar mounting.**

Panel calls availability only after a selected task is visible. It renders fixed Chinese warning text, picker/upload, status, download and delete only. On task/identity/credential/request-epoch change, hidden/closed sidebar, 401/403/404, or aborted stale response, abort in-flight requests and clear selected file plus rows. Mount after `AgentActivity` in `AgentSidebar` without altering instructions, runtime control, or activity semantics.

- [ ] **Step 5: Run GREEN frontend tests and Agent regression.**

Run: `cd frontend && npm test -- --run src/api/agentTaskAttachments.test.ts src/components/agent/AgentTaskAttachments.test.tsx src/components/agent/AgentSidebar.test.tsx src/api/agentTasks.test.ts`

Expected: PASS; no component makes body/content preview requests before availability.

- [ ] **Step 6: Checkpoint.**

Search frontend sources to confirm attachment bytes/names/statuses are absent from browser storage and no plugin/model endpoint receives an attachment reference; do not commit.

## Task 8: Browser evidence, documentation, full regression and clock-out ledger

**Files:**
- Create: `frontend/e2e/specs/agent/task-attachments.spec.ts`
- Create: `backend/tests/e2e/test_agent_task_attachment_browser.py`
- Create: `docs/development/agent-task-attachments.md`
- Modify: `frontend/playwright.agent.config.ts`
- Modify: `docs/architecture.md`
- Modify: `docs/permissions.md`
- Modify: `docs/development.md`
- Modify: `backend/app/services/README.md`
- Modify: `PROGRESS.md`
- Modify: `docs/superpowers/plans/2026-09-26-agent-task-plugin-runtime-roadmap.md`

**Interfaces:**

```text
playwright.agent.config.ts testMatch includes **/agent/task-attachments.spec.ts
backend browser harness starts only the controlled real-ClamAV profile
```

- [ ] **Step 1: Write browser/e2e RED scenario.**

```ts
test("task private attachment is scan-gated and withdrawn on access loss", async ({ page }) => {
  await openAgentTaskSidebar(page);
  await expect(page.getByText("任务私有附件")).toBeVisible();
  await uploadNamedFixture(page, "clean.txt");
  await expect(page.getByRole("button", { name: "下载 clean.txt" })).toBeVisible();
  await revokeCurrentCapaView();
  await expect(page.getByText("任务访问已失效")).toBeVisible();
  await expect(page.getByText("clean.txt")).toHaveCount(0);
});
```

- [ ] **Step 2: Run browser RED scenario.**

Run: `cd frontend && npx playwright test -c playwright.agent.config.ts specs/agent/task-attachments.spec.ts`

Expected: FAIL before panel/profile/harness implementation.

- [ ] **Step 3: Complete real browser scenarios.**

Cover default-off no multipart request, clean upload/download, EICAR refusal, scanner unavailable, task/CAPA revocation withdrawal, close/identity change clearing, and no preview. The backend browser harness must exercise a real API and actual ClamAV service, not fake response fixtures.

- [ ] **Step 4: Write operations documentation.**

Document default-off configuration, one-node/private-volume restriction, scanner profile/definition evidence, file limits, retention, non-delivery to plugins/models, error semantics, safe reconciliation, ordinary-maintenance preservation, explicit disposal records, test-rebuild cleanup, and the absence of production object storage approval.

- [ ] **Step 5: Run focused completion gates.**

Run:

```bash
cd backend && pytest tests/migrations/test_agent_task_attachments_delta.py tests/services/agent_runtime/test_attachment_storage.py tests/services/agent_runtime/test_clamav_scan.py tests/services/agent_runtime/test_task_attachments.py tests/services/agent_runtime/test_attachment_recovery.py tests/api/test_agent_task_attachments.py tests/e2e/test_agent_task_attachment_process.py tests/e2e/test_agent_task_attachment_browser.py -q
cd frontend && npm test -- --run src/api/agentTaskAttachments.test.ts src/components/agent/AgentTaskAttachments.test.tsx src/components/agent/AgentSidebar.test.tsx
cd frontend && npx tsc --noEmit && npm run build && npx tsc --project tsconfig.e2e.json --noEmit
make agent-attachment-e2e
```

Expected: PASS; actual scanner evidence is separate and must not be replaced by mock-only unit results.

- [ ] **Step 6: Run final freeze gates.**

Run the repository-prescribed `make check`, `make check-frontend`, affected Agent R4a/R4b-1 process/browser suites, local documentation-link validation, `git diff --check`, and a before/after hash comparison of unchanged pre-existing source/config files. Report all retained skips/xfail/xpass and Makefile exclusions exactly.

- [ ] **Step 7: Clean self-owned resources and update progress.**

Remove only the run-created database, Compose project, volumes, scanner definitions volume, private storage root, runtime temp directory, server/browser processes and fixture files. Update `PROGRESS.md` and the Agent roadmap with commands, exit status, scanner image/definition version, scope restrictions, disposal behavior, and unapproved production follow-ups. Do not commit.

## Plan Self-Review

- **Spec coverage:** Task 1 covers all schema/default-off/migration constraints; Task 2 covers private storage and strict protocol; Task 3 covers authorization, quotas, state and no-direct-link delivery; Task 4 covers crash recovery, normal maintenance preservation and disposal authority; Task 5 covers early HTTP/body safety; Task 6 covers actual scanner evidence; Task 7 covers no-preview client behavior; Task 8 covers browser proof, documents and final gates.
- **Placeholder scan:** The plan has no unresolved implementation markers, deferred step, or unnamed test obligation. Future `tenant_destroyed` is deliberately named as an unimplemented future trigger and is excluded from this slice.
- **Type consistency:** Task 1 creates the persistence names used by Tasks 3–4; Task 2 defines `AttachmentNamespace`, `PrivateAttachmentStorage` and `ScanResult`; Task 3 consumes these and returns `AttachmentView`; Tasks 5 and 7 expose only the DTO subset; Task 4 is the sole producer of disposal records.

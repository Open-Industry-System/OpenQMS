import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_tenant_aware_session
from app.models.audit import AuditLog
from app.models.control_plan import ControlPlan, ControlPlanItem
from app.models.fmea import FMEADocument
from app.schemas.characteristic import CharacteristicSourceRef
from app.schemas.control_plan import ControlPlanCreate, ControlPlanUpdate, ControlPlanItemResponse, ImportFromFMEARequest
from app.services.cp_validation.engine import CPValidationEngine
from app.services.product_line_service import lock_candidate_scopes, validate_product_line
from app.services.version_service import create_cp_version, stage_cp_version


async def _run_validation_background(cp_id: uuid.UUID, user_id: uuid.UUID, trigger: str) -> None:
    """Run CP validation in a background task with an isolated DB session."""
    async with get_tenant_aware_session() as db:
        try:
            engine = CPValidationEngine()
            await engine.validate(db, cp_id, user_id, trigger=trigger)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Background CP validation failed for %s", cp_id)


async def create_audit_log(
    db: AsyncSession,
    user_id: uuid.UUID,
    action: str,
    target_type: str,
    target_id: uuid.UUID,
    detail: dict | None = None,
) -> AuditLog:
    """Create an AuditLog entry."""
    audit_log = AuditLog(
        table_name=target_type,
        record_id=target_id,
        action=action,
        changed_fields=detail or {},
        operated_by=user_id,
    )
    db.add(audit_log)
    return audit_log


async def generate_document_no(db: AsyncSession) -> str:
    """Return next CP-2026-XXX number based on count of existing control plans."""
    count_query = select(func.count(ControlPlan.cp_id))
    result = await db.execute(count_query)
    count = result.scalar() or 0
    next_num = count + 1
    return f"CP-2026-{next_num:03d}"


async def create_control_plan(
    db: AsyncSession, data: ControlPlanCreate, user_id: uuid.UUID, *, factory_id: uuid.UUID | None = None
) -> ControlPlan:
    """Create a new ControlPlan. Use provided document_no if given, else auto-generate."""
    await lock_candidate_scopes(db, [(factory_id, data.product_line_code)])
    await validate_product_line(db, data.product_line_code)
    document_no = data.document_no if data.document_no else await generate_document_no(db)

    cp = ControlPlan(
        cp_id=uuid.uuid4(),
        document_no=document_no,
        title=data.title,
        product_line_code=data.product_line_code,
        fmea_ref_id=data.fmea_ref_id,
        phase=data.phase,
        part_no=data.part_no,
        part_name=data.part_name,
        contact_info=data.contact_info,
        drawing_rev=data.drawing_rev,
        org_factory=data.org_factory,
        core_group=data.core_group,
        created_by=user_id,
        updated_by=user_id,
        factory_id=factory_id,
    )
    db.add(cp)

    await create_audit_log(
        db,
        user_id=user_id,
        action="CREATE",
        target_type="control_plans",
        target_id=cp.cp_id,
        detail={
            "document_no": document_no,
            "title": data.title,
            "phase": data.phase,
        },
    )

    await db.commit()
    await db.refresh(cp)
    return cp


async def get_control_plan(db: AsyncSession, cp_id: uuid.UUID) -> ControlPlan | None:
    """Get a ControlPlan by UUID with items eagerly loaded."""
    result = await db.execute(
        select(ControlPlan)
        .options(selectinload(ControlPlan.items))
        .where(ControlPlan.cp_id == cp_id)
    )
    return result.scalar_one_or_none()


async def list_control_plans(
    db: AsyncSession, page: int = 1, page_size: int = 20, product_line: str | None = None,
    factory_id: uuid.UUID | None = None, allowed_product_lines: list[str] | None = None,
) -> dict:
    """Return paginated list of control plans."""
    query = (
        select(ControlPlan)
        .options(selectinload(ControlPlan.items))
        .order_by(ControlPlan.created_at.desc())
    )
    count_query = select(func.count(ControlPlan.cp_id))

    if product_line:
        query = query.where(ControlPlan.product_line_code == product_line)
        count_query = count_query.where(ControlPlan.product_line_code == product_line)
    if factory_id:
        query = query.where(ControlPlan.factory_id == factory_id)
        count_query = count_query.where(ControlPlan.factory_id == factory_id)
    if allowed_product_lines is not None:
        query = query.where(ControlPlan.product_line_code.in_(allowed_product_lines))
        count_query = count_query.where(ControlPlan.product_line_code.in_(allowed_product_lines))

    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = list(result.scalars().all())

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def update_control_plan(
    db: AsyncSession,
    cp: ControlPlan,
    data: ControlPlanUpdate,
    user_id: uuid.UUID,
) -> ControlPlan:
    """Update control plan fields. Blocks update if status is approved."""
    if cp.status == "approved":
        raise ValueError("Cannot update an approved control plan.")

    lock_version = data.lock_version
    confirmed_latest_lock_version = data.confirmed_latest_lock_version

    requested_product_line = data.product_line_code
    observed_product_line = cp.product_line_code
    if requested_product_line is not None:
        await lock_candidate_scopes(db, [
            (cp.factory_id, observed_product_line),
            (cp.factory_id, requested_product_line),
        ])

    # 原子乐观锁校验：强制刷新 + SELECT ... FOR UPDATE
    result = await db.execute(
        select(ControlPlan)
        .where(ControlPlan.cp_id == cp.cp_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    fresh = result.scalar_one()
    if (
        requested_product_line is not None
        and fresh.product_line_code != observed_product_line
    ):
        raise ValueError("product_line_changed_again")

    if confirmed_latest_lock_version is not None:
        if fresh.lock_version != confirmed_latest_lock_version:
            raise ValueError("lock_version_changed_again")
    elif lock_version is not None:
        if fresh.lock_version != lock_version:
            raise ValueError("lock_version_mismatch")

    if data.product_line_code is not None:
        await validate_product_line(db, data.product_line_code)

    changed_fields = {}

    for field in [
        "title",
        "document_no",
        "fmea_ref_id",
        "phase",
        "part_no",
        "part_name",
        "contact_info",
        "drawing_rev",
        "org_factory",
        "core_group",
        "product_line_code",
    ]:
        value = getattr(data, field, None)
        if value is not None and value != getattr(cp, field, None):
            # AuditLog.changed_fields is JSONB: UUID 须先序列化成 str，否则
            # json.dumps 抛 TypeError（fmea_ref_id 是 UUID 类型）。
            changed_fields[field] = str(value) if isinstance(value, uuid.UUID) else value
            setattr(cp, field, value)

    cp.updated_by = user_id

    # Handle items replacement if provided
    if data.items is not None:
        import json
        items_result = await db.execute(
            select(ControlPlanItem).where(ControlPlanItem.cp_id == cp.cp_id)
        )
        existing_items = list(items_result.scalars().all())
        existing_by_id = {str(i.item_id): i for i in existing_items}

        # Always validate IDs first (even when content looks unchanged) so
        # duplicate / foreign / garbage IDs cannot bypass checks via
        # items_changed == false. Only empty or temp-* may mean "new".
        resolved: list[tuple[object, str | None]] = []  # (item_data, reuse_key|None)
        seen_uuid_ids: set[str] = set()  # canonical UUID form (catches case/brace/hex variants)
        seen_temp_ids: set[str] = set()  # raw temp-* string form
        for item_data in data.items:
            raw_id = getattr(item_data, "item_id", None)
            raw_s = str(raw_id).strip() if raw_id is not None else ""
            if not raw_s:
                resolved.append((item_data, None))
                continue
            if raw_s.lower().startswith("temp-"):
                if raw_s in seen_temp_ids:
                    raise ValueError(f"重复 item_id: {raw_s}")
                seen_temp_ids.add(raw_s)
                resolved.append((item_data, None))
                continue
            # Canonicalize UUID BEFORE dedup so different text forms of the same
            # UUID (case/braces/no-dashes) cannot bypass duplicate detection.
            try:
                cand = uuid.UUID(raw_s)
            except (ValueError, AttributeError, TypeError) as e:
                raise ValueError(f"非法 item_id（须为空、temp-* 或本 CP 的 UUID）: {raw_s}") from e
            sid = str(cand)
            if sid in seen_uuid_ids:
                raise ValueError(f"重复 item_id: {sid}")
            seen_uuid_ids.add(sid)
            if sid not in existing_by_id:
                raise ValueError(f"item_id 不属于当前控制计划: {sid}")
            source_ref = existing_by_id[sid].source_characteristic_ref
            if source_ref is not None:
                try:
                    source_step_id = CharacteristicSourceRef.model_validate(source_ref).step_id
                except ValueError as exc:
                    raise ValueError("stored source_characteristic_ref is invalid") from exc
                if item_data.source_fmea_node_id not in (None, source_step_id):
                    raise ValueError("source_fmea_node_id must match source_characteristic_ref.step_id")
            resolved.append((item_data, sid))

        # Detect content + identity change (include item_id so temp→new is not skipped)
        items_changed = len(existing_items) != len(data.items)
        if not items_changed:
            for old, (new, reuse_key) in zip(existing_items, resolved, strict=False):
                if reuse_key != str(old.item_id):
                    items_changed = True
                    break
                old_dict = {
                    k: getattr(old, k) for k in [
                        "step_no", "process_name", "equipment", "characteristic_no",
                        "product_characteristic", "process_characteristic", "special_class",
                        "specification_tolerance", "evaluation_method", "sample_size",
                        "sample_frequency", "control_method", "reaction_plan",
                        "source_fmea_node_id", "sort_order",
                    ]
                }
                new_dict = {
                    k: getattr(new, k) for k in [
                        "step_no", "process_name", "equipment", "characteristic_no",
                        "product_characteristic", "process_characteristic", "special_class",
                        "specification_tolerance", "evaluation_method", "sample_size",
                        "sample_frequency", "control_method", "reaction_plan",
                        "source_fmea_node_id", "sort_order",
                    ]
                }
                if json.dumps(old_dict, sort_keys=True, default=str) != json.dumps(new_dict, sort_keys=True, default=str):
                    items_changed = True
                    break

        if items_changed:
            keep_ids: set[str] = set()
            created = 0
            for idx, (item_data, reuse_key) in enumerate(resolved):
                if reuse_key is not None:
                    keep_ids.add(reuse_key)
                    old = existing_by_id[reuse_key]
                    old.step_no = item_data.step_no
                    old.process_name = item_data.process_name
                    old.equipment = item_data.equipment
                    old.characteristic_no = item_data.characteristic_no
                    old.product_characteristic = item_data.product_characteristic
                    old.process_characteristic = item_data.process_characteristic
                    old.special_class = item_data.special_class
                    old.specification_tolerance = item_data.specification_tolerance
                    old.evaluation_method = item_data.evaluation_method
                    old.sample_size = item_data.sample_size
                    old.sample_frequency = item_data.sample_frequency
                    old.control_method = item_data.control_method
                    old.reaction_plan = item_data.reaction_plan
                    old.source_fmea_node_id = (
                        CharacteristicSourceRef.model_validate(old.source_characteristic_ref).step_id
                        if old.source_characteristic_ref is not None
                        else item_data.source_fmea_node_id
                    )
                    old.sort_order = idx
                    continue
                db.add(ControlPlanItem(
                    item_id=uuid.uuid4(),
                    cp_id=cp.cp_id,
                    factory_id=cp.factory_id,
                    step_no=item_data.step_no,
                    process_name=item_data.process_name,
                    equipment=item_data.equipment,
                    characteristic_no=item_data.characteristic_no,
                    product_characteristic=item_data.product_characteristic,
                    process_characteristic=item_data.process_characteristic,
                    special_class=item_data.special_class,
                    specification_tolerance=item_data.specification_tolerance,
                    evaluation_method=item_data.evaluation_method,
                    sample_size=item_data.sample_size,
                    sample_frequency=item_data.sample_frequency,
                    control_method=item_data.control_method,
                    reaction_plan=item_data.reaction_plan,
                    source_fmea_node_id=item_data.source_fmea_node_id,
                    sort_order=idx,
                ))
                created += 1
            deleted = 0
            for sid, old in existing_by_id.items():
                if sid not in keep_ids:
                    await db.delete(old)
                    deleted += 1

            changed_fields["items_count"] = len(keep_ids) + created
            changed_fields["items_updated"] = len(keep_ids)
            changed_fields["items_created"] = created
            changed_fields["items_deleted"] = deleted

    if changed_fields:
        cp.lock_version += 1  # 只在有实际变更时递增乐观锁版本
        await create_audit_log(
            db,
            user_id=user_id,
            action="UPDATE",
            target_type="control_plans",
            target_id=cp.cp_id,
            detail=changed_fields,
        )

        # 强制覆盖时记录审计日志
        if confirmed_latest_lock_version is not None:
            await create_audit_log(
                db,
                user_id=user_id,
                action="FORCE_SAVE_OVERRIDE",
                target_type="control_plans",
                target_id=cp.cp_id,
                detail={"reason": "User confirmed overwrite after conflict detection"},
            )

    await db.commit()
    await db.refresh(cp)

    # Trigger background validation only when fields actually changed
    if changed_fields:
        asyncio.create_task(
            _run_validation_background(cp.cp_id, user_id, trigger="auto_on_save")
        )

    return cp


async def delete_control_plan(
    db: AsyncSession, cp: ControlPlan, user_id: uuid.UUID
) -> None:
    """Delete a control plan and log the action."""
    from app.services.capa_review_source_guard import (
        assert_source_references_unchanged,
        lock_source_capa_references,
    )

    locked_capa_ids = await lock_source_capa_references(db, "control_plan", cp.cp_id)
    observed_product_line = cp.product_line_code
    await lock_candidate_scopes(
        db, [(cp.factory_id, observed_product_line)]
    )
    fresh = await db.scalar(
        select(ControlPlan)
        .where(ControlPlan.cp_id == cp.cp_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if fresh is None:
        raise ValueError("Control plan not found")
    if (
        fresh.factory_id != cp.factory_id
        or fresh.product_line_code != observed_product_line
    ):
        raise ValueError("product_line_changed_again")

    cp_id = fresh.cp_id
    await assert_source_references_unchanged(db, "control_plan", cp_id, locked_capa_ids)
    await db.delete(fresh)

    await create_audit_log(
        db,
        user_id=user_id,
        action="DELETE",
        target_type="control_plans",
        target_id=cp_id,
        detail={"document_no": fresh.document_no, "title": fresh.title},
    )

    await db.commit()


async def approve_control_plan(
    db: AsyncSession, cp: ControlPlan, user_id: uuid.UUID
) -> ControlPlan:
    """Approve a control plan. Validates all referenced gauges are active and calibrated."""
    if cp.status == "approved":
        raise ValueError("Control plan is already approved.")

    from app.services.gauge_service import validate_gauge_for_use
    for item in cp.items:
        if item.gauge_id:
            await validate_gauge_for_use(db, item.gauge_id)

    cp.status = "approved"
    cp.approved_by = user_id
    cp.approved_at = datetime.now(UTC)
    cp.updated_by = user_id

    # Create version snapshot on approve
    await create_cp_version(db, cp, "approve", "审批通过，版本发布", user_id)

    await create_audit_log(
        db,
        user_id=user_id,
        action="APPROVE",
        target_type="control_plans",
        target_id=cp.cp_id,
        detail={"old_status": "draft", "new_status": "approved"},
    )

    await db.commit()
    await db.refresh(cp)
    return cp


class CharacteristicImportError(ValueError):
    """Safe API-facing failure, without disclosing source names."""

    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


async def _import_tenant_boundary(db: AsyncSession, *, extra_tables=()) -> str:
    """No tenant table may resolve through public fallback (ADR-0012)."""
    from sqlalchemy import text
    from app.core.tenant_utils import current_tenant_schema

    schema = current_tenant_schema.get()
    actual = await db.scalar(text("SELECT current_schema()"))
    if schema is not None:
        if actual != schema:
            raise CharacteristicImportError("资源不存在", 404)
        for table in (
            "control_plans", "control_plan_items", "control_plan_versions",
            "fmea_documents", "fmea_versions", "users", "role_definitions",
            "role_permissions", "user_factories", "user_product_lines",
            "product_lines", "audit_logs",
        ) + tuple(extra_tables):
            namespace = await db.scalar(text(
                "SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE c.oid=to_regclass(:table)"
            ), {"table": table})
            if namespace != schema:
                raise CharacteristicImportError("资源不存在", 404)
    return actual


async def _import_authority(db: AsyncSession, scope, *, lock: bool):
    """Re-resolve authority; neither digest nor cached RequestScope grants access.

    UPDATE locks on user/role also exclude FK insertions into absent grant
    sets (first explicit factory grant replaces fallback-own semantics). Positive
    grant rows are SHARE locked against revocation, in deterministic key order.
    """
    from sqlalchemy.orm import lazyload
    from sqlalchemy.orm.attributes import set_committed_value
    from app.core.factory_scope import resolve_factory_scope, resolve_product_line_scope
    from app.models.user import User
    from app.models.role import RoleDefinition, RolePermission, UserProductLine
    from app.models.factory import UserFactory

    async def fresh(stmt, *, parent=False):
        if lock:
            stmt = stmt.with_for_update(read=not parent)
        return await db.execute(stmt.execution_options(populate_existing=True))

    user = (await fresh(select(User).options(lazyload(User.role_definition)).where(
        User.user_id == scope.user.user_id
    ), parent=True)).scalar_one_or_none()
    if user is None or not user.is_active:
        raise CharacteristicImportError("无导入权限", 403)
    role = (await fresh(select(RoleDefinition).where(RoleDefinition.id == user.role_id), parent=True)).scalar_one_or_none()
    if role is None or not role.is_active:
        raise CharacteristicImportError("无导入权限", 403)
    permissions = (await fresh(select(RolePermission).where(
        RolePermission.role_id == role.id,
        RolePermission.module.in_(["planning", "fmea", "group"]),
    ).order_by(RolePermission.module))).scalars().all()
    levels = {p.module: p.permission_level for p in permissions}
    if levels.get("planning", 0) < 2 or levels.get("fmea", 0) < 1:
        raise CharacteristicImportError("需要计划写权限和 FMEA 查看权限", 403)
    factories = (await fresh(select(UserFactory).where(UserFactory.user_id == user.user_id)
                             .order_by(UserFactory.factory_id))).scalars().all()
    lines = (await fresh(select(UserProductLine).where(UserProductLine.user_id == user.user_id)
                         .order_by(UserProductLine.product_line_code))).scalars().all()
    set_committed_value(user, "role_definition", role)
    factory_scope = resolve_factory_scope(user, [r.factory_id for r in factories], levels.get("group", 0) >= 5)
    pl_scope = resolve_product_line_scope(user, [r.product_line_code for r in lines], factory_scope)
    return factory_scope, pl_scope


def _import_check_access(entity, scope, factory_scope, pl_scope):
    if (
        (scope.effective_factory_id is not None and entity.factory_id != scope.effective_factory_id)
        or (factory_scope.accessible_factory_ids is not None and entity.factory_id not in factory_scope.accessible_factory_ids)
        or (scope.factory_scope.accessible_factory_ids is not None and entity.factory_id not in scope.factory_scope.accessible_factory_ids)
        or pl_scope.mode == "NONE"
        or (pl_scope.mode == "EXPLICIT" and entity.product_line_code not in (pl_scope.codes or []))
        or scope.pl_scope.mode == "NONE"
        or (scope.pl_scope.mode == "EXPLICIT" and entity.product_line_code not in (scope.pl_scope.codes or []))
    ):
        raise CharacteristicImportError("资源不存在", 404)


async def _characteristic_import_context(db, cp_id, req, scope, *, lock=False):
    from app.models.fmea_version import FMEAVersion
    from app.services.version_service import lock_version_parents_in_order, verify_fmea_version

    tenant = await _import_tenant_boundary(db)
    if req.source_fmea_version_id is None or req.expected_lock_version is None:
        raise CharacteristicImportError("缺少预览上下文，请重新 preview / 预览后导入")
    cp = await db.scalar(select(ControlPlan).where(ControlPlan.cp_id == cp_id)
                         .execution_options(populate_existing=True))
    fmea = await db.scalar(select(FMEADocument).where(FMEADocument.fmea_id == req.fmea_id)
                           .execution_options(populate_existing=True))
    if cp is None or fmea is None:
        raise CharacteristicImportError("资源不存在", 404)
    if lock:
        # Existing scope-before-parent ordering and deterministic version locks.
        observed = (cp.factory_id, cp.product_line_code, fmea.factory_id, fmea.product_line_code)
        try:
            await lock_candidate_scopes(db, [(cp.factory_id, cp.product_line_code), (fmea.factory_id, fmea.product_line_code)])
            await lock_version_parents_in_order(db, [("control_plan", cp_id), ("fmea", req.fmea_id)])
        except ValueError as exc:
            raise CharacteristicImportError("资源范围已变化，请重新预览") from exc
        await db.refresh(cp)
        await db.refresh(fmea)
        if observed != (cp.factory_id, cp.product_line_code, fmea.factory_id, fmea.product_line_code):
            raise CharacteristicImportError("资源范围已变化，请重新预览")
    factory_scope, pl_scope = await _import_authority(db, scope, lock=lock)
    for entity in (cp, fmea):
        _import_check_access(entity, scope, factory_scope, pl_scope)
    if cp.factory_id != fmea.factory_id or cp.product_line_code != fmea.product_line_code:
        raise CharacteristicImportError("来源与目标范围不一致")
    if cp.status != "draft":
        raise CharacteristicImportError("仅草稿控制计划允许首次导入")
    if cp.lock_version != req.expected_lock_version:
        raise CharacteristicImportError("控制计划已变化，请重新预览")
    if cp.fmea_ref_id not in (None, fmea.fmea_id):
        raise CharacteristicImportError("source_conflict: 控制计划已关联其他来源")
    if cp.source_fmea_version_id is not None:
        accepted_source = await db.scalar(select(FMEAVersion).where(
            FMEAVersion.version_id == cp.source_fmea_version_id,
            FMEAVersion.fmea_id == fmea.fmea_id,
            FMEAVersion.factory_id == cp.factory_id,
        ))
        if accepted_source is None:
            raise CharacteristicImportError("source_conflict: 控制计划版本关联其他来源")
    if fmea.fmea_type != "PFMEA":
        raise CharacteristicImportError("仅允许 PFMEA 来源")
    version = await db.scalar(select(FMEAVersion).where(
        FMEAVersion.version_id == req.source_fmea_version_id,
        FMEAVersion.fmea_id == fmea.fmea_id,
        FMEAVersion.factory_id == fmea.factory_id,
    ))
    # Actual writer: approve publishes a major; snapshot is graph-only, not
    # a status wrapper. The current document may already be in rework.
    if (version is None or version.change_type != "approve" or version.major_no < 1
            or version.minor_no != 0 or not await verify_fmea_version(db, version.version_id)):
        raise CharacteristicImportError("来源必须为本 PFMEA 的真实批准快照，请重新预览")
    return cp, fmea, version, tenant


def _import_step_ids(req, graph):
    if req.step_ids is not None and req.step_nos is not None:
        raise CharacteristicImportError("step_ids 与 step_nos 不可同时指定")
    if req.step_nos is not None:
        ids = []
        for number in req.step_nos:
            matches = [str(n["id"]) for n in graph.get("nodes", [])
                       if n.get("type") == "ProcessStep" and n.get("process_number") == number]
            if len(matches) != 1:
                raise CharacteristicImportError("step_nos 必须唯一匹配工序，请按 ID 重新预览")
            ids.extend(matches)
    else:
        ids = req.step_ids or []
    if not ids:
        raise CharacteristicImportError("请选择工序后重新预览；空选择不代表全部")
    return tuple(sorted(set(ids)))


async def _build_characteristic_import_preview(db, cp, fmea, version, tenant, req):
    from dataclasses import asdict
    from app.services.cp_characteristic_mapping import candidate_key, derive_cp_items
    from app.services.fmea_characteristics import source_key
    from app.services.version_service import compute_snapshot_hash

    step_ids = _import_step_ids(req, version.snapshot)
    result = derive_cp_items(fmea_id=fmea.fmea_id, fmea_type=fmea.fmea_type,
                             graph=version.snapshot, step_ids=step_ids)
    if any(i.code == "invalid_step_selection" for i in result.issues):
        raise CharacteristicImportError("工序选择无效，请重新预览")
    existing = list((await db.scalars(select(ControlPlanItem).where(
        ControlPlanItem.cp_id == cp.cp_id
    ).order_by(ControlPlanItem.sort_order, ControlPlanItem.item_id)
        .execution_options(populate_existing=True))).all())
    by_source = {}
    for row in existing:
        if row.factory_id != cp.factory_id:
            raise CharacteristicImportError("控制计划行范围不一致")
        if row.source_characteristic_ref is not None:
            try:
                ref = CharacteristicSourceRef.model_validate(row.source_characteristic_ref)
            except ValueError as exc:
                raise CharacteristicImportError("旧来源需人工确认，不可首次导入覆盖") from exc
            if ref.fmea_id != fmea.fmea_id:
                raise CharacteristicImportError("source_conflict: 已有行关联其他来源")
            by_source.setdefault(source_key(ref), []).append(row)
        elif row.source_fmea_node_id is not None:
            raise CharacteristicImportError("旧自由文本来源需人工确认，请使用同步流程")
    issues = [asdict(i) for i in result.issues]
    items = []
    for mapped in result.items:
        ref = mapped.source_ref.model_copy(update={"accepted_source_version_id": version.version_id})
        matches = by_source.get(source_key(ref), [])
        if len(matches) > 1:
            issues.append({"code": "ambiguous_existing_rows", "node_id": ref.step_id,
                           "blocking": True, "message": "同源多个控制行，请人工确认；不覆盖或合并"})
        if len(matches) == 1:
            issues.append({"code": "existing_source_requires_sync", "node_id": ref.step_id,
                           "blocking": False, "message": "已有同源行原样保留，变更请使用同步流程"})
        action = "existing" if matches else "add"
        item_id = matches[0].item_id if len(matches) == 1 else None
        items.append({"candidate_key": candidate_key(action, ref, item_id), "action": action,
                      "item_id": str(item_id) if item_id else None,
                      "source_ref": ref.model_dump(mode="json"), "fields": mapped.fields})
    preview = {"source_fmea_version_id": str(version.version_id), "expected_lock_version": cp.lock_version,
               "mapping_version": 1, "items": items, "issues": issues}
    preview["preview_digest"] = compute_snapshot_hash({
        **preview, "tenant_schema": tenant, "cp_id": str(cp.cp_id), "cp_status": cp.status,
        "cp_factory_id": str(cp.factory_id), "cp_product_line": cp.product_line_code,
        "cp_fmea_ref_id": str(cp.fmea_ref_id) if cp.fmea_ref_id else None,
        "cp_source_version_id": str(cp.source_fmea_version_id) if cp.source_fmea_version_id else None,
        "source_snapshot_hash": version.sha256_hash, "step_ids": list(step_ids),
        # Bind actual row material too, even if a legacy writer omitted a lock bump.
        "existing_rows": [{"item_id": str(r.item_id), "source_ref": r.source_characteristic_ref,
                           "fields": {c.name: str(getattr(r, c.name)) if isinstance(getattr(r, c.name), uuid.UUID)
                                      else getattr(r, c.name) for c in ControlPlanItem.__table__.columns
                                      if c.name != "source_characteristic_ref"}} for r in existing],
    })
    return preview, existing


async def preview_import_from_fmea(db, cp_id, req, scope):
    """Read-only projection of an explicitly requested immutable approved snapshot."""
    with db.no_autoflush:
        context = await _characteristic_import_context(db, cp_id, req, scope)
        preview, _ = await _build_characteristic_import_preview(db, *context, req)
        return preview


async def import_from_fmea(
    db: AsyncSession, cp_id: uuid.UUID, req: ImportFromFMEARequest, user_id: uuid.UUID,
    *, scope=None,
) -> list["ControlPlanItemResponse"]:
    """Apply a fresh authorized full preview; never overwrite/delete existing rows.

    Stage the shared snapshot without committing; materialize the response before
    the sole commit. No post-commit business queries can lose tenant binding.
    """
    if scope is None or scope.user.user_id != user_id:
        raise CharacteristicImportError("需要当前请求授权上下文", 403)
    if not req.preview_digest or req.selected_candidate_keys is None:
        raise CharacteristicImportError("缺少预览上下文，请重新 preview / 预览后导入")
    if not req.selected_candidate_keys or len(set(req.selected_candidate_keys)) != len(req.selected_candidate_keys):
        raise CharacteristicImportError("请选择有效候选，空或重复选择不可导入")
    savepoint = await db.begin_nested()
    released = False
    try:
        context = await _characteristic_import_context(db, cp_id, req, scope, lock=True)
        cp, fmea, version, _ = context
        preview, existing = await _build_characteristic_import_preview(db, *context, req)
        if preview["preview_digest"] != req.preview_digest:
            raise CharacteristicImportError("预览已过期，请重新预览")
        candidates = {i["candidate_key"]: i for i in preview["items"]}
        if not set(req.selected_candidate_keys) <= candidates.keys():
            raise CharacteristicImportError("候选键不属于本次预览")
        if any(i["blocking"] for i in preview["issues"]):
            raise CharacteristicImportError("预览存在阻塞问题，请人工确认后重新预览")
        selected = set(req.selected_candidate_keys)
        by_id = {str(r.item_id): r for r in existing}
        accepted = []
        added = 0
        order = max((r.sort_order for r in existing), default=-1) + 1
        for candidate in preview["items"]:
            if candidate["candidate_key"] not in selected:
                continue
            if candidate["action"] == "existing":
                accepted.append(by_id[candidate["item_id"]])
                continue
            row = ControlPlanItem(
                item_id=uuid.uuid4(), cp_id=cp_id, factory_id=cp.factory_id,
                source_fmea_node_id=candidate["source_ref"]["step_id"],
                source_characteristic_ref=candidate["source_ref"], item_source="fmea",
                sort_order=order + added, **candidate["fields"],
            )
            db.add(row)
            accepted.append(row)
            added += 1
        if added:
            cp.fmea_ref_id = fmea.fmea_id
            cp.source_fmea_version_id = version.version_id
            cp.updated_by = user_id
            cp.lock_version += 1
            await create_audit_log(db, user_id, "IMPORT_FMEA", "control_plans", cp_id, {
                "fmea_id": str(fmea.fmea_id), "source_fmea_version_id": str(version.version_id),
                "preview_digest": preview["preview_digest"], "items_created": added,
                "selected_candidate_keys": req.selected_candidate_keys,
            })
            await db.flush()
            # Approval may already have been delivered before this CP existed.
            # Persist incomplete coverage now; never wait for another event.
            cp.sync_pending = not await _cp_has_handled_latest_approval(db, cp)
            await stage_cp_version(db, cp, "import", "PFMEA 特性首次导入", user_id,
                                    source_fmea_version_id=version.version_id)
        response = [ControlPlanItemResponse.model_validate(row) for row in accepted]
        await savepoint.commit()
        released = True
        await db.commit()
        return response
    except Exception:
        if released:
            await db.rollback()
        else:
            # Includes a nested transaction deactivated by failed flush.
            await savepoint.rollback()
        raise


async def check_stale_items(db: AsyncSession, cp_id: uuid.UUID, *, scope, source_fmea_version_id=None) -> list[dict]:
    """Use the exact approved-snapshot sync projection, including conflicts and protection."""
    from app.services.version_service import build_sync_preview
    preview = await build_sync_preview(db, cp_id, source_fmea_version_id, scope=scope)
    return [{**item, "status": "deleted" if item["action"] == "delete" else "modified"}
            for item in preview["items"]] + [
                {**i, "status": "conflict" if i["blocking"] else "modified",
                 "diff_fields": i.get("diff_fields", []), "issues": [i]}
                for i in preview["issues"] if i.get("item_id")]


async def _cp_has_handled_latest_approval(db, cp) -> bool:
    """Completion must cover the highest approval, not only a chosen historical source.

    Writers already hold scope and CP/FMEA parent locks. Verify ownership/hash
    and actual accepted coverage with the same conservative worker predicate.
    """
    from app.models.fmea_version import FMEAVersion

    versions = list((await db.scalars(select(FMEAVersion).where(
        FMEAVersion.fmea_id == cp.fmea_ref_id, FMEAVersion.factory_id == cp.factory_id,
        FMEAVersion.change_type == "approve", FMEAVersion.major_no >= 1,
        FMEAVersion.minor_no == 0).order_by(FMEAVersion.major_no.desc()).limit(2))).all())
    if not versions or (len(versions) > 1 and versions[0].major_no == versions[1].major_no):
        return False
    return await _cp_has_handled_approval(db, cp, versions[0].version_id)


async def _cp_has_handled_approval(db, cp, event_version_id) -> bool:
    """Acknowledge only a valid complete accepted baseline, never a guess.

    The document pointer alone is insufficient (partial imports can carry it).
    Unchanged rows may retain older per-row accepted versions.
    """
    from app.models.fmea_version import FMEAVersion
    from app.services.fmea_characteristics import source_key
    from app.services.version_service import verify_fmea_version, _mapped_snapshot

    source = await db.scalar(select(FMEADocument).where(FMEADocument.fmea_id == cp.fmea_ref_id)
                             .execution_options(populate_existing=True))
    if (source is None or source.fmea_type != 'PFMEA' or source.factory_id != cp.factory_id
            or source.product_line_code != cp.product_line_code):
        return False
    cache = {}

    async def approved(version_id):
        if version_id not in cache:
            version = await db.scalar(select(FMEAVersion).where(
                FMEAVersion.version_id == version_id, FMEAVersion.fmea_id == cp.fmea_ref_id,
                FMEAVersion.factory_id == cp.factory_id, FMEAVersion.change_type == 'approve',
                FMEAVersion.major_no >= 1, FMEAVersion.minor_no == 0)) if version_id else None
            cache[version_id] = version if version and await verify_fmea_version(db, version.version_id) else None
        return cache[version_id]

    event = await approved(event_version_id)
    accepted = await approved(cp.source_fmea_version_id)
    if event is None or accepted is None or accepted.major_no < event.major_no:
        return False
    projections = {}

    def projection(version):
        if version.version_id not in projections:
            mapped = _mapped_snapshot(cp.fmea_ref_id, version.snapshot)
            projections[version.version_id] = None if any(i.blocking for i in mapped.issues) else {
                source_key(item.source_ref): item for item in mapped.items}
        return projections[version.version_id]

    target = projection(accepted)
    if target is None:
        return False
    rows = list((await db.scalars(select(ControlPlanItem).where(ControlPlanItem.cp_id == cp.cp_id)
                                 .order_by(ControlPlanItem.item_id)
                                 .execution_options(populate_existing=True))).all())
    covered = set()
    for row in rows:
        try:
            ref = CharacteristicSourceRef.model_validate(row.source_characteristic_ref)
        except (ValueError, TypeError):
            return False
        key = source_key(ref)
        expected = target.get(key)
        baseline = await approved(ref.accepted_source_version_id)
        if (row.factory_id != cp.factory_id or ref.mapping_version != 1 or expected is None
                or ref.step_id != row.source_fmea_node_id
                or ref.work_element_id != expected.source_ref.work_element_id
                or baseline is None or baseline.major_no > accepted.major_no):
            return False
        base_items = projection(baseline)
        base = base_items.get(key) if base_items is not None else None
        # Match _sync_projection's unchanged-source completion semantics:
        # trusted accepted SOURCE material must match the completed document
        # baseline. Current local values may differ as a permitted nonblocking
        # override; neither explicit acknowledgment nor notification rewrites it.
        if (base is None or base.source_ref.work_element_id != ref.work_element_id
                or base.fields != expected.fields):
            return False
        covered.add(key)
    return covered == set(target)


async def apply_cp_sync_pending(db: AsyncSession, outbox, user_id: uuid.UUID) -> int:
    """Notify genuinely unhandled approvals under the existing CP mutex.

    Scope locks precede CP parent locks, in deterministic order as import/sync
    writers. Refresh after waiting so late delivery cannot overwrite their clear.
    Only sync_pending and its actual false-to-true audit are written; the caller
    completes the outbox atomically in the same transaction.
    """
    from app.services.version_service import lock_version_parents_in_order

    query = select(ControlPlan.cp_id, ControlPlan.factory_id, ControlPlan.product_line_code).where(
        ControlPlan.fmea_ref_id == outbox.fmea_id).order_by(ControlPlan.cp_id)
    observed = list((await db.execute(query)).all())
    source_scope = (await db.execute(select(FMEADocument.factory_id, FMEADocument.product_line_code)
                                    .where(FMEADocument.fmea_id == outbox.fmea_id))).first()
    scopes = {(row.factory_id, row.product_line_code) for row in observed}
    if source_scope is not None:
        scopes.add((source_scope.factory_id, source_scope.product_line_code))
    if not scopes:
        return 0
    await lock_candidate_scopes(db, scopes)
    # A create may have committed while discovery waited on the scope mutex.
    candidates = list((await db.execute(query)).all())
    if any((row.factory_id, row.product_line_code) not in scopes for row in candidates):
        raise ValueError('CP candidate scope changed; retry approval notification')
    await lock_version_parents_in_order(db, [('control_plan', row.cp_id) for row in candidates])
    cps = list((await db.scalars(select(ControlPlan).where(
        ControlPlan.cp_id.in_([row.cp_id for row in candidates])).order_by(ControlPlan.cp_id)
        .execution_options(populate_existing=True))).all())
    identities = {row.cp_id: (row.factory_id, row.product_line_code) for row in candidates}
    if any(cp.fmea_ref_id != outbox.fmea_id or identities[cp.cp_id] != (cp.factory_id, cp.product_line_code) for cp in cps):
        raise ValueError('CP source or scope changed; retry approval notification')
    processed = 0
    for cp in cps:
        if cp.sync_pending or await _cp_has_handled_approval(db, cp, outbox.fmea_version_id):
            continue
        cp.sync_pending = True
        db.add(AuditLog(table_name='control_plans', record_id=cp.cp_id, action='UPDATE',
            changed_fields={'sync_pending': 'false->true',
                            'trigger_fmea_version_id': str(outbox.fmea_version_id)}, operated_by=user_id))
        processed += 1
    return processed


# ─── CSR Sync ───

async def sync_csr_to_control_plan(
    db: AsyncSession,
    plan_id: uuid.UUID,
    customer_ids: list[uuid.UUID],
    user_id: uuid.UUID,
):
    from app.models.audit import AuditLog
    from app.models.control_plan import ControlPlan
    from app.models.customer_quality import Customer

    # 1. Query control plan
    result = await db.execute(select(ControlPlan).where(ControlPlan.cp_id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise ValueError("控制计划不存在")

    # 2. Query customer CSR
    result = await db.execute(select(Customer).where(Customer.customer_id.in_(customer_ids)))
    customers = result.scalars().all()

    # 3. Build CSR map keyed by (source_customer_id, title)
    new_csr_map: dict[tuple, dict] = {}
    for customer in customers:
        if customer.csr_list:
            for item in customer.csr_list:
                key = (str(customer.customer_id), item.get("title", ""))
                new_csr_map[key] = {
                    "title": item.get("title", ""),
                    "description": item.get("description", ""),
                    "source_customer_id": str(customer.customer_id),
                    "synced_at": datetime.now(UTC).isoformat(),
                    "source": "csr",
                }

    # 4. Preserve existing manual items
    existing = plan.customer_requirements or []
    manual_items = [item for item in existing if item.get("source") == "manual"]

    # 5. Merge: csr items replace, manual items preserved
    merged = list(new_csr_map.values()) + manual_items
    plan.customer_requirements = merged

    # AuditLog
    audit = AuditLog(
        table_name="control_plans",
        record_id=plan_id,
        action="SYNC_CSR",
        changed_fields={"customer_ids": [str(cid) for cid in customer_ids], "csr_count": len(new_csr_map)},
        operated_by=user_id,
    )
    db.add(audit)

    await db.commit()
    return plan

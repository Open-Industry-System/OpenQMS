"""Complete D4 history: integrity metadata never grants body authority."""
import hashlib
import hmac
import json
from types import SimpleNamespace

from sqlalchemy import select
from app.config import settings
from app.core.permissions import PermissionLevel
from app.models.capa import CAPAEightD
from app.models.capa_d4_delivery import CapaD4RootCauseRevision
from app.models.capa_r6 import (CapaR6MaterialVersion, CapaR6EntrySwitch,
    CapaR6RootRevisionBody, CapaR6RootRevisionSource, CapaR6SourceOrigin)
from app.services.capa_current_access import (current_capa_actor_access,
    current_capa_target_metadata)


def origin_digest(ids):
    return hashlib.sha256(json.dumps(sorted(str(i) for i in ids), separators=(',', ':')).encode()).hexdigest()


def ordinary_capa_predicate(report_expression):
    """SQL fragments are server-owned identifiers, never caller input."""
    return f"""NOT EXISTS (SELECT 1 FROM capa_ai_adoption r6_known_legacy
        WHERE r6_known_legacy.capa_id={report_expression} AND r6_known_legacy.item_ref ? 'r6_capture_id')
        AND NOT EXISTS (SELECT 1 FROM capa_r6_root_revision_bodies r6_body
        WHERE r6_body.report_id = {report_expression} AND r6_body.source_count > 0)
        AND NOT EXISTS (SELECT 1 FROM capa_d4_root_cause_revisions r6_revision
        WHERE r6_revision.report_id = {report_expression}
          AND r6_revision.revision_id = (SELECT r6_latest.revision_id
              FROM capa_d4_root_cause_revisions r6_latest
              WHERE r6_latest.report_id = {report_expression}
              ORDER BY r6_latest.revision_no DESC LIMIT 1)
          AND ((NOT EXISTS (SELECT 1 FROM capa_r6_root_revision_bodies r6_missing
                            WHERE r6_missing.revision_id = r6_revision.revision_id
                              AND r6_missing.report_id = {report_expression})
                AND (r6_revision.write_path LIKE 'r6:%' OR EXISTS (
                    SELECT 1 FROM capa_r6_root_revision_bodies r6_prior
                    WHERE r6_prior.report_id = {report_expression})))
            OR EXISTS (SELECT 1 FROM capa_r6_root_revision_bodies r6_current
                WHERE r6_current.revision_id = r6_revision.revision_id
                  AND (r6_current.report_id <> {report_expression}
                    OR r6_current.binding_state <> 'legacy_unattested'
                    OR r6_current.source_count <> 0
                    OR r6_current.origin_digest <> '{origin_digest(())}'
                    OR EXISTS (SELECT 1 FROM capa_r6_root_revision_sources r6_source
                        WHERE r6_source.revision_id = r6_revision.revision_id)))))"""


async def root_metadata(db, report_id):
    """No body columns; a missing binding on an R6 writer fails closed."""
    revision = await db.scalar(select(CapaD4RootCauseRevision).where(
        CapaD4RootCauseRevision.report_id == report_id).order_by(
        CapaD4RootCauseRevision.revision_no.desc()).limit(1))
    if revision is None:
        return None, ()
    body = (await db.execute(select(CapaR6RootRevisionBody.binding_state,
        CapaR6RootRevisionBody.source_count, CapaR6RootRevisionBody.origin_digest).where(
        CapaR6RootRevisionBody.revision_id == revision.revision_id,
        CapaR6RootRevisionBody.report_id == report_id))).one_or_none()
    if body is None:
        prior_binding = await db.scalar(select(CapaR6RootRevisionBody.revision_id).where(
            CapaR6RootRevisionBody.report_id == report_id).limit(1))
        if revision.write_path.startswith("r6:") or prior_binding is not None:
            raise PermissionError('D4_MATERIAL_UNAVAILABLE')
        return revision, ()
    sources = tuple((await db.scalars(select(CapaR6SourceOrigin).join(
        CapaR6RootRevisionSource, CapaR6RootRevisionSource.source_id == CapaR6SourceOrigin.source_id).where(
        CapaR6RootRevisionSource.revision_id == revision.revision_id,
        CapaR6RootRevisionSource.report_id == report_id,
        CapaR6SourceOrigin.report_id == report_id))).all())
    if (len(sources) != body.source_count or origin_digest(s.source_id for s in sources) != body.origin_digest
            or (body.binding_state == 'controlled') != bool(sources)):
        raise PermissionError('D4_MATERIAL_UNAVAILABLE')
    return revision, sources


async def require_legacy_root_only(db, report_id):
    """A legacy outlet cannot carry or erase a controlled root's origins."""
    from app.services.capa_current_access import require_business_namespace
    await require_business_namespace(db)
    _, sources = await root_metadata(db, report_id)
    from app.services.capa_legacy_capture import require_ordinary_capture_material
    await require_ordinary_capture_material(db,report_id)
    from app.models.capa_r6 import CapaR6LocalRevision
    local = await db.scalar(select(CapaR6LocalRevision.revision_id).where(CapaR6LocalRevision.report_id==report_id).limit(1))
    if sources or local:
        raise PermissionError('D4_FULL_MATERIAL_UNAVAILABLE: continue manual D5')


async def require_current_egress_statement(db):
    """A repeatable-read projection snapshot is never live egress authority."""
    from sqlalchemy import text
    from app.services.capa_current_access import require_business_namespace
    await require_business_namespace(db)
    if await db.scalar(text('SHOW transaction_isolation')) != 'read committed':
        raise PermissionError('D4_CURRENT_AUTHORITY_UNAVAILABLE')


async def require_legacy_context(db, context):
    await require_current_egress_statement(db)
    if context is not None:
        report_id = context.capa_data.get('report_id')
        if report_id is not None:
            if getattr(context, 'actor_id', None) is not None:
                current = await legacy_recommendation_binding(db, SimpleNamespace(user_id=context.actor_id), report_id)
                _, current_lines = await current_capa_actor_access(db, context.actor_id, PermissionLevel.VIEW)
                if current_lines.mode != 'ALL':
                    permitted = set(current_lines.codes or [])
                    context.user_product_lines = sorted(permitted if context.user_product_lines is None
                        else permitted.intersection(context.user_product_lines))
                if context.material_version is not None and current != context.material_version:
                    raise PermissionError('D4_RECOMMENDATION_MATERIAL_CHANGED')
            else:
                await require_legacy_root_only(db, report_id)


async def capture_legacy_candidate_bindings(db, candidates, *, actor=None):
    """Freeze server-recalled parents before fusion can discard their metadata."""
    from uuid import UUID
    parents = set()
    for candidate in candidates:
        for key in ('historical_capa_id', 'source_capa_id', 'capa_id'):
            value = candidate.metadata.get(key)
            if value:
                try:
                    parents.add(UUID(str(value)))
                except (TypeError, ValueError):
                    raise PermissionError('D4_SOURCE_MATERIAL_UNAVAILABLE') from None
    bindings = []
    for report_id in sorted(parents, key=str):
        if actor is not None:
            version = await legacy_capa_read_binding(db, actor, report_id)
        else:
            await require_legacy_root_only(db, report_id)
            version = await material_version(db, report_id)
        bindings.append((str(report_id), version))
    return tuple(bindings)


async def require_legacy_candidate_bindings(db, bindings, *, actor=None):
    for report_id, original in bindings:
        from uuid import UUID
        report_id = UUID(str(report_id))
        if actor is not None:
            current = await legacy_capa_read_binding(db, actor, report_id)
        else:
            await require_legacy_root_only(db, report_id)
            current = await material_version(db, report_id)
        if current != original:
            raise PermissionError('D4_SOURCE_MATERIAL_CHANGED')


async def legacy_recommendation_binding(db, actor, report_id):
    await require_current_egress_statement(db)
    from app.core.permissions import Module
    from app.services.capa_current_access import current_module_access
    scope = SimpleNamespace(user=actor)
    factories, lines = await current_capa_actor_access(db, actor.user_id, PermissionLevel.VIEW)
    await current_capa_target_metadata(db, report_id, factories, lines)
    await current_module_access(db, scope, Module.FMEA, PermissionLevel.VIEW)
    await require_legacy_root_only(db, report_id)
    return await material_version(db, report_id)


async def legacy_capa_read_binding(db, actor, report_id, *, required_level=PermissionLevel.VIEW):
    await require_current_egress_statement(db)
    factories, lines = await current_capa_actor_access(db, actor.user_id, required_level)
    await current_capa_target_metadata(db, report_id, factories, lines)
    await require_legacy_root_only(db, report_id)
    return await material_version(db, report_id)


async def embedding_source_report_id(db, entity_type, entity_id):
    report_id = entity_id if entity_type == 'capa' else None
    if entity_type == 'capa_lesson':
        from app.models.capa_lesson import CapaLessonLearned
        report_id = await db.scalar(select(CapaLessonLearned.capa_id).where(CapaLessonLearned.lesson_id == entity_id))
    elif entity_type == 'knowledge_entry':
        from app.models.knowledge_entry import KnowledgeEntry
        report_id = await db.scalar(select(KnowledgeEntry.source_id).where(
            KnowledgeEntry.entry_id == entity_id, KnowledgeEntry.source_type == 'capa'))
    return report_id


async def require_legacy_embedding_source(db, entity_type, entity_id):
    report_id = await embedding_source_report_id(db, entity_type, entity_id)
    if report_id is not None:
        await require_legacy_root_only(db, report_id)


async def authorize_root(db, actor_id, report_id, required_level=PermissionLevel.VIEW):
    """Authorize target and every inherited source before any protected body SELECT."""
    factories, lines = await current_capa_actor_access(db, actor_id, required_level)
    target = await current_capa_target_metadata(db, report_id, factories, lines)
    from app.services.capa_legacy_capture import authorize_bound_sources
    await authorize_bound_sources(db,actor_id,report_id,d_step="d4")
    revision, sources = await root_metadata(db, report_id)
    from app.services.fmea_agent_sources import visible_fmea_source
    scope = SimpleNamespace(user=SimpleNamespace(user_id=actor_id))
    for source in sources:
        if source.kind == 'fmea_projection':
            visible = await visible_fmea_source(db, scope, source.fmea_id)
            if (visible.factory_id != source.factory_id or visible.product_line_code != source.product_line_code):
                raise PermissionError('D4_MATERIAL_UNAVAILABLE')
        elif source.kind == 'report_snapshot':
            if source.object_id != report_id:
                raise PermissionError('D4_MATERIAL_UNAVAILABLE')
            if source.factory_id != target.factory_id or source.product_line_code != target.product_line_code:
                raise PermissionError('D4_MATERIAL_UNAVAILABLE')
        else:
            raise PermissionError('D4_MATERIAL_UNAVAILABLE')
    from app.services.capa_r6_local_closure import authorize_local_current_sources
    await authorize_local_current_sources(db, actor_id, report_id)
    return revision, sources


async def read_root(db, actor_id, report_id):
    before = await authorize_root(db, actor_id, report_id)
    with db.no_autoflush:
        text = await db.scalar(select(CAPAEightD.d4_root_cause).where(CAPAEightD.report_id == report_id))
    if before[0] is not None:
        snapshot = await db.scalar(select(CapaR6RootRevisionBody.body).where(
            CapaR6RootRevisionBody.revision_id == before[0].revision_id))
        if snapshot is not None:
            from app.services.capa_d4_provenance import current_field_namespace, field_hmac
            namespace = await current_field_namespace(db)
            digest = field_hmac(settings.SECRET_KEY.encode(), namespace, report_id, text)
            if snapshot != (text or '') or not hmac.compare_digest(digest, before[0].field_hmac):
                raise PermissionError('D4_MATERIAL_UNAVAILABLE')
    after = await authorize_root(db, actor_id, report_id)
    if (before[0].revision_id if before[0] else None) != (after[0].revision_id if after[0] else None):
        raise PermissionError('D4_MATERIAL_UNAVAILABLE')
    return text


async def bump_material(db, report_id):
    from sqlalchemy.dialects.postgresql import insert
    statement = insert(CapaR6MaterialVersion).values(report_id=report_id, counter=1)
    await db.execute(statement.on_conflict_do_update(
        index_elements=[CapaR6MaterialVersion.report_id],
        set_={'counter': CapaR6MaterialVersion.counter + 1}))
    await db.flush()


async def material_version(db, report_id, *, include_entry_epoch=True):
    from app.services.capa_d4_provenance import current_field_namespace
    namespace = await current_field_namespace(db)
    counter = await db.scalar(select(CapaR6MaterialVersion.counter).where(CapaR6MaterialVersion.report_id == report_id))
    epoch = await db.scalar(select(CapaR6EntrySwitch.epoch).order_by(CapaR6EntrySwitch.epoch.desc()).limit(1))
    # Optimistic employee forms bind the *current* source parents, while immutable
    # origins retain their historic capture epochs. No graph or body is read.
    revision, sources = await root_metadata(db, report_id)
    from app.models.fmea import FMEADocument
    parents = []
    for fmea_id in sorted({source.fmea_id for source in sources if source.kind == 'fmea_projection'}, key=str):
        row = (await db.execute(select(FMEADocument.fmea_id, FMEADocument.lock_version,
            FMEADocument.factory_id, FMEADocument.product_line_code).where(FMEADocument.fmea_id == fmea_id))).one_or_none()
        if row is None:
            parents.append(dict(kind='missing', fmea_id=str(fmea_id)))
        elif type(row.lock_version) is not int or row.lock_version < 0:
            raise PermissionError('D4_MATERIAL_UNAVAILABLE')
        else:
            parents.append(dict(kind='present', fmea_id=str(row.fmea_id), epoch=row.lock_version,
                factory_id=str(row.factory_id), product_line_code=row.product_line_code))
    from app.services.capa_legacy_capture import current_capture_material
    captured = await current_capture_material(db,report_id)
    payload=dict(namespace=namespace, report_id=str(report_id), counter=counter or 0,
        root_revision_id=None if revision is None else str(revision.revision_id),
        source_ids=sorted(str(source.source_id) for source in sources), source_parents=parents)
    if include_entry_epoch:payload['switch_epoch']=epoch or 0
    if captured:payload['legacy_captures']=captured
    value=json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
    domain=b'openqms.r6.material.v2\n' if include_entry_epoch else b'openqms.r6.semantic-material.v1\n'
    return hmac.new(settings.SECRET_KEY.encode(),domain+value,hashlib.sha256).hexdigest()


async def append_root_body(db, revision, text, added_source_ids=()):
    """Caller holds parent lock. Sources accumulate even for manual replace/clear."""
    previous = await db.scalar(select(CapaR6RootRevisionBody).join(CapaD4RootCauseRevision,
        CapaD4RootCauseRevision.revision_id == CapaR6RootRevisionBody.revision_id).where(
        CapaR6RootRevisionBody.report_id == revision.report_id).order_by(
        CapaD4RootCauseRevision.revision_no.desc()).limit(1))
    inherited = set((await db.scalars(select(CapaR6RootRevisionSource.source_id).where(
        CapaR6RootRevisionSource.revision_id == previous.revision_id))).all()) if previous else set()
    ids = inherited | set(added_source_ids)
    db.add(CapaR6RootRevisionBody(revision_id=revision.revision_id, report_id=revision.report_id,
        body=text or '', binding_state='controlled' if ids else 'legacy_unattested',
        predecessor_id=previous.revision_id if previous else None, source_count=len(ids), origin_digest=origin_digest(ids)))
    await db.flush()
    for source_id in ids:
        db.add(CapaR6RootRevisionSource(revision_id=revision.revision_id, report_id=revision.report_id, source_id=source_id))
    if ids:
        from app.services.embedding_outbox import enqueue_embedding
        coordinates = (await db.execute(select(CAPAEightD.factory_id, CAPAEightD.product_line_code).where(
            CAPAEightD.report_id == revision.report_id))).one()
        await enqueue_embedding(db, 'capa', revision.report_id, coordinates.product_line_code, coordinates.factory_id)
        from app.models.capa_lesson import CapaLessonLearned
        from app.models.knowledge_entry import KnowledgeEntry
        lessons = await db.scalars(select(CapaLessonLearned.lesson_id).where(CapaLessonLearned.capa_id == revision.report_id))
        for lesson_id in lessons:
            await enqueue_embedding(db, 'capa_lesson', lesson_id, coordinates.product_line_code, coordinates.factory_id)
        entries = (await db.execute(select(KnowledgeEntry.entry_id, KnowledgeEntry.content_hash).where(
            KnowledgeEntry.source_type == 'capa', KnowledgeEntry.source_id == revision.report_id))).all()
        for entry_id, content_hash in entries:
            await enqueue_embedding(db, 'knowledge_entry', entry_id, coordinates.product_line_code,
                coordinates.factory_id, content_hash=content_hash)
    await bump_material(db, revision.report_id)


async def require_root_freshness(db, actor_id, report_id):
    """New use/delivery only; stale origins never hide authorized history."""
    revision, sources = await authorize_root(db, actor_id, report_id)
    from app.services.fmea_agent_sources import visible_fmea_source, failure_cause_version
    from app.models.capa_r6 import CapaR6ReportSnapshot
    scope = SimpleNamespace(user=SimpleNamespace(user_id=actor_id))
    for source in sources:
        if source.kind == 'fmea_projection':
            visible = await visible_fmea_source(db, scope, source.fmea_id)
            current = await failure_cause_version(db, visible, source.node_id)
            if current != source.version:
                raise PermissionError('D4_MATERIAL_STALE')
            from app.models.fmea import FMEADocument
            counter = await db.scalar(select(FMEADocument.lock_version).where(FMEADocument.fmea_id == source.fmea_id))
            if (type(source.source_version_counter) is not int or type(counter) is not int
                    or source.source_version_counter < 0 or source.source_version_counter != counter):
                raise PermissionError('D4_MATERIAL_STALE')
        else:
            kind = await db.scalar(select(CapaR6ReportSnapshot.kind).where(
                CapaR6ReportSnapshot.snapshot_id == source.snapshot_id,
                CapaR6ReportSnapshot.report_id == report_id))
            if kind is None:
                raise PermissionError('D4_MATERIAL_UNAVAILABLE')
            latest = await db.scalar(select(CapaR6ReportSnapshot.version).where(
                CapaR6ReportSnapshot.report_id == report_id,
                CapaR6ReportSnapshot.kind == kind).order_by(CapaR6ReportSnapshot.version.desc()).limit(1))
            if str(latest) != source.version:
                raise PermissionError('D4_MATERIAL_STALE')
    return revision, sources


async def capture_fmea_origin(db, actor_id, report_id, fmea_id, node_id):
    """RW owner holds CAPA first; source parent fences hash AND capture epoch."""
    from app.models.fmea import FMEADocument
    from app.services.fmea_agent_sources import visible_fmea_source, failure_cause_version
    factories, lines = await current_capa_actor_access(db, actor_id, PermissionLevel.VIEW)
    await current_capa_target_metadata(db, report_id, factories, lines)
    scope = SimpleNamespace(user=SimpleNamespace(user_id=actor_id))
    await visible_fmea_source(db, scope, fmea_id)
    await db.scalar(select(FMEADocument.fmea_id).where(FMEADocument.fmea_id == fmea_id).with_for_update())
    visible = await visible_fmea_source(db, scope, fmea_id)
    version = await failure_cause_version(db, visible, node_id)
    counter = await db.scalar(select(FMEADocument.lock_version).where(FMEADocument.fmea_id == fmea_id))
    if type(counter) is not int or counter < 0:
        raise PermissionError('D4_MATERIAL_UNAVAILABLE')
    existing = await db.scalar(select(CapaR6SourceOrigin).where(
        CapaR6SourceOrigin.report_id == report_id, CapaR6SourceOrigin.kind == 'fmea_projection',
        CapaR6SourceOrigin.module == 'fmea', CapaR6SourceOrigin.object_id == fmea_id,
        CapaR6SourceOrigin.projection_id == 'fmea.failure_cause.reference.v1',
        CapaR6SourceOrigin.fmea_id == fmea_id, CapaR6SourceOrigin.node_id == node_id,
        CapaR6SourceOrigin.factory_id == visible.factory_id,
        CapaR6SourceOrigin.product_line_code == visible.product_line_code,
        CapaR6SourceOrigin.version == version, CapaR6SourceOrigin.source_version_counter == counter)
        .order_by(CapaR6SourceOrigin.source_id).limit(1))
    if existing is not None:
        return existing
    origin = CapaR6SourceOrigin(report_id=report_id, kind='fmea_projection', module='fmea',
        object_id=fmea_id, projection_id='fmea.failure_cause.reference.v1', version=version,
        source_version_counter=counter, factory_id=visible.factory_id, product_line_code=visible.product_line_code,
        fmea_id=fmea_id, node_id=node_id)
    db.add(origin)
    await db.flush()
    return origin


async def root_review_material(db, report_id, access):
    """Complete review binding using already freshly resolved review authority."""
    from app.core.permissions import Module
    from app.models.fmea import FMEADocument
    revision, sources = await root_metadata(db, report_id)
    if revision is None or await db.scalar(select(CapaR6RootRevisionBody.revision_id).where(
            CapaR6RootRevisionBody.revision_id == revision.revision_id)) is None:
        return None
    if sources:
        if access is None:
            raise PermissionError('CAPA_OUTCOME_REVIEW_ACCESS_DENIED')
        levels, factories, lines = access
        for source in sources:
            if (levels.get(source.module, PermissionLevel.NONE) < PermissionLevel.VIEW
                    or (factories.accessible_factory_ids is not None and source.factory_id not in factories.accessible_factory_ids)
                    or (lines.mode != 'ALL' and source.product_line_code not in (lines.codes or []))):
                raise PermissionError('CAPA_OUTCOME_REVIEW_ACCESS_DENIED')
            if source.module == Module.FMEA:
                coordinates = (await db.execute(select(FMEADocument.factory_id, FMEADocument.product_line_code).where(
                    FMEADocument.fmea_id == source.fmea_id))).one_or_none()
                if coordinates is None or tuple(coordinates) != (source.factory_id, source.product_line_code):
                    raise PermissionError('CAPA_OUTCOME_REVIEW_ACCESS_DENIED')
    return {'revision_id': str(revision.revision_id) if revision else None,
            'origin_digest': origin_digest(s.source_id for s in sources),
            'source_ids': sorted(str(s.source_id) for s in sources),
            'material_version': await material_version(db, report_id)}


async def snapshot_report_input(db, report, kind):
    """Under report lock, persist a per-field version; detects A/B/A changes."""
    from app.models.capa_r6 import CapaR6ReportSnapshot
    latest = await db.scalar(select(CapaR6ReportSnapshot.version).where(
        CapaR6ReportSnapshot.report_id == report.report_id,
        CapaR6ReportSnapshot.kind == kind).order_by(CapaR6ReportSnapshot.version.desc()).limit(1))
    field = {'d2': 'd2_description', 'd3': 'd3_interim'}[kind]
    snapshot = CapaR6ReportSnapshot(report_id=report.report_id, kind=kind,
        version=(latest or 0) + 1, body=getattr(report, field) or '')
    db.add(snapshot)
    await bump_material(db, report.report_id)
    return snapshot

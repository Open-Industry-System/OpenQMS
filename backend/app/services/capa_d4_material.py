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


async def authorize_root(db, actor_id, report_id, required_level=PermissionLevel.VIEW):
    """Authorize target and every inherited source before any protected body SELECT."""
    factories, lines = await current_capa_actor_access(db, actor_id, required_level)
    target = await current_capa_target_metadata(db, report_id, factories, lines)
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


async def material_version(db, report_id):
    from app.services.capa_d4_provenance import current_field_namespace
    namespace = await current_field_namespace(db)
    counter = await db.scalar(select(CapaR6MaterialVersion.counter).where(CapaR6MaterialVersion.report_id == report_id))
    epoch = await db.scalar(select(CapaR6EntrySwitch.epoch).order_by(CapaR6EntrySwitch.epoch.desc()).limit(1))
    value = json.dumps([namespace, str(report_id), counter or 0, epoch or 0], sort_keys=True).encode()
    return hmac.new(settings.SECRET_KEY.encode(), b'openqms.r6.material.v1\n' + value, hashlib.sha256).hexdigest()


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
        else:
            snapshot = await db.get(CapaR6ReportSnapshot, source.snapshot_id)
            if snapshot is None:
                raise PermissionError('D4_MATERIAL_UNAVAILABLE')
            latest = await db.scalar(select(CapaR6ReportSnapshot.version).where(
                CapaR6ReportSnapshot.report_id == report_id,
                CapaR6ReportSnapshot.kind == snapshot.kind).order_by(CapaR6ReportSnapshot.version.desc()).limit(1))
            if str(latest) != source.version:
                raise PermissionError('D4_MATERIAL_STALE')
    return revision, sources


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

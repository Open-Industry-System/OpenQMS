"""Current-authorized, readonly D4 candidates with opaque source versions and safe audit."""
from dataclasses import dataclass, field as dc_field
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
from uuid import UUID

from sqlalchemy import Text, cast, func, select, text

from app import database
from app.config import settings
from app.core.permissions import Module, PermissionLevel
from app.core.tenant_transaction import TenantBinding, TenantUnavailable, bind_business_transaction
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.schemas.capa_d4_text_preview import D4PreviewAvailability, D4PreviewField, D4PreviewSource, D4PreviewVersion, D4TextPreview
from app.services.capa_current_access import capa_target_filters, current_capa_access
from app.services.capa_d4_redaction import RULE_VERSION, redact_text


class PreviewConflict(ValueError):
    def __init__(self): super().__init__('PREVIEW_SOURCE_CHANGED')


class PreviewSourceLimit(ValueError):
    def __init__(self): super().__init__('PREVIEW_SOURCE_LIMIT')


@dataclass(frozen=True)
class Reference:
    object_id: UUID
    node_id: str
    factory_id: UUID
    product_line_code: str
    lock_version: int
    updated_at: str


@dataclass(frozen=True)
class SourceField:
    field: str
    verification_id: UUID | None
    text: str | None = dc_field(repr=False)
    reference: Reference | None = None


@dataclass(frozen=True)
class Snapshot:
    report_id: UUID
    factory_id: UUID
    product_line_code: str
    tenant_id: str
    generation: int
    fields: tuple[SourceField, ...] = dc_field(repr=False)
    canonical: str = dc_field(repr=False)


def _version(value, domain):
    return hmac.new(settings.SECRET_KEY.encode(), (domain+'\0'+value).encode(), hashlib.sha256).hexdigest()


def source_version(snapshot):
    return _version(snapshot.canonical, 'openqms.capa.d4-text-source.v1')


async def _target_meta(db, report_id, factories, lines):
    with db.no_autoflush:
        target = (await db.execute(capa_target_filters(select(CAPAEightD.report_id, CAPAEightD.factory_id,
            CAPAEightD.product_line_code).where(CAPAEightD.report_id == report_id), factories, lines))).one_or_none()
    if target is None: raise LookupError('PREVIEW_TARGET_UNAVAILABLE')
    return target


async def _reference(connection, value, parent):
    if (type(value) is not dict or set(value) != {'fmea_id', 'cause_node_id'}
            or type(value['fmea_id']) is not str or type(value['cause_node_id']) is not str
            or not 1 <= len(value['cause_node_id']) <= 128):
        raise PermissionError('PREVIEW_ACCESS_DENIED')
    try:
        identifier = UUID(value['fmea_id'])
        if str(identifier) != value['fmea_id'] or identifier != parent.fmea_ref_id: raise ValueError
    except (ValueError, TypeError): raise PermissionError('PREVIEW_ACCESS_DENIED') from None
    row = (await connection.execute(text("""
        SELECT fmea_id,factory_id,product_line_code,lock_version,updated_at,
          EXISTS (SELECT 1 FROM jsonb_array_elements(CASE WHEN jsonb_typeof(graph_data->'nodes')='array'
            THEN graph_data->'nodes' ELSE '[]'::jsonb END) n
            WHERE n->>'id'=:node AND n->>'type'='FailureCause') AS present
        FROM fmea_documents WHERE fmea_id=:id
    """), {'id': identifier, 'node': value['cause_node_id']})).one_or_none()
    if (row is None or not row.present or row.factory_id != parent.factory_id
            or row.product_line_code != parent.product_line_code):
        raise PermissionError('PREVIEW_ACCESS_DENIED')
    return Reference(row.fmea_id, value['cause_node_id'], row.factory_id, row.product_line_code,
        row.lock_version, row.updated_at.astimezone(UTC).isoformat())


async def read_snapshot(report_id, *, binding, engine=None):
    if settings.TENANT_MODE == 'single':
        if binding is not None: raise TenantUnavailable('single preview requires public binding')
    elif not isinstance(binding, TenantBinding) or binding.mode != 'business':
        raise TenantUnavailable('business binding required')
    async with (engine or database.engine).connect() as connection:
        async with connection.begin():
            await connection.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
            if binding is None: await connection.execute(text('SET LOCAL search_path TO public, pg_catalog'))
            else: await connection.run_sync(bind_business_transaction, binding)
            parent = (await connection.execute(select(CAPAEightD.report_id, CAPAEightD.factory_id,
                CAPAEightD.product_line_code, CAPAEightD.status, CAPAEightD.fmea_ref_id, CAPAEightD.updated_at,
                func.coalesce(func.octet_length(CAPAEightD.d4_root_cause), 0).label('size'))
                .where(CAPAEightD.report_id == report_id))).one_or_none()
            if parent is None: raise LookupError('PREVIEW_TARGET_UNAVAILABLE')
            child = CapaRootCauseVerification
            size1 = func.coalesce(func.octet_length(child.root_cause_text), 0)
            size2 = func.coalesce(func.octet_length(child.result), 0)
            budget = (await connection.execute(select(func.count().label('count'),
                func.coalesce(func.max(size1), 0).label('first_max'), func.coalesce(func.max(size2), 0).label('second_max'),
                func.coalesce(func.sum(size1+size2), 0).label('total'),
                func.coalesce(func.max(func.octet_length(cast(child.source_ref, Text))), 0).label('ref_max'),
                func.count().filter(child.factory_id != parent.factory_id).label('wrong_factory'))
                .where(child.capa_id == report_id))).one()
            if budget.wrong_factory: raise PermissionError('PREVIEW_ACCESS_DENIED')
            if (budget.count > 200 or max(parent.size, budget.first_max, budget.second_max) > 65536
                    or parent.size+budget.total > 262144 or budget.ref_max > 2048):
                raise PreviewSourceLimit()
            body = await connection.scalar(select(CAPAEightD.d4_root_cause).where(CAPAEightD.report_id == report_id))
            rows = (await connection.execute(select(child.verification_id, child.root_cause_text, child.result,
                child.source_ref, child.updated_at)
                .where(child.capa_id == report_id).order_by(child.verification_id))).all()
            fields = [SourceField('d4_root_cause', None, body)]
            data = {'tenant_id': 'single' if binding is None else str(binding.tenant_id),
                'generation': 0 if binding is None else binding.generation,
                'report_id': str(parent.report_id), 'factory_id': str(parent.factory_id),
                'product_line_code': parent.product_line_code, 'status': parent.status,
                'fmea_ref_id': None if parent.fmea_ref_id is None else str(parent.fmea_ref_id),
                'updated_at': parent.updated_at.astimezone(UTC).isoformat(), 'd4_root_cause': body, 'verifications': []}
            references = {}
            for row in rows:
                ref = None
                if row.source_ref is not None:
                    key = json.dumps(row.source_ref, sort_keys=True)
                    if key not in references: references[key] = await _reference(connection, row.source_ref, parent)
                    ref = references[key]
                fields.extend((SourceField('root_cause_text', row.verification_id, row.root_cause_text, ref),
                    SourceField('result', row.verification_id, row.result, ref)))
                data['verifications'].append({'id': str(row.verification_id), 'root_cause_text': row.root_cause_text,
                    'result': row.result,
                    'source_ref': None if ref is None else {'id': str(ref.object_id), 'node': ref.node_id,
                        'lock_version': ref.lock_version, 'updated_at': ref.updated_at},
                    'updated_at': row.updated_at.astimezone(UTC).isoformat()})
            return Snapshot(parent.report_id, parent.factory_id, parent.product_line_code,
                data['tenant_id'], data['generation'], tuple(fields),
                json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')))


def _admit(snapshot, levels, factories, lines):
    if ((factories.accessible_factory_ids is not None and snapshot.factory_id not in factories.accessible_factory_ids)
            or (lines.mode != 'ALL' and snapshot.product_line_code not in (lines.codes or []))):
        raise PermissionError('PREVIEW_ACCESS_DENIED')
    for field in snapshot.fields:
        ref = field.reference
        if ref is not None and (levels.get(Module.FMEA, PermissionLevel.NONE) < PermissionLevel.VIEW
                or (factories.accessible_factory_ids is not None and ref.factory_id not in factories.accessible_factory_ids)
                or (lines.mode != 'ALL' and ref.product_line_code not in (lines.codes or []))):
            raise PermissionError('PREVIEW_ACCESS_DENIED')


async def _current(db, scope, report_id):
    levels, factories, lines = await current_capa_access(db, scope)
    target = await _target_meta(db, report_id, factories, lines)
    snapshot = await read_snapshot(report_id, binding=db.info.get('tenant_binding'))
    _admit(snapshot, levels, factories, lines)
    if (snapshot.factory_id, snapshot.product_line_code) != (target.factory_id, target.product_line_code):
        raise PreviewConflict()
    return snapshot


async def _final(db, scope, initial):
    current = await _current(db, scope, initial.report_id)
    levels, factories, lines = await current_capa_access(db, scope)
    target = await _target_meta(db, initial.report_id, factories, lines)
    _admit(current, levels, factories, lines)
    if (source_version(current) != source_version(initial)
            or (current.factory_id, current.product_line_code) != (target.factory_id, target.product_line_code)):
        raise PreviewConflict()


async def availability(db, scope, report_id):
    _, factories, lines = await current_capa_access(db, scope)
    await _target_meta(db, report_id, factories, lines)
    return D4PreviewAvailability()


async def get_version(db, scope, report_id):
    snapshot = await _current(db, scope, report_id)
    await _final(db, scope, snapshot)
    return D4PreviewVersion(report_id=report_id, source_version=source_version(snapshot))


async def create_preview(db, scope, report_id, request):
    snapshot = await _current(db, scope, report_id)
    fields = []
    for value in snapshot.fields:
        redacted = redact_text(value.text, tuple(request.replacement_terms))
        ref = value.reference
        source = None if ref is None else D4PreviewSource(object_id=ref.object_id, node_id=ref.node_id,
            version=_version(json.dumps({'id': str(ref.object_id), 'node': ref.node_id,
                'lock_version': ref.lock_version, 'updated_at': ref.updated_at}, sort_keys=True),
                'openqms.capa.d4-fmea-reference.v1'))
        fields.append(D4PreviewField(field=value.field, verification_id=value.verification_id,
            redacted_text=redacted.text, match_counts=dict(redacted.match_counts),
            source_status='unverified' if ref is None else 'validated_reference', source_ref=source))
    await _final(db, scope, snapshot)
    now = datetime.now(UTC)
    version = source_version(snapshot)
    output = D4TextPreview(report_id=report_id, source_version=version, generated_at=now,
        expires_at=now+timedelta(seconds=30), fields=fields)
    db.add(AuditLog(table_name='capa_eightd', record_id=report_id, operated_by=scope.user.user_id,
        factory_id=snapshot.factory_id, action='PREVIEW_CAPA_D4_TEXT', changed_fields={
            'report_id': str(report_id), 'rule_version': RULE_VERSION, 'source_version': version, 'outcome': 'generated'}))
    await db.commit()
    return output

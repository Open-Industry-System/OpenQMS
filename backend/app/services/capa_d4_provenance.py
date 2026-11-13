"""Root-field revision metadata only; no proof signing or body authorization."""
import hashlib
import hmac
import json
from uuid import UUID, uuid4

from sqlalchemy import select

from app.config import settings
from app.models.capa import CAPAEightD
from app.models.capa_d4_delivery import CapaD4RootCauseRevision
from app.services.capa_current_access import current_capa_access, capa_target_filters, require_business_namespace
from app.services.agent.permissions.derived_sources import SourceRevisionConflict


def field_hmac(key, namespace, report_id, text):
    """Hash exact text under a validated, server-owned typed namespace."""
    if not isinstance(namespace, dict):
        raise ValueError('Invalid field namespace')
    if namespace == {'kind': 'single_public'}:
        pass
    elif set(namespace) == {'kind', 'tenant_id'} and namespace['kind'] == 'tenant':
        try:
            tenant_id = UUID(namespace['tenant_id'])
        except (ValueError, TypeError, AttributeError):
            raise ValueError('Invalid field namespace') from None
        if tenant_id.int == 0 or str(tenant_id) != namespace['tenant_id']:
            raise ValueError('Invalid field namespace')
    else:
        raise ValueError('Invalid field namespace')
    encoded = json.dumps({'namespace': namespace, 'report': str(report_id),
        'is_null': text is None, 'text': text}, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode('utf-8')
    return hmac.new(key, b'openqms.capa.root-field.v1\n' + encoded, hashlib.sha256).hexdigest()


async def current_field_namespace(db):
    """Never take a namespace from HTTP, a cached actor scope, or synthetic UUIDs."""
    await require_business_namespace(db)
    if settings.TENANT_MODE == 'single':
        return {'kind': 'single_public'}
    binding = db.info['tenant_binding']
    if not isinstance(binding.tenant_id, UUID) or binding.tenant_id.int == 0:
        raise PermissionError('Business namespace unavailable')
    return {'kind': 'tenant', 'tenant_id': str(binding.tenant_id)}


async def current_report_coordinates(db, actor_scope, report_id):
    """Fresh CAPA VIEW followed by a scope-filtered three-scalar projection."""
    _, factories, lines = await current_capa_access(db, actor_scope)
    with db.no_autoflush:
        row = (await db.execute(capa_target_filters(select(CAPAEightD.report_id,
            CAPAEightD.factory_id, CAPAEightD.product_line_code).where(
            CAPAEightD.report_id == report_id), factories, lines))).one_or_none()
    if row is None:
        raise LookupError('8D report not found')
    return row


async def record_root_revision(db, *, report_id, actor_id, write_path):
    """Caller owns the CAPA parent lock; append in its transaction, never commit.

    Production writers call only after a real field mutation (or initial finding
    creation). Legacy same-value writes therefore do not bootstrap a revision.
    """
    namespace = await current_field_namespace(db)
    # Flush the caller's exact new text before selecting the scalar; no ORM body load.
    await db.flush()
    current = (await db.execute(select(CAPAEightD.d4_root_cause).where(
        CAPAEightD.report_id == report_id))).one_or_none()
    if current is None:
        raise SourceRevisionConflict()
    digest = field_hmac(settings.SECRET_KEY.encode('utf-8'), namespace, report_id, current.d4_root_cause)
    latest = await db.scalar(select(CapaD4RootCauseRevision).where(
        CapaD4RootCauseRevision.report_id == report_id).order_by(
        CapaD4RootCauseRevision.revision_no.desc()).limit(1))
    revision = CapaD4RootCauseRevision(revision_id=uuid4(), report_id=report_id,
        revision_no=latest.revision_no + 1 if latest is not None else 1,
        field_hmac=digest, actor_id=actor_id, write_path=write_path)
    db.add(revision)
    await db.flush()
    return revision

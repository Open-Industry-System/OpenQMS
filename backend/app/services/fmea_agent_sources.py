"""FMEA-owned internal source projection; not a public capability."""
import hashlib
import hmac
import json
from dataclasses import dataclass, field

from sqlalchemy import select, text

from app.config import settings
from app.core.permissions import Module, PermissionLevel
from app.models.fmea import FMEADocument
from app.services.agent.permissions.context_contracts import SourceProjectionContract
from app.services.agent.permissions.derived_sources import SourceUnavailable
from app.services.capa_current_access import current_module_access

FAILURE_CAUSE_REFERENCE = SourceProjectionContract(
    source_projection_id='fmea.failure_cause.reference.v1', owner=Module.FMEA,
    minimum_level=PermissionLevel.VIEW, coords=('fmea_id', 'cause_node_id'),
    version_method='failure_cause_version',
)


@dataclass(frozen=True)
class VisibleFmeaSource:
    fmea_id: object
    factory_id: object
    product_line_code: str
    actor_scope: object = field(repr=False, compare=False)


async def visible_fmea_source(db, actor_scope, fmea_id):
    """Resolve live FMEA authority before selecting only visible coordinates."""
    try:
        _, factories, lines = await current_module_access(db, actor_scope, Module.FMEA, PermissionLevel.VIEW)
        query = select(FMEADocument.fmea_id, FMEADocument.factory_id, FMEADocument.product_line_code).where(
            FMEADocument.fmea_id == fmea_id)
        if factories.accessible_factory_ids is not None:
            query = query.where(FMEADocument.factory_id.in_(factories.accessible_factory_ids))
        if lines.mode != 'ALL':
            query = query.where(FMEADocument.product_line_code.in_(lines.codes or []))
        with db.no_autoflush:
            row = (await db.execute(query)).one_or_none()
        if row is None:
            raise SourceUnavailable()
        return VisibleFmeaSource(row.fmea_id, row.factory_id, row.product_line_code, actor_scope)
    except (PermissionError, LookupError, AttributeError):
        raise SourceUnavailable() from None


_NODES = """WITH nodes AS (
 SELECT n FROM fmea_documents d,
 LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(d.graph_data->'nodes')='array'
 THEN d.graph_data->'nodes' ELSE '[]'::jsonb END) n
 WHERE d.fmea_id=:fmea_id AND n->>'id'=:node_id
) """


async def failure_cause_version(db, visible_source, cause_node_id, *, diagnose_invalid_node=False):
    """Budget and select one node only, rechecking authority before returning.

    Employee declaration creation may request missing/type diagnostics. Runtime
    callers keep the default fixed denial; neither mode skips live authority.
    """
    current = await visible_fmea_source(db, visible_source.actor_scope, visible_source.fmea_id)
    if current != visible_source:
        raise SourceUnavailable()
    params = {'fmea_id': current.fmea_id, 'node_id': cause_node_id}
    try:
        with db.no_autoflush:
            count, size = (await db.execute(text(_NODES +
                'SELECT count(*), max(octet_length(n::text)) FROM nodes'), params)).one()
            if count == 0 and diagnose_invalid_node:
                raise ValueError('Invalid FailureCause node')
            if count != 1 or size is None or size > 64 * 1024:
                raise SourceUnavailable()
            # The document can change between statements under READ COMMITTED.
            # Reapply both guards in the same snapshot as the body read.
            node = (await db.execute(text(_NODES + '''
                SELECT n FROM nodes
                WHERE octet_length(n::text) <= 65536
                  AND (SELECT count(*) FROM nodes) = 1
            '''), params)).scalar_one_or_none()
        if not isinstance(node, dict):
            raise SourceUnavailable()
        if node.get('type') != 'FailureCause':
            if diagnose_invalid_node:
                raise ValueError('Invalid FailureCause node')
            raise SourceUnavailable()
        try:
            encoded = json.dumps(node, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                                 allow_nan=False).encode('utf-8')
        except (ValueError, TypeError, UnicodeError):
            raise SourceUnavailable() from None
        return hmac.new(settings.SECRET_KEY.encode(),
            b'openqms.fmea.failure-cause-node.v1\n' + encoded, hashlib.sha256).hexdigest()
    finally:
        latest = await visible_fmea_source(db, visible_source.actor_scope, visible_source.fmea_id)
        if latest != visible_source:
            raise SourceUnavailable()

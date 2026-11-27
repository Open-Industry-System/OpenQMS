"""Authenticated input lineage for retained ordinary recommendation caches."""
import hashlib
import hmac
import json

from sqlalchemy import select

from app.models.recommendation_cache import RecommendationCache
from app.services.capa_d4_material import require_legacy_candidate_bindings


def _body_digest(cards):
    return hashlib.sha256(json.dumps(cards, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _signature(db, key, header):
    from app.services.agent_runtime.d4_text_delivery import _digest
    binding = db.info.get('tenant_binding')
    namespace = str(binding.tenant_id) if binding else 'public'
    return _digest('openqms.r6.ordinary-cache.v1', dict(namespace=namespace, key=key, header=header))


def seal_cache(db, key, bindings, cards, details):
    header = dict(version=1, cards_digest=_body_digest(cards),
        parents=[list(item) for item in bindings], details=details)
    return dict(header=header, signature=_signature(db, key, header), cards=cards)


async def load_cache(db, key, filters, *, actor):
    """No card SELECT until authenticated parents are currently readable.

    Freeze the exact authenticated envelope in the second statement: an upsert
    at the same cache PK cannot replace the approved input set between reads.
    """
    row = (await db.execute(select(RecommendationCache.cache_id,
        RecommendationCache.suggestions['header'].label('header'),
        RecommendationCache.suggestions['signature'].astext.label('signature')).where(*filters))).one_or_none()
    if row is None or not isinstance(row.header, dict) or not isinstance(row.signature, str):
        return None
    header = row.header
    if (set(header) != {'version', 'cards_digest', 'parents', 'details'}
            or type(header['version']) is not int or header['version'] != 1
            or not isinstance(header['parents'], list) or not isinstance(header['details'], dict)
            or not hmac.compare_digest(row.signature, _signature(db, key, header))):
        return None
    try:
        parents = tuple(tuple(item) for item in header['parents'])
        if (any(len(item) != 2 or not all(isinstance(value, str) for value in item) for item in parents)
                or parents != tuple(sorted(set(parents)))):
            return None
        await require_legacy_candidate_bindings(db, parents, actor=actor)
    except (PermissionError, LookupError, ValueError, TypeError):
        return None
    cards = await db.scalar(select(RecommendationCache.suggestions['cards']).where(
        *filters, RecommendationCache.cache_id == row.cache_id,
        RecommendationCache.suggestions['header'] == header,
        RecommendationCache.suggestions['signature'].astext == row.signature))
    if not isinstance(cards, list) or _body_digest(cards) != header['cards_digest']:
        return None
    await require_legacy_candidate_bindings(db, parents, actor=actor)
    return cards, parents, header['details']

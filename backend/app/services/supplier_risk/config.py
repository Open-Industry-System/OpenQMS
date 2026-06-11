"""Rule configuration CRUD with 4-layer priority resolution.

Priority (highest first):
1. supplier_id + product_line_code (both NOT NULL)
2. supplier_id only (product_line_code IS NULL)
3. product_line_code only (supplier_id IS NULL)
4. Global default (both NULL)
"""
import uuid
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier_risk import SupplierRiskConfig


async def get_effective_configs(
    db: AsyncSession,
    product_line_code: str | None = None,
    supplier_id: uuid.UUID | None = None,
) -> list[SupplierRiskConfig]:
    """Get effective configs for a supplier+product_line, resolving priority layers."""
    results = []
    for rule_id in [f"R{i:02d}" for i in range(1, 11)]:
        config = await _resolve_config(db, rule_id, product_line_code, supplier_id)
        if config:
            results.append(config)
    return results


async def get_effective_configs_batch(
    db: AsyncSession,
    supplier_ids: list[uuid.UUID],
    product_line_code: str | None = None,
) -> dict[uuid.UUID, list[SupplierRiskConfig]]:
    """Batch load effective configs for many suppliers in one query.

    Returns a dict mapping supplier_id → list of effective configs.
    Pure-Python priority resolution avoids per-supplier-per-rule DB round-trips.
    """
    if not supplier_ids:
        return {}

    # Fetch all relevant configs in a single query.
    # We need configs where:
    #   (supplier_id IN supplier_ids AND (PL matches OR NULL)) OR
    #   (supplier_id IS NULL AND (PL matches OR NULL))
    cond = or_(
        and_(
            SupplierRiskConfig.supplier_id.in_(supplier_ids),
            SupplierRiskConfig.product_line_code == product_line_code,
        ),
        and_(
            SupplierRiskConfig.supplier_id.in_(supplier_ids),
            SupplierRiskConfig.product_line_code.is_(None),
        ),
        and_(
            SupplierRiskConfig.supplier_id.is_(None),
            SupplierRiskConfig.product_line_code == product_line_code,
        ),
        and_(
            SupplierRiskConfig.supplier_id.is_(None),
            SupplierRiskConfig.product_line_code.is_(None),
        ),
    )
    result = await db.execute(select(SupplierRiskConfig).where(cond))
    all_configs = list(result.scalars().all())

    # Group by (rule_id, scope) for O(1) lookup
    # scope_key: "s:pl", "s", "pl", "g"
    by_rule_scope: dict[tuple[str, str], list[SupplierRiskConfig]] = {}
    for cfg in all_configs:
        has_s = cfg.supplier_id is not None
        has_pl = cfg.product_line_code is not None
        if has_s and has_pl:
            scope = "s:pl"
        elif has_s:
            scope = "s"
        elif has_pl:
            scope = "pl"
        else:
            scope = "g"
        key = (cfg.rule_id, scope)
        by_rule_scope.setdefault(key, []).append(cfg)

    # Index by (rule_id, supplier_id, scope) for O(1) lookup
    def _get(rule_id: str, scope: str, supplier_id: uuid.UUID | None = None) -> SupplierRiskConfig | None:
        candidates = by_rule_scope.get((rule_id, scope), [])
        if scope == "s:pl" or scope == "s":
            for c in candidates:
                if c.supplier_id == supplier_id:
                    return c
            return None
        # global or pl-only: only one candidate each
        return candidates[0] if candidates else None

    output: dict[uuid.UUID, list[SupplierRiskConfig]] = {}
    rule_ids = [f"R{i:02d}" for i in range(1, 11)]
    for sid in supplier_ids:
        configs: list[SupplierRiskConfig] = []
        for rid in rule_ids:
            cfg = None
            if product_line_code:
                cfg = _get(rid, "s:pl", sid)
            if cfg is None:
                cfg = _get(rid, "s", sid)
            if cfg is None and product_line_code:
                cfg = _get(rid, "pl")
            if cfg is None:
                cfg = _get(rid, "g")
            if cfg:
                configs.append(cfg)
        output[sid] = configs

    return output


async def _resolve_config(
    db: AsyncSession,
    rule_id: str,
    product_line_code: str | None,
    supplier_id: uuid.UUID | None,
) -> SupplierRiskConfig | None:
    """Resolve a single rule's config through the priority chain."""
    # Layer 1: supplier + product_line
    if supplier_id and product_line_code:
        result = await db.execute(
            select(SupplierRiskConfig).where(and_(
                SupplierRiskConfig.rule_id == rule_id,
                SupplierRiskConfig.supplier_id == supplier_id,
                SupplierRiskConfig.product_line_code == product_line_code,
            ))
        )
        cfg = result.scalar_one_or_none()
        if cfg:
            return cfg

    # Layer 2: supplier global override
    if supplier_id:
        result = await db.execute(
            select(SupplierRiskConfig).where(and_(
                SupplierRiskConfig.rule_id == rule_id,
                SupplierRiskConfig.supplier_id == supplier_id,
                SupplierRiskConfig.product_line_code.is_(None),
            ))
        )
        cfg = result.scalar_one_or_none()
        if cfg:
            return cfg

    # Layer 3: product_line default
    if product_line_code:
        result = await db.execute(
            select(SupplierRiskConfig).where(and_(
                SupplierRiskConfig.rule_id == rule_id,
                SupplierRiskConfig.supplier_id.is_(None),
                SupplierRiskConfig.product_line_code == product_line_code,
            ))
        )
        cfg = result.scalar_one_or_none()
        if cfg:
            return cfg

    # Layer 4: global default
    result = await db.execute(
        select(SupplierRiskConfig).where(and_(
            SupplierRiskConfig.rule_id == rule_id,
            SupplierRiskConfig.supplier_id.is_(None),
            SupplierRiskConfig.product_line_code.is_(None),
        ))
    )
    return result.scalar_one_or_none()


async def list_configs(
    db: AsyncSession,
    product_line_code: str | None = None,
    supplier_id: uuid.UUID | None = None,
) -> list[SupplierRiskConfig]:
    """List all configs (raw, for admin UI)."""
    query = select(SupplierRiskConfig)
    if product_line_code:
        query = query.where(SupplierRiskConfig.product_line_code == product_line_code)
    if supplier_id:
        query = query.where(SupplierRiskConfig.supplier_id == supplier_id)
    query = query.order_by(SupplierRiskConfig.rule_id)
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_config(
    db: AsyncSession,
    config_id: uuid.UUID,
    updates: dict,
    user_id: uuid.UUID,
) -> SupplierRiskConfig:
    """Update a rule config."""
    config = await db.get(SupplierRiskConfig, config_id)
    if not config:
        raise ValueError("配置不存在")
    for key, value in updates.items():
        if value is not None and hasattr(config, key):
            setattr(config, key, value)
    config.updated_by = user_id
    await db.commit()
    await db.refresh(config)
    return config

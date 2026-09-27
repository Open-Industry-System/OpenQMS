"""Object-level tenant schema parity against an independently migrated public schema."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.tenant_utils import strict_tenant_search_path_sql
from app.core.tenant_sql_tokens import rewrite_qualifiers, scan_sql

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "alembic_tenant/snapshot/manifest.json"
EXCLUDED = frozenset({"tenants", "tenant_migrations", "platform_admin_users", "reference_templates",
                      "alembic_version", "tenant_schema_version"})


@dataclass(frozen=True)
class SchemaDifference:
    object_type: str
    object_key: str
    expected: str
    actual: str


def load_snapshot_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


def verify_snapshot_checksum(manifest: dict) -> None:
    from alembic_tenant.snapshot.business_20260927 import DDL
    digest = hashlib.sha256("\n".join(DDL).encode()).hexdigest()
    if digest != manifest.get("sha256") or manifest.get("pg_major") != 15:
        raise ValueError("Tenant baseline checksum or PostgreSQL major mismatch")


def _normalize_varchar_arrays(source: str) -> str:
    """Normalize PG15 dump/restore's varchar[]→text[] cast at token boundaries."""
    tokens = scan_sql(source)
    values = [t.text for t in tokens]
    def next_code(i):
        while i < len(tokens) and tokens[i].kind in {"space", "comment"}:
            i += 1
        return i

    for i, token in enumerate(tokens):
        if token.identifier != "array":
            continue
        opening = next_code(i + 1)
        if opening >= len(tokens) or values[opening] != "[":
            continue
        depth, closing = 1, opening + 1
        while closing < len(tokens) and depth:
            if values[closing] == "[": depth += 1
            if values[closing] == "]": depth -= 1
            closing += 1
        if depth:
            continue
        suffix = []
        pos = next_code(closing)
        for part in (":", ":", "text", "[", "]"):
            if pos >= len(tokens) or values[pos].lower() != part:
                break
            suffix.append(pos)
            pos = next_code(pos + 1)
        if len(suffix) != 5:
            continue
        casts = []
        for j in range(opening + 1, closing - 1):
            if values[j] != ":":
                continue
            second = next_code(j + 1)
            typ = next_code(second + 1)
            varying = next_code(typ + 1)
            if (second < len(tokens) and values[second] == ":" and typ < len(tokens)
                    and tokens[typ].identifier == "character" and varying < len(tokens)
                    and tokens[varying].identifier == "varying"):
                casts.append(varying)
        if casts:
            for j in casts:
                values[j] += "::text"
            for j in suffix:
                values[j] = ""
    return "".join(values)


def _normalize(value: object, schema: str) -> str:
    result = str(value) if value is not None else "<null>"
    # pg_dump recreates varchar literal arrays with equivalent element casts.
    # Only rewrite SQL tokens, never quoted literals containing array-like text.
    result = _normalize_varchar_arrays(result)
    return rewrite_qualifiers(result, schema, shared_public=frozenset({"vector", "vector_cosine_ops"}),
                              canonicalize_shared_digest=True, collapse_space=True)


async def _objects(connection: AsyncConnection, schema: str) -> dict[tuple[str, str], str]:
    query = text("""
        SELECT 'table' AS kind, c.relname::text AS key, c.relkind::text AS definition
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=:schema AND c.relkind IN ('r','p') AND c.relname <> ALL(:excluded)
        UNION ALL
        SELECT 'column', c.relname||'.'||a.attname,
          pg_catalog.format_type(a.atttypid,a.atttypmod)||'|'||a.attnotnull::text||'|'||
          coalesce(pg_get_expr(d.adbin,d.adrelid),'')||'|'||a.attidentity::text||'|'||a.attgenerated::text
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
        LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
        WHERE n.nspname=:schema AND c.relkind IN ('r','p') AND c.relname <> ALL(:excluded)
        UNION ALL
        SELECT 'constraint', c.relname||'.'||con.conname, con.contype::text||'|'||
          pg_get_constraintdef(con.oid,true)||'|'||con.condeferrable::text||'|'||con.condeferred::text
        FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=:schema AND c.relname <> ALL(:excluded)
        UNION ALL
        SELECT 'index', tab.relname||'.'||idx.relname, pg_get_indexdef(idx.oid)||'|'||
            i.indisvalid::text||'|'||i.indisready::text
        FROM pg_index i JOIN pg_class idx ON idx.oid=i.indexrelid
        JOIN pg_class tab ON tab.oid=i.indrelid
        JOIN pg_namespace n ON n.oid=tab.relnamespace
        WHERE n.nspname=:schema AND tab.relname <> ALL(:excluded)
        UNION ALL
        SELECT 'function', p.proname||'('||pg_get_function_identity_arguments(p.oid)||')', pg_get_functiondef(p.oid)
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname=:schema AND NOT EXISTS (
            SELECT 1 FROM pg_depend d WHERE d.objid=p.oid AND d.classid='pg_proc'::regclass AND d.deptype='e')
        UNION ALL
        SELECT 'trigger', c.relname||'.'||t.tgname, pg_get_triggerdef(t.oid,true)
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=:schema AND NOT t.tgisinternal AND c.relname <> ALL(:excluded)
        UNION ALL
        SELECT 'text_search_config', cfg.cfgname, cfg.cfgparser::regproc::text||'|'||
            coalesce((SELECT string_agg(m.maptokentype::text||':'||m.mapseqno::text||':'||dict.dictname,
                                        ',' ORDER BY m.maptokentype,m.mapseqno)
                      FROM pg_ts_config_map m JOIN pg_ts_dict dict ON dict.oid=m.mapdict
                      WHERE m.mapcfg=cfg.oid),'')
        FROM pg_ts_config cfg JOIN pg_namespace n ON n.oid=cfg.cfgnamespace
        WHERE n.nspname=:schema
    """)
    rows = (await connection.execute(query, {"schema": schema, "excluded": list(EXCLUDED)})).all()
    return {(kind, key): _normalize(definition, schema) for kind, key, definition in rows}


async def compare_business_schema(connection: AsyncConnection, reference_schema: str, tenant_schema: str,
                                  manifest: dict) -> list[SchemaDifference]:
    if reference_schema != "public":
        raise ValueError("Only canonical public schema is a supported reference")
    strict_tenant_search_path_sql(tenant_schema)
    verify_snapshot_checksum(manifest)
    reference = await _objects(connection, reference_schema)
    tenant = await _objects(connection, tenant_schema)
    return [SchemaDifference(kind, key, reference.get((kind, key), "<missing>"),
                             tenant.get((kind, key), "<missing>"))
            for kind, key in sorted(reference.keys() | tenant.keys()) if reference.get((kind, key)) != tenant.get((kind, key))]

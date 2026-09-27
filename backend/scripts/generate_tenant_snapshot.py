"""Development-only PostgreSQL 15 tenant DDL snapshot generator.

Run against a newly migrated disposable _test database; never against a live tenant.
The generated Python and manifest are reviewed and committed, never generated at runtime.
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlparse

EXCLUDED_PLATFORM_TABLES = frozenset({
    "tenants", "tenant_migrations", "platform_admin_users", "reference_templates", "alembic_version",
})
BASE = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class TocEntry:
    type: str
    schema: str
    name: str
    dependencies: tuple[str, ...] = ()
    ddl: tuple[str, ...] = ()


def _command(program: str) -> list[str]:
    """Use PostgreSQL 15 tools, optionally in the disposable DB's Docker container."""
    container = os.environ.get("PG15_CONTAINER")
    return ["docker", "exec", "-i", container, program] if container else [program]


def _run(program: str, *args: str, input: bytes | None = None) -> bytes:
    command = _command(program)
    version = subprocess.run(command + ["--version"], capture_output=True, check=True).stdout
    if not re.search(rb"\b15\.\d+\b", version):
        raise RuntimeError(f"PostgreSQL 15 tool required: {version!r}")
    return subprocess.run(command + list(args), input=input, capture_output=True, check=True).stdout


def pg_dump_custom(url: str, schema: str, schema_only: bool = True) -> bytes:
    parsed = urlparse(url.replace("postgresql+asyncpg://", "postgresql://"))
    if not parsed.path.lstrip("/").endswith("_test"):
        raise ValueError("Snapshot generator only accepts a disposable _test database")
    if schema != "public" or not schema_only:
        raise ValueError("Only public schema-only archives are permitted")
    # docker exec talks to the container's own DB. Locally, libpq uses the URL.
    if os.environ.get("PG15_CONTAINER"):
        if parsed.hostname not in {"localhost", "127.0.0.1"} or (parsed.port or 5432) != 5432:
            raise ValueError("Container pg_dump requires a local port-5432 disposable DB URL")
        return _run("pg_dump", "-U", parsed.username or "qms", "-d", parsed.path.lstrip("/"),
                    "--schema=public", "--schema-only", "--no-owner", "--no-acl", "-Fc")
    env = os.environ.copy()
    env["PGPASSWORD"] = parsed.password or ""
    command = _command("pg_dump")
    if b"15." not in subprocess.run(command + ["--version"], capture_output=True, check=True).stdout:
        raise RuntimeError("PostgreSQL 15 pg_dump required")
    return subprocess.run(command + ["--dbname", parsed.path.lstrip("/"),
                                     "--host", parsed.hostname or "localhost", "--port", str(parsed.port or 5432),
                                     "--username", parsed.username or "qms", "--schema=public",
                                     "--schema-only", "--no-owner", "--no-acl", "-Fc"],
                          env=env, capture_output=True, check=True).stdout


def _split_sql(source: str) -> tuple[str, ...]:
    """Split statements while preserving PL/pgSQL dollar-quoted function bodies."""
    statements, buf = [], []
    quote = None
    i = 0
    while i < len(source):
        char = source[i]
        if quote == "'":
            if char == "'" and source[i:i + 2] == "''":
                buf.append("''"); i += 2; continue
            if char == "'": quote = None
        elif quote == '"':
            if char == '"' and source[i:i + 2] == '""':
                buf.append('""'); i += 2; continue
            if char == '"': quote = None
        elif quote and quote.startswith("$"):
            if source.startswith(quote, i):
                buf.append(quote); i += len(quote); quote = None; continue
        else:
            token = re.match(r"\$[A-Za-z_0-9]*\$", source[i:]) if char == "$" else None
            if token:
                quote = token.group(); buf.append(quote); i += len(quote); continue
            if char in ("'", '"'): quote = char
            if char == ";":
                statement = "".join(buf).strip()
                if statement: statements.append(statement + ";")
                buf = []; i += 1; continue
        buf.append(char)
        i += 1
    if quote or "".join(buf).strip():
        raise ValueError("Non-terminated or trailing SQL statement")
    return tuple(statements)


def pg_restore_list(archive: bytes) -> list[TocEntry]:
    listing = _run("pg_restore", "--list", input=archive).decode()
    sql = _run("pg_restore", "--schema-only", "--no-owner", "--no-acl", "--file=-", input=archive).decode()
    toc = []
    for line in listing.splitlines():
        match = re.match(r"^\d+; \d+ \d+ (.+?) public (.+?) (?:\S+)$", line)
        if not match:
            if line.startswith(";") or not line.strip() or " SCHEMA - public " in line or " COMMENT - SCHEMA public " in line:
                continue
            raise ValueError(f"Unrecognized pg_restore TOC entry: {line}")
        kind, name = match.groups()
        if kind not in {"TABLE", "FUNCTION", "TEXT SEARCH CONFIGURATION", "COMMENT", "CHECK CONSTRAINT",
                        "CONSTRAINT", "FK CONSTRAINT", "INDEX", "TRIGGER"}:
            raise ValueError(f"Unknown schema object type: {kind} {name}")
        toc.append(TocEntry(kind, "public", name))
    # pg_restore emits TOC entries in dependency order. Block boundaries are its
    # own Name/Type/Schema headers; SQL is split only after selecting each block.
    blocks = re.split(r"(?m)^--\n-- Name: (.*?); Type: (.*?); Schema: public; Owner: -\n--\n", sql)
    mapping = {}
    for j in range(1, len(blocks), 3):
        name, kind, raw = blocks[j:j + 3]
        raw = "\n".join(line for line in raw.splitlines() if not line.startswith(("--", "\\")))
        statements = tuple(stmt for stmt in _split_sql(raw) if not stmt.startswith(("SET ", "SELECT ", "\\")))
        mapping[(kind, name)] = statements
    result = []
    for entry in toc:
        ddl = mapping.get((entry.type, entry.name))
        if ddl is None:
            raise ValueError(f"Missing DDL for {entry.type} {entry.name}")
        deps = tuple(sorted(set(re.findall(r"\b(?:ON|REFERENCES|TABLE|FUNCTION)\s+(?:ONLY\s+)?public\.([a-z_][a-z_0-9]*)", " ".join(ddl), re.I))))
        result.append(TocEntry(entry.type, entry.schema, entry.name, deps, ddl))
    return result


def select_business_objects(toc: list[TocEntry], excluded_platform_tables: frozenset[str]) -> list[TocEntry]:
    selected = []
    for obj in toc:
        if obj.type not in {"TABLE", "FUNCTION", "TEXT SEARCH CONFIGURATION", "COMMENT", "CHECK CONSTRAINT",
                            "CONSTRAINT", "FK CONSTRAINT", "INDEX", "TRIGGER"}:
            raise ValueError(f"Unknown schema object type: {obj.type} {obj.name}")
        owner = obj.name.split()[0]
        if obj.type == "COMMENT" and obj.name.startswith("COLUMN "):
            owner = obj.name.removeprefix("COLUMN ").split(".", 1)[0]
        if owner in excluded_platform_tables or any(d in excluded_platform_tables for d in obj.dependencies):
            continue
        if obj.type == "INDEX" and not obj.dependencies:
            raise ValueError(f"Index without owning relation: {obj.name}")
        if obj.type in {"CONSTRAINT", "FK CONSTRAINT", "CHECK CONSTRAINT", "TRIGGER"} and not obj.dependencies:
            raise ValueError(f"Dependent object without owning relation: {obj.type} {obj.name}")
        if any(re.search(r"\b(?:ON|REFERENCES|TABLE)\s+(?:ONLY\s+)?public\." + name + r"\b", " ".join(obj.ddl), re.I)
               for name in excluded_platform_tables):
            raise ValueError(f"Unexpected platform DDL dependency: {obj.name}")
        selected.append(obj)
    return selected


def _statements(objects: list[TocEntry]) -> tuple[str, ...]:
    result = []
    business_names = {obj.name for obj in objects if obj.type in {"TABLE", "TEXT SEARCH CONFIGURATION"}}
    business_names.update(obj.name.split("(", 1)[0] for obj in objects if obj.type == "FUNCTION")
    shared_names = {"vector", "vector_cosine_ops", "digest"}
    for obj in objects:
        for statement in obj.ddl:
            references = set(re.findall(r"\bpublic\.([A-Za-z_][A-Za-z_0-9]*)", statement))
            if unknown := references - business_names - shared_names:
                raise ValueError(f"Unreviewed public reference: {obj.name}: {sorted(unknown)}")
            # pg_dump's schema-qualified business references must resolve in the
            # verified tenant search_path, never public. The pgcrypto digest
            # extension is shared and explicitly schema-qualified instead.
            sql = statement.replace("public.vector_cosine_ops", "__SHARED_VECTOR_COSINE_OPS__")
            sql = sql.replace("public.vector(", "__SHARED_VECTOR_TYPE__(")
            sql = sql.replace("public.", "")
            sql = sql.replace("__SHARED_VECTOR_COSINE_OPS__", "public.vector_cosine_ops")
            sql = sql.replace("__SHARED_VECTOR_TYPE__", "public.vector")
            if obj.type == "FUNCTION" and obj.name == "verify_version_hash()":
                sql = sql.replace("digest(payload::text", "public.digest(payload::text")
            unexpected = re.findall(r"public\.([A-Za-z_][A-Za-z_0-9]*)", sql)
            if any(name not in {"vector", "vector_cosine_ops", "digest"} for name in unexpected):
                raise ValueError(f"Unreviewed public reference: {obj.name}: {unexpected}")
            if not sql.startswith(("CREATE ", "ALTER TABLE ", "ALTER TEXT SEARCH CONFIGURATION ", "COMMENT ON ")):
                raise ValueError(f"Unexpected DDL: {sql[:100]}")
            result.append(sql)
    return tuple(result)


def write_versioned_ddl(objects: list[TocEntry], output: str) -> None:
    statements = _statements(objects)
    payload = '"""Frozen tenant business DDL from canonical PostgreSQL 15 public head. Do not edit manually."""\n\nDDL = (\n'
    payload += "".join(f"    {statement!r},\n" for statement in statements) + ")\n"
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(payload)


def write_snapshot_manifest(objects: list[TocEntry], source_commit: str, public_head: str, pg_major: int) -> dict:
    statements = _statements(objects)
    manifest = {"source_commit": source_commit, "public_head": public_head, "pg_major": pg_major,
                "object_keys": [f"{o.type}:{o.name}" for o in objects],
                "sha256": hashlib.sha256("\n".join(statements).encode()).hexdigest()}
    destination = BASE / "alembic_tenant/snapshot/manifest.json"
    destination.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest


def generate_snapshot(canonical_database_url: str, source_commit: str, public_head: str) -> dict:
    archive = pg_dump_custom(canonical_database_url, "public", schema_only=True)
    objects = pg_restore_list(archive)
    selected = select_business_objects(objects, EXCLUDED_PLATFORM_TABLES)
    from app.database import TenantBase
    import app.models  # noqa: F401
    model_tables = {table.name for table in TenantBase.metadata.tables.values()}
    snapshot_tables = {item.name for item in selected if item.type == "TABLE"}
    if missing := model_tables - snapshot_tables:
        raise ValueError(f"Canonical public schema is missing TenantBase tables: {sorted(missing)}")
    write_versioned_ddl(selected, str(BASE / "alembic_tenant/snapshot/business_20260927.py"))
    return write_snapshot_manifest(selected, source_commit, public_head, pg_major=15)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database_url", help="disposable _test database, already migrated to public head")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--public-head", required=True)
    args = parser.parse_args()
    print(json.dumps(generate_snapshot(args.database_url, args.source_commit, args.public_head), indent=2))

"""Migration script: convert existing single-tenant deployment to multi-tenant.

Steps (per design spec):
1. Backup public.alembic_version
2. CREATE SCHEMA tenant_default
3. ALTER TABLE ... SET SCHEMA tenant_default (all business objects + ENUMs + sequences)
4. alembic -x schema=tenant_default stamp tenant@head
5. Clear public.alembic_version
6. alembic upgrade platform@head
7. INSERT INTO public.tenants (...) VALUES (...)
8. Set TENANT_MODE=production

IMPORTANT: Steps 4-6 must be in this exact order. Clearing alembic_version (step 5)
before running platform upgrade (step 6) prevents Alembic revision graph mismatch.
"""
import asyncio
import sys
import os
import subprocess

from sqlalchemy import text


# Business tables come from TenantBase (the authoritative allowlist).
# ENUM types and sequences are discovered from the database (they are
# dependencies of TenantBase tables and cannot be easily enumerated from metadata).
async def discover_business_objects(conn):
    """Discover business objects to move to tenant schema.

    Tables: from TenantBase.metadata — the authoritative allowlist.
    ENUMs and sequences: all objects in public schema are moved, on the
    assumption that before multi-tenant migration they all belong to business
    tables. If non-business enums/sequences exist, add them to an exclusion
    list in this function.
    """
    from app.database import TenantBase
    import app.models  # trigger model registration

    # Use TenantBase as the authoritative source — avoids moving unrelated
    # tables (extension tables, reporting tables, etc.) that happen to be in public.
    business_tables = sorted(TenantBase.metadata.tables.keys())

    # Verify all TenantBase tables actually exist in public schema before moving
    result = await conn.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    ))
    existing_tables = {row[0] for row in result}
    missing = set(business_tables) - existing_tables
    if missing:
        print(f"WARNING: TenantBase tables not found in public schema: {missing}")
        print("These tables may not need migration or the model may have changed.")

    # ENUM types in public schema — before multi-tenant migration, all enums in
    # public are assumed to belong to business tables. After migration, new enums
    # should be created in tenant schemas directly. If non-business enums exist,
    # add them to an exclusion list below.
    result = await conn.execute(text(
        "SELECT t.typname FROM pg_type t JOIN pg_namespace n ON t.typnamespace = n.oid "
        "WHERE n.nspname = 'public' AND t.typtype = 'e' ORDER BY t.typname"
    ))
    enum_types = [row[0] for row in result]

    # Sequences in public schema (those not auto-moved with tables)
    # Same assumption: all sequences in public belong to business tables.
    # Add non-business sequences to an exclusion list if needed.
    result = await conn.execute(text(
        "SELECT sequencename FROM pg_sequences WHERE schemaname = 'public' ORDER BY sequencename"
    ))
    sequences = [row[0] for row in result]

    return business_tables, enum_types, sequences


async def migrate():
    from app.database import async_session

    async with async_session() as conn:
        # Step 1: Backup alembic_version
        result = await conn.execute(text("SELECT version_num FROM public.alembic_version"))
        old_versions = [row[0] for row in result]
        print(f"Backed up {len(old_versions)} old revision(s): {old_versions}")

        # Step 2: Create tenant schema
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "tenant_default"'))
        await conn.commit()
        print("Created schema tenant_default")

        # Step 3: Discover and move all business objects
        business_tables, enum_types, sequences = await discover_business_objects(conn)
        print(f"Discovered {len(business_tables)} tables, {len(enum_types)} enums, {len(sequences)} sequences")

        for table in business_tables:
            await conn.execute(text(f'ALTER TABLE IF EXISTS public."{table}" SET SCHEMA "tenant_default"'))
        for enum_type in enum_types:
            await conn.execute(text(f'ALTER TYPE IF EXISTS public."{enum_type}" SET SCHEMA "tenant_default"'))
        for seq in sequences:
            await conn.execute(text(f'ALTER SEQUENCE IF EXISTS public."{seq}" SET SCHEMA "tenant_default"'))
        await conn.commit()
        print(f"Moved {len(business_tables)} tables, {len(enum_types)} enums, {len(sequences)} sequences")

    # Step 4: Stamp tenant_default with tenant branch
    subprocess.run(
        ["alembic", "-x", "schema=tenant_default", "stamp", "tenant@head"],
        check=True,
    )
    print("Stamped tenant_default at tenant@head")

    # Step 5: Clear public.alembic_version
    async with async_session() as conn:
        await conn.execute(text("DELETE FROM public.alembic_version"))
        await conn.commit()
    print("Cleared public.alembic_version")

    # Step 6: Run platform migrations
    subprocess.run(["alembic", "upgrade", "platform@head"], check=True)
    print("Ran platform@head migrations")

    # Step 7: Insert first tenant record
    async with async_session() as conn:
        await conn.execute(text("""
            INSERT INTO public.tenants (name, slug, schema_name, subdomain, plan, status)
            VALUES ('Default', 'default', 'tenant_default', 'app', 'enterprise', 'active')
        """))
        await conn.commit()
    print("Inserted default tenant record")

    # Step 8: Enable TENANT_MODE
    print("Set TENANT_MODE=production in your .env file")
    print("Migration complete!")


if __name__ == "__main__":
    asyncio.run(migrate())
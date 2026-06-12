#!/usr/bin/env python3
"""Verify that t001_tenant_squash.py covers all TenantBase tables.
Exit 1 if any table is missing from the migration.
"""
import re
import sys
import glob
from app.database import TenantBase
import app.models  # trigger model registration


def main():
    expected = set(TenantBase.metadata.tables.keys())

    # Find the squash migration file — Alembic may generate a filename with
    # additional suffix beyond the rev-id, e.g. t001_tenant_squash_tenant_squash.py
    migration_files = glob.glob("alembic/versions/t001_tenant_squash*.py")
    if len(migration_files) == 0:
        print("ERROR: no migration file matching alembic/versions/t001_tenant_squash*.py")
        print("Did the autogenerate step succeed?")
        sys.exit(1)
    if len(migration_files) > 1:
        print(f"ERROR: multiple migration files match t001_tenant_squash*.py:")
        for f in migration_files:
            print(f"  {f}")
        sys.exit(1)
    migration_path = migration_files[0]
    print(f"Verifying: {migration_path}")
    with open(migration_path) as f:
        content = f.read()

    # Verify revision metadata — down_revision must point to the branch root
    down_rev_match = re.search(r"down_revision\s*=\s*['\"](\w+)['\"]", content)
    if not down_rev_match:
        print("ERROR: could not find down_revision in migration file")
        sys.exit(1)
    down_revision = down_rev_match.group(1)
    if down_revision != "t000_tenant_baseline":
        print(f"ERROR: down_revision is '{down_revision}', expected 't000_tenant_baseline'")
        print("The squash migration must chain from the tenant branch root.")
        print("Manually set down_revision = 't000_tenant_baseline' and re-run this script.")
        sys.exit(1)

    created_tables = set()
    for match in re.finditer(r"op\.create_table\(\s*['\"](\w+)['\"]", content):
        created_tables.add(match.group(1))

    missing = expected - created_tables
    extra = created_tables - expected

    if missing:
        print(f"ERROR: {len(missing)} tables missing from squash migration:")
        for t in sorted(missing):
            print(f"  - {t}")
        sys.exit(1)

    if extra:
        print(f"WARNING: {len(extra)} extra tables in squash (not in TenantBase):")
        for t in sorted(extra):
            print(f"  + {t}")

    print(f"OK: all {len(expected)} TenantBase tables present in squash migration")
    sys.exit(0)


if __name__ == "__main__":
    main()
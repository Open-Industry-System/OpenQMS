"""Preview by default; explicitly authorized execution requires observed offline services."""
import argparse
import asyncio
import json
from dataclasses import asdict
from getpass import getpass
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.schemas.platform import TenantCreateRequest
from app.services.tenant_test_rebuild import (
    RebuildInventory, preview_rebuild, rebuild_test_tenants, require_execute_flags,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Offline test tenant rebuild (preview by default)")
    result.add_argument("--inventory", type=Path, required=True)
    result.add_argument("--compose-project", required=True)
    result.add_argument("--execute", action="store_true")
    result.add_argument("--confirm", default="")
    return result


async def run(args: argparse.Namespace) -> int:
    inventory = RebuildInventory.from_json(args.inventory.read_text())
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        current = await preview_rebuild([t.tenant_id for t in inventory.targets], engine=engine)
        if tuple(current) != inventory.targets:
            raise PermissionError("test inventory drift; refresh exact inventory")
        if not args.execute:
            print(json.dumps({"test_only": True, "targets": [asdict(t) for t in current]}, default=str))
            return 0
        require_execute_flags(args.confirm)
        requests = {}
        for target in current:
            email = input(f"Admin email for {target.slug}: ").strip()
            password = getpass(f"Admin password for {target.slug}: ")
            requests[target.tenant_id] = TenantCreateRequest(name=target.slug, slug=target.slug,
                                                            admin_email=email, admin_password=password)
        results = await rebuild_test_tenants(current, args.confirm, requests, inventory=inventory,
                                            compose_project=args.compose_project, engine=engine)
        print(json.dumps([asdict(result) for result in results], default=str))
        return 0 if all(r.status == "active" for r in results) else 1
    finally:
        await engine.dispose()


def main() -> None:
    args = parser().parse_args()
    try:
        code = asyncio.run(run(args))
    except Exception:
        # Validation/DB diagnostics may contain input credentials; do not render them.
        print("Test tenant rebuild refused; verify flags, exact inventory and observed offline state.")
        code = 1
    raise SystemExit(code)


if __name__ == "__main__":
    main()

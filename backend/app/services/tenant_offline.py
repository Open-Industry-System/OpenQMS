"""Observed offline proof; never stop containers or terminate database sessions."""
import asyncio
import json
import re
from collections.abc import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


class TenantBusy(ValueError):
    """Safe reason code, independent of Docker/database diagnostic text."""


async def _docker_json(*args: str) -> str:
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            "docker", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=10)
        if process.returncode != 0:
            raise TenantBusy("services_not_offline")
        return stdout.decode()
    except (OSError, UnicodeError, asyncio.TimeoutError) as exc:
        raise TenantBusy("services_not_offline") from exc
    finally:
        if process is not None and process.returncode is None:
            process.kill()  # Only our Docker inspection CLI, never a container.
            await process.wait()


async def observe_compose_containers(project: str) -> list[dict]:
    identifiers = []
    for service in ("backend", "graph-worker"):
        output = await _docker_json("ps", "--all", "--quiet", "--filter",
            f"label=com.docker.compose.project={project}", "--filter",
            f"label=com.docker.compose.service={service}")
        ids = output.split()
        if not ids or any(not re.fullmatch(r"[0-9a-f]{12,64}", item) for item in ids):
            raise TenantBusy("services_not_offline")
        identifiers.extend(ids)
    try:
        rows = json.loads(await _docker_json("inspect", *identifiers))
    except (ValueError, TypeError) as exc:
        raise TenantBusy("services_not_offline") from exc
    if not isinstance(rows, list) or len(rows) != len(identifiers):
        raise TenantBusy("services_not_offline")
    return rows


class ComposeOfflineObserver:
    def __init__(self, *, observe: Callable[[str], Awaitable[list[dict]]] = observe_compose_containers):
        self.observe = observe

    async def require_stopped(self, project: str) -> None:
        if not isinstance(project, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", project):
            raise TenantBusy("services_not_offline")
        try:
            rows = await self.observe(project)
            services, ids = set(), set()
            if not isinstance(rows, list) or not rows:
                raise TenantBusy("services_not_offline")
            for row in rows:
                labels, state = row["Config"]["Labels"], row["State"]
                service, identifier = labels["com.docker.compose.service"], row["Id"]
                if (labels["com.docker.compose.project"] != project
                        or service not in {"backend", "graph-worker"}
                        or not identifier or identifier in ids
                        or state["Status"] != "exited"
                        or any(state[key] is not False for key in ("Running", "Paused", "Restarting"))):
                    raise TenantBusy("services_not_offline")
                ids.add(identifier)
                services.add(service)
            if services != {"backend", "graph-worker"}:
                raise TenantBusy("services_not_offline")
        except Exception as exc:
            raise TenantBusy("services_not_offline") from exc


async def require_test_database(connection: AsyncConnection) -> None:
    name = await connection.scalar(text("SELECT pg_catalog.current_database()"))
    if not isinstance(name, str) or not name.endswith("_test"):
        raise PermissionError("test database required")


async def require_no_other_clients(connection: AsyncConnection) -> None:
    """Count idle clients too; hidden/unverifiable backend types also refuse."""
    count = await connection.scalar(text("""
        SELECT count(*) FROM pg_catalog.pg_stat_activity
        WHERE datname=pg_catalog.current_database() AND pid<>pg_catalog.pg_backend_pid()
          AND (backend_type='client backend' OR backend_type IS NULL)
    """))
    if count != 0:
        raise TenantBusy("database_not_quiescent")

"""Optional synthetic records for the exact PR being deployed to preview."""

import re
from collections.abc import Mapping
from importlib import import_module
from importlib.util import find_spec
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def preview_pr_from_env(environ: Mapping[str, str]) -> int | None:
    """Read the PR number set by the trusted preview initializer."""
    value = environ.get("PREVIEW_PR")
    if value is None:
        return None
    if not re.fullmatch(r"[1-9][0-9]{0,8}", value):
        raise ValueError("invalid preview PR number")
    database = urlsplit(environ.get("DATABASE_URL", ""))
    if (database.scheme, database.hostname, database.path) != (
        "postgresql+asyncpg", "db", "/qms_preview",
    ):
        raise ValueError("PR fixtures require the isolated preview database URL")
    return int(value)


async def seed_preview_fixture(db: AsyncSession, preview_pr: int | None) -> None:
    """Run only the matching fixture in the caller's seed transaction."""
    if preview_pr is None:
        return
    name = f"{__name__}.pr_{preview_pr}"
    if find_spec(name) is None:
        return
    if await db.scalar(text("SELECT current_database()")) != "qms_preview":
        raise ValueError("PR fixtures require the isolated preview database")
    await import_module(name).seed(db)

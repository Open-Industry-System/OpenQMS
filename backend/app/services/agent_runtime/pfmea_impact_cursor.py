"""Run, lease, and snapshot-bound continuation tokens for R7 queries."""

from hashlib import sha256
import hmac
import re
from typing import Literal

from app.config import settings
from app.services.agent_runtime.pfmea_impact_ledger import scope_digest
from app.services.agent_runtime.pfmea_impact_release import FMEA_MAX_ATTEMPTS, PageScope


CursorKind = Literal["page", "search"]
_MAX_OFFSET = {"page": FMEA_MAX_ATTEMPTS - 1, "search": 500}
_TOKEN = re.compile(r"(0|[1-9][0-9]{0,2})\.([a-f0-9]{64})")


def sign_cursor(scope: PageScope, kind: CursorKind, position: int) -> str:
    """Seal a server-chosen zero-based index or candidate offset."""
    if kind not in _MAX_OFFSET or type(position) is not int or not 0 <= position <= _MAX_OFFSET[kind]:
        raise ValueError("Invalid impact continuation")
    value = f"openqms.r7.cursor.v1:{kind}:{scope_digest(scope)}:{position}".encode("ascii")
    mac = hmac.new(settings.SECRET_KEY.encode(), value, sha256).hexdigest()
    return f"{position}.{mac}"


def read_cursor(scope: PageScope, kind: CursorKind, cursor: str) -> int:
    """Resolve a continuation; caller must separately verify the live run."""
    match = _TOKEN.fullmatch(cursor) if isinstance(cursor, str) and len(cursor) <= 68 else None
    if match is not None:
        position = int(match[1])
        try:
            if hmac.compare_digest(cursor, sign_cursor(scope, kind, position)):
                return position
        except ValueError:
            pass
    raise PermissionError("Impact continuation unavailable")

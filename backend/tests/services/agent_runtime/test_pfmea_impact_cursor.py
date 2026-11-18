from dataclasses import replace
from uuid import uuid4

import pytest

from app.services.agent_runtime.pfmea_impact_release import PageScope


def test_continuation_cannot_cross_scope_snapshot_or_lease():
    from app.services.agent_runtime.pfmea_impact_cursor import read_cursor, sign_cursor

    scope = PageScope(uuid4(), uuid4(), 2, "binding", "snapshot", "OP40")
    cursor = sign_cursor(scope, "page", 3)
    assert read_cursor(scope, "page", cursor) == 3
    for changed in (
        replace(scope, run_id=uuid4()),
        replace(scope, lease_epoch=3),
        replace(scope, snapshot_digest="next-snapshot"),
        replace(scope, scope_ref="OP41"),
    ):
        with pytest.raises(PermissionError):
            read_cursor(changed, "page", cursor)
    with pytest.raises(PermissionError):
        read_cursor(scope, "search", cursor)


def test_tampered_or_malformed_continuation_fails_closed():
    from app.services.agent_runtime.pfmea_impact_cursor import read_cursor, sign_cursor

    scope = PageScope(uuid4(), uuid4(), 2, "binding", "snapshot", "search/泵体")
    valid = sign_cursor(scope, "search", 25)
    assert read_cursor(scope, "search", valid) == 25
    for token in (valid[:-1], "250." + valid.split(".")[1], "25." + "あ" * 64, "025." + valid.split(".")[1]):
        with pytest.raises(PermissionError):
            read_cursor(scope, "search", token)


@pytest.mark.parametrize("kind,index", [("page", 16), ("page", -1), ("search", 501), ("search", True)])
def test_internal_continuations_cannot_exceed_projection_limits(kind, index):
    from app.services.agent_runtime.pfmea_impact_cursor import sign_cursor

    scope = PageScope(uuid4(), uuid4(), 2, "binding", "snapshot", "OP40")
    with pytest.raises(ValueError):
        sign_cursor(scope, kind, index)

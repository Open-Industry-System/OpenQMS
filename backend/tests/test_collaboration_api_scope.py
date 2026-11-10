import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, func, select, update

from app.core.deps import get_request_scope
from app.main import app
from app.models.collaboration_session import CollaborationSession
from app.models.fmea import FMEADocument
from app.models.control_plan import ControlPlan
from app.models.role import RolePermission
from app.core.factory_scope import FactoryScope, ProductLineScope
from tests.conftest import _scope_for

pytestmark = pytest.mark.requires_db


async def _make_fmea(db, factory_id, user_id):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(),
        document_no=f"PFMEA-COLLAB-SCOPE-{uuid.uuid4().hex[:8]}",
        title="collaboration scope test",
        fmea_type="PFMEA",
        product_line_code="DC-DC-100",
        factory_id=factory_id,
        status="draft",
        created_by=user_id,
        graph_data={"nodes": [], "edges": []},
    )
    db.add(fmea)
    await db.flush()
    return fmea


async def _make_session(db, *, document_type, document_id, user, factory_id):
    row = CollaborationSession(
        session_id=uuid.uuid4(),
        document_type=document_type,
        document_id=document_id,
        user_id=user.user_id,
        user_name=user.display_name,
        action="viewing",
        editing_area=None,
        last_activity=datetime.now(UTC) - timedelta(seconds=10),
        factory_id=factory_id,
    )
    db.add(row)
    await db.flush()
    return row


def _restrict_to_other_factory(scope):
    app.dependency_overrides[get_request_scope] = lambda: scope


async def _session_count(db, document_type, document_id, user_id):
    return await db.scalar(
        select(func.count()).select_from(CollaborationSession).where(
            CollaborationSession.document_type == document_type,
            CollaborationSession.document_id == document_id,
            CollaborationSession.user_id == user_id,
        )
    )


async def _call(client, operation, document_type, document_id):
    if operation == "heartbeat":
        return await client.post(
            "/api/collaboration/heartbeat",
            json={
                "document_type": document_type,
                "document_id": str(document_id),
                "action": "editing",
                "editing_area": {"section": "risk"},
            },
        )
    if operation == "active-users":
        return await client.get(
            f"/api/collaboration/{document_type}/{document_id}/active-users"
        )
    return await client.delete(
        f"/api/collaboration/leave/{document_type}/{document_id}"
    )


@pytest.mark.asyncio
async def test_same_factory_collaboration_round_trip(
    admin_client, db, default_factory, admin_user, other_admin_user
):
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    other = await _make_session(
        db,
        document_type="fmea",
        document_id=fmea.fmea_id,
        user=other_admin_user,
        factory_id=default_factory.id,
    )

    heartbeat = await _call(admin_client, "heartbeat", "fmea", fmea.fmea_id)
    assert heartbeat.status_code == 204

    active = await _call(admin_client, "active-users", "fmea", fmea.fmea_id)
    assert active.status_code == 200
    assert active.json() == {
        "users": [{
            "user_id": str(other_admin_user.user_id),
            "user_name": other_admin_user.display_name,
            "action": "viewing",
            "editing_area": None,
        }],
        "total": 1,
    }

    leave = await _call(admin_client, "leave", "fmea", fmea.fmea_id)
    assert leave.status_code == 204
    assert await _session_count(
        db, "fmea", fmea.fmea_id, admin_user.user_id
    ) == 0
    await db.refresh(other)


@pytest.mark.asyncio
async def test_cross_factory_heartbeat_does_not_create_session(
    admin_client, db, default_factory, admin_user,
    request_scope_restricted_other_factory,
):
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    _restrict_to_other_factory(request_scope_restricted_other_factory)

    response = await _call(admin_client, "heartbeat", "fmea", fmea.fmea_id)

    assert response.status_code == 404
    assert response.json() == {"detail": "document_not_found"}
    assert await _session_count(
        db, "fmea", fmea.fmea_id, admin_user.user_id
    ) == 0


@pytest.mark.asyncio
async def test_cross_factory_heartbeat_does_not_refresh_session(
    admin_client, db, default_factory, admin_user,
    request_scope_restricted_other_factory,
):
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    row = await _make_session(
        db,
        document_type="fmea",
        document_id=fmea.fmea_id,
        user=admin_user,
        factory_id=default_factory.id,
    )
    before = (
        row.user_name,
        row.action,
        row.editing_area,
        row.last_activity,
        row.factory_id,
    )
    _restrict_to_other_factory(request_scope_restricted_other_factory)

    response = await _call(admin_client, "heartbeat", "fmea", fmea.fmea_id)

    assert response.status_code == 404
    assert response.json() == {"detail": "document_not_found"}
    await db.refresh(row)
    assert (
        row.user_name,
        row.action,
        row.editing_area,
        row.last_activity,
        row.factory_id,
    ) == before


@pytest.mark.asyncio
async def test_cross_factory_active_users_does_not_expose_sessions(
    admin_client, db, default_factory, admin_user, other_admin_user,
    request_scope_restricted_other_factory,
):
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    row = await _make_session(
        db,
        document_type="fmea",
        document_id=fmea.fmea_id,
        user=other_admin_user,
        factory_id=default_factory.id,
    )
    _restrict_to_other_factory(request_scope_restricted_other_factory)

    response = await _call(admin_client, "active-users", "fmea", fmea.fmea_id)

    assert response.status_code == 404
    assert response.json() == {"detail": "document_not_found"}
    assert other_admin_user.display_name not in response.text
    await db.refresh(row)


@pytest.mark.asyncio
async def test_cross_factory_leave_does_not_delete_session(
    admin_client, db, default_factory, admin_user,
    request_scope_restricted_other_factory,
):
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    row = await _make_session(
        db,
        document_type="fmea",
        document_id=fmea.fmea_id,
        user=admin_user,
        factory_id=default_factory.id,
    )
    _restrict_to_other_factory(request_scope_restricted_other_factory)

    response = await _call(admin_client, "leave", "fmea", fmea.fmea_id)

    assert response.status_code == 404
    assert response.json() == {"detail": "document_not_found"}
    await db.refresh(row)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["heartbeat", "active-users", "leave"])
@pytest.mark.parametrize(
    ("document_type", "expected_detail"),
    [
        ("fmea", "document_not_found"),
        ("unsupported", "unsupported_document_type"),
    ],
)
async def test_invalid_collaboration_target_has_no_side_effects(
    admin_client, db, default_factory, admin_user,
    operation, document_type, expected_detail,
):
    missing_id = uuid.uuid4()
    row = await _make_session(
        db,
        document_type=document_type,
        document_id=missing_id,
        user=admin_user,
        factory_id=default_factory.id,
    )
    before = (
        row.user_name,
        row.action,
        row.editing_area,
        row.last_activity,
        row.factory_id,
    )

    response = await _call(admin_client, operation, document_type, missing_id)

    assert response.status_code == 404
    assert response.json() == {"detail": expected_detail}
    await db.refresh(row)
    assert (
        row.user_name,
        row.action,
        row.editing_area,
        row.last_activity,
        row.factory_id,
    ) == before


async def _make_cp(db, factory_id, user_id):
    cp = ControlPlan(cp_id=uuid.uuid4(), document_no=f"CP-COLLAB-{uuid.uuid4().hex[:8]}",
        title="CP collaboration scope", product_line_code="DC-DC-100",
        factory_id=factory_id, status="draft", created_by=user_id)
    db.add(cp)
    await db.flush()
    return cp


@pytest.mark.asyncio
async def test_cp_same_factory_explicit_line_view_permission_round_trip(
    admin_client, db, default_factory, admin_user, other_admin_user,
):
    cp = await _make_cp(db, default_factory.id, admin_user.user_id)
    await db.execute(update(RolePermission).where(
        RolePermission.role_id == admin_user.role_id, RolePermission.module == "planning"
    ).values(permission_level=1))
    scope = _scope_for(admin_user, default_factory, [default_factory.id], "EXPLICIT", ["DC-DC-100"])
    app.dependency_overrides[get_request_scope] = lambda: scope
    other = await _make_session(db, document_type="control_plan", document_id=cp.cp_id,
        user=other_admin_user, factory_id=default_factory.id)
    assert (await _call(admin_client, "heartbeat", "control_plan", cp.cp_id)).status_code == 204
    current = await db.scalar(select(CollaborationSession).where(
        CollaborationSession.document_type == "control_plan", CollaborationSession.document_id == cp.cp_id,
        CollaborationSession.user_id == admin_user.user_id))
    assert current.factory_id == default_factory.id and current.action == "editing"
    active = await _call(admin_client, "active-users", "control_plan", cp.cp_id)
    assert active.status_code == 200
    assert active.json() == {"users": [{"user_id": str(other_admin_user.user_id),
        "user_name": other_admin_user.display_name, "action": "viewing", "editing_area": None}], "total": 1}
    assert (await _call(admin_client, "leave", "control_plan", cp.cp_id)).status_code == 204
    assert await _session_count(db, "control_plan", cp.cp_id, admin_user.user_id) == 0
    await db.refresh(other)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["heartbeat", "active-users", "leave"])
@pytest.mark.parametrize("denial", ["missing", "factory", "effective", "line_none", "line_other", "permission", "permission_missing"])
async def test_cp_collaboration_admission_never_reads_or_mutates_hidden_presence(
    admin_client, db, default_factory, admin_user, operation, denial,
):
    cp_id = uuid.uuid4() if denial in {"missing", "permission_missing"} else (
        await _make_cp(db, default_factory.id, admin_user.user_id)).cp_id
    row = await _make_session(db, document_type="control_plan", document_id=cp_id,
        user=admin_user, factory_id=default_factory.id)
    before = (row.user_name, row.action, row.editing_area, row.last_activity, row.factory_id)
    scope = _scope_for(admin_user, default_factory, [default_factory.id], "EXPLICIT", ["DC-DC-100"])
    if denial == "factory":
        other = uuid.uuid4()
        scope.factory_scope = FactoryScope([other], other)
        scope.effective_factory_id = other
    elif denial == "effective":
        scope.factory_scope = FactoryScope(None, default_factory.id)
        scope.effective_factory_id = uuid.uuid4()
    elif denial == "line_none":
        scope.pl_scope = ProductLineScope("NONE", [])
    elif denial == "line_other":
        scope.pl_scope = ProductLineScope("EXPLICIT", ["OTHER"])
    elif denial.startswith("permission"):
        await db.execute(update(RolePermission).where(
            RolePermission.role_id == admin_user.role_id, RolePermission.module == "planning"
        ).values(permission_level=0))
    app.dependency_overrides[get_request_scope] = lambda: scope
    statements = []
    def observed(state):
        statements.append(str(state.statement))
    event.listen(db.sync_session, "do_orm_execute", observed)
    try:
        response = await _call(admin_client, operation, "control_plan", cp_id)
    finally:
        event.remove(db.sync_session, "do_orm_execute", observed)
    permission_denied = denial.startswith("permission")
    assert response.status_code == (403 if permission_denied else 404)
    assert response.json() == {"detail": "需要计划模块的 VIEW 权限" if permission_denied else "document_not_found"}
    assert row.user_name not in response.text
    assert not any("collaboration_sessions" in sql for sql in statements)
    if permission_denied:
        assert not any("FROM control_plans" in sql for sql in statements), "module admission precedes every target lookup"
    await db.refresh(row)
    assert (row.user_name, row.action, row.editing_area, row.last_activity, row.factory_id) == before

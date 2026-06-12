"""Integration tests for multi-factory data isolation.

Verifies that the scope resolution pipeline correctly isolates factory data
and that the bypass/GROUP ADMIN boundary is enforced end-to-end.

Run: cd backend && SECRET_KEY=test-secret-key-for-ci python tests/test_factory_isolation.py
"""
import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci")

import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, AsyncMock, patch

from fastapi import HTTPException

from app.core.factory_scope import (
    FactoryScope,
    ProductLineScope,
    resolve_factory_scope,
    resolve_product_line_scope,
    resolve_effective_factory_id,
    apply_scope_filter,
    validate_factory_invariant,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

F1 = uuid.uuid4()
F2 = uuid.uuid4()
F3 = uuid.uuid4()


def make_user(factory_id=None, bypass=False, user_id=None):
    """Create a mock User with the given factory_id and bypass flag."""
    user = MagicMock()
    user.user_id = user_id or uuid.uuid4()
    user.factory_id = factory_id
    user.role_definition = MagicMock()
    user.role_definition.bypass_row_level_security = bypass
    return user


def make_db_mock(factory_id_result=None):
    """Create an async mock DB session."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = factory_id_result
    db.execute.return_value = mock_result
    return db


def mock_select(*args, **kwargs):
    """Replace sqlalchemy.select so mock model attributes work."""
    q = MagicMock()
    q.where.return_value = q
    return q


# ===================================================================
# 1. Factory Isolation — end-to-end scope pipeline
# ===================================================================

def test_factory_a_user_sees_own_factory_only():
    """Factory A operator: scope pipeline resolves to single factory."""
    user_a = make_user(factory_id=F1, bypass=False)
    fscope = resolve_factory_scope(user_a, user_factory_ids=[], has_group_admin=False)
    assert fscope.accessible_factory_ids == [F1]
    assert fscope.default_factory_id == F1

    # Product line scope for non-bypass user
    plscope = resolve_product_line_scope(user_a, user_product_line_codes=["DC-DC-100"], factory_scope=fscope)
    assert plscope.mode == "EXPLICIT"
    assert plscope.codes == ["DC-DC-100"]

    # Effective factory is locked to F1
    eff = resolve_effective_factory_id(fscope, requested_factory_id=None)
    assert eff == F1

    # Requesting F2 should be rejected
    try:
        resolve_effective_factory_id(fscope, requested_factory_id=F2)
        assert False, "Should have raised HTTPException"
    except HTTPException as e:
        assert e.status_code == 403


def test_factory_b_user_sees_own_factory_only():
    """Factory B operator: scope pipeline resolves to their own factory."""
    user_b = make_user(factory_id=F2, bypass=False)
    fscope = resolve_factory_scope(user_b, user_factory_ids=[], has_group_admin=False)
    assert fscope.accessible_factory_ids == [F2]
    assert fscope.default_factory_id == F2

    # Factory B user cannot access F1
    try:
        resolve_effective_factory_id(fscope, requested_factory_id=F1)
        assert False, "Should have raised HTTPException"
    except HTTPException as e:
        assert e.status_code == 403


def test_group_admin_sees_all_factories():
    """GROUP ADMIN: scope pipeline resolves to all factories (None)."""
    admin = make_user(factory_id=F1, bypass=True)
    fscope = resolve_factory_scope(admin, user_factory_ids=[], has_group_admin=True)
    assert fscope.accessible_factory_ids is None  # None = all factories

    # Without query param, no factory filter
    eff = resolve_effective_factory_id(fscope, requested_factory_id=None)
    assert eff is None

    # Can query any specific factory
    for fid in [F1, F2, F3]:
        eff = resolve_effective_factory_id(fscope, requested_factory_id=fid)
        assert eff == fid


def test_group_viewer_sees_assigned_factories():
    """Group viewer: can see F1 and F2 but not F3."""
    viewer = make_user(factory_id=F1, bypass=False)
    fscope = resolve_factory_scope(viewer, user_factory_ids=[F1, F2], has_group_admin=False)
    assert fscope.accessible_factory_ids == [F1, F2]
    assert fscope.default_factory_id == F1

    # Can access F2
    eff = resolve_effective_factory_id(fscope, requested_factory_id=F2)
    assert eff == F2

    # Cannot access F3
    try:
        resolve_effective_factory_id(fscope, requested_factory_id=F3)
        assert False, "Should have raised HTTPException"
    except HTTPException as e:
        assert e.status_code == 403


# ===================================================================
# 2. Bypass vs GROUP Decoupling
# ===================================================================

def test_bypass_without_group_still_locked_to_factory():
    """bypass_row_level_security=True but no GROUP ADMIN:
    - Product line scope = ALL (bypasses product line filter)
    - Factory scope = still only own factory (does NOT bypass factory isolation)
    """
    admin = make_user(factory_id=F1, bypass=True)
    fscope = resolve_factory_scope(admin, user_factory_ids=[], has_group_admin=False)

    # Factory scope is still limited to own factory
    assert fscope.accessible_factory_ids == [F1]
    assert fscope.accessible_factory_ids is not None  # NOT None (not cross-factory)

    # But product line scope bypasses to ALL
    plscope = resolve_product_line_scope(admin, user_product_line_codes=["DC-DC-100"], factory_scope=fscope)
    assert plscope.mode == "ALL"
    assert plscope.codes is None

    # Still cannot access F2
    try:
        resolve_effective_factory_id(fscope, requested_factory_id=F2)
        assert False, "Should have raised HTTPException"
    except HTTPException as e:
        assert e.status_code == 403


def test_bypass_with_group_admin_sees_all_factories():
    """bypass_row_level_security=True AND GROUP ADMIN:
    - Factory scope = all factories (None)
    - Product line scope = ALL
    - Can access any factory
    """
    group_admin = make_user(factory_id=F1, bypass=True)
    fscope = resolve_factory_scope(group_admin, user_factory_ids=[F2], has_group_admin=True)
    assert fscope.accessible_factory_ids is None

    plscope = resolve_product_line_scope(group_admin, user_product_line_codes=[], factory_scope=fscope)
    assert plscope.mode == "ALL"

    # Can access any factory
    eff = resolve_effective_factory_id(fscope, requested_factory_id=F3)
    assert eff == F3


def test_bypass_does_not_grant_cross_factory_product_lines():
    """Even with bypass, the query filter still restricts to accessible factories.

    apply_scope_filter with bypass user who only has F1 access:
    - Factory filter: model.factory_id == F1
    - Product line filter: NONE (ALL mode, no filter)
    """
    admin = make_user(factory_id=F1, bypass=True)
    fscope = resolve_factory_scope(admin, user_factory_ids=[], has_group_admin=False)
    eff = resolve_effective_factory_id(fscope, requested_factory_id=None)
    assert eff == F1  # Locked to own factory

    plscope = resolve_product_line_scope(admin, user_product_line_codes=[], factory_scope=fscope)
    assert plscope.mode == "ALL"

    # Apply to mock query
    model = MagicMock()
    model.factory_id = MagicMock()
    model.factory_id.__eq__ = MagicMock(return_value=MagicMock())
    model.__tablename__ = "fmea_documents"
    del model.product_line_code

    query = MagicMock()
    query.where = MagicMock(return_value=query)

    apply_scope_filter(query, model, "fmea", fscope, F1, plscope, admin, make_db_mock())

    # Factory filter applied: model.factory_id == F1
    model.factory_id.__eq__.assert_called_once_with(F1)


# ===================================================================
# 3. ProductLineScope Modes
# ===================================================================

def test_pl_scope_none_mode_empty_results():
    """ProductLineScope NONE mode: apply_scope_filter produces WHERE FALSE."""
    user = make_user(factory_id=F1, bypass=False)
    fscope = FactoryScope(accessible_factory_ids=[F1], default_factory_id=F1)
    plscope = ProductLineScope(mode="NONE", codes=None)

    model = MagicMock()
    model.factory_id = MagicMock()
    model.factory_id.__eq__ = MagicMock(return_value=MagicMock())
    model.product_line_code = MagicMock()
    model.product_line_code.in_ = MagicMock(return_value=MagicMock())
    model.__tablename__ = "fmea_documents"

    query = MagicMock()
    query.where = MagicMock(return_value=query)

    apply_scope_filter(query, model, "fmea", fscope, F1, plscope, user, make_db_mock())

    # Should have WHERE FALSE (no data)
    call_args = [call[0][0] for call in query.where.call_args_list]
    assert False in call_args


def test_pl_scope_explicit_mode_filters_to_codes():
    """ProductLineScope EXPLICIT mode: filter to specific product line codes."""
    user = make_user(factory_id=F1, bypass=False)
    fscope = FactoryScope(accessible_factory_ids=[F1], default_factory_id=F1)
    plscope = ProductLineScope(mode="EXPLICIT", codes=["DC-DC-100", "PCB-SMT-200"])

    model = MagicMock()
    model.factory_id = MagicMock()
    model.factory_id.__eq__ = MagicMock(return_value=MagicMock())
    model.product_line_code = MagicMock()
    model.product_line_code.in_ = MagicMock(return_value=MagicMock())
    model.__tablename__ = "fmea_documents"

    query = MagicMock()
    query.where = MagicMock(return_value=query)

    apply_scope_filter(query, model, "fmea", fscope, F1, plscope, user, make_db_mock())

    # Should filter to explicit product line codes
    model.product_line_code.in_.assert_called_once_with(["DC-DC-100", "PCB-SMT-200"])


def test_pl_scope_all_mode_no_pl_filter():
    """ProductLineScope ALL mode: no product line filtering applied."""
    user = make_user(bypass=True)
    fscope = FactoryScope(accessible_factory_ids=[F1], default_factory_id=F1)
    plscope = ProductLineScope(mode="ALL", codes=None)

    model = MagicMock()
    model.factory_id = MagicMock()
    model.factory_id.__eq__ = MagicMock(return_value=MagicMock())
    model.product_line_code = MagicMock()
    model.product_line_code.in_ = MagicMock(return_value=MagicMock())
    model.__tablename__ = "fmea_documents"

    query = MagicMock()
    query.where = MagicMock(return_value=query)

    apply_scope_filter(query, model, "fmea", fscope, F1, plscope, user, make_db_mock())

    # Factory filter applied, product line NOT filtered
    model.factory_id.__eq__.assert_called_once_with(F1)
    model.product_line_code.in_.assert_not_called()


def test_pl_scope_explicit_with_group_admin_no_factory_filter():
    """GROUP ADMIN with EXPLICIT product lines:
    - No factory filter (accessible_factory_ids=None)
    - Product line filter to specific codes
    """
    user = make_user(factory_id=None, bypass=False)
    fscope = FactoryScope(accessible_factory_ids=None, default_factory_id=None)
    plscope = ProductLineScope(mode="EXPLICIT", codes=["DC-DC-100"])

    model = MagicMock()
    model.factory_id = MagicMock()
    model.factory_id.__eq__ = MagicMock(return_value=MagicMock())
    model.factory_id.in_ = MagicMock(return_value=MagicMock())
    model.product_line_code = MagicMock()
    model.product_line_code.in_ = MagicMock(return_value=MagicMock())
    model.__tablename__ = "fmea_documents"

    query = MagicMock()
    query.where = MagicMock(return_value=query)

    apply_scope_filter(query, model, "fmea", fscope, None, plscope, user, make_db_mock())

    # No factory filter (GROUP ADMIN), product line filter to codes
    model.factory_id.__eq__.assert_not_called()
    model.factory_id.in_.assert_not_called()
    model.product_line_code.in_.assert_called_once_with(["DC-DC-100"])


# ===================================================================
# 4. Factory Invariant Tests
# ===================================================================

def _run_async(coro):
    """Run an async function synchronously (no current event loop required)."""
    import asyncio
    return asyncio.run(coro)


def test_factory_invariant_product_line_mismatch():
    """Creating a record with factory_id that doesn't match product_line's factory → ValueError."""
    record = MagicMock()
    record.factory_id = F1  # Record says factory 1
    record.product_line_code = "DC-DC-100"  # But product line belongs to factory 2
    record.product_line = None
    record.supplier_id = None

    db = make_db_mock(factory_id_result=F2)  # Product line belongs to F2

    with patch("app.core.factory_scope.select", side_effect=mock_select):
        try:
            _run_async(validate_factory_invariant(record, db))
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "factory_id" in str(e)


def test_factory_invariant_product_line_match():
    """Creating a record with factory_id that matches product_line's factory → passes."""
    record = MagicMock()
    record.factory_id = F1
    record.product_line_code = "DC-DC-100"
    record.product_line = None
    record.supplier_id = None

    db = make_db_mock(factory_id_result=F1)  # Product line belongs to F1 (match)

    with patch("app.core.factory_scope.select", side_effect=mock_select):
        _run_async(validate_factory_invariant(record, db))
        # Should not raise


def test_factory_invariant_no_product_line_no_error():
    """Record with factory_id but no product_line_code → no validation needed, passes."""
    record = MagicMock()
    record.factory_id = F1
    del record.product_line_code
    record.product_line = None
    record.supplier_id = None

    db = make_db_mock(factory_id_result=F1)

    _run_async(validate_factory_invariant(record, db))
    # Should not raise, no execute calls needed


# ===================================================================
# 5. Boundary / Edge Cases
# ===================================================================

def test_no_factory_access_returns_empty_scope():
    """User with no factory association gets empty accessible_factory_ids."""
    user = make_user(factory_id=None, bypass=False)
    fscope = resolve_factory_scope(user, user_factory_ids=[], has_group_admin=False)
    assert fscope.accessible_factory_ids == []
    assert fscope.default_factory_id is None

    # Trying to access any factory should fail
    try:
        resolve_effective_factory_id(fscope, requested_factory_id=F1)
        assert False, "Should have raised HTTPException"
    except HTTPException as e:
        assert e.status_code == 403


def test_empty_accessible_factory_ids_with_no_request():
    """Empty accessible_factory_ids with no request → None (but apply_scope_filter returns WHERE FALSE)."""
    scope = FactoryScope(accessible_factory_ids=[], default_factory_id=None)
    result = resolve_effective_factory_id(scope, requested_factory_id=None)
    # When accessible_factory_ids is empty and no request, effective is None
    # but apply_scope_filter will add WHERE FALSE for the empty list
    assert result is None


def test_single_factory_user_locked_even_with_bypass():
    """Single factory user: bypass doesn't change factory scope, only product line scope."""
    user = make_user(factory_id=F1, bypass=True)
    fscope = resolve_factory_scope(user, user_factory_ids=[], has_group_admin=False)

    # Factory scope still locked to F1
    assert fscope.accessible_factory_ids == [F1]
    eff = resolve_effective_factory_id(fscope, requested_factory_id=None)
    assert eff == F1

    # Product line scope is ALL (bypass)
    plscope = resolve_product_line_scope(user, user_product_line_codes=[], factory_scope=fscope)
    assert plscope.mode == "ALL"


def test_multi_factory_user_default_factory():
    """Multi-factory user: default_factory_id comes from user.factory_id."""
    user = make_user(factory_id=F1, bypass=False)
    fscope = resolve_factory_scope(user, user_factory_ids=[F1, F2], has_group_admin=False)
    assert fscope.default_factory_id == F1  # user's own factory_id is the default


def test_multi_factory_user_default_from_first_user_factory():
    """Multi-factory user without factory_id: default from first user_factory."""
    user = make_user(factory_id=None, bypass=False)
    fscope = resolve_factory_scope(user, user_factory_ids=[F2, F3], has_group_admin=False)
    assert fscope.default_factory_id == F2  # first in the list


def test_group_admin_default_factory_is_user_factory():
    """GROUP ADMIN: default_factory_id is user's own factory_id."""
    user = make_user(factory_id=F2, bypass=True)
    fscope = resolve_factory_scope(user, user_factory_ids=[F1], has_group_admin=True)
    assert fscope.default_factory_id == F2  # not F1 from user_factories


def test_group_admin_no_personal_factory():
    """GROUP ADMIN with no personal factory: default_factory_id=None."""
    user = make_user(factory_id=None, bypass=True)
    fscope = resolve_factory_scope(user, user_factory_ids=[], has_group_admin=True)
    assert fscope.default_factory_id is None


# ===================================================================
# Run all tests
# ===================================================================

if __name__ == "__main__":
    tests = [
        # 1. Factory Isolation
        test_factory_a_user_sees_own_factory_only,
        test_factory_b_user_sees_own_factory_only,
        test_group_admin_sees_all_factories,
        test_group_viewer_sees_assigned_factories,
        # 2. Bypass vs GROUP Decoupling
        test_bypass_without_group_still_locked_to_factory,
        test_bypass_with_group_admin_sees_all_factories,
        test_bypass_does_not_grant_cross_factory_product_lines,
        # 3. ProductLineScope Modes
        test_pl_scope_none_mode_empty_results,
        test_pl_scope_explicit_mode_filters_to_codes,
        test_pl_scope_all_mode_no_pl_filter,
        test_pl_scope_explicit_with_group_admin_no_factory_filter,
        # 4. Factory Invariant
        test_factory_invariant_product_line_mismatch,
        test_factory_invariant_product_line_match,
        test_factory_invariant_no_product_line_no_error,
        # 5. Boundary / Edge Cases
        test_no_factory_access_returns_empty_scope,
        test_empty_accessible_factory_ids_with_no_request,
        test_single_factory_user_locked_even_with_bypass,
        test_multi_factory_user_default_factory,
        test_multi_factory_user_default_from_first_user_factory,
        test_group_admin_default_factory_is_user_factory,
        test_group_admin_no_personal_factory,
    ]

    passed = 0
    failed = 0
    for test in tests:
        name = test.__name__
        try:
            test()
            print(f"✓ {name}")
            passed += 1
        except Exception as e:
            print(f"✗ {name}: {e}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    if failed > 0:
        exit(1)
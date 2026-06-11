"""Unit tests for multi-factory scope resolution logic.

Covers all 5 scope functions in app.core.factory_scope:
- resolve_factory_scope
- resolve_product_line_scope
- resolve_effective_factory_id
- apply_scope_filter
- populate_factory_id / validate_factory_invariant (DB-mocked)
"""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci")

import sys
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

# Ensure backend is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.factory_scope import (
    FactoryScope,
    ProductLineScope,
    resolve_factory_scope,
    resolve_product_line_scope,
    resolve_effective_factory_id,
    apply_scope_filter,
    populate_factory_id,
    validate_factory_invariant,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(factory_id=None, bypass=False):
    """Create a mock User with the given factory_id and bypass flag."""
    user = MagicMock()
    user.user_id = uuid4()
    user.factory_id = factory_id
    user.role_definition = MagicMock()
    user.role_definition.bypass_row_level_security = bypass
    return user


F1 = uuid4()
F2 = uuid4()
F3 = uuid4()


def make_db_mock(factory_id_result=None):
    """Create an async mock DB session whose execute returns factory_id_result.

    The mock handles the pattern: result = await db.execute(select(...)); result.scalar_one_or_none()
    """
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = factory_id_result
    db.execute.return_value = mock_result
    return db


def mock_select(*args, **kwargs):
    """Replace sqlalchemy.select in tests so it accepts mock model attributes.

    The real select() validates that arguments are SQLAlchemy column elements,
    which fails when model classes are mocked. This stub returns a simple object
    that supports .where() chaining and can be passed to db.execute().
    """
    q = MagicMock()
    q.where.return_value = q  # .where() returns itself for chaining
    return q


# ===================================================================
# 1. resolve_factory_scope
# ===================================================================

class TestResolveFactoryScope:
    """Test all 5 user types from spec §2."""

    def test_factory_operator_own_factory_only(self):
        """Factory operator: user.factory_id set, no user_factories → accessible=[factory_id]."""
        user = make_user(factory_id=F1)
        result = resolve_factory_scope(user, user_factory_ids=[], has_group_admin=False)
        assert result.accessible_factory_ids == [F1]
        assert result.default_factory_id == F1

    def test_factory_admin_bypass_still_own_factory(self):
        """Factory admin (bypass, no user_factories) → accessible=[factory_id], NOT None.

        bypass_row_level_security bypasses product-line filtering only,
        NOT factory scope.
        """
        user = make_user(factory_id=F1, bypass=True)
        result = resolve_factory_scope(user, user_factory_ids=[], has_group_admin=False)
        assert result.accessible_factory_ids == [F1]
        assert result.accessible_factory_ids is not None  # NOT cross-factory
        assert result.default_factory_id == F1

    def test_group_viewer_no_factory_id_with_user_factories(self):
        """Group viewer: factory_id=None, user_factory_ids=[F1,F2] → accessible=user_factory_ids."""
        user = make_user(factory_id=None)
        result = resolve_factory_scope(user, user_factory_ids=[F1, F2], has_group_admin=False)
        assert result.accessible_factory_ids == [F1, F2]
        assert result.default_factory_id == F1  # first user_factory as fallback

    def test_group_viewer_with_factory_id_and_user_factories(self):
        """Group viewer who also has a factory_id → user_factories takes precedence."""
        user = make_user(factory_id=F3)
        result = resolve_factory_scope(user, user_factory_ids=[F1, F2], has_group_admin=False)
        assert result.accessible_factory_ids == [F1, F2]
        assert result.default_factory_id == F3  # user.factory_id used as default

    def test_group_admin_all_factories(self):
        """Group admin → accessible=None (all factories), default from user.factory_id."""
        user = make_user(factory_id=F1)
        result = resolve_factory_scope(user, user_factory_ids=[], has_group_admin=True)
        assert result.accessible_factory_ids is None  # None = all
        assert result.default_factory_id == F1

    def test_group_admin_ignores_user_factories(self):
        """Group admin: even if user_factory_ids are provided, they're ignored."""
        user = make_user(factory_id=F1)
        result = resolve_factory_scope(user, user_factory_ids=[F2, F3], has_group_admin=True)
        assert result.accessible_factory_ids is None

    def test_no_factory_no_user_factories_empty_access(self):
        """No factory_id, no user_factories → accessible=[] (no data access)."""
        user = make_user(factory_id=None)
        result = resolve_factory_scope(user, user_factory_ids=[], has_group_admin=False)
        assert result.accessible_factory_ids == []
        assert result.default_factory_id is None

    def test_group_admin_no_personal_factory(self):
        """Group admin without personal factory_id → default_factory_id=None."""
        user = make_user(factory_id=None)
        result = resolve_factory_scope(user, user_factory_ids=[], has_group_admin=True)
        assert result.accessible_factory_ids is None
        assert result.default_factory_id is None


# ===================================================================
# 2. resolve_product_line_scope
# ===================================================================

class TestResolveProductLineScope:

    def test_bypass_returns_all_mode(self):
        """bypass_row_level_security=True → mode=ALL, codes=None."""
        user = make_user(bypass=True)
        scope = FactoryScope(accessible_factory_ids=[F1], default_factory_id=F1)
        result = resolve_product_line_scope(user, user_product_line_codes=["DC-DC-100"], factory_scope=scope)
        assert result.mode == "ALL"
        assert result.codes is None

    def test_bypass_ignores_product_line_codes(self):
        """Bypass overrides even when product line codes are present."""
        user = make_user(bypass=True)
        scope = FactoryScope(accessible_factory_ids=[F1], default_factory_id=F1)
        result = resolve_product_line_scope(user, user_product_line_codes=["X", "Y"], factory_scope=scope)
        assert result.mode == "ALL"

    def test_no_product_line_codes_returns_none_mode(self):
        """No product line codes → mode=NONE, no data access."""
        user = make_user(bypass=False)
        scope = FactoryScope(accessible_factory_ids=[F1], default_factory_id=F1)
        result = resolve_product_line_scope(user, user_product_line_codes=[], factory_scope=scope)
        assert result.mode == "NONE"
        assert result.codes is None

    def test_explicit_product_line_codes(self):
        """Has product line codes → mode=EXPLICIT, codes match."""
        user = make_user(bypass=False)
        scope = FactoryScope(accessible_factory_ids=[F1], default_factory_id=F1)
        result = resolve_product_line_scope(user, user_product_line_codes=["DC-DC-100", "AC-DC-200"], factory_scope=scope)
        assert result.mode == "EXPLICIT"
        assert result.codes == ["DC-DC-100", "AC-DC-200"]

    def test_factory_admin_bypass_not_cross_factory(self):
        """Factory admin with bypass: product line = ALL but factory scope is still limited.

        This confirms bypass only affects product-line layer, not factory layer.
        """
        user = make_user(factory_id=F1, bypass=True)
        fscope = resolve_factory_scope(user, user_factory_ids=[], has_group_admin=False)
        assert fscope.accessible_factory_ids == [F1]  # factory still limited
        plscope = resolve_product_line_scope(user, user_product_line_codes=["DC-DC-100"], factory_scope=fscope)
        assert plscope.mode == "ALL"  # but product line bypassed


# ===================================================================
# 3. resolve_effective_factory_id
# ===================================================================

class TestResolveEffectiveFactoryId:

    def test_single_factory_user_locked(self):
        """Single-factory user → locked to that factory, ignores None query."""
        scope = FactoryScope(accessible_factory_ids=[F1], default_factory_id=F1)
        result = resolve_effective_factory_id(scope, requested_factory_id=None)
        assert result == F1

    def test_multi_factory_user_with_query_param(self):
        """Multi-factory user with query param → returns requested if accessible."""
        scope = FactoryScope(accessible_factory_ids=[F1, F2], default_factory_id=F1)
        result = resolve_effective_factory_id(scope, requested_factory_id=F2)
        assert result == F2

    def test_multi_factory_user_without_query_param(self):
        """Multi-factory user without query param → None (see all accessible)."""
        scope = FactoryScope(accessible_factory_ids=[F1, F2], default_factory_id=F1)
        result = resolve_effective_factory_id(scope, requested_factory_id=None)
        assert result is None

    def test_group_admin_without_query_param(self):
        """GROUP ADMIN without query param → None (no filter)."""
        scope = FactoryScope(accessible_factory_ids=None, default_factory_id=F1)
        result = resolve_effective_factory_id(scope, requested_factory_id=None)
        assert result is None

    def test_group_admin_with_query_param(self):
        """GROUP ADMIN with query param → returns requested factory."""
        scope = FactoryScope(accessible_factory_ids=None, default_factory_id=F1)
        result = resolve_effective_factory_id(scope, requested_factory_id=F3)
        assert result == F3

    def test_unauthorized_factory_raises_403(self):
        """Requested factory not in accessible_factory_ids → HTTPException 403."""
        scope = FactoryScope(accessible_factory_ids=[F1, F2], default_factory_id=F1)
        with pytest.raises(HTTPException) as exc_info:
            resolve_effective_factory_id(scope, requested_factory_id=F3)
        assert exc_info.value.status_code == 403

    def test_single_factory_user_cannot_request_other(self):
        """Single-factory user requesting different factory → 403."""
        scope = FactoryScope(accessible_factory_ids=[F1], default_factory_id=F1)
        with pytest.raises(HTTPException) as exc_info:
            resolve_effective_factory_id(scope, requested_factory_id=F2)
        assert exc_info.value.status_code == 403

    def test_empty_accessible_with_request_raises_403(self):
        """No accessible factories but requesting one → 403."""
        scope = FactoryScope(accessible_factory_ids=[], default_factory_id=None)
        with pytest.raises(HTTPException) as exc_info:
            resolve_effective_factory_id(scope, requested_factory_id=F1)
        assert exc_info.value.status_code == 403

    def test_multi_factory_user_requests_first(self):
        """Multi-factory user requesting their first accessible → returns it."""
        scope = FactoryScope(accessible_factory_ids=[F1, F2], default_factory_id=F1)
        result = resolve_effective_factory_id(scope, requested_factory_id=F1)
        assert result == F1


# ===================================================================
# 4. apply_scope_filter
# ===================================================================

class TestApplyScopeFilter:

    def _make_model(self, has_factory_id=True, has_product_line_code=True, product_line_field_name="product_line_code"):
        """Create a mock SQLAlchemy model with configurable attributes."""
        model = MagicMock()
        if has_factory_id:
            model.factory_id = MagicMock()
            model.factory_id.__eq__ = MagicMock(return_value=MagicMock())
            model.factory_id.in_ = MagicMock(return_value=MagicMock())
        else:
            del model.factory_id

        if has_product_line_code:
            field_attr = MagicMock()
            field_attr.in_ = MagicMock(return_value=MagicMock())
            setattr(model, product_line_field_name, field_attr)
        else:
            if hasattr(model, product_line_field_name):
                delattr(model, product_line_field_name)

        model.__tablename__ = "test_table"
        return model

    def test_factory_filter_with_effective_factory_id(self):
        """effective_factory_id set → query.where(model.factory_id == effective_factory_id)."""
        model = self._make_model()
        query = MagicMock()
        query.where = MagicMock(return_value=query)

        factory_scope = FactoryScope(accessible_factory_ids=[F1], default_factory_id=F1)
        pl_scope = ProductLineScope(mode="ALL", codes=None)
        user = make_user(bypass=True)
        db = MagicMock()

        apply_scope_filter(query, model, "fmea", factory_scope, F1, pl_scope, user, db)

        model.factory_id.__eq__.assert_called_once_with(F1)
        query.where.assert_called()

    def test_factory_filter_with_accessible_factory_ids(self):
        """No effective_factory_id, but accessible_factory_ids list → .in_()."""
        model = self._make_model()
        query = MagicMock()
        query.where = MagicMock(return_value=query)

        factory_scope = FactoryScope(accessible_factory_ids=[F1, F2], default_factory_id=F1)
        pl_scope = ProductLineScope(mode="ALL", codes=None)
        user = make_user(bypass=True)
        db = MagicMock()

        # effective_factory_id is None, multiple accessible → should use .in_()
        apply_scope_filter(query, model, "fmea", factory_scope, None, pl_scope, user, db)

        model.factory_id.in_.assert_called_once_with([F1, F2])

    def test_factory_filter_empty_accessible_returns_false(self):
        """accessible_factory_ids=[] → query.where(False) (no data)."""
        model = self._make_model()
        query = MagicMock()
        query.where = MagicMock(return_value=query)

        factory_scope = FactoryScope(accessible_factory_ids=[], default_factory_id=None)
        pl_scope = ProductLineScope(mode="ALL", codes=None)
        user = make_user(bypass=True)
        db = MagicMock()

        apply_scope_filter(query, model, "fmea", factory_scope, None, pl_scope, user, db)

        # Should have called where(False) — at least 2 calls: factory filter + possibly pl filter
        # The important thing is where(False) was called
        call_args = [call[0][0] for call in query.where.call_args_list]
        assert False in call_args  # where(False) was called

    def test_group_admin_no_factory_filter(self):
        """GROUP ADMIN without effective_factory_id → no factory filter applied."""
        model = self._make_model()
        query = MagicMock()
        query.where = MagicMock(return_value=query)

        factory_scope = FactoryScope(accessible_factory_ids=None, default_factory_id=F1)
        pl_scope = ProductLineScope(mode="ALL", codes=None)
        user = make_user(bypass=True)
        db = MagicMock()

        apply_scope_filter(query, model, "fmea", factory_scope, None, pl_scope, user, db)

        # Factory filter should NOT have been applied (no where call for factory_id)
        # Only check that factory_id.__eq__ was NOT called
        model.factory_id.__eq__.assert_not_called()

    def test_model_without_factory_id_no_factory_filter(self):
        """Model without factory_id column → no factory filter."""
        model = self._make_model(has_factory_id=False)
        query = MagicMock()
        query.where = MagicMock(return_value=query)

        factory_scope = FactoryScope(accessible_factory_ids=[F1], default_factory_id=F1)
        pl_scope = ProductLineScope(mode="ALL", codes=None)
        user = make_user(bypass=True)
        db = MagicMock()

        apply_scope_filter(query, model, "fmea", factory_scope, F1, pl_scope, user, db)

        # Should not crash; only product-line filter (or none) applied
        query.where.assert_not_called()

    def test_product_line_none_mode_returns_false(self):
        """PL mode=NONE with model having product_line_code → where(False)."""
        model = self._make_model()
        query = MagicMock()
        query.where = MagicMock(return_value=query)

        factory_scope = FactoryScope(accessible_factory_ids=[F1], default_factory_id=F1)
        pl_scope = ProductLineScope(mode="NONE", codes=None)
        user = make_user(bypass=False)
        db = MagicMock()

        apply_scope_filter(query, model, "fmea", factory_scope, F1, pl_scope, user, db)

        call_args = [call[0][0] for call in query.where.call_args_list]
        assert False in call_args

    def test_product_line_explicit_mode_filters(self):
        """PL mode=EXPLICIT → model.product_line_code.in_(codes)."""
        model = self._make_model()
        query = MagicMock()
        query.where = MagicMock(return_value=query)

        factory_scope = FactoryScope(accessible_factory_ids=[F1], default_factory_id=F1)
        pl_scope = ProductLineScope(mode="EXPLICIT", codes=["DC-DC-100", "AC-DC-200"])
        user = make_user(bypass=False)
        db = MagicMock()

        apply_scope_filter(query, model, "fmea", factory_scope, F1, pl_scope, user, db)

        model.product_line_code.in_.assert_called_once_with(["DC-DC-100", "AC-DC-200"])

    def test_product_line_all_mode_no_pl_filter(self):
        """PL mode=ALL → no product line filter applied."""
        model = self._make_model()
        query = MagicMock()
        query.where = MagicMock(return_value=query)

        factory_scope = FactoryScope(accessible_factory_ids=[F1], default_factory_id=F1)
        pl_scope = ProductLineScope(mode="ALL", codes=None)
        user = make_user(bypass=True)
        db = MagicMock()

        apply_scope_filter(query, model, "fmea", factory_scope, F1, pl_scope, user, db)

        model.product_line_code.in_.assert_not_called()

    def test_product_line_spc_module_uses_product_line_field(self):
        """SPC module uses 'product_line' field, not 'product_line_code'."""
        model = self._make_model(has_product_line_code=False, product_line_field_name="product_line")
        # Also add product_line attribute
        pl_attr = MagicMock()
        pl_attr.in_ = MagicMock(return_value=MagicMock())
        model.product_line = pl_attr
        del model.product_line_code

        query = MagicMock()
        query.where = MagicMock(return_value=query)

        factory_scope = FactoryScope(accessible_factory_ids=[F1], default_factory_id=F1)
        pl_scope = ProductLineScope(mode="EXPLICIT", codes=["DC-DC-100"])
        user = make_user(bypass=False)
        db = MagicMock()

        apply_scope_filter(query, model, "spc", factory_scope, F1, pl_scope, user, db)

        pl_attr.in_.assert_called_once_with(["DC-DC-100"])

    def test_unknown_module_no_pl_filter(self):
        """Unknown module → no product line field mapping → no PL filter."""
        model = self._make_model()
        query = MagicMock()
        query.where = MagicMock(return_value=query)

        factory_scope = FactoryScope(accessible_factory_ids=[F1], default_factory_id=F1)
        pl_scope = ProductLineScope(mode="EXPLICIT", codes=["DC-DC-100"])
        user = make_user(bypass=False)
        db = MagicMock()

        apply_scope_filter(query, model, "unknown_module", factory_scope, F1, pl_scope, user, db)

        # Only factory filter, no PL filter (module not in _PRODUCT_LINE_FIELD_MAP)
        model.product_line_code.in_.assert_not_called()


# ===================================================================
# 5. populate_factory_id / validate_factory_invariant (DB-mocked)
# ===================================================================

class TestPopulateFactoryId:
    """Test populate_factory_id with mocked DB session.

    The function uses lazy imports and sqlalchemy.select internally.
    We patch 'select' in factory_scope to accept mock model attributes,
    since the real select() validates column types strictly.
    """

    @pytest.mark.asyncio
    async def test_already_set_factory_id_no_overwrite(self):
        """If factory_id is already set, do not overwrite."""
        record = MagicMock()
        record.factory_id = F1
        record.product_line_code = "DC-DC-100"

        db = AsyncMock()

        await populate_factory_id(record, type(record), db)

        # factory_id should remain F1, no DB calls made
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_product_line_derived(self):
        """Record with product_line_code → factory_id from ProductLine lookup."""
        record = MagicMock()
        record.factory_id = None
        record.product_line_code = "DC-DC-100"

        db = make_db_mock(factory_id_result=F1)

        with patch("app.core.factory_scope.select", side_effect=mock_select):
            await populate_factory_id(record, type(record), db)
        assert record.factory_id == F1

    @pytest.mark.asyncio
    async def test_spc_product_line_field(self):
        """SPC records use 'product_line' attribute instead of 'product_line_code'."""
        record = MagicMock()
        record.factory_id = None
        del record.product_line_code
        record.product_line = "DC-DC-100"

        db = make_db_mock(factory_id_result=F2)

        with patch("app.core.factory_scope.select", side_effect=mock_select):
            await populate_factory_id(record, type(record), db)
        assert record.factory_id == F2

    @pytest.mark.asyncio
    async def test_parent_derived_fmea(self):
        """Record with fmea_id → factory_id from FMEADocument lookup."""
        record = MagicMock()
        record.factory_id = None
        del record.product_line_code
        record.fmea_id = uuid4()

        db = make_db_mock(factory_id_result=F3)

        with patch("app.core.factory_scope.select", side_effect=mock_select):
            await populate_factory_id(record, type(record), db)
        assert record.factory_id == F3

    @pytest.mark.asyncio
    async def test_parent_derived_control_plan(self):
        """Record with cp_id → factory_id from ControlPlan lookup."""
        record = MagicMock()
        record.factory_id = None
        del record.product_line_code
        record.cp_id = uuid4()

        db = make_db_mock(factory_id_result=F1)

        with patch("app.core.factory_scope.select", side_effect=mock_select):
            await populate_factory_id(record, type(record), db)
        assert record.factory_id == F1

    @pytest.mark.asyncio
    async def test_parent_derived_supplier(self):
        """Record with supplier_id → factory_id from Supplier lookup."""
        record = MagicMock()
        record.factory_id = None
        del record.product_line_code
        record.supplier_id = uuid4()

        db = make_db_mock(factory_id_result=F2)

        with patch("app.core.factory_scope.select", side_effect=mock_select):
            await populate_factory_id(record, type(record), db)
        assert record.factory_id == F2

    @pytest.mark.asyncio
    async def test_explicit_scope_default_factory_id(self):
        """No product_line, no parent → uses effective_factory_id from scope."""
        record = MagicMock()
        record.factory_id = None
        del record.product_line_code
        # No parent FK attributes
        record.fmea_id = None
        record.cp_id = None
        record.supplier_id = None
        record.program_id = None
        record.connection_id = None

        db = make_db_mock(factory_id_result=None)

        scope = MagicMock()
        scope.effective_factory_id = F1
        scope.factory_scope = MagicMock()
        scope.factory_scope.default_factory_id = None

        await populate_factory_id(record, type(record), db, scope=scope)
        assert record.factory_id == F1

    @pytest.mark.asyncio
    async def test_scope_factory_scope_default(self):
        """Falls back to factory_scope.default_factory_id when effective_factory_id is None."""
        record = MagicMock()
        record.factory_id = None
        del record.product_line_code
        record.fmea_id = None
        record.cp_id = None
        record.supplier_id = None
        record.program_id = None
        record.connection_id = None

        db = make_db_mock(factory_id_result=None)

        scope = MagicMock()
        scope.effective_factory_id = None
        scope.factory_scope = MagicMock()
        scope.factory_scope.default_factory_id = F2

        await populate_factory_id(record, type(record), db, scope=scope)
        assert record.factory_id == F2

    @pytest.mark.asyncio
    async def test_default_factory_id_parameter(self):
        """Uses default_factory_id parameter when no scope and no derivation."""
        record = MagicMock()
        record.factory_id = None
        del record.product_line_code
        record.fmea_id = None
        record.cp_id = None
        record.supplier_id = None
        record.program_id = None
        record.connection_id = None

        db = make_db_mock(factory_id_result=None)

        await populate_factory_id(record, type(record), db, default_factory_id=F3)
        assert record.factory_id == F3

    @pytest.mark.asyncio
    async def test_no_derivation_raises_value_error(self):
        """Cannot determine factory_id → raises ValueError."""
        record = MagicMock()
        record.factory_id = None
        del record.product_line_code
        record.fmea_id = None
        record.cp_id = None
        record.supplier_id = None
        record.program_id = None
        record.connection_id = None

        db = make_db_mock(factory_id_result=None)

        with pytest.raises(ValueError, match="factory_id"):
            await populate_factory_id(record, type(record), db)

    @pytest.mark.asyncio
    async def test_model_without_factory_id_noop(self):
        """Model without factory_id attribute → no-op."""
        record = MagicMock(spec=[])  # empty spec = no attributes
        db = AsyncMock()

        await populate_factory_id(record, type(record), db)
        # Should not crash, no factory_id set


class TestValidateFactoryInvariant:
    """Test validate_factory_invariant with mocked DB session."""

    @pytest.mark.asyncio
    async def test_no_factory_id_no_validation(self):
        """Record without factory_id → no-op."""
        record = MagicMock()
        record.factory_id = None
        db = AsyncMock()

        await validate_factory_invariant(record, db)
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_product_line_code_no_error(self):
        """Record with factory_id but no product_line_code → passes (nothing to validate against)."""
        record = MagicMock()
        record.factory_id = F1
        del record.product_line_code
        record.product_line = None
        record.supplier_id = None

        db = AsyncMock()

        await validate_factory_invariant(record, db)
        # Should not raise

    @pytest.mark.asyncio
    async def test_product_line_code_consistent(self):
        """factory_id matches product line's factory_id → passes."""
        record = MagicMock()
        record.factory_id = F1
        record.product_line_code = "DC-DC-100"
        record.product_line = None

        db = make_db_mock(factory_id_result=F1)

        with patch("app.core.factory_scope.select", side_effect=mock_select):
            await validate_factory_invariant(record, db)
            # Should not raise

    @pytest.mark.asyncio
    async def test_product_line_code_inconsistent_raises(self):
        """factory_id does NOT match product line's factory_id → ValueError."""
        record = MagicMock()
        record.factory_id = F1
        record.product_line_code = "DC-DC-100"
        record.product_line = None

        db = make_db_mock(factory_id_result=F2)  # different factory

        with patch("app.core.factory_scope.select", side_effect=mock_select):
            with pytest.raises(ValueError, match="factory_id"):
                await validate_factory_invariant(record, db)

    @pytest.mark.asyncio
    async def test_spc_product_line_inconsistent_raises(self):
        """SPC: product_line attribute factory_id mismatch → ValueError."""
        record = MagicMock()
        record.factory_id = F1
        del record.product_line_code
        record.product_line = "DC-DC-100"

        db = make_db_mock(factory_id_result=F2)

        with patch("app.core.factory_scope.select", side_effect=mock_select):
            with pytest.raises(ValueError, match="factory_id"):
                await validate_factory_invariant(record, db)

    @pytest.mark.asyncio
    async def test_supplier_inconsistent_raises(self):
        """Supplier-derived: factory_id mismatch with Supplier → ValueError."""
        record = MagicMock()
        record.factory_id = F1
        del record.product_line_code
        record.product_line = None
        record.supplier_id = uuid4()

        db = make_db_mock(factory_id_result=F2)  # different factory

        with patch("app.core.factory_scope.select", side_effect=mock_select):
            with pytest.raises(ValueError, match="factory_id"):
                await validate_factory_invariant(record, db)

    @pytest.mark.asyncio
    async def test_supplier_consistent_passes(self):
        """Supplier-derived: factory_id matches → passes."""
        record = MagicMock()
        record.factory_id = F1
        del record.product_line_code
        record.product_line = None
        record.supplier_id = uuid4()

        db = make_db_mock(factory_id_result=F1)  # same factory

        with patch("app.core.factory_scope.select", side_effect=mock_select):
            await validate_factory_invariant(record, db)
            # Should not raise


# ===================================================================
# Standalone runner (python tests/test_factory_scope.py)
# ===================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
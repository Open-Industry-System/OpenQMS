"""Unit tests for IQC AQL rule engine and AQL state calculation.

Pure unit tests — no database required. Tests cover:
- get_aql_by_state: AQL ladder calculation for normal/tightened/reduced/frozen states
- RuleEngine.evaluate: rule priority, condition matching, result building
- Dedup consistency: rule engine produces identical results for identical inputs
"""

import uuid

import pytest

from app.services.iqc_aql_service import get_aql_by_state, RuleEngine, AqlContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(**overrides) -> AqlContext:
    """Build an AqlContext with sensible defaults; override any field."""
    defaults = dict(
        supplier_id=uuid.uuid4(),
        material_id=uuid.uuid4(),
        profile_state="normal",
        current_aql=1.0,
        base_aql=1.0,
        consecutive_accepted=0,
        consecutive_rejected=0,
        last_30d_batch_count=0,
        last_30d_ppm=None,
        last_90d_ppm=None,
        open_scar_count=0,
        supplier_rating=None,
        has_safety_defect=False,
        linked_customer_complaint=False,
        ppm_threshold_high=5000.0,
        ppm_threshold_low=1000.0,
    )
    defaults.update(overrides)
    return AqlContext(**defaults)


# ===================================================================
# get_aql_by_state tests
# ===================================================================


def test_get_aql_by_state_normal():
    """base_aql=1.0, state='normal' returns 1.0 unchanged."""
    assert get_aql_by_state(base_aql=1.0, state="normal") == 1.0


def test_get_aql_by_state_tightened():
    """base_aql=1.0, state='tightened', aql_steps=1 → 0.65 (one step left on ladder)."""
    assert get_aql_by_state(base_aql=1.0, state="tightened", aql_steps=1) == 0.65


def test_get_aql_by_state_reduced():
    """base_aql=1.0, state='reduced', aql_steps=1 → 1.5 (one step right on ladder)."""
    assert get_aql_by_state(base_aql=1.0, state="reduced", aql_steps=1) == 1.5


def test_get_aql_by_state_frozen_returns_current():
    """state='frozen' returns current_aql (NOT base_aql)."""
    assert get_aql_by_state(
        base_aql=1.0, state="frozen", current_aql=0.65
    ) == 0.65


def test_get_aql_by_state_frozen_no_current_falls_back():
    """state='frozen' with current_aql=None falls back to base_aql."""
    assert get_aql_by_state(
        base_aql=1.0, state="frozen", current_aql=None
    ) == 1.0


def test_get_aql_by_state_aql_steps_2():
    """base_aql=1.0, state='tightened', aql_steps=2 → 0.40 (two steps left)."""
    assert get_aql_by_state(base_aql=1.0, state="tightened", aql_steps=2) == 0.40


def test_get_aql_by_state_min_max_boundary():
    """base_aql=1.0, state='reduced', aql_steps=3, max_aql=2.5 → clamped to 2.5."""
    # Without max_aql this would be index 13 = 4.0, but max_aql clamps to 2.5
    assert get_aql_by_state(
        base_aql=1.0, state="reduced", aql_steps=3, max_aql=2.5
    ) == 2.5


# ===================================================================
# RuleEngine tests
# ===================================================================


def test_rule_engine_safety_defect():
    """has_safety_defect=True triggers FREEZE_SAFETY_DEFECT (highest priority)."""
    ctx = _make_ctx(has_safety_defect=True)
    result = RuleEngine().evaluate(ctx)
    assert result["target_state"] == "frozen"
    assert result["frozen_aql_policy"] == "tighten"
    assert result["aql_steps"] == 1
    assert result["rule_id"] == "FREEZE_SAFETY_DEFECT"


def test_rule_engine_scar_unresolved_reduced():
    """open_scar_count=1 + profile_state='reduced' triggers FREEZE_SCAR_UNRESOLVED."""
    ctx = _make_ctx(open_scar_count=1, profile_state="reduced")
    result = RuleEngine().evaluate(ctx)
    assert result["target_state"] == "frozen"
    assert result["frozen_aql_policy"] == "current"
    assert result["rule_id"] == "FREEZE_SCAR_UNRESOLVED"


def test_rule_engine_1_reject():
    """consecutive_rejected=1 triggers TIGHTEN_1_REJECT."""
    ctx = _make_ctx(consecutive_rejected=1)
    result = RuleEngine().evaluate(ctx)
    assert result["target_state"] == "tightened"
    assert result["aql_steps"] == 1
    assert result["rule_id"] == "TIGHTEN_1_REJECT"


def test_rule_engine_2_rejects():
    """consecutive_rejected=2 triggers TIGHTEN_2_REJECTS (priority 80 > TIGHTEN_1_REJECT 70)."""
    ctx = _make_ctx(consecutive_rejected=2)
    result = RuleEngine().evaluate(ctx)
    assert result["target_state"] == "tightened"
    assert result["aql_steps"] == 2
    assert result["rule_id"] == "TIGHTEN_2_REJECTS"


def test_rule_engine_return_to_normal():
    """profile_state='tightened' + consecutive_accepted=5 triggers RETURN_TO_NORMAL."""
    ctx = _make_ctx(profile_state="tightened", consecutive_accepted=5)
    result = RuleEngine().evaluate(ctx)
    assert result["target_state"] == "normal"
    assert result["aql_steps"] == 0
    assert result["rule_id"] == "RETURN_TO_NORMAL"


def test_rule_engine_reduce_1():
    """profile_state='normal', consecutive_accepted=5, open_scar_count=0 triggers REDUCE_LEVEL_1."""
    ctx = _make_ctx(
        profile_state="normal",
        consecutive_accepted=5,
        open_scar_count=0,
        has_safety_defect=False,
    )
    result = RuleEngine().evaluate(ctx)
    assert result["target_state"] == "reduced"
    assert result["aql_steps"] == 1
    assert result["rule_id"] == "REDUCE_LEVEL_1"


def test_rule_engine_reduce_2():
    """All REDUCE_LEVEL_2 conditions met: consecutive_accepted=10, rating=A, ppm=500, no SCAR."""
    ctx = _make_ctx(
        profile_state="normal",
        consecutive_accepted=10,
        supplier_rating="A",
        last_90d_ppm=500.0,
        open_scar_count=0,
        has_safety_defect=False,
    )
    result = RuleEngine().evaluate(ctx)
    assert result["target_state"] == "reduced"
    assert result["aql_steps"] == 2
    assert result["rule_id"] == "REDUCE_LEVEL_2"


def test_rule_engine_no_skip_to_reduce():
    """profile_state='tightened' + consecutive_accepted=5 returns to normal, NOT reduced.

    RETURN_TO_NORMAL (priority 30) fires before REDUCE_LEVEL_1 (priority 10).
    """
    ctx = _make_ctx(
        profile_state="tightened",
        consecutive_accepted=5,
        open_scar_count=0,
        has_safety_defect=False,
    )
    result = RuleEngine().evaluate(ctx)
    assert result["target_state"] == "normal"
    assert result["rule_id"] == "RETURN_TO_NORMAL"


def test_rule_engine_keep():
    """No matching rule → direction='keep', stays in current state."""
    ctx = _make_ctx(
        profile_state="normal",
        consecutive_accepted=0,
        consecutive_rejected=0,
        open_scar_count=0,
        has_safety_defect=False,
        linked_customer_complaint=False,
    )
    result = RuleEngine().evaluate(ctx)
    assert result["direction"] == "keep"
    assert result["rule_id"] == "KEEP"


def test_rule_engine_reduce_2_from_reduced():
    """REDUCE_LEVEL_2 also triggers when profile_state='reduced' (condition allows it)."""
    ctx = _make_ctx(
        profile_state="reduced",
        consecutive_accepted=10,
        supplier_rating="A",
        last_90d_ppm=500.0,
        open_scar_count=0,
        has_safety_defect=False,
    )
    result = RuleEngine().evaluate(ctx)
    assert result["target_state"] == "reduced"
    assert result["aql_steps"] == 2
    assert result["rule_id"] == "REDUCE_LEVEL_2"


def test_idempotent_dedup_key():
    """Rule engine produces identical results for identical inputs (dedup consistency).

    The dedup logic in RecommendationManager.generate_recommendation suppresses
    duplicate (profile + target_state + recommended_aql) combinations. This test
    verifies the rule engine itself is deterministic — same context always yields
    the same recommendation parameters.
    """
    ctx = _make_ctx(
        profile_state="normal",
        consecutive_accepted=5,
        open_scar_count=0,
        has_safety_defect=False,
    )
    engine = RuleEngine()

    result1 = engine.evaluate(ctx)
    result2 = engine.evaluate(ctx)

    # Same rule fires
    assert result1["rule_id"] == result2["rule_id"]
    # Same target state and AQL steps → same recommended_aql would be computed
    assert result1["target_state"] == result2["target_state"]
    assert result1["aql_steps"] == result2["aql_steps"]

    # Verify the computed AQL is also identical
    aql1 = get_aql_by_state(ctx.base_aql, result1["target_state"], result1["aql_steps"])
    aql2 = get_aql_by_state(ctx.base_aql, result2["target_state"], result2["aql_steps"])
    assert aql1 == aql2

from dataclasses import replace
from hashlib import sha256
from uuid import UUID

import pytest


def test_final_reserved_attempt_cannot_be_reused_after_transport_failure():
    from app.services.agent_runtime.pfmea_impact_release import (
        FmeaReleaseBudget,
        ProjectionBudgetExceeded,
        reserve_fmea_release,
    )

    committed = FmeaReleaseBudget(attempts=15)
    final = reserve_fmea_release(committed, projection_bytes=b"page", element_keys=["node"])
    assert final.attempts == 16
    assert final.byte_count == 4
    # A committed attempt remains in the ledger even if the transport never sent it.
    with pytest.raises(ProjectionBudgetExceeded, match="attempts"):
        reserve_fmea_release(final, projection_bytes=b"page", element_keys=["node"])
    assert committed.attempts == 15


def test_retry_charges_exact_bytes_and_attempts_but_deduplicates_graph_elements():
    from app.services.agent_runtime.pfmea_impact_release import (
        FmeaReleaseBudget,
        reserve_fmea_release,
    )

    projection = '{"name":"螺栓"}'.encode("utf-8")
    first = reserve_fmea_release(
        FmeaReleaseBudget(), projection_bytes=projection, element_keys=["step", "step", "mode"]
    )
    retry = reserve_fmea_release(first, projection_bytes=projection, element_keys=["mode", "step"])
    assert retry.attempts == 2
    assert retry.byte_count == 2 * len(projection)
    assert retry.element_keys == frozenset({"step", "mode"})


def test_graph_element_limit_counts_the_union_of_reserved_attempts():
    from app.services.agent_runtime.pfmea_impact_release import (
        FmeaReleaseBudget,
        ProjectionBudgetExceeded,
        reserve_fmea_release,
    )

    committed = FmeaReleaseBudget(
        attempts=1, byte_count=100, element_keys=frozenset(str(n) for n in range(199)),
    )
    final = reserve_fmea_release(
        committed, projection_bytes=b"x", element_keys=["100", "new", "new"],
    )
    assert len(final.element_keys) == 200
    with pytest.raises(ProjectionBudgetExceeded, match="elements"):
        reserve_fmea_release(final, projection_bytes=b"x", element_keys=["200th-other"])
    assert len(committed.element_keys) == 199


def test_byte_budget_accepts_exact_boundary_and_rejects_next_byte():
    from app.services.agent_runtime.pfmea_impact_release import (
        FmeaReleaseBudget,
        ProjectionBudgetExceeded,
        reserve_fmea_release,
    )

    committed = FmeaReleaseBudget(attempts=1, byte_count=256 * 1024 - 3)
    final = reserve_fmea_release(
        committed, projection_bytes="漏".encode("utf-8"), element_keys=[],
    )
    assert final.byte_count == 256 * 1024
    with pytest.raises(ProjectionBudgetExceeded, match="bytes"):
        reserve_fmea_release(final, projection_bytes=b"x", element_keys=[])


@pytest.fixture
def release():
    from app.services.agent_runtime.pfmea_impact_release import PageRelease, PageScope

    return PageRelease(
        release_ref=UUID(int=3),
        scope=PageScope(
            task_id=UUID(int=1),
            run_id=UUID(int=2),
            lease_epoch=4,
            binding_digest=sha256(b"task binding").hexdigest(),
            snapshot_digest=sha256(b"snapshot").hexdigest(),
            scope_ref="step-40",
        ),
        page_key="page-1",
        payload_digest=sha256(b"page content").hexdigest(),
    )


def _confirm(release, **overrides):
    from app.services.agent_runtime.pfmea_impact_release import confirm_page

    return confirm_page(
        release,
        **(
            dict(
                scope=release.scope,
                release_ref=release.release_ref,
                page_key=release.page_key,
                payload_digest=release.payload_digest,
            )
            | overrides
        ),
    )


def _expected_pages(release):
    return {release.page_key: release.payload_digest}


def test_release_requires_separate_confirmation_and_retry_cannot_count_twice(release):
    from app.services.agent_runtime.pfmea_impact_release import confirmed_page_keys

    expected = _expected_pages(release)
    assert confirmed_page_keys(release.scope, [], expected_page_digests=expected) == frozenset()
    original = _confirm(release)
    retry = _confirm(replace(release, release_ref=UUID(int=4)))
    assert original == _confirm(release)
    assert confirmed_page_keys(
        release.scope, [original, retry], expected_page_digests=expected,
    ) == frozenset({"page-1"})
    next_digest = sha256(b"next page").hexdigest()
    next_page = _confirm(
        replace(release, release_ref=UUID(int=5), page_key="page-2", payload_digest=next_digest)
    )
    assert confirmed_page_keys(
        release.scope, [original, retry, next_page],
        expected_page_digests=expected | {"page-2": next_digest},
    ) == frozenset({"page-1", "page-2"})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("task_id", UUID(int=10)),
        ("run_id", UUID(int=11)),
        ("lease_epoch", 5),
        ("binding_digest", sha256(b"old binding").hexdigest()),
        ("snapshot_digest", sha256(b"old snapshot").hexdigest()),
        ("scope_ref", "step-50"),
    ],
)
def test_confirmation_cannot_replay_across_scope_or_count_foreign_pages(release, field, value):
    from app.services.agent_runtime.pfmea_impact_release import (
        PageConfirmationMismatch,
        confirmed_page_keys,
    )

    foreign = replace(release.scope, **{field: value})
    with pytest.raises(PageConfirmationMismatch):
        _confirm(release, scope=foreign)
    assert confirmed_page_keys(
        foreign, [_confirm(release)], expected_page_digests=_expected_pages(release),
    ) == frozenset()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("release_ref", UUID(int=8)),
        ("page_key", "page-2"),
        ("payload_digest", sha256(b"partial body").hexdigest()),
    ],
)
def test_confirmation_must_match_exact_committed_body_and_page(release, field, value):
    from app.services.agent_runtime.pfmea_impact_release import PageConfirmationMismatch

    with pytest.raises(PageConfirmationMismatch):
        _confirm(release, **{field: value})


def test_same_page_with_conflicting_committed_digests_cannot_prove_coverage(release):
    from app.services.agent_runtime.pfmea_impact_release import (
        PageConfirmationMismatch,
        confirmed_page_keys,
    )

    changed = replace(
        release,
        release_ref=UUID(int=8),
        payload_digest=sha256(b"different projection").hexdigest(),
    )
    with pytest.raises(PageConfirmationMismatch):
        confirmed_page_keys(
            release.scope, [_confirm(release), _confirm(changed)],
            expected_page_digests=_expected_pages(release),
        )


@pytest.mark.parametrize("invalid", [{"attempts": -1}, {"byte_count": -1}, {"attempts": True}])
def test_invalid_ledger_counts_do_not_expand_budget(invalid):
    from app.services.agent_runtime.pfmea_impact_release import (
        FmeaReleaseBudget,
        reserve_fmea_release,
    )

    with pytest.raises(ValueError, match="ledger counts"):
        reserve_fmea_release(
            FmeaReleaseBudget(**invalid), projection_bytes=b"page", element_keys=[],
        )


def test_committed_release_row_cannot_be_used_as_a_confirmation(release):
    from app.services.agent_runtime.pfmea_impact_release import (
        PageConfirmationMismatch,
        confirmed_page_keys,
    )

    with pytest.raises(PageConfirmationMismatch):
        confirmed_page_keys(release.scope, [release], expected_page_digests=_expected_pages(release))


def test_only_changed_retry_ack_cannot_prove_canonical_coverage(release):
    from app.services.agent_runtime.pfmea_impact_release import (
        PageConfirmationMismatch,
        confirmed_page_keys,
    )

    retry = replace(
        release,
        release_ref=UUID(int=8),
        payload_digest=sha256(b"page altered").hexdigest(),
    )
    retry_ack = _confirm(retry)
    # The retry receipt and its ACK agree, but the original ACK was lost.
    # Independent server expectations must still reject this ACK as coverage.
    with pytest.raises(PageConfirmationMismatch):
        confirmed_page_keys(
            release.scope, [retry_ack], expected_page_digests=_expected_pages(release),
        )


def test_verify_page_payload_hashes_exact_encoded_projection(release):
    from app.services.agent_runtime.pfmea_impact_release import verify_page_payload

    assert verify_page_payload(
        release.page_key, b"page content", expected_page_digests=_expected_pages(release),
    ) == release.payload_digest


@pytest.mark.parametrize(
    ("page_key", "projection_bytes"),
    [("page-1", b"page altered"), ("page-2", b"page content")],
)
def test_verify_page_payload_rejects_changed_or_unplanned_send(release, page_key, projection_bytes):
    from app.services.agent_runtime.pfmea_impact_release import (
        PageConfirmationMismatch,
        verify_page_payload,
    )

    with pytest.raises(PageConfirmationMismatch):
        verify_page_payload(
            page_key, projection_bytes, expected_page_digests=_expected_pages(release),
        )


def test_unplanned_page_ack_cannot_add_coverage(release):
    from app.services.agent_runtime.pfmea_impact_release import (
        PageConfirmationMismatch,
        confirmed_page_keys,
    )

    unknown = _confirm(replace(release, page_key="page-2"))
    with pytest.raises(PageConfirmationMismatch):
        confirmed_page_keys(
            release.scope, [unknown], expected_page_digests=_expected_pages(release),
        )

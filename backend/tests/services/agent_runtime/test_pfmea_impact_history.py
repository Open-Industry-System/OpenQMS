"""R7 history authority and exact receipt association without DB fixtures."""
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.schemas.pfmea_impact import ImpactSourceRef
from app.services.agent_runtime import pfmea_impact_history as history
from app.services.agent_runtime.pfmea_impact_completion import Conclusion

RESULT, TASK, RUN, REPORT, FMEA, APPROVAL, FACTORY, REVIEWER, ACTOR, RECEIPT, SOURCE = (
    UUID(int=index) for index in range(1, 12)
)
HASH = sha256(b"approved graph").hexdigest()
CANDIDATE = ImpactSourceRef(
    source_id=SOURCE, object_id=FMEA, module="fmea", version=HASH,
    projection_id="pfmea.approved.node", factory_id=FACTORY, product_line_code="A",
    snapshot_id=APPROVAL, node_id="original node",
)


@pytest.fixture
def case(monkeypatch):
    db = SimpleNamespace(no_autoflush=nullcontext())
    scope = SimpleNamespace(user=SimpleNamespace(user_id=REVIEWER))
    expected = history.HistoryLookup(report_id=REPORT, task_id=TASK, result_id=RESULT)
    binding = SimpleNamespace(
        target=SimpleNamespace(fmea_id=FMEA, approved_version_id=APPROVAL, major_no=1),
        capa=SimpleNamespace(report_id=REPORT, factory_id=FACTORY, product_line_code="A", sources=()),
    )
    record = history._ResolvedHistory(
        lookup=expected, run_id=RUN, epoch=5, binding=binding, original_hash=HASH,
        conclusion=Conclusion.INSUFFICIENT_EVIDENCE, created_at=datetime.now(UTC),
        receipt_ids=frozenset({RECEIPT}), sources=frozenset({CANDIDATE}),
    )
    state = SimpleNamespace(db=db, scope=scope, expected=expected, record=record, actors=[], phases=[],
                            revoked=False, stale=False, changed=False)

    async def load(db, lookup):
        state.phases.append("load")
        if lookup != expected:
            raise history.ImpactHistoryUnavailable()
        return replace(state.record, epoch=6) if state.changed and "lock" in state.phases else state.record

    async def authorize_bound(db, reader, record):
        state.phases.append("authorize-bound")
        state.actors.append(reader.user.user_id)
        if state.revoked and "lock" in state.phases:
            raise PermissionError("source access withdrawn")

    async def lock(db, reader, record):
        state.phases.append("lock")
        assert record.lookup.report_id == REPORT
        assert reader.user.user_id != ACTOR

    async def baseline(db, record):
        state.phases.append("old-snapshot")

    async def freshness(db, reader, record):
        state.phases.append("freshness")
        return state.stale

    monkeypatch.setattr(history, "_load_history", load)
    monkeypatch.setattr(history, "_authorize_bound", authorize_bound)
    monkeypatch.setattr(history, "_lock_history", lock)
    monkeypatch.setattr(history, "_assert_historical_target", baseline)
    monkeypatch.setattr(history, "_is_stale", freshness)
    return state


@pytest.mark.asyncio
async def test_reader_can_differ_from_initiator_and_entire_bound_set_is_rechecked_under_lock(case):
    async def authorize(db, current, binding, additional):
        case.phases.append("authorize-extra")
        assert current.user.user_id == REVIEWER
        assert additional == frozenset({CANDIDATE})
        return True

    result = await history.read_history_metadata(case.db, case.scope, case.expected, authorize=authorize)

    assert result.result_id == RESULT and result.fmea_id == FMEA
    assert result.approved_version_id == APPROVAL and not result.stale
    assert case.actors == [REVIEWER, REVIEWER]
    assert case.phases == [
        "load", "authorize-bound", "lock", "load", "authorize-bound", "old-snapshot",
        "authorize-extra", "freshness",
    ]


@pytest.mark.asyncio
async def test_direct_evidence_requires_actual_citation_in_saved_measure(case, monkeypatch):
    payload = {"analyses": [{"analysis_ref": "a", "fact_refs": []}],
        "assessments": [{"analysis_ref": "a", "evidence_refs": [], "exclusion_refs": []}]}

    async def read_payload(*args, **kwargs):
        return payload

    async def authorize(*args):
        return True

    monkeypatch.setattr(history, "_review_payload", read_payload)
    with pytest.raises(history.ImpactHistoryUnavailable):
        await history.read_history_evidence(case.db, case.scope, case.expected, SOURCE, authorize=authorize)
    payload["assessments"][0]["evidence_refs"] = [str(SOURCE)]
    result = await history.read_history_evidence(case.db, case.scope, case.expected, SOURCE, authorize=authorize)
    assert result == {"label": CANDIDATE.projection_id, "text": CANDIDATE.version}


@pytest.mark.asyncio
async def test_revoke_between_initial_authorization_and_final_lock_denies_even_when_stale(case):
    case.revoked = case.stale = True

    async def authorize(*args):
        pytest.fail("late revocation must deny before any extra evidence or stale metadata is selected")

    with pytest.raises(history.ImpactHistoryUnavailable, match="^Impact result unavailable$"):
        await history.read_history_metadata(case.db, case.scope, case.expected, authorize=authorize)
    assert "freshness" not in case.phases


@pytest.mark.asyncio
async def test_changed_metadata_during_lock_cannot_be_rebound(case):
    case.changed = True

    async def authorize(*args):
        pytest.fail("history changed between initial and anchored reads")

    with pytest.raises(history.ImpactHistoryUnavailable):
        await history.read_history_metadata(case.db, case.scope, case.expected, authorize=authorize)


@pytest.mark.asyncio
async def test_wrong_result_report_or_task_pair_is_indistinguishable_from_missing(case):
    async def authorize(*args):
        pytest.fail("wrong history coordinates are unavailable")

    for field in ("result_id", "task_id", "report_id"):
        lookup = replace(case.expected, **{field: UUID(int=99)})
        with pytest.raises(history.ImpactHistoryUnavailable, match="^Impact result unavailable$"):
            await history.read_history_metadata(case.db, case.scope, lookup, authorize=authorize)


@pytest.mark.asyncio
async def test_resolved_source_ref_uses_approved_snapshot_even_if_result_is_stale(case):
    case.stale = True

    async def authorize(*args):
        return True

    result = await history.read_history_metadata(case.db, case.scope, case.expected, authorize=authorize)
    assert result.stale
    source = await history.resolve_history_source(case.db, case.scope, case.expected, SOURCE, authorize=authorize)
    assert source == CANDIDATE and source.snapshot_id == APPROVAL

    with pytest.raises(history.ImpactHistoryUnavailable, match="^Impact result unavailable$"):
        await history.resolve_history_source(case.db, case.scope, case.expected, UUID(int=99), authorize=authorize)


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"snapshot_id": UUID(int=97)}, {"object_id": UUID(int=98)}, {"product_line_code": "B"},
], ids=["snapshot", "object", "product-line"])
async def test_wrong_snapshot_object_or_line_cannot_enter_authorized_history(case, changes):
    case.record = replace(case.record, sources=frozenset({CANDIDATE.model_copy(update=changes)}))

    async def authorize(*args):
        pytest.fail("The callback cannot approve references outside the historic binding")

    with pytest.raises(history.ImpactHistoryUnavailable):
        await history.read_history_metadata(case.db, case.scope, case.expected, authorize=authorize)


@pytest.mark.asyncio
async def test_refused_additional_source_denies_full_metadata(case):
    async def authorize(*args):
        return False

    with pytest.raises(history.ImpactHistoryUnavailable):
        await history.read_history_metadata(case.db, case.scope, case.expected, authorize=authorize)
    assert "freshness" not in case.phases


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", [None, "narrowed-links", "missing", "legacy", "active-epoch"])
async def test_load_history_requires_r7_terminal_type_and_every_scoped_release_link(monkeypatch, invalid):
    lookup = history.HistoryLookup(report_id=REPORT, task_id=TASK, result_id=RESULT)
    binding = SimpleNamespace(
        activation=SimpleNamespace(installation_id=ACTOR),
        target=SimpleNamespace(snapshot_hash=HASH),
        capa=SimpleNamespace(report_id=REPORT),
    )
    candidate = SimpleNamespace(
        run_id=RUN, created_at=datetime.now(UTC), data_class="restricted", contract=history.RESULT_CONTRACT,
        result_binding=HASH, binding_digest=HASH, request_digest=HASH, epoch=7, terminal_epoch=8,
        installation_id=ACTOR, conclusion="insufficient_evidence",
    )
    links = [RECEIPT, UUID(int=70)]
    result = candidate
    if invalid == "narrowed-links":
        links.pop()
    elif invalid == "missing":
        result = None
    elif invalid == "legacy":
        candidate.contract = None
    elif invalid == "active-epoch":
        candidate.terminal_epoch = candidate.epoch

    from sqlalchemy.dialects import postgresql

    class DB:
        async def execute(self, statement):
            sql = str(statement.compile(dialect=postgresql.dialect()))
            assert "agent_results.payload," not in sql and "agent_results.payload AS" not in sql
            assert "agent_results.result_id =" in sql
            assert "agent_tasks.target_capa_id =" in sql
            return SimpleNamespace(one_or_none=lambda: result)

        async def scalars(self, statement):
            return SimpleNamespace(all=lambda: links)

    async def load_binding(db, task_id):
        assert task_id == TASK
        return binding

    async def authorized_ledger(db, scope, exact):
        assert scope.run_id == RUN and scope.lease_epoch == 7 and exact is binding
        return (
            (SimpleNamespace(receipt_id=RECEIPT), SimpleNamespace(receipt_id=UUID(int=70))),
            frozenset({CANDIDATE}),
        )

    monkeypatch.setattr(history, "load_binding", load_binding)
    monkeypatch.setattr(history, "_publication_evidence", authorized_ledger)
    if invalid is None:
        record = await history._load_history(DB(), lookup)
        assert record.sources == frozenset({CANDIDATE})
        assert record.receipt_ids == {RECEIPT, UUID(int=70)}
    else:
        with pytest.raises(history.ImpactHistoryUnavailable):
            await history._load_history(DB(), lookup)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["none", "version", "scope-generation", "hash", "new-capa-denied"])
async def test_freshness_is_independent_of_historic_validity(monkeypatch, change):
    generation = UUID(int=121)
    capa = SimpleNamespace(report_id=REPORT, factory_id=FACTORY, product_line_code="A")
    binding = SimpleNamespace(
        target=SimpleNamespace(fmea_id=FMEA, approved_version_id=APPROVAL, scope_generation=generation),
        capa=capa,
    )
    record = SimpleNamespace(binding=binding, original_hash=HASH)

    async def metadata(db, reader, report_id):
        assert report_id == REPORT
        if change == "new-capa-denied":
            raise PermissionError("Only the newly added source is unavailable to this reviewer")
        return SimpleNamespace(binding=capa)

    async def target(db, reader, fmea_id, **scope):
        assert fmea_id == FMEA and scope == {"factory_id": FACTORY, "product_line_code": "A"}
        return SimpleNamespace(
            version_id=UUID(int=122) if change == "version" else APPROVAL,
            scope_generation=UUID(int=123) if change == "scope-generation" else generation,
            sha256_hash="c" * 64 if change == "hash" else HASH,
        )

    monkeypatch.setattr(history.capa_impact_material, "_metadata", metadata)
    monkeypatch.setattr(history, "read_approved_target", target)
    assert await history._is_stale(None, None, record) == (change != "none")

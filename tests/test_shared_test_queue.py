from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import runpy

import pytest


Queue = runpy.run_path(str(Path(__file__).parents[1] / "scripts/shared-test-queue.py"))["Queue"]


def release(pr, head="a"):
    return {"pr": pr, "head": head * 40, "merge": "b" * 40, "plan": "c" * 64}


def test_lowest_eligible_pr_and_slot_cannot_be_stolen(tmp_path):
    db = tmp_path / "queue.sqlite3"
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: Queue(db).tick([release(46), release(45)]), range(2)))
    active, duplicate = claims
    assert active == duplicate
    assert active["pr"] == 45
    queue = Queue(db)
    queue.acknowledge(active["lease"], "ready", eligible=[release(45), release(46)])
    assert queue.tick([release(42), release(45), release(46)])["pr"] == 45

    released = queue.acknowledge(active["lease"], "passed", eligible=[release(45)])
    assert released["phase"] == "releasing"
    assert queue.tick([release(42), release(45), release(46)]) == released
    queue.acknowledge(active["lease"], "released")
    next_slot = queue.tick([release(46), release(45), release(42)])
    assert next_slot["pr"] == 42
    with pytest.raises(ValueError, match="stale"):
        queue.acknowledge(active["lease"], "released")


def test_updated_pr_waits_for_previous_version_cleanup(tmp_path):
    queue = Queue(tmp_path / "queue.sqlite3")
    first = queue.tick([release(45), release(46)])
    new = [release(45, "d"), release(46)]
    assert queue.tick(new) == first  # Never interrupt an in-flight deploy.
    queue.acknowledge(first["lease"], "ready", eligible=[release(45), release(46)])
    with pytest.raises(ValueError, match="no longer eligible"):
        queue.acknowledge(first["lease"], "passed", eligible=new)
    stale = queue.tick(new)
    assert stale["outcome"] == "superseded"
    with pytest.raises(ValueError):
        queue.acknowledge(first["lease"], "passed", eligible=new)
    queue.acknowledge(first["lease"], "released")
    instance = queue.tick(new)
    assert instance["pr"] == 45 and instance["head"] == "d" * 40


def test_testing_retains_legacy_slot_until_human_acceptance(tmp_path):
    queue = Queue(tmp_path / 'queue.sqlite3')
    eligible = [release(45), release(46), release(47)]
    first = queue.tick(eligible)
    queue.acknowledge(first['lease'], 'ready', eligible=eligible)
    with queue.transaction() as db:
        db.execute('UPDATE slot SET expires_at = 1')
    for _ in range(3):
        assert queue.tick(eligible)['lease'] == first['lease']
        assert queue.tick(eligible)['phase'] == 'testing'
    queue.acknowledge(first['lease'], 'passed', eligible=eligible)
    queue.acknowledge(first['lease'], 'released')
    second = queue.tick(eligible)
    assert second['pr'] == 46
    assert queue.acknowledge(second['lease'], 'deploy-failed')['phase'] == 'releasing'
    assert queue.tick([release(47)])['pr'] == 46
    queue.acknowledge(second['lease'], 'released')
    assert queue.tick(eligible)['pr'] == 47


def test_retry_requires_exact_cleaned_deployment_failure_and_new_lease(tmp_path):
    queue = Queue(tmp_path / 'queue.sqlite3')
    current = release(45)
    eligible = [current, release(46)]
    first = queue.tick(eligible)
    with pytest.raises(ValueError, match='idle'):
        queue.retry_failed(current)
    queue.acknowledge(first['lease'], 'deploy-failed')
    queue.acknowledge(first['lease'], 'released')
    with pytest.raises(ValueError, match='exact deployment failure'):
        queue.retry_failed(release(45, 'd'))
    assert queue.retry_failed(current) == {'phase': 'idle'}
    retried = queue.tick(eligible)
    assert retried['pr'] == 45 and retried['lease'] != first['lease']
    queue.acknowledge(retried['lease'], 'ready', eligible=eligible)
    queue.acknowledge(retried['lease'], 'passed', eligible=eligible)
    queue.acknowledge(retried['lease'], 'released')
    with pytest.raises(ValueError, match='exact deployment failure'):
        queue.retry_failed(current)


def test_switch_holds_inflight_deployment_then_cleans_and_requeues(tmp_path):
    queue = Queue(tmp_path / 'queue.sqlite3')
    earlier, target = release(45), release(48)
    eligible = [earlier, target]
    initial = queue.tick(eligible)
    assert initial['pr'] == 45
    assert queue.request_switch(11, target, eligible) == initial
    assert queue.tick(eligible) == initial
    queue.acknowledge(initial['lease'], 'ready', eligible=eligible)
    interrupted = queue.tick(eligible)
    assert interrupted['outcome'] == 'switched'
    assert queue.tick(eligible)['lease'] == initial['lease']
    queue.acknowledge(initial['lease'], 'released')
    chosen = queue.tick(eligible)
    assert chosen['pr'] == 48
    assert queue.request_switch(11, target, eligible) == chosen
    queue.acknowledge(chosen['lease'], 'ready', eligible=eligible)
    queue.acknowledge(chosen['lease'], 'passed', eligible=eligible)
    queue.acknowledge(chosen['lease'], 'released')
    with pytest.raises(ValueError, match='already passed'):
        queue.request_switch(12, target, eligible)
    assert queue.tick(eligible)['pr'] == 45


def test_switch_target_changes_before_lease_release(tmp_path):
    queue = Queue(tmp_path / 'queue.sqlite3')
    earlier, target = release(45), release(48)
    initial = queue.tick([earlier, target])
    queue.acknowledge(initial['lease'], 'ready', eligible=[earlier, target])
    with pytest.raises(ValueError, match='not currently eligible'):
        queue.request_switch(1, target, [earlier])
    queue.request_switch(1, target, [earlier, target])
    with pytest.raises(ValueError, match='already pending'):
        queue.request_switch(2, earlier, [earlier, target])
    old = queue.tick([earlier, release(48, 'd')])
    assert (old['phase'], old['lease']) == ('testing', initial['lease'])
    queue.request_switch(1, target, [earlier, target])
    assert queue.tick([earlier, target])['phase'] == 'testing'

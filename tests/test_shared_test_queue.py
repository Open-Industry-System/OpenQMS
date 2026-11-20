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
        claims = list(pool.map(lambda _: Queue(db).tick([release(46), release(45)], 10), range(2)))
    active, duplicate = claims
    assert active == duplicate
    assert active["pr"] == 45
    queue = Queue(db)
    queue.acknowledge(active["lease"], "ready", 20, 60, [release(45), release(46)])
    assert queue.tick([release(42), release(45), release(46)], 25)["pr"] == 45

    released = queue.acknowledge(active["lease"], "passed", 30, eligible=[release(45)])
    assert released["phase"] == "releasing"
    assert queue.tick([release(42), release(45), release(46)], 35) == released
    queue.acknowledge(active["lease"], "released", 40)
    next_slot = queue.tick([release(46), release(45), release(42)], 41)
    assert next_slot["pr"] == 42
    with pytest.raises(ValueError, match="stale"):
        queue.acknowledge(active["lease"], "released", 42)


def test_updated_pr_waits_for_previous_version_cleanup(tmp_path):
    queue = Queue(tmp_path / "queue.sqlite3")
    first = queue.tick([release(45), release(46)], 1)
    new = [release(45, "d"), release(46)]
    assert queue.tick(new, 2) == first  # Never interrupt an in-flight deploy.
    queue.acknowledge(first["lease"], "ready", 3, 60, [release(45), release(46)])
    with pytest.raises(ValueError, match="no longer eligible"):
        queue.acknowledge(first["lease"], "passed", 4, eligible=new)
    stale = queue.tick(new, 4)
    assert stale["outcome"] == "superseded"
    with pytest.raises(ValueError):
        queue.acknowledge(first["lease"], "passed", 5, eligible=new)
    queue.acknowledge(first["lease"], "released", 6)
    instance = queue.tick(new, 7)
    assert instance["pr"] == 45 and instance["head"] == "d" * 40


def test_expired_or_failed_lease_moves_on_after_cleanup(tmp_path):
    queue = Queue(tmp_path / "queue.sqlite3")
    first = queue.tick([release(45), release(46), release(47)], 10)
    queue.acknowledge(first["lease"], "ready", 20, 10, [release(45)])
    with pytest.raises(ValueError, match="expired"):
        queue.acknowledge(first["lease"], "passed", 30, eligible=[release(45)])
    assert queue.tick([release(45), release(46), release(47)], 30)["outcome"] == "expired"
    queue.acknowledge(first["lease"], "released", 31)
    second = queue.tick([release(45), release(46), release(47)], 32)
    assert second["pr"] == 46
    assert queue.acknowledge(second["lease"], "deploy-failed", 33)["phase"] == "releasing"
    assert queue.tick([release(47)], 34)["pr"] == 46
    queue.acknowledge(second["lease"], "released", 35)
    assert queue.tick([release(45), release(46), release(47)], 36)["pr"] == 47


def test_retry_requires_exact_cleaned_deployment_failure_and_new_lease(tmp_path):
    queue = Queue(tmp_path / 'queue.sqlite3')
    current = release(45)
    eligible = [current, release(46)]
    first = queue.tick(eligible, 10)
    with pytest.raises(ValueError, match='idle'):
        queue.retry_failed(current)
    queue.acknowledge(first['lease'], 'deploy-failed', 12)
    queue.acknowledge(first['lease'], 'released', 13)
    with pytest.raises(ValueError, match='exact deployment failure'):
        queue.retry_failed(release(45, 'd'))
    assert queue.retry_failed(current) == {'phase': 'idle'}
    retried = queue.tick(eligible, 14)
    assert retried['pr'] == 45 and retried['lease'] != first['lease']
    queue.acknowledge(retried['lease'], 'ready', 15, 20, eligible)
    queue.acknowledge(retried['lease'], 'passed', 16, eligible=eligible)
    queue.acknowledge(retried['lease'], 'released', 17)
    with pytest.raises(ValueError, match='exact deployment failure'):
        queue.retry_failed(current)


def test_switch_holds_inflight_deployment_then_cleans_and_requeues(tmp_path):
    queue = Queue(tmp_path / 'queue.sqlite3')
    earlier, target = release(45), release(48)
    eligible = [earlier, target]
    initial = queue.tick(eligible, 1)
    assert initial['pr'] == 45
    assert queue.request_switch(11, target, eligible) == initial
    assert queue.tick(eligible, 2) == initial
    queue.acknowledge(initial['lease'], 'ready', 3, 60, eligible)
    interrupted = queue.tick(eligible, 4)
    assert interrupted['outcome'] == 'switched'
    assert queue.tick(eligible, 5)['lease'] == initial['lease']
    queue.acknowledge(initial['lease'], 'released', 6)
    chosen = queue.tick(eligible, 7)
    assert chosen['pr'] == 48
    assert queue.request_switch(11, target, eligible) == chosen
    queue.acknowledge(chosen['lease'], 'ready', 8, 60, eligible)
    queue.acknowledge(chosen['lease'], 'passed', 9, eligible=eligible)
    queue.acknowledge(chosen['lease'], 'released', 10)
    with pytest.raises(ValueError, match='already passed'):
        queue.request_switch(12, target, eligible)
    assert queue.tick(eligible, 11)['pr'] == 45


def test_switch_target_changes_before_lease_release(tmp_path):
    queue = Queue(tmp_path / 'queue.sqlite3')
    earlier, target = release(45), release(48)
    initial = queue.tick([earlier, target], 1)
    queue.acknowledge(initial['lease'], 'ready', 2, 60, [earlier, target])
    with pytest.raises(ValueError, match='not currently eligible'):
        queue.request_switch(1, target, [earlier])
    queue.request_switch(1, target, [earlier, target])
    with pytest.raises(ValueError, match='already pending'):
        queue.request_switch(2, earlier, [earlier, target])
    old = queue.tick([earlier, release(48, 'd')], 3)
    assert (old['phase'], old['lease']) == ('testing', initial['lease'])
    queue.request_switch(1, target, [earlier, target])
    assert queue.tick([earlier, target], 4)['phase'] == 'testing'

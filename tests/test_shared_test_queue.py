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

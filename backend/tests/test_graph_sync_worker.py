"""测试 GraphSyncWorker 的去重和退避逻辑（不连 Neo4j/PG，纯逻辑测试）。"""
import pytest
from app.services.graph_sync_worker import deduplicate_tasks, backoff_delay


def _make_task(aggregate_id: str, event_type: str, created_offset: float = 0):
    """构造简化 task 对象用于去重测试。"""
    from datetime import datetime, timezone, timedelta
    return {
        "id": f"task-{aggregate_id}-{event_type}",
        "aggregate_id": aggregate_id,
        "event_type": event_type,
        "created_at": datetime.now(timezone.utc) - timedelta(seconds=created_offset),
    }


class TestDeduplicate:
    def test_same_aggregate_keeps_newest(self):
        """同一 fmea_id 多条事件只保留最新一条。"""
        tasks = [
            _make_task("fmea-1", "fmea.updated", created_offset=30),
            _make_task("fmea-1", "fmea.updated", created_offset=10),
            _make_task("fmea-1", "fmea.approved", created_offset=0),
        ]
        result = deduplicate_tasks(tasks)
        assert len(result["process"]) == 1
        assert result["process"][0]["event_type"] == "fmea.approved"
        assert len(result["skip"]) == 2

    def test_different_aggregates_all_kept(self):
        """不同 fmea_id 不互相去重。"""
        tasks = [
            _make_task("fmea-1", "fmea.updated"),
            _make_task("fmea-2", "fmea.created"),
        ]
        result = deduplicate_tasks(tasks)
        assert len(result["process"]) == 2
        assert len(result["skip"]) == 0

    def test_empty_input(self):
        result = deduplicate_tasks([])
        assert result["process"] == []
        assert result["skip"] == []


class TestBackoff:
    def test_first_retry_10s(self):
        assert backoff_delay(1) == 10

    def test_second_retry_30s(self):
        assert backoff_delay(2) == 30

    def test_third_retry_90s(self):
        assert backoff_delay(3) == 90

    def test_fourth_retry_270s(self):
        assert backoff_delay(4) == 270

    def test_fifth_is_dead(self):
        """第 5 次不应返回退避，应直接标记 dead。"""
        assert backoff_delay(5) is None

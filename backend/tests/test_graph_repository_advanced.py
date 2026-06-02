import os
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
from app.graph.jsonb_repository import JSONBRepository


class StubDB:
    """Minimal async stub for testing abstract method instantiation."""
    pass


def test_jsonb_repo_has_find_similar_nodes_advanced():
    """验证 JSONBRepository 已实现 find_similar_nodes_advanced。"""
    repo = JSONBRepository(StubDB())
    assert hasattr(repo, "find_similar_nodes_advanced")
    import inspect
    assert "compute_similarity" in inspect.getsource(repo.find_similar_nodes_advanced)

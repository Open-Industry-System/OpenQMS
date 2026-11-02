"""Pure graph checks: no application imports or database fixtures."""
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[2]
MERGE = "20261102_agent_mainline_merge"
PARENTS = {"20260929_agent_read_task", "20261009_agent_task_attachments"}


def _scripts(directory):
    config = Config()
    config.set_main_option("script_location", str(ROOT / directory))
    return ScriptDirectory.from_config(config)


def test_public_head_merges_both_published_agent_branches():
    scripts = _scripts("alembic")
    assert scripts.get_heads() == [MERGE]
    merge = scripts.get_revision(MERGE)
    assert set(merge.down_revision) == PARENTS
    ancestors = {item.revision for item in scripts.walk_revisions()}
    assert PARENTS <= ancestors
    assert len(MERGE) <= 32


def test_tenant_head_adds_read_tasks_without_replaying_public_history():
    scripts = _scripts("alembic_tenant")
    assert scripts.get_heads() == ["tv006_agent_read_tasks"]
    assert scripts.get_revision("tv006_agent_read_tasks").down_revision == "tv005_agent_task_attachments"
    assert [item.revision for item in scripts.walk_revisions()] == [
        "tv006_agent_read_tasks", "tv005_agent_task_attachments",
        "tv004_agent_readonly_controls", "tv003_agent_readonly_delivery",
        "tv002_agent_task_core", "tv001_business_snapshot",
    ]
    assert len("tv006_agent_read_tasks") <= 32


def test_tenant_read_task_delta_matches_published_public_ddl():
    import ast

    public = ast.parse((ROOT / "alembic/versions/20260929_agent_read_task.py").read_text())
    tenant_path = ROOT / "alembic_tenant/versions/tv006_agent_read_tasks.py"
    assert tenant_path.exists(), "reviewed tenant read-task delta is required"
    tenant = ast.parse(tenant_path.read_text())
    for name in ("upgrade", "downgrade"):
        original = next(node for node in public.body if isinstance(node, ast.FunctionDef) and node.name == name)
        delta = next(node for node in tenant.body if isinstance(node, ast.FunctionDef) and node.name == name)
        assert ast.dump(original, include_attributes=False) == ast.dump(delta, include_attributes=False)
    merge = _scripts("alembic").get_revision(MERGE).module
    assert merge.upgrade() is None
    assert merge.downgrade() is None
    assert not any(isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app")
                   for node in tenant.body)
    assert not any(isinstance(node, ast.Import) and any(alias.name.startswith("app") for alias in node.names)
                   for node in tenant.body)

"""Integration of the two independently published migration branches."""
from pathlib import Path
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[2]


def scripts(name):
    config = Config()
    config.set_main_option('script_location', str(ROOT / name))
    return ScriptDirectory.from_config(config)


def test_public_merge_preserves_both_published_heads():
    graph = scripts('alembic')
    assert graph.get_heads() == ['20261114_r4b_main_merge']
    assert set(graph.get_revision('20261114_r4b_main_merge').down_revision) == {
        '20261108_merge_characteristics', '20261113_d4_recovery'}


def test_tenant_merge_preserves_both_published_heads():
    graph = scripts('alembic_tenant')
    assert graph.get_heads() == ['tv009_r4b_main_merge']
    assert set(graph.get_revision('tv009_r4b_main_merge').down_revision) == {
        'tv007_characteristic_refs', 'tv008_d4_recovery'}


def test_downgrade_only_accepts_strict_ancestors():
    from alembic_tenant import _is_strict_ancestor
    graph = scripts('alembic_tenant')
    merge = 'tv009_r4b_main_merge'
    char = 'tv007_characteristic_refs'
    text = 'tv007_d4_text_delivery'
    recovery = 'tv008_d4_recovery'
    common = 'tv006_agent_read_tasks'
    assert _is_strict_ancestor(graph, merge, char)
    assert _is_strict_ancestor(graph, merge, recovery)
    assert _is_strict_ancestor(graph, recovery, text)
    assert _is_strict_ancestor(graph, char, common)
    assert not _is_strict_ancestor(graph, recovery, char)
    assert not _is_strict_ancestor(graph, char, text)
    assert not _is_strict_ancestor(graph, recovery, recovery)
    assert not _is_strict_ancestor(graph, recovery, 'unknown')


def test_tv006_historical_difference_is_only_its_first_docstring_line():
    import ast
    import hashlib
    current = (ROOT / 'alembic_tenant/versions/tv006_agent_read_tasks.py').read_bytes()
    assert hashlib.sha256(current).hexdigest() == '4336ad07244aeb314e4784060c7e28f78ef63a7e2564e91d9756587865841d8f'
    historical = current.replace(b'Agent read tasks.\n', b'Agent read tasks as a reviewed delta.\n', 1)
    assert historical != current
    assert hashlib.sha256(historical).hexdigest() == '7992fc048151ae638e671f49a5f4e358c003061adfb2badbb8f051f3bf43217a'
    for contents in (current, historical):
        module = ast.parse(contents)
        module.body = module.body[1:]
        if contents == current:
            original = ast.dump(module, include_attributes=False)
        else:
            assert ast.dump(module, include_attributes=False) == original


def test_downgrade_never_leaves_two_active_heads():
    import alembic_tenant
    _has_single_downgrade_target = getattr(alembic_tenant, '_has_single_downgrade_target', None)
    assert callable(_has_single_downgrade_target)
    graph = scripts('alembic_tenant')
    assert not _has_single_downgrade_target(graph, 'tv009_r4b_main_merge', 'tv007_characteristic_refs')
    assert not _has_single_downgrade_target(graph, 'tv009_r4b_main_merge', 'tv008_d4_recovery')
    assert not _has_single_downgrade_target(graph, 'tv009_r4b_main_merge', 'tv007_d4_text_delivery')
    assert _has_single_downgrade_target(graph, 'tv009_r4b_main_merge', 'tv006_agent_read_tasks')
    assert _has_single_downgrade_target(graph, 'tv008_d4_recovery', 'tv007_d4_text_delivery')
    assert _has_single_downgrade_target(graph, 'tv007_characteristic_refs', 'tv006_agent_read_tasks')

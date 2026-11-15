import importlib.util
from pathlib import Path
from unittest.mock import Mock
import pytest
spec=importlib.util.spec_from_file_location('initialize',Path(__file__).parents[1]/'scripts/oracle-preview-initialize.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

@pytest.mark.parametrize('url',['postgresql+asyncpg://qms:secret@db/qms','postgresql+asyncpg://qms:secret@127.0.0.1/qms_preview','postgresql+asyncpg://qms:secret@production/qms_preview'])
def test_production_target_rejected(url):
    with pytest.raises(ValueError):module.validate_target(dict(PREVIEW_PR='7',DATABASE_URL=url))

def test_only_fresh_database_seeded_and_credentials_suppressed():
    runner=Mock()
    module.seed_if_empty(0,runner)
    assert runner.call_args.args[0][-1]=='--no-print-credentials'
    assert runner.call_args.kwargs['stdout']==module.subprocess.DEVNULL
    assert runner.call_args.kwargs['stderr']==module.subprocess.DEVNULL
    module.seed_if_empty(4,runner)
    assert runner.call_count==1

def test_seed_failure_propagates_before_publication():
    runner=Mock(side_effect=RuntimeError('seed failed'))
    with pytest.raises(RuntimeError):module.seed_if_empty(0,runner)

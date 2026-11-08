from __future__ import annotations

from pathlib import Path
import sys


def test_scanner_gate_requires_a_real_selected_child_receipt(tmp_path: Path) -> None:
    """A removed hook, empty selection, or skipped child must not pass scanner acceptance."""
    from tests.ci.scanner_gate import run_scanner_gate

    child = tmp_path / 'test_actual_scanner_child.py'
    child.write_text(
        'import pytest\n\n'
        '@pytest.mark.real_scanner\n'
        'def test_real_scanner_child():\n'
        '    assert True\n'
    )
    artifacts = tmp_path / 'artifacts'
    receipt = run_scanner_gate(
        'process',
        source={'SECRET_KEY': 'test-secret-key-for-ci-pure-only'},
        database_url='postgresql+asyncpg://qms:qms@127.0.0.1:1/openqms_ci_pure_test',
        artifacts=artifacts,
        targets=(str(child),),
        python=sys.executable,
    )

    assert receipt['status'] == 'PASSED'
    assert receipt['selected'] == receipt['passed'] == 1
    published = list(artifacts.glob('*-receipt.json'))
    assert len(published) == 1


def test_scanner_gate_rejects_a_skipped_real_scanner_child(tmp_path: Path) -> None:
    """An explicitly selected scanner child cannot turn its opt-in skip into success."""
    import pytest

    from tests.ci.scanner_gate import run_scanner_gate

    child = tmp_path / 'test_skipped_scanner_child.py'
    child.write_text(
        'import pytest\n\n'
        '@pytest.mark.real_scanner\n'
        'def test_skipped_scanner_child():\n'
        "    pytest.skip('scanner dependency absent')\n"
    )

    with pytest.raises(ValueError, match='did not complete successfully'):
        run_scanner_gate(
            'process',
            source={'SECRET_KEY': 'test-secret-key-for-ci-pure-only'},
            database_url='postgresql+asyncpg://qms:qms@127.0.0.1:1/openqms_ci_pure_test',
            artifacts=tmp_path / 'artifacts',
            targets=(str(child),),
            python=sys.executable,
        )

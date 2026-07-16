"""Release entrypoint tests: migrate -> check -> preflight -> rollout, serially."""
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "deploy-release.sh"


def _append_command(log: Path, name: str) -> str:
    return f"printf '%s\\n' {shlex.quote(name)} >> {shlex.quote(str(log))}"


def test_release_script_runs_all_steps_in_exact_serial_order(tmp_path):
    log = tmp_path / "release.log"
    env = {
        **os.environ,
        "DATABASE_URL": "postgresql+asyncpg://release-target/example",
        "MIGRATE_CMD": _append_command(log, "migrate"),
        "CHECK_CMD": _append_command(log, "check"),
        "PREFLIGHT_CMD": _append_command(log, "preflight"),
        "ROLLOUT_CMD": _append_command(log, "rollout"),
    }

    result = subprocess.run(
        [str(SCRIPT)], cwd=ROOT, env=env, text=True, capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert log.read_text().splitlines() == [
        "migrate", "check", "preflight", "rollout",
    ]


def test_release_script_requires_rollout_before_migration(tmp_path):
    log = tmp_path / "release.log"
    env = {
        **os.environ,
        "DATABASE_URL": "postgresql+asyncpg://release-target/example",
        "MIGRATE_CMD": _append_command(log, "migrate"),
        "CHECK_CMD": _append_command(log, "check"),
        "PREFLIGHT_CMD": _append_command(log, "preflight"),
    }
    env.pop("ROLLOUT_CMD", None)

    result = subprocess.run(
        [str(SCRIPT)], cwd=ROOT, env=env, text=True, capture_output=True,
    )

    assert result.returncode != 0
    assert "ROLLOUT_CMD is required" in result.stderr
    assert not log.exists() or log.read_text() == ""


def test_make_deploy_release_has_one_serial_script_invocation():
    env = {
        **os.environ,
        "DATABASE_URL": "postgresql+asyncpg://release-target/example",
        "ROLLOUT_CMD": "true",
    }
    result = subprocess.run(
        ["make", "-n", "-j2", "deploy-release"],
        cwd=ROOT, env=env, text=True, capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.count("scripts/deploy-release.sh") == 1
    assert "alembic upgrade head" not in result.stdout
    assert "pytest" not in result.stdout
    assert "app.services.capa_doc_gate_preflight" not in result.stdout

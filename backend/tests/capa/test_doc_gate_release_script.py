"""Release entrypoint tests: migrate -> check -> preflight -> rollout, serially."""
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "deploy-release.sh"
TARGET_URL = "postgresql+asyncpg://release-target/example"
TEST_URL = "postgresql+asyncpg://release-test/example"


def _append_command(log: Path, name: str) -> str:
    return f"printf '%s\\n' {shlex.quote(name)} >> {shlex.quote(str(log))}"


def _capture_env_command(log: Path, name: str) -> str:
    return (
        f"printf '%s|%s|%s\\n' {shlex.quote(name)} \"$DATABASE_URL\" "
        f"\"${{TEST_DATABASE_URL-unset}}\" >> {shlex.quote(str(log))}"
    )


def test_release_script_runs_all_steps_in_exact_serial_order(tmp_path):
    log = tmp_path / "release.log"
    env = {
        **os.environ,
        "DATABASE_URL": TARGET_URL,
        "TEST_DATABASE_URL": TEST_URL,
        "MIGRATE_CMD": _capture_env_command(log, "migrate"),
        "CHECK_CMD": _capture_env_command(log, "check"),
        "PREFLIGHT_CMD": _capture_env_command(log, "preflight"),
        "ROLLOUT_CMD": _capture_env_command(log, "rollout"),
    }

    result = subprocess.run(
        [str(SCRIPT)], cwd=ROOT, env=env, text=True, capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert log.read_text().splitlines() == [
        f"migrate|{TARGET_URL}|unset",
        f"check|{TEST_URL}|{TEST_URL}",
        f"preflight|{TARGET_URL}|unset",
        f"rollout|{TARGET_URL}|unset",
    ]


@pytest.mark.parametrize(
    ("missing_name", "error"),
    [
        ("DATABASE_URL", "DATABASE_URL is required"),
        ("ROLLOUT_CMD", "ROLLOUT_CMD is required"),
        ("TEST_DATABASE_URL", "TEST_DATABASE_URL is required"),
    ],
)
def test_release_script_requires_inputs_before_migration(tmp_path, missing_name, error):
    log = tmp_path / "release.log"
    env = {
        **os.environ,
        "DATABASE_URL": TARGET_URL,
        "TEST_DATABASE_URL": TEST_URL,
        "MIGRATE_CMD": _append_command(log, "migrate"),
        "CHECK_CMD": _append_command(log, "check"),
        "PREFLIGHT_CMD": _append_command(log, "preflight"),
        "ROLLOUT_CMD": _append_command(log, "rollout"),
    }
    env.pop(missing_name, None)

    result = subprocess.run(
        [str(SCRIPT)], cwd=ROOT, env=env, text=True, capture_output=True,
    )

    assert result.returncode != 0
    assert error in result.stderr
    assert not log.exists() or log.read_text() == ""


def test_release_script_rejects_test_database_equal_to_target(tmp_path):
    log = tmp_path / "release.log"
    env = {
        **os.environ,
        "DATABASE_URL": TARGET_URL,
        "TEST_DATABASE_URL": TARGET_URL,
        "MIGRATE_CMD": _append_command(log, "migrate"),
        "CHECK_CMD": _append_command(log, "check"),
        "PREFLIGHT_CMD": _append_command(log, "preflight"),
        "ROLLOUT_CMD": _append_command(log, "rollout"),
    }

    result = subprocess.run(
        [str(SCRIPT)], cwd=ROOT, env=env, text=True, capture_output=True,
    )

    assert result.returncode != 0
    assert "TEST_DATABASE_URL must differ from DATABASE_URL" in result.stderr
    assert not log.exists() or log.read_text() == ""


@pytest.mark.parametrize("failed_step", ["migrate", "check", "preflight", "rollout"])
def test_release_script_stops_on_failed_pipeline(tmp_path, failed_step):
    log = tmp_path / "release.log"
    names = ["migrate", "check", "preflight", "rollout"]
    commands = {name: _append_command(log, name) for name in names}
    commands[failed_step] += "; false | true"
    env = {
        **os.environ,
        "DATABASE_URL": TARGET_URL,
        "TEST_DATABASE_URL": TEST_URL,
        "MIGRATE_CMD": commands["migrate"],
        "CHECK_CMD": commands["check"],
        "PREFLIGHT_CMD": commands["preflight"],
        "ROLLOUT_CMD": commands["rollout"],
    }

    result = subprocess.run(
        [str(SCRIPT)], cwd=ROOT, env=env, text=True, capture_output=True,
    )

    failed_index = names.index(failed_step)
    assert result.returncode != 0
    assert log.read_text().splitlines() == names[:failed_index + 1]
    assert "deploy-release OK" not in result.stdout


def test_make_deploy_release_has_one_serial_script_invocation():
    env = {
        **os.environ,
        "DATABASE_URL": TARGET_URL,
        "TEST_DATABASE_URL": TEST_URL,
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

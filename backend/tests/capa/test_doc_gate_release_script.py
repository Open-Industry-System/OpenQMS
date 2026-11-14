"""Release entrypoint tests for identity, migration, checks, and rollout order."""
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "deploy-release.sh"
TARGET_URL = "postgresql+asyncpg://target.internal/openqms"
TEST_URL = "postgresql+asyncpg://test.internal/openqms_test"


def _append_command(log: Path, name: str) -> str:
    return f"printf '%s\\n' {shlex.quote(name)} >> {shlex.quote(str(log))}"


def _capture_env_command(log: Path, name: str) -> str:
    return (
        f"printf '%s|%s|%s\\n' {shlex.quote(name)} "
        f'"${{DATABASE_URL-unset}}" "${{TEST_DATABASE_URL-unset}}" '
        f">> {shlex.quote(str(log))}"
    )


def _release_harness(tmp_path: Path) -> Path:
    """Copy the release script with a fake Python guard; no DB is contacted."""
    root = tmp_path / "repo"
    scripts = root / "scripts"
    python_dir = root / "backend" / ".venv" / "bin"
    scripts.mkdir(parents=True)
    python_dir.mkdir(parents=True)
    harness_script = scripts / "deploy-release.sh"
    harness_script.write_text(SCRIPT.read_text())
    harness_script.chmod(0o755)
    fake_python = python_dir / "python"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ \"$*\" == *\"app.cli.tenant_migrate --all\"* ]]; then\n"
        "  printf '%s|%s|%s\\n' tenant-default \"${DATABASE_URL-unset}\" "
        "\"${TEST_DATABASE_URL-unset}\" >> \"$RELEASE_LOG\"\n"
        "fi\n"
    )
    fake_python.chmod(0o755)
    return harness_script


def _release_env(log: Path, **overrides: str) -> dict[str, str]:
    env = {
        **os.environ,
        "DATABASE_URL": TARGET_URL,
        "TEST_DATABASE_URL": TEST_URL,
        "TARGET_IDENTITY_CMD": _capture_env_command(log, "identity"),
        "MIGRATE_CMD": _capture_env_command(log, "migrate"),
        "CHECK_CMD": _capture_env_command(log, "check"),
        "PREFLIGHT_CMD": _capture_env_command(log, "preflight"),
        "ROLLOUT_CMD": _capture_env_command(log, "rollout"),
        "TENANT_MODE": "single",
        "TENANT_MIGRATE_CMD": "",
        "INITIALIZE_CMD": "",
        "RELEASE_LOG": str(log),
    }
    env.update(overrides)
    return env


def _run_release(script: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(script)],
        cwd=script.parents[1],
        env=env,
        text=True,
        capture_output=True,
    )


def test_release_script_runs_single_tenant_steps_in_exact_serial_order(tmp_path):
    log = tmp_path / "release.log"
    script = _release_harness(tmp_path)

    result = _run_release(script, _release_env(log))

    assert result.returncode == 0, result.stderr
    assert log.read_text().splitlines() == [
        f"identity|{TARGET_URL}|unset",
        f"migrate|{TARGET_URL}|unset",
        f"check|{TEST_URL}|{TEST_URL}",
        f"preflight|{TARGET_URL}|unset",
        "rollout|unset|unset",
    ]


def test_release_test_harness_ignores_inherited_optional_operator_commands(
    tmp_path, monkeypatch
):
    log = tmp_path / "release.log"
    script = _release_harness(tmp_path)
    monkeypatch.setenv("TENANT_MODE", "production")
    monkeypatch.setenv("TENANT_MIGRATE_CMD", _append_command(log, "inherited-tenant"))
    monkeypatch.setenv("INITIALIZE_CMD", _append_command(log, "inherited-initialize"))

    result = _run_release(script, _release_env(log))

    assert result.returncode == 0, result.stderr
    assert "inherited-tenant" not in log.read_text()
    assert "inherited-initialize" not in log.read_text()


def test_release_script_runs_optional_initializer_without_database_environment(tmp_path):
    log = tmp_path / "release.log"
    script = _release_harness(tmp_path)
    env = _release_env(log, INITIALIZE_CMD=_capture_env_command(log, "initialize"))

    result = _run_release(script, env)

    assert result.returncode == 0, result.stderr
    assert log.read_text().splitlines() == [
        f"identity|{TARGET_URL}|unset",
        f"migrate|{TARGET_URL}|unset",
        f"check|{TEST_URL}|{TEST_URL}",
        "initialize|unset|unset",
        f"preflight|{TARGET_URL}|unset",
        "rollout|unset|unset",
    ]


@pytest.mark.parametrize(
    ("missing_name", "error"),
    [
        ("DATABASE_URL", "DATABASE_URL is required"),
        ("TEST_DATABASE_URL", "TEST_DATABASE_URL is required"),
        ("TARGET_IDENTITY_CMD", "TARGET_IDENTITY_CMD is required"),
        ("ROLLOUT_CMD", "ROLLOUT_CMD is required"),
    ],
)
def test_release_script_requires_inputs_before_any_step(
    tmp_path, missing_name: str, error: str
):
    log = tmp_path / "release.log"
    script = _release_harness(tmp_path)
    env = _release_env(log)
    env.pop(missing_name, None)

    result = _run_release(script, env)

    assert result.returncode == 2
    assert error in result.stderr
    assert not log.exists() or log.read_text() == ""


@pytest.mark.parametrize(
    ("failed_step", "expected"),
    [
        ("identity", ["identity"]),
        ("migrate", ["identity", "migrate"]),
        ("check", ["identity", "migrate", "check"]),
        ("initialize", ["identity", "migrate", "check", "initialize"]),
        (
            "preflight",
            ["identity", "migrate", "check", "initialize", "preflight"],
        ),
        (
            "rollout",
            [
                "identity",
                "migrate",
                "check",
                "initialize",
                "preflight",
                "rollout",
            ],
        ),
    ],
)
def test_release_script_stops_on_failed_single_tenant_step(
    tmp_path, failed_step: str, expected: list[str]
):
    log = tmp_path / "release.log"
    script = _release_harness(tmp_path)
    names = ["identity", "migrate", "check", "initialize", "preflight", "rollout"]
    commands = {name: _append_command(log, name) for name in names}
    commands[failed_step] += "; false"
    env = _release_env(
        log,
        TARGET_IDENTITY_CMD=commands["identity"],
        MIGRATE_CMD=commands["migrate"],
        CHECK_CMD=commands["check"],
        INITIALIZE_CMD=commands["initialize"],
        PREFLIGHT_CMD=commands["preflight"],
        ROLLOUT_CMD=commands["rollout"],
    )

    result = _run_release(script, env)

    assert result.returncode != 0
    assert log.read_text().splitlines() == expected
    assert "deploy-release OK" not in result.stdout


def test_release_script_runs_production_tenant_migration_after_public_migration(
    tmp_path,
):
    log = tmp_path / "release.log"
    script = _release_harness(tmp_path)
    env = _release_env(
        log,
        TENANT_MODE="production",
        TENANT_MIGRATE_CMD=_capture_env_command(log, "tenant-migrate"),
    )

    result = _run_release(script, env)

    assert result.returncode == 0, result.stderr
    assert log.read_text().splitlines() == [
        f"identity|{TARGET_URL}|unset",
        f"migrate|{TARGET_URL}|unset",
        f"tenant-migrate|{TARGET_URL}|unset",
        f"check|{TEST_URL}|{TEST_URL}",
        f"preflight|{TARGET_URL}|unset",
        "rollout|unset|unset",
    ]


def test_release_script_uses_default_tenant_migration_in_production(tmp_path):
    log = tmp_path / "release.log"
    script = _release_harness(tmp_path)

    result = _run_release(script, _release_env(log, TENANT_MODE="production"))

    assert result.returncode == 0, result.stderr
    assert f"tenant-default|{TARGET_URL}|unset" in log.read_text().splitlines()


def test_explicit_tenant_migration_command_runs_outside_production(tmp_path):
    log = tmp_path / "release.log"
    script = _release_harness(tmp_path)
    env = _release_env(
        log,
        TENANT_MODE="single",
        TENANT_MIGRATE_CMD=_capture_env_command(log, "tenant-migrate"),
    )

    result = _run_release(script, env)

    assert result.returncode == 0, result.stderr
    lines = log.read_text().splitlines()
    assert lines.index(f"tenant-migrate|{TARGET_URL}|unset") == 2


def test_tenant_migration_failure_stops_remaining_release_steps(tmp_path):
    log = tmp_path / "release.log"
    script = _release_harness(tmp_path)
    tenant_command = _append_command(log, "tenant-migrate") + "; false"
    env = _release_env(
        log,
        TENANT_MODE="production",
        TENANT_MIGRATE_CMD=tenant_command,
    )

    result = _run_release(script, env)

    assert result.returncode != 0
    assert log.read_text().splitlines() == [
        f"identity|{TARGET_URL}|unset",
        f"migrate|{TARGET_URL}|unset",
        "tenant-migrate",
    ]


def test_release_script_rejects_unknown_tenant_mode_before_any_step(tmp_path):
    log = tmp_path / "release.log"
    script = _release_harness(tmp_path)

    result = _run_release(script, _release_env(log, TENANT_MODE="typo"))

    assert result.returncode == 2
    assert "TENANT_MODE must be single, dev, or production" in result.stderr
    assert not log.exists()


@pytest.mark.parametrize(
    ("target_url", "test_url"),
    [
        (TARGET_URL, TARGET_URL),
        (
            "postgresql+asyncpg://qms@localhost/openqms?b=2&a=1",
            "postgresql+psycopg://qms@127.0.0.1:5432/openqms?a=1&b=2",
        ),
    ],
)
def test_release_script_rejects_equivalent_databases_before_identity(
    tmp_path, target_url: str, test_url: str
):
    log = tmp_path / "release.log"
    env = _release_env(log)
    env["DATABASE_URL"] = target_url
    env["TEST_DATABASE_URL"] = test_url

    result = subprocess.run(
        [str(SCRIPT)], cwd=ROOT, env=env, text=True, capture_output=True
    )

    assert result.returncode != 0
    assert "same canonical database" in result.stderr
    assert not log.exists()


def test_legacy_guard_override_cannot_bypass_identical_database_rejection(tmp_path):
    log = tmp_path / "release.log"
    env = _release_env(log, TEST_DATABASE_GUARD_CMD="true")
    env["TEST_DATABASE_URL"] = TARGET_URL

    result = subprocess.run(
        [str(SCRIPT)], cwd=ROOT, env=env, text=True, capture_output=True
    )

    assert result.returncode != 0
    assert "same canonical database" in result.stderr
    assert not log.exists()


def test_make_deploy_release_has_one_serial_script_invocation():
    env = {
        **os.environ,
        "DATABASE_URL": TARGET_URL,
        "TEST_DATABASE_URL": TEST_URL,
        "TARGET_IDENTITY_CMD": "true",
        "ROLLOUT_CMD": "true",
    }
    result = subprocess.run(
        ["make", "-n", "-j2", "deploy-release"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.count("scripts/deploy-release.sh") == 1
    assert "alembic upgrade head" not in result.stdout
    assert "pytest" not in result.stdout
    assert "app.services.capa_doc_gate_preflight" not in result.stdout


def test_unsafe_combined_deploy_check_target_is_removed():
    help_result = subprocess.run(
        ["make", "help"], cwd=ROOT, text=True, capture_output=True
    )
    target_result = subprocess.run(
        ["make", "-n", "deploy-check"], cwd=ROOT, text=True, capture_output=True
    )

    assert help_result.returncode == 0, help_result.stderr
    assert "deploy-check" not in help_result.stdout
    assert target_result.returncode != 0
    assert "No rule to make target" in target_result.stderr
    assert "deploy-check" in target_result.stderr

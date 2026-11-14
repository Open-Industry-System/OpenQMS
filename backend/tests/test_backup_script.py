import json
import os
import shutil
import signal
import stat
import subprocess
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "backup-postgres.sh"
SERVICE = ROOT / "deploy" / "openqms-backup.service"
TIMER = ROOT / "deploy" / "openqms-backup.timer"
TIMESTAMP = "20260914T031700Z"
SECRET = "backup-test-secret-must-not-leak"
DUMP_BYTES = b"PGDMP\x01fake-custom-format\n"
EXPECTED_DUMP_COMMAND = [
    "exec",
    "-T",
    "db",
    "sh",
    "-ec",
    'exec pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
]
EXPECTED_RESTORE_COMMAND = ["exec", "-T", "db", "pg_restore", "--list"]


def _require(condition: bool, fixed_message: str) -> None:
    if not condition:
        pytest.fail(fixed_message, pytrace=False)


def _write_harness(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    openqms_dir = tmp_path / "openqms"
    scripts_dir = openqms_dir / "scripts"
    scripts_dir.mkdir(parents=True)
    compose_log = tmp_path / "compose.jsonl"
    fake_wrapper = scripts_dir / "production-compose.sh"
    fake_wrapper.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path

args = sys.argv[1:]
with Path(os.environ["FAKE_COMPOSE_LOG"]).open("a") as stream:
    stream.write(json.dumps(args) + "\\n")
if args[:3] != ["exec", "-T", "db"]:
    raise SystemExit(64)
if any("pg_dump" in arg for arg in args):
    mode = os.environ.get("FAKE_DUMP_MODE", "success")
    if mode == "fail":
        raise SystemExit(23)
    if mode == "block":
        Path(os.environ["FAKE_DUMP_STARTED"]).touch()
        while not Path(os.environ["FAKE_DUMP_RELEASE"]).exists():
            time.sleep(0.01)
    if mode != "empty":
        sys.stdout.buffer.write(b"PGDMP\\x01fake-custom-format\\n")
    raise SystemExit(0)
if args[-2:] == ["pg_restore", "--list"]:
    payload = sys.stdin.buffer.read()
    race_path = os.environ.get("FAKE_CREATE_FINAL")
    if race_path:
        if os.environ.get("FAKE_CREATE_FINAL_KIND") == "directory":
            Path(race_path).mkdir()
        else:
            Path(race_path).write_bytes(b"existing-backup-must-survive")
    if os.environ.get("FAKE_RESTORE_MODE") == "fail" or not payload.startswith(b"PGDMP"):
        raise SystemExit(24)
    raise SystemExit(0)
raise SystemExit(65)
"""
    )
    fake_wrapper.chmod(0o755)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_date = fake_bin / "date"
    fake_date.write_text(
        "#!/bin/sh\n"
        "if [ \"$*\" != '-u +%Y%m%dT%H%M%SZ' ]; then exit 66; fi\n"
        f"printf '%s\\n' '{TIMESTAMP}'\n"
    )
    fake_date.chmod(0o755)
    return openqms_dir, tmp_path / "backups", compose_log, fake_bin


def _environment(
    openqms_dir: Path,
    backup_dir: Path,
    compose_log: Path,
    fake_bin: Path,
    **overrides: str,
) -> dict[str, str]:
    environment = {
        **os.environ,
        "OPENQMS_DIR": str(openqms_dir),
        "BACKUP_DIR": str(backup_dir),
        "RETENTION_DAYS": "7",
        "FAKE_COMPOSE_LOG": str(compose_log),
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "POSTGRES_PASSWORD": SECRET,
        "DATABASE_URL": f"postgresql+asyncpg://qms:{SECRET}@db:5432/qms",
    }
    environment.update(overrides)
    return environment


def _run(tmp_path: Path, **overrides: str):
    openqms_dir, backup_dir, compose_log, fake_bin = _write_harness(tmp_path)
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=tmp_path,
        env=_environment(
            openqms_dir, backup_dir, compose_log, fake_bin, **overrides
        ),
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    return result, backup_dir, compose_log


def _calls(compose_log: Path) -> list[list[str]]:
    if not compose_log.exists():
        return []
    return [json.loads(line) for line in compose_log.read_text().splitlines()]


def _partials(backup_dir: Path) -> list[Path]:
    return list(backup_dir.glob("*.partial.*")) if backup_dir.exists() else []


def _assert_no_secret(result: subprocess.CompletedProcess[str]) -> None:
    _require(SECRET not in result.stdout + result.stderr, "backup output leaked a secret")


def test_backup_script_is_executable_valid_bash_with_signal_cleanup_contract():
    assert SCRIPT.is_file()
    assert SCRIPT.stat().st_mode & 0o111 == 0o111
    source = SCRIPT.read_text()
    assert source.splitlines()[:3] == [
        "#!/usr/bin/env bash",
        "set +x",
        "set -euo pipefail",
    ]
    assert "umask 077" in source
    assert "trap cleanup_partial EXIT" in source
    assert "trap handle_signal HUP INT TERM QUIT" in source
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        text=True,
        capture_output=True,
        check=False,
    )
    _require(result.returncode == 0, "backup script syntax check failed")


def test_backup_requires_python3_for_exact_atomic_publication(tmp_path):
    openqms_dir, backup_dir, compose_log, fake_bin = _write_harness(tmp_path)
    bash = shutil.which("bash")
    assert bash is not None
    environment = _environment(openqms_dir, backup_dir, compose_log, fake_bin)
    environment["PATH"] = str(fake_bin)

    result = subprocess.run(
        [bash, str(SCRIPT)],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    assert result.returncode != 0
    assert not backup_dir.exists()
    assert _calls(compose_log) == []
    _require(result.stdout == "", "missing-python path wrote stdout")
    _require(
        result.stderr == "error: python3 is required for atomic publication\n",
        "missing-python error category changed",
    )
    _assert_no_secret(result)


def test_success_publishes_valid_dump_securely_then_applies_narrow_retention(tmp_path):
    openqms_dir, backup_dir, compose_log, fake_bin = _write_harness(tmp_path)
    backup_dir.mkdir()
    old_dump = backup_dir / "old.dump"
    recent_dump = backup_dir / "recent.dump"
    unrelated = backup_dir / "keep.txt"
    partial = backup_dir / ".manual.partial"
    symlink = backup_dir / "linked.dump"
    outside = tmp_path / "outside.dump"
    for path in (old_dump, recent_dump, unrelated, partial, outside):
        path.write_bytes(b"keep")
    symlink.symlink_to(outside)
    old = time.time() - 9 * 24 * 60 * 60
    os.utime(old_dump, (old, old))
    os.utime(unrelated, (old, old))
    os.utime(partial, (old, old))
    os.utime(outside, (old, old))

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=tmp_path,
        env=_environment(openqms_dir, backup_dir, compose_log, fake_bin),
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    _require(result.returncode == 0, "valid backup command failed")
    assert stat.S_IMODE(backup_dir.stat().st_mode) == 0o700
    final = backup_dir / f"openqms-postgres-{TIMESTAMP}.dump"
    assert final.read_bytes() == DUMP_BYTES
    assert stat.S_IMODE(final.stat().st_mode) == 0o600
    assert _calls(compose_log) == [EXPECTED_DUMP_COMMAND, EXPECTED_RESTORE_COMMAND]
    assert not old_dump.exists()
    assert recent_dump.exists()
    assert unrelated.exists()
    assert partial.exists()
    assert symlink.is_symlink()
    assert outside.exists()
    assert _partials(backup_dir) == []
    _require(result.stdout == "PostgreSQL backup completed\n", "success output changed")
    _require(result.stderr == "", "successful backup wrote stderr")
    _assert_no_secret(result)


@pytest.mark.parametrize(
    ("overrides", "expected_error", "expected_calls"),
    [
        ({"FAKE_DUMP_MODE": "fail"}, "error: PostgreSQL dump failed\n", 1),
        ({"FAKE_DUMP_MODE": "empty"}, "error: PostgreSQL dump is empty\n", 1),
        ({"FAKE_RESTORE_MODE": "fail"}, "error: PostgreSQL dump validation failed\n", 2),
    ],
    ids=("dump-failure", "empty-dump", "restore-validation"),
)
def test_failed_dump_or_validation_never_publishes_or_runs_retention(
    tmp_path, overrides, expected_error, expected_calls
):
    openqms_dir, backup_dir, compose_log, fake_bin = _write_harness(tmp_path)
    backup_dir.mkdir()
    old_dump = backup_dir / "old.dump"
    old_dump.write_bytes(b"keep")
    old = time.time() - 9 * 24 * 60 * 60
    os.utime(old_dump, (old, old))

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=tmp_path,
        env=_environment(
            openqms_dir, backup_dir, compose_log, fake_bin, **overrides
        ),
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    assert result.returncode != 0
    assert list(backup_dir.glob("openqms-postgres-*.dump")) == []
    assert old_dump.exists()
    assert _partials(backup_dir) == []
    assert len(_calls(compose_log)) == expected_calls
    _require(result.stdout == "", "failed backup wrote stdout")
    _require(result.stderr == expected_error, "backup failure category changed")
    _assert_no_secret(result)


@pytest.mark.parametrize(
    "existing_kind",
    ["file", "fifo", "directory", "file-symlink", "directory-symlink"],
)
def test_existing_final_target_is_rejected_without_altering_target(
    tmp_path, existing_kind
):
    openqms_dir, backup_dir, compose_log, fake_bin = _write_harness(tmp_path)
    backup_dir.mkdir()
    final = backup_dir / f"openqms-postgres-{TIMESTAMP}.dump"
    original = b"existing-backup-must-survive"
    target = tmp_path / "target"

    if existing_kind == "file":
        final.write_bytes(original)
    elif existing_kind == "fifo":
        os.mkfifo(final, mode=0o600)
    elif existing_kind == "directory":
        final.mkdir()
    elif existing_kind == "file-symlink":
        target.write_bytes(original)
        final.symlink_to(target)
    else:
        target.mkdir()
        final.symlink_to(target, target_is_directory=True)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=tmp_path,
        env=_environment(openqms_dir, backup_dir, compose_log, fake_bin),
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    assert result.returncode != 0
    assert _calls(compose_log) == []
    assert _partials(backup_dir) == []
    if existing_kind == "file":
        assert final.read_bytes() == original
    elif existing_kind == "fifo":
        assert stat.S_ISFIFO(final.stat().st_mode)
    elif existing_kind == "directory":
        assert final.is_dir() and list(final.iterdir()) == []
    elif existing_kind == "file-symlink":
        assert final.is_symlink() and target.read_bytes() == original
    else:
        assert final.is_symlink() and target.is_dir() and list(target.iterdir()) == []
    _require(result.stdout == "", "existing-target refusal wrote stdout")
    _require(
        result.stderr == "error: backup already exists\n",
        "existing-target error changed",
    )
    _assert_no_secret(result)


def test_atomic_publication_refuses_directory_created_after_initial_check(tmp_path):
    openqms_dir, backup_dir, compose_log, fake_bin = _write_harness(tmp_path)
    backup_dir.mkdir()
    final = backup_dir / f"openqms-postgres-{TIMESTAMP}.dump"
    old_dump = backup_dir / "old.dump"
    old_dump.write_bytes(b"keep")
    old = time.time() - 9 * 24 * 60 * 60
    os.utime(old_dump, (old, old))

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=tmp_path,
        env=_environment(
            openqms_dir,
            backup_dir,
            compose_log,
            fake_bin,
            FAKE_CREATE_FINAL=str(final),
            FAKE_CREATE_FINAL_KIND="directory",
        ),
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    assert result.returncode != 0
    assert final.is_dir()
    assert list(final.iterdir()) == []
    assert old_dump.exists()
    assert _partials(backup_dir) == []
    assert _calls(compose_log) == [EXPECTED_DUMP_COMMAND, EXPECTED_RESTORE_COMMAND]
    _require(result.stdout == "", "collision refusal wrote stdout")
    _require(result.stderr == "error: backup already exists\n", "collision error changed")
    _assert_no_secret(result)


@pytest.mark.parametrize("value", ["", "-1", "1.5", "seven", " 7"])
def test_invalid_retention_is_rejected_before_backup(tmp_path, value):
    result, backup_dir, compose_log = _run(tmp_path, RETENTION_DAYS=value)

    assert result.returncode != 0
    assert not backup_dir.exists()
    assert _calls(compose_log) == []
    _require(result.stdout == "", "invalid retention wrote stdout")
    _require(result.stderr == "error: RETENTION_DAYS must be a nonnegative integer\n", "retention error changed")
    _assert_no_secret(result)


def test_inherited_xtrace_does_not_disclose_secrets(tmp_path):
    bash_env = tmp_path / "bash-env"
    bash_env.write_text("set -x\n")

    result, backup_dir, _compose_log = _run(tmp_path, BASH_ENV=str(bash_env))

    _require(result.returncode == 0, "xtrace backup failed")
    assert len(list(backup_dir.glob("openqms-postgres-*.dump"))) == 1
    _assert_no_secret(result)


def test_term_signal_removes_private_partial(tmp_path):
    openqms_dir, backup_dir, compose_log, fake_bin = _write_harness(tmp_path)
    started = tmp_path / "dump-started"
    release = tmp_path / "dump-release"
    environment = _environment(
        openqms_dir,
        backup_dir,
        compose_log,
        fake_bin,
        FAKE_DUMP_MODE="block",
        FAKE_DUMP_STARTED=str(started),
        FAKE_DUMP_RELEASE=str(release),
    )
    process = subprocess.Popen(
        ["bash", str(SCRIPT)],
        cwd=tmp_path,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )

    try:
        deadline = time.monotonic() + 5
        while not started.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert started.exists()
        assert len(_partials(backup_dir)) == 1
        os.killpg(process.pid, signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=10)
    finally:
        if process.poll() is None:
            release.touch()
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)

    assert process.returncode != 0
    assert list(backup_dir.glob("openqms-postgres-*.dump")) == []
    assert _partials(backup_dir) == []
    _require(SECRET not in stdout + stderr, "signal output leaked a secret")


def test_systemd_service_and_timer_run_daily_persistent_backup_as_ubuntu():
    assert SERVICE.read_text() == """[Unit]
Description=OpenQMS PostgreSQL backup
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/opt/openqms
ExecStart=/opt/openqms/scripts/backup-postgres.sh
"""
    assert TIMER.read_text() == """[Unit]
Description=Daily OpenQMS PostgreSQL backup

[Timer]
OnCalendar=*-*-* 03:17:00
Persistent=true
RandomizedDelaySec=10m

[Install]
WantedBy=timers.target
"""

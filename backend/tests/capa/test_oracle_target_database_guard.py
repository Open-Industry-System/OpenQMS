"""Pure tests for the Oracle runtime database identity guard."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
GUARD_PATH = SCRIPTS / "check-oracle-target-database.py"
LOCAL_DSN = "postgresql+asyncpg://tunnel.internal/openqms"


def _load_guard():
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location(
            "check_oracle_target_database", GUARD_PATH
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS))


def _remote_result(
    stdout: str = (
        '{"system_identifier":"cluster-a","database":"qms",'
        '"database_oid":16384}\n'
    ),
    *,
    returncode: int = 0,
    stderr: str = "",
):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _verify(guard, monkeypatch, result=None):
    local = guard.DatabaseIdentity("cluster-a", "qms", 16384)
    calls = []
    monkeypatch.setattr(guard, "resolve_live_identity", lambda _dsn: local)

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return result or _remote_result()

    monkeypatch.setattr(guard.subprocess, "run", run)
    guard.verify_runtime_target_identity(
        dsn=LOCAL_DSN,
        ssh_target="ubuntu@oracle.internal",
        ssh_key="/safe/id_ed25519",
        app_dir="/opt/openqms",
    )
    return calls


def test_matching_local_and_remote_identity_succeeds(monkeypatch):
    guard = _load_guard()

    calls = _verify(guard, monkeypatch)

    assert len(calls) == 1


@pytest.mark.parametrize(
    "remote",
    [
        '{"system_identifier":"cluster-b","database":"qms","database_oid":16384}',
        '{"system_identifier":"cluster-a","database":"other","database_oid":16384}',
        '{"system_identifier":"cluster-a","database":"qms","database_oid":16385}',
    ],
)
def test_any_remote_identity_mismatch_fails_closed(monkeypatch, remote: str):
    guard = _load_guard()

    with pytest.raises(guard.DatabaseIdentityError, match="identity mismatch"):
        _verify(guard, monkeypatch, _remote_result(remote + "\n"))


@pytest.mark.parametrize(
    "remote",
    [
        "not-json\n",
        '{"system_identifier":"cluster-a","database":"qms"}\n',
        '{"system_identifier":1,"database":"qms","database_oid":16384}\n',
        '{"system_identifier":"cluster-a","database":[],"database_oid":16384}\n',
        '{"system_identifier":"cluster-a","database":"qms","database_oid":"16384"}\n',
        '{"system_identifier":"cluster-a","database":"qms","database_oid":true}\n',
        '{"system_identifier":"cluster-a","database":"qms","database_oid":16384,"extra":1}\n',
        "{}\n{}\n",
    ],
)
def test_malformed_or_non_strict_remote_json_fails_closed(monkeypatch, remote: str):
    guard = _load_guard()

    with pytest.raises(guard.DatabaseIdentityError, match="invalid remote identity"):
        _verify(guard, monkeypatch, _remote_result(remote))


def test_ssh_failure_raises_non_secret_identity_error(monkeypatch):
    guard = _load_guard()
    leaked = "postgresql://name:password@secret.internal/qms"

    with pytest.raises(guard.DatabaseIdentityError, match="ssh command failed") as exc:
        _verify(
            guard,
            monkeypatch,
            _remote_result(leaked, returncode=255, stderr=leaked),
        )

    assert leaked not in str(exc.value)


def test_remote_command_unsets_local_db_variables_and_uses_container_variables(
    monkeypatch,
):
    guard = _load_guard()

    calls = _verify(guard, monkeypatch)

    argv, kwargs = calls[0]
    remote_command = argv[-1]
    assert argv == [
        "ssh",
        "-i",
        "/safe/id_ed25519",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectionAttempts=1",
        "-o",
        "ConnectTimeout=10",
        "ubuntu@oracle.internal",
        remote_command,
    ]
    assert LOCAL_DSN not in argv
    assert remote_command.startswith(
        "cd /opt/openqms && unset DATABASE_URL TEST_DATABASE_URL && docker compose"
    )
    assert "--env-file .env.production -f docker-compose.prod.yml exec -T db" in remote_command
    assert 'psql -XAt -U "$POSTGRES_USER" -d "$POSTGRES_DB"' in remote_command
    assert "POSTGRES_PASSWORD" not in remote_command
    assert kwargs == {
        "stdin": guard.subprocess.DEVNULL,
        "capture_output": True,
        "text": True,
        "check": False,
        "timeout": 60,
    }


def test_cli_ssh_timeout_is_fixed_and_does_not_echo_exception_data(
    monkeypatch, capsys
):
    guard = _load_guard()
    secret = "credential-bearing timeout detail"
    monkeypatch.setenv("DATABASE_URL", LOCAL_DSN)
    monkeypatch.setenv("ORACLE_SSH_TARGET", "ubuntu@oracle.internal")
    monkeypatch.setenv("ORACLE_SSH_KEY", "/private/secret-key")
    monkeypatch.setenv("ORACLE_APP_DIR", "/opt/openqms")
    monkeypatch.setattr(
        guard,
        "resolve_live_identity",
        lambda _dsn: guard.DatabaseIdentity("cluster-a", "qms", 16384),
    )

    def timeout(argv, **kwargs):
        raise guard.subprocess.TimeoutExpired(
            argv,
            kwargs["timeout"],
            output=secret,
            stderr=secret,
        )

    monkeypatch.setattr(guard.subprocess, "run", timeout)

    result = guard.main()

    captured = capsys.readouterr()
    assert result == 2
    assert captured.out == ""
    assert captured.err == "runtime target identity guard failed: ssh command timed out\n"
    assert secret not in captured.err
    assert "ubuntu@oracle.internal" not in captured.err
    assert "/private/secret-key" not in captured.err
    assert LOCAL_DSN not in captured.err


def test_cli_prints_only_success_text(monkeypatch, capsys):
    guard = _load_guard()
    monkeypatch.setenv("DATABASE_URL", LOCAL_DSN)
    monkeypatch.setenv("ORACLE_SSH_TARGET", "ubuntu@oracle.internal")
    monkeypatch.setenv("ORACLE_SSH_KEY", "/safe/id_ed25519")
    monkeypatch.setenv("ORACLE_APP_DIR", "/opt/openqms")
    monkeypatch.setattr(guard, "verify_runtime_target_identity", lambda **_kwargs: None)

    result = guard.main()

    captured = capsys.readouterr()
    assert result == 0
    assert captured.out == "runtime target identity guard OK\n"
    assert captured.err == ""


def test_cli_failure_does_not_echo_remote_output_or_environment(monkeypatch, capsys):
    guard = _load_guard()
    secret = "postgresql://name:password@secret.internal/qms"
    monkeypatch.setenv("DATABASE_URL", secret)
    monkeypatch.setenv("ORACLE_SSH_TARGET", "ubuntu@oracle.internal")
    monkeypatch.setenv("ORACLE_SSH_KEY", "/private/secret-key")
    monkeypatch.setenv("ORACLE_APP_DIR", "/opt/openqms")

    def fail(**_kwargs):
        raise guard.DatabaseIdentityError("ssh command failed")

    monkeypatch.setattr(guard, "verify_runtime_target_identity", fail)

    result = guard.main()

    captured = capsys.readouterr()
    assert result != 0
    assert captured.out == ""
    assert captured.err == "runtime target identity guard failed: ssh command failed\n"
    assert secret not in captured.err
    assert "/private/secret-key" not in captured.err

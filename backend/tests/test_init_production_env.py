import ast
import hashlib
import hmac
import os
import re
import shutil
import signal
import stat
import subprocess
import time
from collections import Counter
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "init-production-env.sh"

REQUIRED_KEYS = (
    "SITE_ADDRESS",
    "TAILSCALE_IP",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "DATABASE_URL",
    "REDIS_PASSWORD",
    "REDIS_URL",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "NEO4J_URI",
    "NEO4J_DATABASE",
    "SECRET_KEY",
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "REFRESH_TOKEN_EXPIRE_DAYS",
    "ALGORITHM",
    "GRAPH_REPOSITORY",
    "TENANT_MODE",
    "E2E_MODE",
    "LLM_PROVIDER",
    "LLM_API_KEY",
    "LLM_MODEL",
    "LLM_BASE_URL",
    "EMBEDDING_PROVIDER",
    "EMBEDDING_API_KEY",
    "EMBEDDING_MODEL",
    "EMBEDDING_BASE_URL",
    "VITE_PUBLIC_DEMO_ENABLED",
    "VITE_PUBLIC_DEMO_USERNAME",
    "VITE_PUBLIC_DEMO_PASSWORD",
    "VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS",
)


def _environment(output: Path) -> dict[str, str]:
    return {
        **os.environ,
        "SITE_ADDRESS": "qms.example.test",
        "TAILSCALE_IP": "100.64.0.10",
        "OUTPUT_PATH": str(output),
    }


def _run(output: Path, **overrides: str) -> subprocess.CompletedProcess[str]:
    environment = _environment(output)
    environment.update(overrides)
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )


def _read_dotenv(path: Path) -> tuple[Counter[str], dict[str, str]]:
    entries = [
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if line and not line.startswith("#")
    ]
    return Counter(key for key, _ in entries), dict(entries)


def _require(condition: bool, fixed_message: str) -> None:
    if not condition:
        pytest.fail(fixed_message, pytrace=False)


def _assert_generated_content(values: dict[str, str]) -> None:
    password_keys = ("POSTGRES_PASSWORD", "REDIS_PASSWORD", "NEO4J_PASSWORD")
    for key in password_keys:
        _require(
            re.fullmatch(r"[0-9a-f]{48}", values.get(key, "")) is not None,
            f"{key} format invalid",
        )
    _require(
        re.fullmatch(r"[0-9a-f]{96}", values.get("SECRET_KEY", "")) is not None,
        "SECRET_KEY format invalid",
    )
    fingerprints = {
        hashlib.sha256(values[key].encode()).digest()
        for key in (*password_keys, "SECRET_KEY")
    }
    _require(len(fingerprints) == 4, "generated secrets are not unique")

    expected_database_url = (
        "postgresql+asyncpg://qms:"
        + values["POSTGRES_PASSWORD"]
        + "@db:5432/qms"
    )
    expected_redis_url = "redis://:" + values["REDIS_PASSWORD"] + "@redis:6379/0"
    _require(
        hmac.compare_digest(values.get("DATABASE_URL", ""), expected_database_url),
        "DATABASE_URL internal target invalid",
    )
    _require(
        hmac.compare_digest(values.get("REDIS_URL", ""), expected_redis_url),
        "REDIS_URL internal target invalid",
    )


def _assert_sensitive_values_absent(values: dict[str, str], output: str) -> None:
    for key in (
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "NEO4J_PASSWORD",
        "SECRET_KEY",
        "DATABASE_URL",
        "REDIS_URL",
    ):
        value = values.get(key, "")
        _require(bool(value), f"{key} missing from generated file")
        _require(value not in output, f"{key} leaked to process output")


def _temporary_outputs(output: Path) -> list[Path]:
    return list(output.parent.glob(f".{output.name}.tmp.*"))


def _blocking_openssl_environment(
    tmp_path: Path, output: Path, *, block_on_call: int
) -> tuple[dict[str, str], Path, Path]:
    real_openssl = shutil.which("openssl")
    assert real_openssl is not None
    fake_bin = tmp_path / "blocking-bin"
    fake_bin.mkdir()
    fake_openssl = fake_bin / "openssl"
    fake_openssl.write_text(
        """#!/bin/sh
count=0
if [ -f "$OPENSSL_COUNT" ]; then
  count=$(cat "$OPENSSL_COUNT")
fi
count=$((count + 1))
printf '%s\n' "$count" > "$OPENSSL_COUNT"
if [ "$count" -eq "$OPENSSL_BLOCK_ON_CALL" ]; then
  : > "$OPENSSL_STARTED"
  while [ ! -e "$OPENSSL_RELEASE" ]; do
    sleep 0.01
  done
fi
exec "$REAL_OPENSSL" "$@"
"""
    )
    fake_openssl.chmod(0o755)
    started = tmp_path / "openssl-started"
    release = tmp_path / "openssl-release"
    environment = {
        **_environment(output),
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "REAL_OPENSSL": real_openssl,
        "OPENSSL_COUNT": str(tmp_path / "openssl-count"),
        "OPENSSL_BLOCK_ON_CALL": str(block_on_call),
        "OPENSSL_STARTED": str(started),
        "OPENSSL_RELEASE": str(release),
    }
    return environment, started, release


def _wait_for(path: Path, timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {path.name}")


def test_script_is_executable_valid_bash():
    assert SCRIPT.is_file()
    assert SCRIPT.stat().st_mode & 0o111 == 0o111
    assert SCRIPT.read_text().splitlines()[:3] == [
        "#!/usr/bin/env bash",
        "set +x",
        "set -euo pipefail",
    ]
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        text=True,
        capture_output=True,
        check=False,
    )
    _require(result.returncode == 0, "command failed")


def test_generator_requires_python3_for_atomic_publication(tmp_path):
    output = tmp_path / "no-python.env"
    empty_path = tmp_path / "empty-bin"
    empty_path.mkdir()
    bash = shutil.which("bash")
    assert bash is not None
    environment = _environment(output)
    environment["PATH"] = str(empty_path)

    result = subprocess.run(
        [bash, str(SCRIPT)],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    assert result.returncode != 0
    assert not output.exists()
    _require(result.stdout == "", "missing-python path wrote stdout")
    _require(
        result.stderr == "error: python3 is required for atomic publication\n",
        "missing-python error category invalid",
    )
    assert _temporary_outputs(output) == []


def test_generator_creates_secure_complete_environment_without_leaking_secrets(tmp_path):
    output = tmp_path / "production config with spaces.env"

    result = _run(output)

    _require(result.returncode == 0, "command failed")
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    counts, values = _read_dotenv(output)
    assert set(counts) == set(REQUIRED_KEYS)
    assert all(counts[key] == 1 for key in REQUIRED_KEYS)

    _assert_generated_content(values)
    _require(values.get("NEO4J_URI") == "bolt://neo4j:7687", "NEO4J_URI invalid")
    _require(values.get("TENANT_MODE") == "single", "TENANT_MODE invalid")
    _require(values.get("E2E_MODE") == "false", "E2E_MODE invalid")
    _require(
        values.get("VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS") == "",
        "privileged demo accounts must be disabled by default",
    )
    for key in (
        "LLM_PROVIDER",
        "LLM_API_KEY",
        "LLM_MODEL",
        "LLM_BASE_URL",
        "EMBEDDING_PROVIDER",
        "EMBEDDING_API_KEY",
        "EMBEDDING_MODEL",
        "EMBEDDING_BASE_URL",
    ):
        _require(values.get(key) == "", f"{key} must be empty")

    combined_output = result.stdout + result.stderr
    _require(
        result.stdout == f"production environment created at {output}\n",
        "generator success status invalid",
    )
    _require(result.stderr == "", "generator wrote unexpected stderr")
    _assert_sensitive_values_absent(values, combined_output)
    assert _temporary_outputs(output) == []


def test_generator_refuses_to_overwrite_existing_file(tmp_path):
    output = tmp_path / "already-exists.env"
    original = b"DO_NOT_REPLACE=yes\n"
    original_digest = hashlib.sha256(original).digest()
    output.write_bytes(original)

    result = _run(output)

    assert result.returncode != 0
    _require(
        hmac.compare_digest(hashlib.sha256(output.read_bytes()).digest(), original_digest),
        "existing output was modified",
    )
    _require(result.stdout == "", "generator wrote unexpected stdout")
    _require(
        result.stderr == "error: output already exists\n",
        "overwrite refusal category invalid",
    )
    assert _temporary_outputs(output) == []


def test_generator_refuses_symlink_to_existing_file_without_changing_target(tmp_path):
    target = tmp_path / "real-existing.env"
    original = b"DO_NOT_REPLACE=yes\n"
    original_digest = hashlib.sha256(original).digest()
    target.write_bytes(original)
    output = tmp_path / "symlink-output.env"
    output.symlink_to(target)

    result = _run(output)

    assert result.returncode != 0
    assert output.is_symlink()
    _require(
        hmac.compare_digest(hashlib.sha256(target.read_bytes()).digest(), original_digest),
        "symlink target was modified",
    )
    _require(result.stdout == "", "generator wrote unexpected stdout")
    _require(
        result.stderr == "error: output already exists\n",
        "symlink refusal category invalid",
    )
    assert _temporary_outputs(output) == []


def test_generator_refuses_existing_fifo_without_writing_secrets(tmp_path):
    output = tmp_path / "attacker-fifo.env"
    os.mkfifo(output, mode=0o600)
    reader = os.open(output, os.O_RDONLY | os.O_NONBLOCK)
    try:
        result = _run(output)
        leaked = os.read(reader, 65536)
    finally:
        os.close(reader)

    assert result.returncode != 0
    assert stat.S_ISFIFO(output.stat().st_mode)
    _require(leaked == b"", "generator wrote secret content to an existing FIFO")
    _require(result.stdout == "", "generator wrote unexpected stdout")
    _require(
        result.stderr == "error: output already exists\n",
        "overwrite refusal category invalid",
    )
    assert _temporary_outputs(output) == []


@pytest.mark.parametrize("existing_kind", ["directory", "directory-symlink"])
def test_generator_refuses_existing_directory_targets_without_hidden_secret_link(
    tmp_path, existing_kind
):
    output = tmp_path / "existing-target"
    if existing_kind == "directory":
        target_directory = output
        target_directory.mkdir()
    else:
        target_directory = tmp_path / "real-directory"
        target_directory.mkdir()
        output.symlink_to(target_directory, target_is_directory=True)

    result = _run(output)

    assert result.returncode != 0
    _require(result.stdout == "", "generator reported success for directory target")
    _require(
        result.stderr == "error: output already exists\n",
        "directory-target refusal category invalid",
    )
    assert list(target_directory.iterdir()) == []
    if existing_kind == "directory-symlink":
        assert output.is_symlink()
    else:
        assert output.is_dir()
    assert _temporary_outputs(output) == []


def test_generator_disables_inherited_xtrace_before_secret_work(tmp_path):
    output = tmp_path / "xtrace.env"
    bash_env = tmp_path / "bash-env"
    bash_env.write_text("set -x\n")
    environment = _environment(output)
    environment["BASH_ENV"] = str(bash_env)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0
    _, values = _read_dotenv(output)
    _assert_generated_content(values)
    _assert_sensitive_values_absent(values, result.stdout + result.stderr)


def test_secret_checks_do_not_use_pytest_assertion_introspection():
    source = Path(__file__).read_text()
    tree = ast.parse(source)
    forbidden_fragments = (
        "values[",
        "values.get(",
        "password_keys",
        "combined_output",
        "result.stdout",
        "result.stderr",
        "stdout + stderr",
        "rerun.stderr",
        "read_bytes() == original",
    )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        expression = ast.get_source_segment(source, node.test) or ""
        _require(
            not any(fragment in expression for fragment in forbidden_fragments),
            "secret-bearing assertion must use a fixed-message helper",
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("SITE_ADDRESS", "qms.example.test\nINJECTED=value"),
        ("SITE_ADDRESS", "qms.example.test\rINJECTED=value"),
        ("SITE_ADDRESS", "qms.example.test bad"),
        ("TAILSCALE_IP", "100.64.0.10\tINJECTED=value"),
    ],
)
def test_generator_rejects_dotenv_injection_without_creating_output(
    tmp_path, field, value
):
    output = tmp_path / "rejected.env"

    result = _run(output, **{field: value})

    assert result.returncode != 0
    assert not output.exists()
    _require(result.stdout == "", "generator wrote unexpected stdout")
    _require(
        result.stderr == f"error: invalid {field}\n",
        "invalid-input error category invalid",
    )
    assert _temporary_outputs(output) == []


@pytest.mark.parametrize("field", ["SITE_ADDRESS", "TAILSCALE_IP"])
def test_generator_requires_nonempty_runtime_inputs(tmp_path, field):
    output = tmp_path / "missing.env"

    result = _run(output, **{field: ""})

    assert result.returncode != 0
    assert not output.exists()
    _require(result.stdout == "", "generator wrote unexpected stdout")
    _require(
        result.stderr == f"error: {field} is required\n",
        "missing-input error category invalid",
    )
    assert _temporary_outputs(output) == []


def test_generator_removes_partial_output_when_secret_generation_fails(tmp_path):
    output = tmp_path / "partial.env"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_openssl = fake_bin / "openssl"
    fake_openssl.write_text("#!/bin/sh\nexit 23\n")
    fake_openssl.chmod(0o755)

    result = _run(output, PATH=f"{fake_bin}{os.pathsep}{os.environ['PATH']}")

    assert result.returncode != 0
    assert not output.exists()
    _require(result.stdout == "", "generator wrote unexpected stdout")
    _require(
        result.stderr == "error: secret generation failed\n",
        "secret-generation error category invalid",
    )
    assert _temporary_outputs(output) == []


def test_generator_removes_written_output_when_finalization_fails(tmp_path):
    output = tmp_path / "written-but-not-finalized.env"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_chmod = fake_bin / "chmod"
    fake_chmod.write_text("#!/bin/sh\nexit 24\n")
    fake_chmod.chmod(0o755)

    result = _run(output, PATH=f"{fake_bin}{os.pathsep}{os.environ['PATH']}")

    assert result.returncode != 0
    assert not output.exists()
    _require(result.stdout == "", "generator wrote unexpected stdout")
    _require("SECRET_KEY=" not in result.stderr, "SECRET_KEY leaked on failure")
    _require(
        "postgresql+asyncpg://" not in result.stderr,
        "DATABASE_URL leaked on failure",
    )
    assert _temporary_outputs(output) == []


@pytest.mark.parametrize(
    ("command", "expected_error", "final_exists", "temp_count"),
    [
        ("cat", "error: environment write failed\n", False, 0),
        ("chmod", "error: environment permission failed\n", False, 0),
        ("python3", "error: atomic publication failed\n", False, 0),
        ("rm", "error: temporary output cleanup failed\n", True, 1),
    ],
    ids=("write", "permissions", "atomic-link", "final-temp-removal"),
)
def test_generator_reports_fixed_secret_free_file_operation_failures(
    tmp_path, command, expected_error, final_exists, temp_count
):
    output = tmp_path / "injected-failure.env"
    fake_bin = tmp_path / "failing-bin"
    fake_bin.mkdir()
    failing_command = fake_bin / command
    failing_command.write_text("#!/bin/sh\nexit 42\n")
    failing_command.chmod(0o755)

    result = _run(output, PATH=f"{fake_bin}{os.pathsep}{os.environ['PATH']}")

    assert result.returncode != 0
    assert output.exists() is final_exists
    assert len(_temporary_outputs(output)) == temp_count
    _require(result.stdout == "", "injected failure wrote stdout")
    _require(result.stderr == expected_error, "file-operation error category invalid")
    _require("SECRET_KEY=" not in result.stderr, "secret leaked on file-operation failure")
    _require(
        "postgresql+asyncpg://" not in result.stderr,
        "database URL leaked on file-operation failure",
    )


def test_generator_keeps_final_path_absent_until_atomic_publish(tmp_path):
    output = tmp_path / "atomic production.env"
    environment, started, release = _blocking_openssl_environment(
        tmp_path, output, block_on_call=1
    )
    process = subprocess.Popen(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )

    try:
        _wait_for(started)
        assert not output.exists()
        temporary_outputs = _temporary_outputs(output)
        assert len(temporary_outputs) == 1
        assert stat.S_IMODE(temporary_outputs[0].stat().st_mode) == 0o600
        release.touch()
        stdout, stderr = process.communicate(timeout=15)
    finally:
        if process.poll() is None:
            release.touch(exist_ok=True)
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)

    _require(process.returncode == 0, "barrier-controlled generator failed")
    _require(
        stdout == f"production environment created at {output}\n",
        "barrier-controlled success status invalid",
    )
    _require(stderr == "", "barrier-controlled generator wrote stderr")
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    counts, _ = _read_dotenv(output)
    assert set(counts) == set(REQUIRED_KEYS)
    assert all(counts[key] == 1 for key in REQUIRED_KEYS)
    assert _temporary_outputs(output) == []


def test_generator_refuses_file_created_during_generation(tmp_path):
    output = tmp_path / "created-during-generation.env"
    environment, started, release = _blocking_openssl_environment(
        tmp_path, output, block_on_call=2
    )
    process = subprocess.Popen(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    original = b"CONCURRENT_WRITER_WON=yes\n"
    original_digest = hashlib.sha256(original).digest()

    try:
        _wait_for(started)
        assert not output.exists()
        output.write_bytes(original)
        release.touch()
        stdout, stderr = process.communicate(timeout=15)
    finally:
        if process.poll() is None:
            release.touch(exist_ok=True)
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)

    assert process.returncode != 0
    _require(
        hmac.compare_digest(hashlib.sha256(output.read_bytes()).digest(), original_digest),
        "concurrent output was overwritten",
    )
    _require(stdout == "", "concurrent refusal wrote unexpected stdout")
    _require(
        stderr == "error: output already exists\n",
        "concurrent refusal category invalid",
    )
    assert _temporary_outputs(output) == []


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGQUIT])
def test_generator_signal_during_generation_cleans_temp_and_allows_rerun(
    tmp_path, signum
):
    output = tmp_path / f"signal-{signum}.env"
    environment, started, release = _blocking_openssl_environment(
        tmp_path, output, block_on_call=2
    )
    process = subprocess.Popen(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )

    try:
        _wait_for(started)
        assert not output.exists()
        assert len(_temporary_outputs(output)) == 1
        os.killpg(process.pid, signum)
        stdout, stderr = process.communicate(timeout=15)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)

    assert process.returncode != 0
    assert not output.exists()
    assert _temporary_outputs(output) == []
    _require("SECRET_KEY=" not in stdout + stderr, "SECRET_KEY leaked on signal")
    _require(
        "postgresql+asyncpg://" not in stdout + stderr,
        "DATABASE_URL leaked on signal",
    )

    rerun = _run(output)
    _require(rerun.returncode == 0, "clean rerun after signal failed")
    assert output.exists()
    assert _temporary_outputs(output) == []


def test_generator_exclusive_creation_allows_only_one_racing_writer(tmp_path):
    output = tmp_path / "race.env"
    processes = [
        subprocess.Popen(
            ["bash", str(SCRIPT)],
            cwd=ROOT,
            env=_environment(output),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(8)
    ]

    results = [(*process.communicate(timeout=15), process.returncode) for process in processes]

    assert sum(returncode == 0 for _, _, returncode in results) == 1
    assert all(
        stderr in ("", "error: output already exists\n")
        for _, stderr, _ in results
    )
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    counts, _ = _read_dotenv(output)
    assert set(counts) == set(REQUIRED_KEYS)
    assert all(counts[key] == 1 for key in REQUIRED_KEYS)
    assert _temporary_outputs(output) == []

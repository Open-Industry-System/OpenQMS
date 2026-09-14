import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "production-compose.sh"
COMPOSE = ROOT / "docker-compose.prod.yml"
EXAMPLE = ROOT / ".env.production.example"

ENV_KEYS = (
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
)
REQUIRED_NONEMPTY_KEYS = set(ENV_KEYS) - {
    "LLM_PROVIDER",
    "LLM_API_KEY",
    "LLM_MODEL",
    "LLM_BASE_URL",
    "EMBEDDING_PROVIDER",
    "EMBEDDING_API_KEY",
    "EMBEDDING_MODEL",
    "EMBEDDING_BASE_URL",
}
POISON = "AMBIENT_POISON_MUST_NOT_REACH_DOCKER"


def _require(condition: bool, fixed_message: str) -> None:
    if not condition:
        pytest.fail(fixed_message, pytrace=False)


def _valid_values() -> dict[str, str]:
    postgres_password = "a" * 48
    redis_password = "b" * 48
    neo4j_password = "c" * 48
    values = {
        "SITE_ADDRESS": "qms.example.test",
        "TAILSCALE_IP": "100.64.0.10",
        "POSTGRES_USER": "qms",
        "POSTGRES_PASSWORD": postgres_password,
        "POSTGRES_DB": "qms",
        "DATABASE_URL": (
            f"postgresql+asyncpg://qms:{postgres_password}@db:5432/qms"
        ),
        "REDIS_PASSWORD": redis_password,
        "REDIS_URL": f"redis://:{redis_password}@redis:6379/0",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": neo4j_password,
        "NEO4J_URI": "bolt://neo4j:7687",
        "NEO4J_DATABASE": "neo4j",
        "SECRET_KEY": "d" * 96,
        "ACCESS_TOKEN_EXPIRE_MINUTES": "120",
        "REFRESH_TOKEN_EXPIRE_DAYS": "7",
        "ALGORITHM": "HS256",
        "GRAPH_REPOSITORY": "neo4j",
        "TENANT_MODE": "single",
        "E2E_MODE": "false",
        "LLM_PROVIDER": "",
        "LLM_API_KEY": "",
        "LLM_MODEL": "",
        "LLM_BASE_URL": "",
        "EMBEDDING_PROVIDER": "",
        "EMBEDDING_API_KEY": "",
        "EMBEDDING_MODEL": "",
        "EMBEDDING_BASE_URL": "",
        "VITE_PUBLIC_DEMO_ENABLED": "true",
        "VITE_PUBLIC_DEMO_USERNAME": "viewer",
        "VITE_PUBLIC_DEMO_PASSWORD": "Viewer@2026",
    }
    assert set(values) == set(ENV_KEYS)
    return values


def _env_text(
    *,
    overrides: dict[str, str] | None = None,
    omit: set[str] | None = None,
    duplicate: str | None = None,
) -> str:
    values = _valid_values()
    values.update(overrides or {})
    omitted = omit or set()
    lines = [f"{key}={values[key]}" for key in ENV_KEYS if key not in omitted]
    if duplicate is not None:
        lines.append(f"{duplicate}={values[duplicate]}")
    return "# generated non-secret test environment\n" + "\n".join(lines) + "\n"


def _make_repo(tmp_path: Path, env_text: str) -> Path:
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(SCRIPT, scripts / SCRIPT.name)
    shutil.copy2(COMPOSE, repo / COMPOSE.name)
    (repo / ".env.production").write_text(env_text)
    return repo


def _write_fake_docker(tmp_path: Path) -> tuple[Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "docker-capture.json"
    docker = fake_bin / "docker"
    docker.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

keys = os.environ["CHECK_ENV_KEYS"].split(",")
Path(os.environ["DOCKER_CAPTURE"]).write_text(json.dumps({
    "argv": sys.argv[1:],
    "present_keys": sorted(key for key in keys if key in os.environ),
    "docker_host": os.environ.get("DOCKER_HOST"),
}))
"""
    )
    docker.chmod(0o755)
    return fake_bin, capture


def _run_wrapper(
    tmp_path: Path,
    env_text: str,
    *arguments: str,
    bash_env: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    repo = _make_repo(tmp_path, env_text)
    fake_bin, capture = _write_fake_docker(tmp_path)
    checked_keys = (
        *ENV_KEYS,
        "COMPOSE_FILE",
        "COMPOSE_ENV_FILES",
        "COMPOSE_PROJECT_NAME",
        "OPENQMS_ENV_FILE",
    )
    alternate_env = tmp_path / "must-not-be-used.env"
    alternate_env.write_text(_env_text(overrides={"SECRET_KEY": "e" * 96}))
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "OPENQMS_ENV_FILE": str(alternate_env),
        "DOCKER_CAPTURE": str(capture),
        "CHECK_ENV_KEYS": ",".join(checked_keys),
        "DOCKER_HOST": "unix:///tmp/non-secret-docker.sock",
        "COMPOSE_FILE": "/tmp/attacker-compose.yml",
        "COMPOSE_ENV_FILES": "/tmp/attacker.env",
        "COMPOSE_PROJECT_NAME": "attacker-project",
    }
    environment.update({key: f"{POISON}_{key}" for key in ENV_KEYS})
    environment.update(extra_env or {})
    if bash_env is not None:
        environment["BASH_ENV"] = str(bash_env)
    result = subprocess.run(
        ["bash", str(repo / "scripts" / SCRIPT.name), *arguments],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    return result, capture, repo


def test_production_compose_wrapper_is_executable_valid_and_non_sourcing():
    assert SCRIPT.is_file()
    assert SCRIPT.stat().st_mode & 0o111 == 0o111
    source = SCRIPT.read_text()
    assert source.splitlines()[:3] == [
        "#!/usr/bin/env bash",
        "set +x",
        "set -euo pipefail",
    ]
    assert 'ENV_FILE=${OPENQMS_ENV_FILE' not in source
    assert "source " not in source
    assert "eval " not in source
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        text=True,
        capture_output=True,
        check=False,
    )
    _require(result.returncode == 0, "wrapper syntax check failed")


def test_wrapper_uses_fixed_env_compose_and_project_arguments(tmp_path):
    result, capture, repo = _run_wrapper(
        tmp_path, _env_text(), "config", "--format", "json"
    )

    _require(result.returncode == 0, "wrapper command failed")
    _require(result.stdout == "", "wrapper wrote unexpected stdout")
    _require(result.stderr == "", "wrapper wrote unexpected stderr")
    recorded = json.loads(capture.read_text())
    assert recorded["present_keys"] == []
    assert recorded["docker_host"] == "unix:///tmp/non-secret-docker.sock"
    assert recorded["argv"] == [
        "compose",
        "--project-name",
        "openqms",
        "--project-directory",
        str(repo),
        "--env-file",
        str(repo / ".env.production"),
        "-f",
        str(repo / "docker-compose.prod.yml"),
        "config",
        "--format",
        "json",
    ]


def test_wrapper_forwards_subcommand_arguments_exactly(tmp_path):
    forwarded = ("config", "--services", "value with spaces", "--quiet")

    result, capture, _repo = _run_wrapper(tmp_path, _env_text(), *forwarded)

    _require(result.returncode == 0, "wrapper command failed")
    recorded = json.loads(capture.read_text())
    assert recorded["argv"][-len(forwarded) :] == list(forwarded)


@pytest.mark.parametrize(
    "option",
    ["-f", "--file", "--env-file", "--project-name", "--project-directory"],
)
def test_wrapper_rejects_compose_root_option_as_first_argument(tmp_path, option):
    result, capture, _repo = _run_wrapper(
        tmp_path, _env_text(), option, "/tmp/attacker"
    )

    assert result.returncode != 0
    assert not capture.exists()
    _require(result.stdout == "", "root-option rejection wrote stdout")
    _require(
        result.stderr == "error: invalid Compose subcommand\n",
        "root-option rejection category invalid",
    )


def test_wrapper_requires_compose_subcommand(tmp_path):
    result, capture, _repo = _run_wrapper(tmp_path, _env_text())

    assert result.returncode != 0
    assert not capture.exists()
    _require(result.stdout == "", "missing-subcommand rejection wrote stdout")
    _require(
        result.stderr == "error: Compose subcommand is required\n",
        "missing-subcommand category invalid",
    )


@pytest.mark.parametrize(
    ("env_text", "expected_error"),
    [
        (_env_text(omit={"SECRET_KEY"}), "error: production environment is incomplete\n"),
        (
            _env_text(duplicate="SECRET_KEY"),
            "error: duplicate production environment key\n",
        ),
        (
            _env_text(overrides={"SITE_ADDRESS": ""}),
            "error: required production environment value is empty\n",
        ),
        (
            _env_text(overrides={"SECRET_KEY": "REQUIRED_GENERATED_ON_SERVER"}),
            "error: invalid production secret\n",
        ),
        (
            _env_text(overrides={"POSTGRES_PASSWORD": "A" * 48}),
            "error: invalid production secret\n",
        ),
        (
            _env_text(overrides={"DATABASE_URL": "postgresql+asyncpg://invalid"}),
            "error: invalid internal database URL\n",
        ),
        (
            _env_text(overrides={"REDIS_URL": "redis://invalid"}),
            "error: invalid internal Redis URL\n",
        ),
        (
            _env_text(overrides={"VITE_PUBLIC_DEMO_PASSWORD": "${SECRET_KEY}"}),
            "error: production environment interpolation is not allowed\n",
        ),
    ],
    ids=(
        "missing-required-key",
        "duplicate-required-key",
        "empty-runtime-value",
        "placeholder-secret",
        "invalid-password-format",
        "database-url-mismatch",
        "redis-url-mismatch",
        "compose-interpolation",
    ),
)
def test_wrapper_rejects_invalid_production_environment(
    tmp_path, env_text, expected_error
):
    result, capture, _repo = _run_wrapper(tmp_path, env_text, "config")

    _require(
        result.returncode != 0,
        "wrapper accepted invalid production environment",
    )
    assert not capture.exists()
    _require(result.stdout == "", "invalid environment wrote stdout")
    _require(result.stderr == expected_error, "environment error category invalid")
    _require(POISON not in result.stdout + result.stderr, "ambient poison leaked")


@pytest.mark.parametrize(
    ("key", "invalid_value", "expected_error"),
    [
        ("E2E_MODE", "true", "error: invalid E2E_MODE\n"),
        ("E2E_MODE", "1", "error: invalid E2E_MODE\n"),
        ("E2E_MODE", "False", "error: invalid E2E_MODE\n"),
        ("TENANT_MODE", "dev", "error: invalid TENANT_MODE\n"),
        ("TENANT_MODE", "production", "error: invalid TENANT_MODE\n"),
        ("TENANT_MODE", "other", "error: invalid TENANT_MODE\n"),
        ("ALGORITHM", "HS384", "error: invalid ALGORITHM\n"),
        ("ALGORITHM", "none", "error: invalid ALGORITHM\n"),
        ("ALGORITHM", "", "error: invalid ALGORITHM\n"),
    ],
    ids=(
        "e2e-true",
        "e2e-one",
        "e2e-noncanonical-false",
        "tenant-dev",
        "tenant-production",
        "tenant-other",
        "algorithm-hs384",
        "algorithm-none",
        "algorithm-empty",
    ),
)
def test_wrapper_rejects_unsafe_production_modes(
    tmp_path, key, invalid_value, expected_error
):
    result, capture, _repo = _run_wrapper(
        tmp_path,
        _env_text(overrides={key: invalid_value}),
        "config",
    )

    _require(result.returncode != 0, "wrapper accepted unsafe production mode")
    assert not capture.exists()
    _require(result.stdout == "", "unsafe-mode rejection wrote stdout")
    _require(result.stderr == expected_error, "unsafe-mode error category invalid")


def test_wrapper_rejects_example_placeholders_before_docker(tmp_path):
    result, capture, _repo = _run_wrapper(
        tmp_path, EXAMPLE.read_text(), "config", "--format", "json"
    )

    assert result.returncode != 0
    assert not capture.exists()
    _require(result.stdout == "", "placeholder rejection wrote stdout")
    _require(
        result.stderr == "error: invalid production secret\n",
        "placeholder rejection category invalid",
    )


def test_wrapper_rejects_invalid_dotenv_key_without_printing_value(tmp_path):
    secret_sentinel = "VALUE_MUST_NOT_BE_PRINTED"
    env_text = _env_text() + f"INVALID-KEY={secret_sentinel}\n"

    result, capture, _repo = _run_wrapper(tmp_path, env_text, "config")

    assert result.returncode != 0
    assert not capture.exists()
    _require(result.stdout == "", "invalid env file wrote stdout")
    _require(
        result.stderr == "error: invalid production environment key\n",
        "invalid-key error category invalid",
    )
    _require(
        secret_sentinel not in result.stdout + result.stderr,
        "invalid env value leaked to output",
    )


def test_wrapper_requires_repo_env_file_with_fixed_error(tmp_path):
    repo = _make_repo(tmp_path, _env_text())
    (repo / ".env.production").unlink()
    fake_bin, capture = _write_fake_docker(tmp_path)
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "DOCKER_CAPTURE": str(capture),
        "CHECK_ENV_KEYS": ",".join(ENV_KEYS),
    }

    result = subprocess.run(
        ["bash", str(repo / "scripts" / SCRIPT.name), "config"],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    assert result.returncode != 0
    assert not capture.exists()
    _require(result.stdout == "", "missing env file wrote stdout")
    _require(
        result.stderr == "error: production environment file is not readable\n",
        "missing-env error category invalid",
    )


def test_wrapper_disables_inherited_xtrace_before_parsing_values(tmp_path):
    secret_sentinel = "e" * 96
    bash_env = tmp_path / "bash-env"
    bash_env.write_text("set -x\n")

    result, capture, _repo = _run_wrapper(
        tmp_path,
        _env_text(overrides={"SECRET_KEY": secret_sentinel}),
        "config",
        bash_env=bash_env,
    )

    _require(result.returncode == 0, "xtrace wrapper command failed")
    assert capture.exists()
    _require(
        secret_sentinel not in result.stdout + result.stderr,
        "wrapper env value leaked under xtrace",
    )
    _require(
        POISON not in result.stdout + result.stderr,
        "ambient poison leaked under xtrace",
    )

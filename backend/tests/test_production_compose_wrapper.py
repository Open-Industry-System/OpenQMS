import json
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "production-compose.sh"
COMPOSE = ROOT / "docker-compose.prod.yml"

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
POISON = "AMBIENT_POISON_MUST_NOT_REACH_DOCKER"


def _require(condition: bool, fixed_message: str) -> None:
    if not condition:
        pytest.fail(fixed_message, pytrace=False)


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


def _wrapper_environment(
    tmp_path: Path, env_file: Path, fake_bin: Path, capture: Path
) -> dict[str, str]:
    checked_keys = (
        *ENV_KEYS,
        "COMPOSE_FILE",
        "COMPOSE_ENV_FILES",
        "COMPOSE_PROJECT_NAME",
    )
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "OPENQMS_ENV_FILE": str(env_file),
        "DOCKER_CAPTURE": str(capture),
        "CHECK_ENV_KEYS": ",".join(checked_keys),
        "DOCKER_HOST": "unix:///tmp/non-secret-docker.sock",
        "COMPOSE_FILE": "/tmp/attacker-compose.yml",
        "COMPOSE_ENV_FILES": "/tmp/attacker.env",
        "COMPOSE_PROJECT_NAME": "attacker-project",
    }
    environment.update({key: f"{POISON}_{key}" for key in ENV_KEYS})
    return environment


def _run_wrapper(
    tmp_path: Path, env_file: Path, *arguments: str, bash_env: Path | None = None
) -> tuple[subprocess.CompletedProcess[str], Path]:
    fake_bin, capture = _write_fake_docker(tmp_path)
    environment = _wrapper_environment(tmp_path, env_file, fake_bin, capture)
    if bash_env is not None:
        environment["BASH_ENV"] = str(bash_env)
    result = subprocess.run(
        ["bash", str(SCRIPT), *arguments],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    return result, capture


def test_production_compose_wrapper_is_executable_valid_and_non_sourcing():
    assert SCRIPT.is_file()
    assert SCRIPT.stat().st_mode & 0o111 == 0o111
    source = SCRIPT.read_text()
    assert source.splitlines()[:3] == [
        "#!/usr/bin/env bash",
        "set +x",
        "set -euo pipefail",
    ]
    assert "source " not in source
    assert "eval " not in source
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        text=True,
        capture_output=True,
        check=False,
    )
    _require(result.returncode == 0, "wrapper command failed")


def test_wrapper_unsets_env_file_keys_and_uses_fixed_compose_arguments(tmp_path):
    env_file = tmp_path / "production env with spaces"
    env_file.write_text(
        "# non-secret test values\n"
        "DATABASE_URL=postgresql+asyncpg://example@example.invalid/qms\n"
        "SECRET_KEY=EXAMPLE_ONLY\n"
        "POSTGRES_PASSWORD=EXAMPLE_ONLY\n"
        "REDIS_PASSWORD=EXAMPLE_ONLY\n"
        "NEO4J_PASSWORD=EXAMPLE_ONLY\n"
        "SITE_ADDRESS=qms.example.test\n"
        "TAILSCALE_IP=100.64.0.10\n"
    )

    result, capture = _run_wrapper(
        tmp_path, env_file, "config", "--format", "json"
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
        str(ROOT),
        "--env-file",
        str(env_file),
        "-f",
        str(COMPOSE),
        "config",
        "--format",
        "json",
    ]


def test_wrapper_forwards_each_user_argument_exactly(tmp_path):
    env_file = tmp_path / "valid.env"
    env_file.write_text("SITE_ADDRESS=qms.example.test\n")
    forwarded = ("config", "--services", "value with spaces", "--quiet")

    result, capture = _run_wrapper(tmp_path, env_file, *forwarded)

    _require(result.returncode == 0, "wrapper command failed")
    recorded = json.loads(capture.read_text())
    assert recorded["argv"][-len(forwarded) :] == list(forwarded)


def test_wrapper_rejects_invalid_dotenv_key_without_printing_value(tmp_path):
    env_file = tmp_path / "invalid.env"
    secret_sentinel = "VALUE_MUST_NOT_BE_PRINTED"
    env_file.write_text(
        f"SITE_ADDRESS=qms.example.test\nINVALID-KEY={secret_sentinel}\n"
    )

    result, capture = _run_wrapper(tmp_path, env_file, "config")

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


def test_wrapper_requires_readable_env_file_with_fixed_error(tmp_path):
    missing = tmp_path / "missing.env"

    result, capture = _run_wrapper(tmp_path, missing, "config")

    assert result.returncode != 0
    assert not capture.exists()
    _require(result.stdout == "", "missing env file wrote stdout")
    _require(
        result.stderr == "error: production environment file is not readable\n",
        "missing-env error category invalid",
    )


def test_wrapper_disables_inherited_xtrace_before_parsing_values(tmp_path):
    env_file = tmp_path / "xtrace.env"
    secret_sentinel = "XTRACE_VALUE_MUST_NOT_BE_PRINTED"
    env_file.write_text(f"SECRET_KEY={secret_sentinel}\n")
    bash_env = tmp_path / "bash-env"
    bash_env.write_text("set -x\n")

    result, capture = _run_wrapper(
        tmp_path, env_file, "config", bash_env=bash_env
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

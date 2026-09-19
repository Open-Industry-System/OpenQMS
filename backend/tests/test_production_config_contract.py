import json
import os
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = ROOT / "docker-compose.prod.yml"
ENV_EXAMPLE_PATH = ROOT / ".env.production.example"
PRODUCTION_COMPOSE_SCRIPT = ROOT / "scripts" / "production-compose.sh"
RELEASE_SHA = "0123456789abcdef0123456789abcdef01234567"

REQUIRED_ENV_KEYS = {
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
}
EXPECTED_SERVICES = {"db", "redis", "neo4j", "backend", "graph-worker", "web"}
EXPECTED_IPS = {
    "web": "172.30.0.10",
    "backend": "172.30.0.20",
    "db": "172.30.0.30",
    "redis": "172.30.0.40",
    "neo4j": "172.30.0.50",
    "graph-worker": "172.30.0.60",
}


def _service_block(compose: str, service: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(service)}:\n(?P<body>.*?)(?=^  [\w-]+:\n|^\S|\Z)",
        compose,
    )
    assert match, f"missing {service} service"
    return match.group("body")


def _short_ports(service: str, block: str) -> list[str]:
    match = re.search(
        r"(?ms)^    ports:\n(?P<body>.*?)(?=^    [\w-]+:|^  [\w-]+:|^\S|\Z)",
        block,
    )
    assert match, f"missing ports for {service}"
    return re.findall(r'''(?m)^\s*-\s*["']?([^"'\n]+)["']?\s*$''', match.group("body"))


def _forwarded_allow_ips(backend_block: str) -> list[str]:
    return re.findall(r"--forwarded-allow-ips=([^\s'\"\]]+)", backend_block)


def _has_single_forwarded_allow_ips_option(backend_block: str) -> bool:
    return backend_block.count("--forwarded-allow-ips") == 1


def _mapping_block(block: str, key: str) -> dict[str, str]:
    match = re.search(
        rf"(?ms)^    {re.escape(key)}:\n(?P<body>.*?)(?=^    [\w-]+:|^  [\w-]+:|^\S|\Z)",
        block,
    )
    assert match, f"missing {key} mapping"
    return dict(
        re.findall(r"(?m)^      ([A-Za-z0-9_]+):\s*(.*?)\s*$", match.group("body"))
    )


def _depends_on_conditions(block: str) -> dict[str, str]:
    match = re.search(
        r"(?ms)^    depends_on:\n(?P<body>.*?)(?=^    [\w-]+:|^  [\w-]+:|^\S|\Z)",
        block,
    )
    assert match
    return dict(
        re.findall(
            r"(?m)^      ([\w-]+):\n        condition:\s*([^\s]+)\s*$",
            match.group("body"),
        )
    )


def _assert_exact_environment(actual: dict[str, str], expected: dict[str, str]) -> None:
    assert actual == expected


def _assert_healthy_dependencies(
    actual: dict[str, dict[str, object]], expected_names: set[str]
) -> None:
    assert set(actual) == expected_names
    assert {name: config.get("condition") for name, config in actual.items()} == {
        name: "service_healthy" for name in expected_names
    }


def _dotenv(path: Path) -> tuple[Counter[str], dict[str, str]]:
    entries = [
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if line and not line.startswith("#")
    ]
    return Counter(key for key, _ in entries), dict(entries)


def _compose_cli_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _valid_render_environment() -> dict[str, str]:
    _, values = _dotenv(ENV_EXAMPLE_PATH)
    postgres_password = "a" * 48
    redis_password = "b" * 48
    neo4j_password = "c" * 48
    values.update(
        {
            "POSTGRES_PASSWORD": postgres_password,
            "DATABASE_URL": (
                f"postgresql+asyncpg://{values['POSTGRES_USER']}:"
                f"{postgres_password}@db:5432/{values['POSTGRES_DB']}"
            ),
            "REDIS_PASSWORD": redis_password,
            "REDIS_URL": f"redis://:{redis_password}@redis:6379/0",
            "NEO4J_PASSWORD": neo4j_password,
            "SECRET_KEY": "d" * 96,
        }
    )
    return values


def _temporary_render_repo(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    repo = tmp_path / "render-repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(PRODUCTION_COMPOSE_SCRIPT, scripts / PRODUCTION_COMPOSE_SCRIPT.name)
    shutil.copy2(COMPOSE_PATH, repo / COMPOSE_PATH.name)
    values = _valid_render_environment()
    (repo / ".env.production").write_text(
        "".join(f"{key}={value}\n" for key, value in values.items())
    )
    (repo / ".release-sha").write_text(RELEASE_SHA + "\n")
    return repo, values


def _render_compose(
    tmp_path: Path, **overrides: str
) -> tuple[dict[str, object], Path, dict[str, str]]:
    assert PRODUCTION_COMPOSE_SCRIPT.is_file(), "missing production Compose wrapper"
    repo, values = _temporary_render_repo(tmp_path)
    environment = {**os.environ, **overrides}
    result = subprocess.run(
        [
            str(repo / "scripts" / PRODUCTION_COMPOSE_SCRIPT.name),
            "config",
            "--format",
            "json",
        ],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout), repo, values


def test_forwarded_allow_ips_preserves_comma_separated_values():
    backend = "command: --forwarded-allow-ips=172.30.0.10,203.0.113.1 --proxy-headers"

    assert _forwarded_allow_ips(backend) == ["172.30.0.10,203.0.113.1"]


def test_forwarded_allow_ips_rejects_spaced_wildcard_after_safe_option():
    backend = "command: --forwarded-allow-ips=172.30.0.10 --forwarded-allow-ips '*'"

    assert _forwarded_allow_ips(backend) == ["172.30.0.10"]
    assert not _has_single_forwarded_allow_ips_option(backend)


def test_exact_environment_contract_rejects_removed_auth_and_hardcoded_secret():
    expected = {
        "REDIS_PASSWORD": "REQUIRED_GENERATED_ON_SERVER",
        "SECRET_KEY": "REQUIRED_GENERATED_ON_SERVER",
    }

    with pytest.raises(AssertionError):
        _assert_exact_environment(
            {"SECRET_KEY": "REQUIRED_GENERATED_ON_SERVER"}, expected
        )
    with pytest.raises(AssertionError):
        _assert_exact_environment(
            {
                "REDIS_PASSWORD": "REQUIRED_GENERATED_ON_SERVER",
                "SECRET_KEY": "hardcoded-default",
            },
            expected,
        )


def test_healthy_dependency_contract_rejects_removed_dependency():
    actual = {
        "db": {"condition": "service_healthy"},
        "redis": {"condition": "service_healthy"},
    }

    with pytest.raises(AssertionError):
        _assert_healthy_dependencies(actual, {"db", "redis", "neo4j"})


def test_production_compose_and_caddy_trusted_proxy_contract():
    compose = COMPOSE_PATH.read_text()
    caddy = (ROOT / "deploy" / "Caddyfile").read_text()

    web = _service_block(compose, "web")
    backend = _service_block(compose, "backend")
    db = _service_block(compose, "db")

    assert re.search(r"(?m)^\s*context:\s*\.\s*$", web)
    assert re.search(r"(?m)^\s*dockerfile:\s*frontend/Dockerfile\.prod\s*$", web)
    assert re.search(r"(?m)^\s*ipv4_address:\s*172\.30\.0\.10\s*$", web)
    assert _short_ports("web", web) == ["80:80", "443:443"]
    assert "--proxy-headers" in backend
    assert _has_single_forwarded_allow_ips_option(backend)
    assert _forwarded_allow_ips(backend) == ["172.30.0.10"]
    assert "--forwarded-allow-ips=*" not in backend

    assert _short_ports("db", db) == ["127.0.0.1:5432:5432"]
    assert "published:" not in db
    for service in ("redis", "neo4j", "backend", "graph-worker"):
        assert "ports:" not in _service_block(compose, service)
    assert "ollama" not in compose.lower()
    assert "--reload" not in compose
    assert "env_file:" not in compose
    assert "./backend:/app" not in compose
    assert "./frontend:/app" not in compose
    for secret_key in (
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "NEO4J_PASSWORD",
        "SECRET_KEY",
        "DATABASE_URL",
        "REDIS_URL",
    ):
        assert secret_key not in web
    assert "trusted_proxies" not in caddy


def test_production_images_require_release_revision_build_arg_and_label():
    compose = COMPOSE_PATH.read_text()
    backend_block = _service_block(compose, "backend")
    graph_worker_block = _service_block(compose, "graph-worker")
    web_block = _service_block(compose, "web")
    backend_dockerfile = (ROOT / "backend" / "Dockerfile").read_text()
    frontend_dockerfile = (ROOT / "frontend" / "Dockerfile.prod").read_text()
    frontend_final = frontend_dockerfile.split("FROM caddy:2-alpine", 1)[1]

    assert "ARG RELEASE_SHA" in backend_dockerfile
    assert "ARG RELEASE_SHA=" not in backend_dockerfile
    assert "LABEL org.opencontainers.image.revision=$RELEASE_SHA" in backend_dockerfile
    assert "ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple" in backend_dockerfile
    assert (
        'RUN python -m pip install --no-cache-dir --index-url "$PIP_INDEX_URL" '
        "-r requirements.txt"
    ) in backend_dockerfile
    assert not re.search(r"https?://[^\s\"']+@[^\s\"']+", backend_dockerfile)
    assert re.search(
        r"(?ms)^    build:.*?^      args:.*?^        PIP_INDEX_URL: https://pypi\.org/simple$",
        backend_block,
    )
    assert not re.search(r"(?m)^        PIP_INDEX_URL:.*@", backend_block)
    assert "ARG RELEASE_SHA" in frontend_final
    assert "ARG RELEASE_SHA=" not in frontend_final
    assert "LABEL org.opencontainers.image.revision=$RELEASE_SHA" in frontend_final
    assert re.search(r"(?ms)^    build:.*?^      args:\n        RELEASE_SHA: \$\{RELEASE_SHA\}", backend_block)
    assert re.search(r"(?ms)^    build:.*?^      args:.*?^        RELEASE_SHA: \$\{RELEASE_SHA\}", web_block)
    assert "build:" not in graph_worker_block
    assert "image: openqms-backend:prod" in graph_worker_block


def test_static_production_stack_contract():
    compose = COMPOSE_PATH.read_text()

    assert set(re.findall(r"(?m)^  ([\w-]+):\n", compose.split("services:\n", 1)[1].split("\nnetworks:", 1)[0])) == EXPECTED_SERVICES
    assert "subnet: 172.30.0.0/24" in compose
    assert "pgdata_prod:" in compose
    assert "neo4j_data_prod:" in compose
    assert "caddy_data:" in compose
    assert "caddy_config:" in compose
    db = _service_block(compose, "db")
    redis = _service_block(compose, "redis")
    neo4j = _service_block(compose, "neo4j")
    backend = _service_block(compose, "backend")
    graph_worker = _service_block(compose, "graph-worker")
    web = _service_block(compose, "web")

    _assert_exact_environment(
        _mapping_block(db, "environment"),
        {
            "POSTGRES_USER": "${POSTGRES_USER}",
            "POSTGRES_PASSWORD": "${POSTGRES_PASSWORD}",
            "POSTGRES_DB": "${POSTGRES_DB}",
        },
    )
    _assert_exact_environment(
        _mapping_block(redis, "environment"),
        {"REDIS_PASSWORD": "${REDIS_PASSWORD}"},
    )
    _assert_exact_environment(
        _mapping_block(neo4j, "environment"),
        {
            "NEO4J_AUTH": "${NEO4J_USER}/${NEO4J_PASSWORD}",
            "NEO4J_server_memory_pagecache_size": "128M",
            "NEO4J_server_memory_heap_initial__size": "256M",
            "NEO4J_server_memory_heap_max__size": "512M",
        },
    )
    _assert_exact_environment(
        _mapping_block(backend, "environment"),
        {
            key: f"${{{key}}}"
            for key in (
                "DATABASE_URL",
                "REDIS_URL",
                "SECRET_KEY",
                "ACCESS_TOKEN_EXPIRE_MINUTES",
                "REFRESH_TOKEN_EXPIRE_DAYS",
                "ALGORITHM",
                "NEO4J_URI",
                "NEO4J_USER",
                "NEO4J_PASSWORD",
                "NEO4J_DATABASE",
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
            )
        },
    )
    _assert_exact_environment(
        _mapping_block(graph_worker, "environment"),
        {
            key: f"${{{key}}}"
            for key in (
                "DATABASE_URL",
                "SECRET_KEY",
                "NEO4J_URI",
                "NEO4J_USER",
                "NEO4J_PASSWORD",
                "NEO4J_DATABASE",
                "GRAPH_REPOSITORY",
                "TENANT_MODE",
                "E2E_MODE",
            )
        },
    )
    _assert_exact_environment(
        _mapping_block(web, "environment"),
        {
            "SITE_ADDRESS": "${SITE_ADDRESS}",
            "TAILSCALE_IP": "${TAILSCALE_IP}",
        },
    )
    assert _depends_on_conditions(backend) == {
        "db": "service_healthy",
        "redis": "service_healthy",
        "neo4j": "service_healthy",
    }
    assert _depends_on_conditions(graph_worker) == {
        "db": "service_healthy",
        "neo4j": "service_healthy",
    }
    assert _depends_on_conditions(web) == {"backend": "service_healthy"}

    assert "$$REDIS_PASSWORD" in redis
    assert "REDISCLI_AUTH=" in redis
    assert "redis-cli -a" not in redis
    assert "redis-cli -p" not in redis
    assert "redis-server --requirepass" not in redis
    assert "mktemp /tmp/openqms-redis." in redis
    assert "chmod 600" in redis
    assert 'exec redis-server "$$config"' in redis
    assert "$$POSTGRES_USER" in _service_block(compose, "db")
    assert "$$POSTGRES_DB" in _service_block(compose, "db")
    assert "NEO4J_USERNAME=" in neo4j
    assert "NEO4J_PASSWORD=" in neo4j
    assert "$${NEO4J_AUTH%%/*}" in neo4j
    assert "$${NEO4J_AUTH#*/}" in neo4j
    assert "cypher-shell -p" not in neo4j
    assert "cypher-shell --password" not in neo4j
    assert "http://127.0.0.1:8000/api/health" in _service_block(compose, "backend")
    assert "http://127.0.0.1:8080/api/health" in web
    assert 'test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://127.0.0.1:8080/api/health"]' in web
    assert "python" in _service_block(compose, "graph-worker")
    assert "app.services.graph_sync_worker" in _service_block(compose, "graph-worker")

    for service, address in EXPECTED_IPS.items():
        block = _service_block(compose, service)
        assert f"ipv4_address: {address}" in block
        assert "restart: unless-stopped" in block
        assert "driver: json-file" in block
        assert 'max-size: "10m"' in block
        assert 'max-file: "3"' in block


def test_backend_dockerignore_contract():
    assert (ROOT / "backend" / ".dockerignore").read_text().splitlines() == [
        ".venv",
        ".venv312",
        "venv",
        "__pycache__",
        ".pytest_cache",
        "tests",
        "*.pyc",
        "*.log",
        ".env*",
    ]


def test_production_env_example_and_gitignore_contract():
    counts, values = _dotenv(ENV_EXAMPLE_PATH)

    assert set(counts) == REQUIRED_ENV_KEYS
    assert all(counts[key] == 1 for key in REQUIRED_ENV_KEYS)
    for key in ("POSTGRES_PASSWORD", "REDIS_PASSWORD", "NEO4J_PASSWORD", "SECRET_KEY"):
        assert values[key] == "REQUIRED_GENERATED_ON_SERVER"
    assert values["DATABASE_URL"] == (
        "postgresql+asyncpg://qms:REQUIRED_GENERATED_ON_SERVER@db:5432/qms"
    )
    assert values["REDIS_URL"] == (
        "redis://:REQUIRED_GENERATED_ON_SERVER@redis:6379/0"
    )
    assert values["TENANT_MODE"] == "single"
    assert values["E2E_MODE"] == "false"
    assert values["LLM_PROVIDER"] == ""
    assert values["EMBEDDING_PROVIDER"] == ""
    assert values["VITE_PUBLIC_DEMO_ENABLED"] == "true"
    assert values["VITE_PUBLIC_DEMO_USERNAME"] == "viewer"
    assert values["VITE_PUBLIC_DEMO_PASSWORD"] == "Viewer@2026"
    assert values["VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS"] == ""
    assert "qms_dev_2026" not in ENV_EXAMPLE_PATH.read_text()

    gitignore = (ROOT / ".gitignore").read_text().splitlines()
    env_pattern = gitignore.index(".env.*")
    assert gitignore[env_pattern + 1 : env_pattern + 4] == [
        "!.env.example",
        "!.env.production.example",
        "backups/",
    ]


@pytest.mark.skipif(not _compose_cli_available(), reason="Docker Compose CLI unavailable")
def test_production_compose_quiet_validation_prints_no_resolved_values(tmp_path):
    repo, _values = _temporary_render_repo(tmp_path)
    result = subprocess.run(
        [str(repo / "scripts" / PRODUCTION_COMPOSE_SCRIPT.name), "config", "--quiet"],
        cwd=tmp_path,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, "quiet Compose validation failed"
    assert result.stdout == ""
    assert result.stderr == ""


@pytest.mark.skipif(not _compose_cli_available(), reason="Docker Compose CLI unavailable")
def test_rendered_production_compose_contract(tmp_path):
    rendered, render_root, example = _render_compose(tmp_path)
    services = rendered["services"]

    assert rendered["name"] == "openqms"
    assert set(services) == EXPECTED_SERVICES
    assert set(rendered["volumes"]) == {
        "pgdata_prod",
        "neo4j_data_prod",
        "caddy_data",
        "caddy_config",
    }
    assert rendered["networks"]["openqms_internal"]["ipam"]["config"] == [
        {"subnet": "172.30.0.0/24"}
    ]

    assert services["backend"]["command"] == [
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--proxy-headers",
        "--forwarded-allow-ips=172.30.0.10",
    ]
    assert services["graph-worker"]["command"] == [
        "python",
        "-m",
        "app.services.graph_sync_worker",
    ]
    assert services["backend"]["image"] == services["graph-worker"]["image"]
    assert "build" not in services["graph-worker"]
    assert "PIP_INDEX_URL" not in services["graph-worker"]
    assert services["backend"]["build"]["args"] == {
        "RELEASE_SHA": RELEASE_SHA,
        "PIP_INDEX_URL": "https://pypi.org/simple",
    }
    assert Path(services["backend"]["build"]["context"]) == render_root / "backend"
    assert Path(services["web"]["build"]["context"]) == render_root
    assert services["web"]["build"]["dockerfile"] == "frontend/Dockerfile.prod"
    assert services["web"]["build"]["args"] == {
        "RELEASE_SHA": RELEASE_SHA,
        "VITE_PUBLIC_DEMO_ENABLED": "true",
        "VITE_PUBLIC_DEMO_PASSWORD": "Viewer@2026",
        "VITE_PUBLIC_DEMO_USERNAME": "viewer",
        "VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS": "",
    }
    assert services["web"]["environment"] == {
        "SITE_ADDRESS": "qms.example.test",
        "TAILSCALE_IP": "100.64.0.10",
    }

    _assert_exact_environment(
        services["db"]["environment"],
        {
            "POSTGRES_USER": example["POSTGRES_USER"],
            "POSTGRES_PASSWORD": example["POSTGRES_PASSWORD"],
            "POSTGRES_DB": example["POSTGRES_DB"],
        },
    )
    _assert_exact_environment(
        services["redis"]["environment"],
        {"REDIS_PASSWORD": example["REDIS_PASSWORD"]},
    )
    _assert_exact_environment(
        services["neo4j"]["environment"],
        {
            "NEO4J_AUTH": f"{example['NEO4J_USER']}/{example['NEO4J_PASSWORD']}",
            "NEO4J_server_memory_pagecache_size": "128M",
            "NEO4J_server_memory_heap_initial__size": "256M",
            "NEO4J_server_memory_heap_max__size": "512M",
        },
    )
    backend_environment_keys = (
        "DATABASE_URL",
        "REDIS_URL",
        "SECRET_KEY",
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "REFRESH_TOKEN_EXPIRE_DAYS",
        "ALGORITHM",
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "NEO4J_DATABASE",
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
    )
    _assert_exact_environment(
        services["backend"]["environment"],
        {key: example[key] for key in backend_environment_keys},
    )
    worker_environment_keys = (
        "DATABASE_URL",
        "SECRET_KEY",
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "NEO4J_DATABASE",
        "GRAPH_REPOSITORY",
        "TENANT_MODE",
        "E2E_MODE",
    )
    _assert_exact_environment(
        services["graph-worker"]["environment"],
        {key: example[key] for key in worker_environment_keys},
    )
    assert services["backend"]["environment"]["E2E_MODE"] == "false"
    assert services["backend"]["environment"]["TENANT_MODE"] == "single"
    assert services["backend"]["environment"]["ALGORITHM"] == "HS256"
    assert services["graph-worker"]["environment"]["E2E_MODE"] == "false"
    assert services["graph-worker"]["environment"]["TENANT_MODE"] == "single"
    _assert_healthy_dependencies(
        services["backend"]["depends_on"], {"db", "redis", "neo4j"}
    )
    _assert_healthy_dependencies(
        services["graph-worker"]["depends_on"], {"db", "neo4j"}
    )
    _assert_healthy_dependencies(services["web"]["depends_on"], {"backend"})

    expected_ports = {
        "db": [
            {
                "host_ip": "127.0.0.1",
                "mode": "ingress",
                "protocol": "tcp",
                "published": "5432",
                "target": 5432,
            }
        ],
        "web": [
            {"mode": "ingress", "protocol": "tcp", "published": "80", "target": 80},
            {"mode": "ingress", "protocol": "tcp", "published": "443", "target": 443},
        ],
    }
    assert services["db"]["ports"] == expected_ports["db"]
    assert services["web"]["ports"] == expected_ports["web"]
    for service in EXPECTED_SERVICES - {"db", "web"}:
        assert not services[service].get("ports")

    for service, address in EXPECTED_IPS.items():
        assert services[service]["networks"]["openqms_internal"]["ipv4_address"] == address
        assert services[service]["restart"] == "unless-stopped"
        assert services[service]["logging"] == {
            "driver": "json-file",
            "options": {"max-file": "3", "max-size": "10m"},
        }
        for mount in services[service].get("volumes", []):
            assert mount["type"] == "volume"

    for service in ("db", "redis", "neo4j", "backend", "web"):
        healthcheck = services[service]["healthcheck"]
        assert healthcheck["interval"]
        assert healthcheck["timeout"]
        assert healthcheck["retries"] > 0
        assert healthcheck["test"]
    redis_command = " ".join(services["redis"]["command"])
    assert "--requirepass" not in redis_command
    assert "REQUIRED_GENERATED_ON_SERVER" not in redis_command
    assert "mktemp /tmp/openqms-redis." in redis_command
    assert "chmod 600" in redis_command
    assert 'redis-server "$$config"' in redis_command

    redis_health = " ".join(services["redis"]["healthcheck"]["test"])
    assert "$REDIS_PASSWORD" in redis_health
    assert "REDISCLI_AUTH=" in redis_health
    assert "redis-cli -a" not in redis_health
    assert "redis-cli -p" not in redis_health
    assert "REQUIRED_GENERATED_ON_SERVER" not in redis_health
    assert "$POSTGRES_USER" in " ".join(services["db"]["healthcheck"]["test"])
    assert "$POSTGRES_DB" in " ".join(services["db"]["healthcheck"]["test"])

    neo4j_health = services["neo4j"]["healthcheck"]["test"]
    assert neo4j_health[0] == "CMD-SHELL"
    neo4j_health_command = " ".join(neo4j_health[1:])
    assert "NEO4J_USERNAME=" in neo4j_health_command
    assert "NEO4J_PASSWORD=" in neo4j_health_command
    assert "$${NEO4J_AUTH%%/*}" in neo4j_health_command
    assert "$${NEO4J_AUTH#*/}" in neo4j_health_command
    assert " -p " not in f" {neo4j_health_command} "
    assert "--password" not in neo4j_health_command
    assert "REQUIRED_GENERATED_ON_SERVER" not in neo4j_health_command

    assert "127.0.0.1:8000/api/health" in " ".join(
        services["backend"]["healthcheck"]["test"]
    )
    assert services["web"]["healthcheck"]["test"] == [
        "CMD",
        "wget",
        "--no-verbose",
        "--tries=1",
        "--spider",
        "http://127.0.0.1:8080/api/health",
    ]


@pytest.mark.skipif(not _compose_cli_available(), reason="Docker Compose CLI unavailable")
def test_rendered_web_build_uses_optional_public_accounts_from_file(tmp_path):
    repo, _values = _temporary_render_repo(tmp_path)
    accounts = json.dumps([
        {"username": "admin", "password": "public-admin-sentinel"},
        {"username": "engineer", "password": "public-engineer-sentinel"},
        {"username": "manager", "password": "public-manager-sentinel"},
        {"username": "groupadmin", "password": "public-groupadmin-sentinel"},
    ], separators=(",", ":"))
    env_file = repo / ".env.production"
    source = env_file.read_text()
    marker = "VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS=\n"
    assert source.count(marker) == 1
    env_file.write_text(source.replace(marker, f"VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS={accounts}\n"))

    result = subprocess.run(
        [str(repo / "scripts" / PRODUCTION_COMPOSE_SCRIPT.name), "config", "--format", "json"],
        cwd=tmp_path,
        env={**os.environ, "VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS": "ambient-stale-value"},
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, "optional demo Compose render failed"
    rendered = json.loads(result.stdout)
    assert rendered["services"]["web"]["build"]["args"]["VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS"] == accounts


@pytest.mark.skipif(not _compose_cli_available(), reason="Docker Compose CLI unavailable")
def test_rendered_compose_ignores_ambient_test_credentials(tmp_path, monkeypatch):
    ambient_database_url = "postgresql+asyncpg://test:test@localhost:5432/qms_test"
    ambient_secret = "ambient-test-secret"
    monkeypatch.setenv("DATABASE_URL", ambient_database_url)
    monkeypatch.setenv("SECRET_KEY", ambient_secret)
    monkeypatch.setenv("POSTGRES_PASSWORD", ambient_secret)
    monkeypatch.setenv("REDIS_PASSWORD", ambient_secret)
    monkeypatch.setenv("NEO4J_PASSWORD", ambient_secret)
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "attacker-project")
    monkeypatch.setenv("COMPOSE_FILE", "/tmp/attacker-compose.yml")
    monkeypatch.setenv("COMPOSE_ENV_FILES", "/tmp/attacker.env")
    monkeypatch.setenv("OPENQMS_ENV_FILE", "/tmp/attacker-production.env")

    rendered, _render_root, example = _render_compose(tmp_path)
    services = rendered["services"]

    assert rendered["name"] == "openqms"
    assert services["backend"]["environment"]["DATABASE_URL"] == example["DATABASE_URL"]
    assert services["graph-worker"]["environment"]["DATABASE_URL"] == example["DATABASE_URL"]
    assert services["backend"]["environment"]["SECRET_KEY"] == example["SECRET_KEY"]
    assert services["graph-worker"]["environment"]["SECRET_KEY"] == example["SECRET_KEY"]
    assert services["db"]["environment"]["POSTGRES_PASSWORD"] == example["POSTGRES_PASSWORD"]
    rendered_environments = json.dumps(
        {name: service.get("environment", {}) for name, service in services.items()}
    )
    assert ambient_database_url not in rendered_environments
    assert ambient_secret not in rendered_environments

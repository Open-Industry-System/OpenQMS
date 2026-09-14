import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


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


def test_production_compose_and_caddy_trusted_proxy_contract():
    compose = (ROOT / "docker-compose.prod.yml").read_text()
    caddy = (ROOT / "deploy" / "Caddyfile").read_text()

    web = _service_block(compose, "web")
    backend = _service_block(compose, "backend")
    db = _service_block(compose, "db")

    assert "172.30.0.10" in compose
    assert re.search(r"(?m)^\s*ipv4_address:\s*172\.30\.0\.10\s*$", web)
    assert "--proxy-headers" in backend
    forwarded_allow_ips = re.findall(
        r"--forwarded-allow-ips=([^\s'\"\],]+)", backend
    )
    assert forwarded_allow_ips == ["172.30.0.10"]
    assert "--forwarded-allow-ips=*" not in backend

    assert _short_ports("db", db) == ["127.0.0.1:5432:5432"]
    assert "published:" not in db
    for service in ("redis", "neo4j", "backend", "graph-worker"):
        assert "ports:" not in _service_block(compose, service)
    assert "ollama" not in compose.lower()
    assert "trusted_proxies" not in caddy

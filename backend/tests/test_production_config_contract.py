from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_production_compose_and_caddy_trusted_proxy_contract():
    compose = (ROOT / "docker-compose.prod.yml").read_text()
    caddy = (ROOT / "deploy" / "Caddyfile").read_text()

    assert "172.30.0.10" in compose
    assert "--proxy-headers" in compose
    assert "--forwarded-allow-ips=172.30.0.10" in compose
    assert "--forwarded-allow-ips=*" not in compose
    assert '"127.0.0.1:5432:5432"' in compose
    for forbidden in ("6379:6379", "7474:7474", "7687:7687", "8000:8000", "11434"):
        assert forbidden not in compose
    assert "trusted_proxies" not in caddy

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-proxy-rate-limit.sh"


def test_proxy_rate_limit_script_has_required_safety_contract():
    script = SCRIPT.read_text()

    assert "#!/usr/bin/env bash" in script
    assert "set -euo pipefail" in script
    for required in ("COMPOSE_FILE", "SITE_HOST", "LOGIN_PASSWORD"):
        assert f"${{{required}:-}}" in script
    assert 'docker compose -f "$COMPOSE_FILE" ps -q backend' in script
    assert "docker inspect" in script
    assert 'docker compose -f "$COMPOSE_FILE" restart backend' in script
    assert 'curlimages/curl' in script
    assert '--entrypoint /bin/sh' in script
    assert '"$CURL_IMAGE" -eu -c' in script
    assert '"$CURL_IMAGE" /bin/sh -eu -c' not in script
    assert '--resolve "$SITE_HOST:443:172.30.0.10"' in script
    assert '-e LOGIN_PASSWORD' in script
    assert 'LOGIN_PASSWORD=' not in script
    assert 'echo "$LOGIN_PASSWORD"' not in script


def test_proxy_rate_limit_script_covers_both_fixed_probe_scenarios():
    script = SCRIPT.read_text()

    assert "172.30.0.101" in script
    assert "172.30.0.102" in script
    assert "X-Forwarded-For" in script
    assert "429" in script

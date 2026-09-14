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
    assert 'SITE_SCHEME="${SITE_SCHEME:-http}"' in script
    assert 'case "$SITE_SCHEME" in' in script
    assert "SITE_PORT=80" in script
    assert "SITE_PORT=443" in script
    assert '--resolve "$SITE_HOST:$SITE_PORT:172.30.0.10"' in script
    assert '"${SITE_SCHEME}://${SITE_HOST}' in script
    assert '-e LOGIN_PASSWORD' not in script
    assert "${LOGIN_PASSWORD}" not in script
    assert "__rate_limit_probe_password__" in script
    health_probe = script.split("health_is_ready()", 1)[1].split("wait_for_ready()", 1)[0]
    login_probe = script.split("login_status()", 1)[1].split("expect_status()", 1)[0]
    assert "--connect-timeout" in health_probe
    assert "--max-time" in health_probe
    assert "--connect-timeout" in login_probe
    assert "--max-time" in login_probe
    assert "export SITE_SCHEME SITE_PORT CURL_CONNECT_TIMEOUT CURL_MAX_TIME" in script
    assert 'LOGIN_PASSWORD=' not in script
    assert 'echo "$LOGIN_PASSWORD"' not in script


def test_proxy_rate_limit_script_covers_both_fixed_probe_scenarios():
    script = SCRIPT.read_text()

    assert "172.30.0.101" in script
    assert "172.30.0.102" in script
    assert "X-Forwarded-For" in script
    assert "expect_not_rate_limited" not in script
    assert script.count('expect_status 401 "$PROBE_ONE_IP"\n') == 2
    assert 'expect_status 401 "$PROBE_TWO_IP"' in script
    assert 'expect_status 401 "$PROBE_ONE_IP" "203.0.113.200"' in script
    assert script.count('expect_status 429 "$PROBE_ONE_IP"') == 2

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-proxy-rate-limit.sh"
PRODUCTION_NETWORK_ASSIGNMENT = 'PRODUCTION_NETWORK="${backend_networks[0]}"'
EXPECTED_EXECUTION_TAIL = [
    "wait_for_ready",
    'echo "check-proxy-rate-limit: scenario 1 — independent client quotas"',
    "for _ in $(seq 1 10); do",
    'expect_status 401 "$PROBE_ONE_IP"',
    "done",
    'expect_status 429 "$PROBE_ONE_IP"',
    'expect_status 401 "$PROBE_TWO_IP"',
    'echo "check-proxy-rate-limit: restarting backend before forged-header scenario"',
    'docker compose -f "$COMPOSE_FILE" restart backend',
    "wait_for_ready",
    'echo "check-proxy-rate-limit: scenario 2 — forged X-Forwarded-For shares probe bucket"',
    "for _ in $(seq 1 9); do",
    'expect_status 401 "$PROBE_ONE_IP"',
    "done",
    'expect_status 401 "$PROBE_ONE_IP" "203.0.113.200"',
    'expect_status 429 "$PROBE_ONE_IP"',
    'echo "check-proxy-rate-limit: passed"',
]


def _assert_execution_tail_contract(script: str) -> None:
    assert script.count(PRODUCTION_NETWORK_ASSIGNMENT) == 1
    tail = script.split(PRODUCTION_NETWORK_ASSIGNMENT, 1)[1]
    executable_lines = [line.strip() for line in tail.splitlines() if line.strip()]
    assert executable_lines == EXPECTED_EXECUTION_TAIL


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
    _assert_execution_tail_contract(script)


def test_execution_tail_contract_rejects_extra_commands():
    script = SCRIPT.read_text()
    mutations = [
        (
            "quota request before scenario 1 banner",
            '''PRODUCTION_NETWORK="${backend_networks[0]}"

wait_for_ready

echo "check-proxy-rate-limit: scenario 1 — independent client quotas"''',
            '''PRODUCTION_NETWORK="${backend_networks[0]}"

wait_for_ready
expect_status 401 "$PROBE_ONE_IP"

echo "check-proxy-rate-limit: scenario 1 — independent client quotas"''',
        ),
        (
            "quota request before scenario 2 banner",
            '''docker compose -f "$COMPOSE_FILE" restart backend
wait_for_ready

echo "check-proxy-rate-limit: scenario 2 — forged X-Forwarded-For shares probe bucket"''',
            '''docker compose -f "$COMPOSE_FILE" restart backend
wait_for_ready
expect_status 401 "$PROBE_ONE_IP"

echo "check-proxy-rate-limit: scenario 2 — forged X-Forwarded-For shares probe bucket"''',
        ),
        (
            "quota request before scenario 1 loop",
            '''echo "check-proxy-rate-limit: scenario 1 — independent client quotas"
for _ in $(seq 1 10); do''',
            '''echo "check-proxy-rate-limit: scenario 1 — independent client quotas"
expect_status 401 "$PROBE_ONE_IP"
for _ in $(seq 1 10); do''',
        ),
        (
            "quota request before scenario 2 loop",
            '''echo "check-proxy-rate-limit: scenario 2 — forged X-Forwarded-For shares probe bucket"
for _ in $(seq 1 9); do''',
            '''echo "check-proxy-rate-limit: scenario 2 — forged X-Forwarded-For shares probe bucket"
expect_status 401 "$PROBE_ONE_IP"
for _ in $(seq 1 9); do''',
        ),
        (
            "quota request in scenario 1 loop body",
            '''for _ in $(seq 1 10); do
    expect_status 401 "$PROBE_ONE_IP"
done''',
            '''for _ in $(seq 1 10); do
    expect_status 401 "$PROBE_ONE_IP"
    expect_status 401 '$PROBE_ONE_IP'
done''',
        ),
        (
            "quota request in scenario 2 loop body",
            '''for _ in $(seq 1 9); do
    expect_status 401 "$PROBE_ONE_IP"
done''',
            '''for _ in $(seq 1 9); do
    expect_status 401 "$PROBE_ONE_IP"
    expect_status 401 '$PROBE_ONE_IP'
done''',
        ),
        (
            "quota request after scenario 1 loop",
            '''done
expect_status 429 "$PROBE_ONE_IP"
expect_status 401 "$PROBE_TWO_IP"''',
            '''done
expect_status 401 '$PROBE_ONE_IP'
expect_status 429 "$PROBE_ONE_IP"
expect_status 401 "$PROBE_TWO_IP"''',
        ),
        (
            "direct quota request after scenario 2 assertions",
            '''expect_status 429 "$PROBE_ONE_IP"

echo "check-proxy-rate-limit: passed"''',
            '''expect_status 429 "$PROBE_ONE_IP"
login_status "$PROBE_ONE_IP"

echo "check-proxy-rate-limit: passed"''',
        ),
    ]

    for label, original, replacement in mutations:
        mutated = script.replace(original, replacement, 1)
        assert mutated != script, f"failed to apply mutation: {label}"
        try:
            _assert_execution_tail_contract(mutated)
        except AssertionError:
            continue
        raise AssertionError(f"execution tail accepted {label}")

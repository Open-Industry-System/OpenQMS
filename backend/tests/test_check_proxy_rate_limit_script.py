import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-proxy-rate-limit.sh"


def _loop_body_and_post(scenario: str, limit: int) -> tuple[list[str], list[str]]:
    match = re.fullmatch(
        rf"(?ms)\A[ \t\r\n]*for _ in \$\(seq 1 {limit}\); do\n(?P<body>.*?)^[ \t]*done\n(?P<post>.*)\Z",
        scenario,
    )
    assert match, f"missing exact seq 1 {limit} loop"
    body = [line.strip() for line in match.group("body").splitlines() if line.strip()]
    post = [line.strip() for line in match.group("post").splitlines() if line.strip()]
    return body, post


def _assert_loop_contract(scenario: str, limit: int, post_commands: list[str]) -> None:
    body, post = _loop_body_and_post(scenario, limit)
    assert body == ['expect_status 401 "$PROBE_ONE_IP"']
    assert post == post_commands


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
    scenario_one = script.split(
        'echo "check-proxy-rate-limit: scenario 1 — independent client quotas"\n', 1
    )[1].split(
        'echo "check-proxy-rate-limit: restarting backend before forged-header scenario"\n',
        1,
    )[0]
    scenario_two = script.split(
        'echo "check-proxy-rate-limit: scenario 2 — forged X-Forwarded-For shares probe bucket"\n',
        1,
    )[1]
    _assert_loop_contract(
        scenario_one,
        10,
        [
            'expect_status 429 "$PROBE_ONE_IP"',
            'expect_status 401 "$PROBE_TWO_IP"',
        ],
    )
    _assert_loop_contract(
        scenario_two,
        9,
        [
            'expect_status 401 "$PROBE_ONE_IP" "203.0.113.200"',
            'expect_status 429 "$PROBE_ONE_IP"',
            'echo "check-proxy-rate-limit: passed"',
        ],
    )


def test_loop_contract_rejects_extra_quota_request():
    scenario = '''
for _ in $(seq 1 10); do
    expect_status 401 "$PROBE_ONE_IP"
    expect_status 401 '$PROBE_ONE_IP'
done
expect_status 429 "$PROBE_ONE_IP"
expect_status 401 "$PROBE_TWO_IP"
'''

    try:
        _assert_loop_contract(
            scenario,
            10,
            [
                'expect_status 429 "$PROBE_ONE_IP"',
                'expect_status 401 "$PROBE_TWO_IP"',
            ],
        )
    except AssertionError:
        return
    raise AssertionError("extra quota request was accepted")


def test_loop_contract_rejects_extra_quota_request_before_scenario_loop():
    script = SCRIPT.read_text()
    cases = [
        (
            'echo "check-proxy-rate-limit: scenario 1 — independent client quotas"',
            'echo "check-proxy-rate-limit: restarting backend before forged-header scenario"',
            10,
            [
                'expect_status 429 "$PROBE_ONE_IP"',
                'expect_status 401 "$PROBE_TWO_IP"',
            ],
        ),
        (
            'echo "check-proxy-rate-limit: scenario 2 — forged X-Forwarded-For shares probe bucket"',
            None,
            9,
            [
                'expect_status 401 "$PROBE_ONE_IP" "203.0.113.200"',
                'expect_status 429 "$PROBE_ONE_IP"',
                'echo "check-proxy-rate-limit: passed"',
            ],
        ),
    ]

    for banner, next_banner, limit, post_commands in cases:
        loop = f"for _ in $(seq 1 {limit}); do"
        mutated = script.replace(
            f"{banner}\n{loop}",
            f'{banner}\nexpect_status 401 "$PROBE_ONE_IP"\n{loop}',
            1,
        )
        assert mutated != script, f"failed to mutate scenario {limit}"
        scenario = mutated.split(f"{banner}\n", 1)[1]
        if next_banner is not None:
            scenario = scenario.split(f"{next_banner}\n", 1)[0]

        try:
            _assert_loop_contract(scenario, limit, post_commands)
        except AssertionError:
            continue
        raise AssertionError(f"pre-loop quota request was accepted for scenario {limit}")

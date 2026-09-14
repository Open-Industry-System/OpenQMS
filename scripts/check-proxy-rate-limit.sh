#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${COMPOSE_FILE:-}" ]]; then
    echo "check-proxy-rate-limit: COMPOSE_FILE is required" >&2
    exit 2
fi

if ! SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P); then
    echo "check-proxy-rate-limit: repository root resolution failed" >&2
    exit 2
fi
REPO_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd -P)
EXPECTED_COMPOSE_FILE="$REPO_ROOT/docker-compose.prod.yml"
if ! COMPOSE_FILE_DIR=$(cd -- "$(dirname -- "$COMPOSE_FILE")" 2>/dev/null && pwd -P); then
    echo "check-proxy-rate-limit: COMPOSE_FILE must name repository docker-compose.prod.yml" >&2
    exit 2
fi
COMPOSE_FILE_RESOLVED="$COMPOSE_FILE_DIR/$(basename -- "$COMPOSE_FILE")"
if [[ "$COMPOSE_FILE_RESOLVED" != "$EXPECTED_COMPOSE_FILE" ]]; then
    echo "check-proxy-rate-limit: COMPOSE_FILE must name repository docker-compose.prod.yml" >&2
    exit 2
fi
PRODUCTION_COMPOSE_WRAPPER="$REPO_ROOT/scripts/production-compose.sh"

if [[ -z "${SITE_HOST:-}" ]]; then
    echo "check-proxy-rate-limit: SITE_HOST is required" >&2
    exit 2
fi
if [[ -z "${LOGIN_PASSWORD:-}" ]]; then
    echo "check-proxy-rate-limit: LOGIN_PASSWORD is required" >&2
    exit 2
fi

SITE_SCHEME="${SITE_SCHEME:-http}"
case "$SITE_SCHEME" in
    http)
        SITE_PORT=80
        ;;
    https)
        SITE_PORT=443
        ;;
    *)
        echo "check-proxy-rate-limit: SITE_SCHEME must be http or https" >&2
        exit 2
        ;;
esac

CURL_IMAGE="curlimages/curl:8.11.1"
CURL_CONNECT_TIMEOUT=5
CURL_MAX_TIME=10
PROBE_ONE_IP="172.30.0.101"
PROBE_TWO_IP="172.30.0.102"
export SITE_SCHEME SITE_PORT CURL_CONNECT_TIMEOUT CURL_MAX_TIME

backend_container() {
    "$PRODUCTION_COMPOSE_WRAPPER" ps -q backend
}

wait_for() {
    local description="$1"
    shift
    local deadline=$((SECONDS + 60))

    until "$@"; do
        if (( SECONDS >= deadline )); then
            echo "check-proxy-rate-limit: timed out waiting for ${description}" >&2
            exit 1
        fi
        sleep 1
    done
}

backend_is_running() {
    [[ "$(docker inspect -f '{{.State.Running}}' "$BACKEND_CONTAINER")" == "true" ]]
}

web_is_running() {
    [[ "$(docker inspect -f '{{.State.Running}}' "$WEB_CONTAINER")" == "true" ]]
}

health_is_ready() {
    docker run --rm --entrypoint /bin/sh --network "$PRODUCTION_NETWORK" --ip "$PROBE_TWO_IP" \
        -e SITE_HOST -e SITE_SCHEME -e SITE_PORT -e CURL_CONNECT_TIMEOUT -e CURL_MAX_TIME \
        "$CURL_IMAGE" -eu -c '
            curl --fail --silent --show-error --output /dev/null \
                --connect-timeout "$CURL_CONNECT_TIMEOUT" \
                --max-time "$CURL_MAX_TIME" \
                --resolve "$SITE_HOST:$SITE_PORT:172.30.0.10" \
                "${SITE_SCHEME}://${SITE_HOST}/api/health"
        '
}

wait_for_ready() {
    BACKEND_CONTAINER="$(backend_container)"
    WEB_CONTAINER="$("$PRODUCTION_COMPOSE_WRAPPER" ps -q web)"
    if [[ -z "$BACKEND_CONTAINER" || -z "$WEB_CONTAINER" ]]; then
        echo "check-proxy-rate-limit: backend and web containers must exist" >&2
        exit 1
    fi

    wait_for "backend container" backend_is_running
    wait_for "web container" web_is_running
    wait_for "Caddy health endpoint" health_is_ready
}

login_status() {
    local client_ip="$1"
    local forged_xff="${2:-}"

    FORGED_XFF="$forged_xff" docker run --rm --entrypoint /bin/sh --network "$PRODUCTION_NETWORK" --ip "$client_ip" \
        -e SITE_HOST -e SITE_SCHEME -e SITE_PORT -e CURL_CONNECT_TIMEOUT -e CURL_MAX_TIME -e FORGED_XFF "$CURL_IMAGE" -eu -c '
            if [ -n "${FORGED_XFF:-}" ]; then
                curl --silent --show-error --output /dev/null --write-out "%{http_code}" \
                    --connect-timeout "$CURL_CONNECT_TIMEOUT" \
                    --max-time "$CURL_MAX_TIME" \
                    --request POST \
                    --resolve "$SITE_HOST:$SITE_PORT:172.30.0.10" \
                    --header "Content-Type: application/json" \
                    --header "X-Forwarded-For: ${FORGED_XFF}" \
                    --data "{\"username\":\"__proxy_rate_limit_probe__\",\"password\":\"__rate_limit_probe_password__\"}" \
                    "${SITE_SCHEME}://${SITE_HOST}/api/auth/login"
            else
                curl --silent --show-error --output /dev/null --write-out "%{http_code}" \
                    --connect-timeout "$CURL_CONNECT_TIMEOUT" \
                    --max-time "$CURL_MAX_TIME" \
                    --request POST \
                    --resolve "$SITE_HOST:$SITE_PORT:172.30.0.10" \
                    --header "Content-Type: application/json" \
                    --data "{\"username\":\"__proxy_rate_limit_probe__\",\"password\":\"__rate_limit_probe_password__\"}" \
                    "${SITE_SCHEME}://${SITE_HOST}/api/auth/login"
            fi
        '
}

expect_status() {
    local expected="$1"
    shift
    local actual
    actual="$(login_status "$@")"
    if [[ "$actual" != "$expected" ]]; then
        echo "check-proxy-rate-limit: expected HTTP ${expected}, got ${actual}" >&2
        exit 1
    fi
}

BACKEND_CONTAINER="$(backend_container)"
if [[ -z "$BACKEND_CONTAINER" ]]; then
    echo "check-proxy-rate-limit: backend container must exist" >&2
    exit 1
fi

mapfile -t backend_networks < <(
    docker inspect -f '{{range $name, $network := .NetworkSettings.Networks}}{{println $name}}{{end}}' \
        "$BACKEND_CONTAINER"
)
if [[ "${#backend_networks[@]}" -ne 1 ]]; then
    echo "check-proxy-rate-limit: backend must be attached to exactly one production network" >&2
    exit 1
fi
PRODUCTION_NETWORK="${backend_networks[0]}"

wait_for_ready

echo "check-proxy-rate-limit: scenario 1 — independent client quotas"
for _ in $(seq 1 10); do
    expect_status 401 "$PROBE_ONE_IP"
done
expect_status 429 "$PROBE_ONE_IP"
expect_status 401 "$PROBE_TWO_IP"

echo "check-proxy-rate-limit: restarting backend before forged-header scenario"
"$PRODUCTION_COMPOSE_WRAPPER" restart backend
wait_for_ready

echo "check-proxy-rate-limit: scenario 2 — forged X-Forwarded-For shares probe bucket"
for _ in $(seq 1 9); do
    expect_status 401 "$PROBE_ONE_IP"
done
expect_status 401 "$PROBE_ONE_IP" "203.0.113.200"
expect_status 429 "$PROBE_ONE_IP"

echo "check-proxy-rate-limit: passed"

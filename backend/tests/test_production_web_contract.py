import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
DEPLOY = ROOT / "deploy"


def _dockerignore_patterns(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def _glob_matches(path: str, pattern: str, include_descendants: bool = False) -> bool:
    pattern = pattern.lstrip("/").rstrip("/")
    if not pattern:
        return False

    regex = ""
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*" and pattern[index : index + 2] == "**":
            if index + 2 < len(pattern) and pattern[index + 2] == "/":
                regex += "(?:.*/)?"
                index += 3
            else:
                regex += ".*"
                index += 2
        elif char == "*":
            regex += "[^/]*"
            index += 1
        elif char == "?":
            regex += "[^/]"
            index += 1
        else:
            regex += re.escape(char)
            index += 1

    if "/" not in pattern:
        if include_descendants:
            return any(re.fullmatch(regex, part) is not None for part in path.split("/"))
        return re.fullmatch(regex, path) is not None
    if re.fullmatch(regex, path) is not None:
        return True
    return include_descendants and path.startswith(f"{pattern}/")


def _included_in_docker_context(path: str, patterns: list[str]) -> bool:
    included = True
    for raw_pattern in patterns:
        negated = raw_pattern.startswith("!")
        pattern = raw_pattern[1:] if negated else raw_pattern
        if _glob_matches(path, pattern, include_descendants=not negated):
            included = negated
    return included


def test_frontend_context_ignore_excludes_generated_content_without_raw_order_dependence():
    patterns = _dockerignore_patterns((FRONTEND / ".dockerignore").read_text())

    for excluded_path in (
        "node_modules/esbuild/bin/esbuild",
        "dist/assets/app.js",
        "test-results/results.json",
        "e2e/.storage-state/viewer.json",
        "frontend.log",
    ):
        assert not _included_in_docker_context(excluded_path, patterns)


def test_root_context_allowlist_admits_only_required_production_build_inputs():
    patterns = _dockerignore_patterns((FRONTEND / "Dockerfile.prod.dockerignore").read_text())

    for required_path in (
        "frontend",
        "frontend/package.json",
        "frontend/package-lock.json",
        "frontend/index.html",
        "frontend/tsconfig.json",
        "frontend/tsconfig.node.json",
        "frontend/vite.config.ts",
        "frontend/src",
        "frontend/src/main.tsx",
        "frontend/src/App.test.tsx",
        "frontend/public",
        "frontend/public/logo.svg",
        "deploy",
        "deploy/Caddyfile",
    ):
        assert _included_in_docker_context(required_path, patterns)

    for excluded_path in (
        ".env.production",
        "frontend/.env.production.local",
        "backend/.env",
        ".git/config",
        ".claude/settings.json",
        ".superpowers/sdd/task-9-report.md",
        "backend/app/main.py",
        "docs/deploy.md",
        "scripts/release.sh",
        "frontend/node_modules/esbuild/bin/esbuild",
        "frontend/dist/assets/app.js",
        "frontend/tsconfig.tsbuildinfo",
        "frontend/test-results/results.json",
        "frontend/coverage/lcov.info",
        "frontend/playwright-report/index.html",
        "frontend/blob-report/report.zip",
        "frontend/e2e/smoke.spec.ts",
        "frontend/e2e/.storage-state/viewer.json",
        "frontend/debug.log",
        "deploy/private.key",
    ):
        assert not _included_in_docker_context(excluded_path, patterns)

    assert not _included_in_docker_context("frontend/package.json", [*patterns, "**"])
    assert _included_in_docker_context("frontend/package.json", [*patterns, "**", "!frontend/package.json"])


def test_production_dockerfile_keeps_disabled_demo_credentials_out_of_vite_and_final_stage_minimal():
    dockerfile = (FRONTEND / "Dockerfile.prod").read_text()

    assert "FROM node:20-alpine AS build" in dockerfile
    assert "RUN npm ci" in dockerfile
    assert "COPY frontend/package.json frontend/package-lock.json ./" in dockerfile
    assert "COPY frontend/ ./" in dockerfile
    assert "EXPOSE 80 443 8080" in dockerfile
    assert "ENV VITE_PUBLIC_DEMO_" not in dockerfile
    assert 'if [ "$VITE_PUBLIC_DEMO_ENABLED" = "true" ]' in dockerfile
    assert "VITE_PUBLIC_DEMO_USERNAME=$VITE_PUBLIC_DEMO_USERNAME" in dockerfile
    assert "VITE_PUBLIC_DEMO_PASSWORD=$VITE_PUBLIC_DEMO_PASSWORD" in dockerfile
    assert "VITE_PUBLIC_DEMO_ENABLED=false VITE_PUBLIC_DEMO_USERNAME= VITE_PUBLIC_DEMO_PASSWORD= npm run build" in dockerfile

    final_stage = dockerfile.split("FROM caddy:2-alpine", maxsplit=1)[1]
    assert re.findall(r"(?m)^COPY .+$", final_stage) == [
        "COPY deploy/Caddyfile /etc/caddy/Caddyfile",
        "COPY --from=build /app/dist /srv",
    ]


def test_caddy_serves_api_before_spa_fallback_on_all_required_listeners():
    caddyfile = (DEPLOY / "Caddyfile").read_text()

    assert "admin off" in caddyfile
    assert "(openqms_app)" in caddyfile
    assert "encode zstd gzip" in caddyfile
    assert re.search(r"handle /api/\* \{\s+reverse_proxy backend:8000\s+\}", caddyfile)
    assert "root * /srv" in caddyfile
    assert "try_files {path} /index.html" in caddyfile
    assert "file_server" in caddyfile
    assert "X-Content-Type-Options nosniff" in caddyfile
    assert "Referrer-Policy strict-origin-when-cross-origin" in caddyfile
    assert "X-Frame-Options SAMEORIGIN" in caddyfile
    assert re.search(r"\{\$SITE_ADDRESS\} \{\s+import openqms_app\s+\}", caddyfile)
    assert re.search(r"http://\{\$TAILSCALE_IP\} \{\s+import openqms_app\s+\}", caddyfile)
    assert re.search(r":8080 \{\s+import openqms_app\s+\}", caddyfile)
    assert "trusted_proxies" not in caddyfile

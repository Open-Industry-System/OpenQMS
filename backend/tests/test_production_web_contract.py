import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
DEPLOY = ROOT / "deploy"


def test_frontend_root_and_frontend_context_ignores_are_bounded():
    assert (FRONTEND / ".dockerignore").read_text().splitlines() == [
        "node_modules",
        "dist",
        "test-results",
        "e2e/.storage-state",
        "*.log",
    ]

    root_context_ignore = (FRONTEND / "Dockerfile.prod.dockerignore").read_text().splitlines()
    for excluded_path in (
        ".git",
        ".claude",
        ".superpowers",
        "backend",
        "docs",
        "scripts",
        "frontend/node_modules",
        "frontend/dist",
        "frontend/test-results",
        "frontend/e2e/.storage-state",
        "*.log",
        "deploy/*",
    ):
        assert excluded_path in root_context_ignore
    assert "!deploy/Caddyfile" in root_context_ignore


def test_production_dockerfile_keeps_disabled_demo_credentials_out_of_vite():
    dockerfile = (FRONTEND / "Dockerfile.prod").read_text()

    assert "FROM node:20-alpine AS build" in dockerfile
    assert "RUN npm ci" in dockerfile
    assert "COPY frontend/package.json frontend/package-lock.json ./" in dockerfile
    assert "COPY frontend/ ./" in dockerfile
    assert "FROM caddy:2-alpine" in dockerfile
    assert "COPY deploy/Caddyfile /etc/caddy/Caddyfile" in dockerfile
    assert "COPY --from=build /app/dist /srv" in dockerfile
    assert "EXPOSE 80 443 8080" in dockerfile
    assert "ENV VITE_PUBLIC_DEMO_" not in dockerfile
    assert 'if [ "$VITE_PUBLIC_DEMO_ENABLED" = "true" ]' in dockerfile
    assert "VITE_PUBLIC_DEMO_USERNAME=$VITE_PUBLIC_DEMO_USERNAME" in dockerfile
    assert "VITE_PUBLIC_DEMO_PASSWORD=$VITE_PUBLIC_DEMO_PASSWORD" in dockerfile
    assert "VITE_PUBLIC_DEMO_ENABLED=false VITE_PUBLIC_DEMO_USERNAME= VITE_PUBLIC_DEMO_PASSWORD= npm run build" in dockerfile


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

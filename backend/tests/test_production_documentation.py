import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
ZH_DEPLOYMENT = ROOT / "docs" / "deployment.md"
EN_DEPLOYMENT = ROOT / "docs" / "en" / "deployment.md"
USER_GUIDE = ROOT / "docs" / "user-guide.md"
EN_ARCHITECTURE = ROOT / "docs" / "en" / "architecture.md"
DECISIONS = ROOT / "docs" / "DECISIONS.md"
TARGET_DOCS = (
    README,
    ZH_DEPLOYMENT,
    EN_DEPLOYMENT,
    USER_GUIDE,
    EN_ARCHITECTURE,
    DECISIONS,
)


def _text(path: Path) -> str:
    return path.read_text()


def _section(path: Path, start_heading: str, end_heading: str | None) -> str:
    text = _text(path)
    start = text.index(start_heading)
    end = text.index(end_heading, start) if end_heading else len(text)
    return text[start:end]


def _bash_blocks(text: str) -> str:
    return "\n".join(re.findall(r"```bash\n(.*?)```", text, flags=re.DOTALL))


def _normalized(text: str) -> str:
    return re.sub(r"\\\n\s*", " ", text)


@pytest.mark.parametrize(
    ("path", "start_heading", "end_heading"),
    [
        (README, "## Oracle ARM64 生产部署", "## 模块支持状态"),
        (ZH_DEPLOYMENT, "## 1. Oracle ARM64 生产部署", "## 2. 本地开发环境"),
        (EN_DEPLOYMENT, "## 1. Oracle ARM64 Production Deployment", "## 2. Local Development Environment"),
    ],
)
def test_production_shell_blocks_use_only_authoritative_wrapper_and_scripts(
    path, start_heading, end_heading
):
    commands = _normalized(_bash_blocks(_section(path, start_heading, end_heading)))
    assert "docker compose" not in commands.lower()
    assert "--env-file .env.production" not in commands
    assert "-f docker-compose.prod.yml" not in commands
    assert "./scripts/init-production-env.sh" in commands
    assert "./scripts/production-compose.sh config" in commands
    assert "./scripts/production-compose.sh up -d db redis neo4j" in commands
    assert "./scripts/production-compose.sh ps" in commands
    assert "scripts/check-oracle-target-database.py" in commands
    assert "make deploy-release" in commands
    assert "INITIALIZE_CMD='./scripts/production-compose.sh run --rm backend python -m app.seed --no-print-credentials'" in commands
    assert "ROLLOUT_CMD='./scripts/production-compose.sh up -d --build backend graph-worker web'" in commands
    assert "./scripts/check-proxy-rate-limit.sh" in commands
    assert "./scripts/production-compose.sh logs" in commands
    assert "./scripts/production-compose.sh restart backend" in commands
    assert "/opt/openqms/scripts/backup-postgres.sh" in commands
    assert "./scripts/production-compose.sh exec -T db pg_restore --list" in commands


@pytest.mark.parametrize("path", (README, ZH_DEPLOYMENT, EN_DEPLOYMENT))
def test_production_docs_explain_wrapper_and_data_safe_rollback(path):
    text = _text(path)
    assert "openqms" in text
    assert "production-compose.sh" in text
    assert "ambient" in text.lower() or "环境覆盖" in text
    assert "down -v" not in text
    assert "qms.smartindustry.world" in text
    assert "DNS-only" in text
    assert "Tailscale" in text
    assert "ARM64" in text
    assert "Ollama" in text
    assert "120" in text


@pytest.mark.parametrize("path", (ZH_DEPLOYMENT, EN_DEPLOYMENT))
def test_bilingual_runbooks_cover_launch_security_and_restore_boundaries(path):
    text = _text(path)
    required_literals = (
        "172.30.0.10",
        "TENANT_MODE=single",
        "TEST_DATABASE_URL",
        "TARGET_IDENTITY_CMD",
        "INITIALIZE_CMD",
        "--no-print-credentials",
        "VITE_PUBLIC_DEMO_ENABLED=true",
        "VITE_PUBLIC_DEMO_USERNAME=viewer",
        "VITE_PUBLIC_DEMO_PASSWORD=Viewer@2026",
        "frontend/.env.local",
        "VITE_PUBLIC_DEMO_ENABLED=false",
        "VITE_PUBLIC_DEMO_USERNAME=",
        "VITE_PUBLIC_DEMO_PASSWORD=",
        "openqms-backup.timer",
        "RETENTION_DAYS=7",
        "pg_restore --list",
        "/login",
    )
    for literal in required_literals:
        assert literal in text
    assert re.search(r"(?:public|公开).{0,30}/", text, flags=re.IGNORECASE)
    assert re.search(r"(?:privileged|特权).{0,60}(?:rotate|轮换|password|密码)", text, flags=re.IGNORECASE)
    assert re.search(r"(?:SSH).{0,100}(?:HTTPS).{0,100}(?:private|私网|Tailscale)", text, flags=re.IGNORECASE | re.DOTALL)
    assert re.search(r"(?:restore|恢复).{0,200}(?:empty|空).{0,100}(?:database|数据库)", text, flags=re.IGNORECASE | re.DOTALL)


def test_docs_distinguish_compose_env_from_standalone_vite_public_values():
    for path in (README, ZH_DEPLOYMENT, EN_DEPLOYMENT):
        text = _text(path)
        assert ".env.production" in text
        assert "frontend/.env.local" in text
        assert "Viewer@2026" in text
        assert re.search(r"(?:browser-visible|浏览器可见|公开).{0,120}(?:Viewer|viewer)", text, flags=re.IGNORECASE | re.DOTALL)
        assert re.search(r"(?:never|不得|不能).{0,80}(?:privileged|特权).{0,40}(?:credential|凭据|账号)", text, flags=re.IGNORECASE | re.DOTALL)


def test_no_generated_secrets_or_private_key_material_are_documented():
    combined = "\n".join(_text(path) for path in TARGET_DOCS)
    assert "-----BEGIN " not in combined
    assert not re.search(r"(?:POSTGRES_PASSWORD|REDIS_PASSWORD|NEO4J_PASSWORD)=[0-9a-f]{48}(?:\s|$)", combined)
    assert not re.search(r"SECRET_KEY=[0-9a-f]{96}(?:\s|$)", combined)
    assert not re.search(r"(?:ssh-rsa|ssh-ed25519) [A-Za-z0-9+/]{40,}", combined)


def test_user_and_architecture_docs_describe_safe_automatic_refresh():
    user_guide = _text(USER_GUIDE)
    architecture = _text(EN_ARCHITECTURE)
    combined = user_guide + architecture
    assert "暂不支持自动刷新" not in user_guide
    assert "does not auto-refresh tokens" not in architecture
    assert "users must re-login after 120 minutes" not in architecture
    assert "120" in combined
    assert "refresh" in combined.lower()
    assert "rolling" in architecture.lower()
    assert "inactivity" in architecture.lower()
    assert "cross-tab" in architecture.lower()
    assert "identity" in architecture.lower()
    assert "/auth/me" in architecture
    assert "/" in user_guide
    assert "/login" in user_guide


def test_adr_0014_supersedes_legacy_refresh_decision_with_security_boundaries():
    decisions = _text(DECISIONS)
    adr_0005 = _section(DECISIONS, "## ADR-0005", "## ADR-0006")
    adr_0014 = _section(DECISIONS, "## ADR-0014", "## 何时写新 ADR")
    assert "Superseded by ADR-0014" in adr_0005
    for literal in (
        "sid",
        "jti",
        "SHA-256",
        "LoginAuditLog",
        "AuditLog",
        "120",
        "legacy",
    ):
        assert literal.lower() in adr_0014.lower()
    assert re.search(r"(?:row lock|行锁).{0,120}(?:replay|重放)", adr_0014, flags=re.IGNORECASE | re.DOTALL)
    assert re.search(r"(?:rolling|滚动).{0,80}(?:inactivity|不活跃)", adr_0014, flags=re.IGNORECASE | re.DOTALL)
    assert re.search(r"(?:password reset|密码重置).{0,160}(?:revoke|撤销).{0,160}(?:access|访问)", adr_0014, flags=re.IGNORECASE | re.DOTALL)
    assert decisions.index("## ADR-0014") > decisions.index("## ADR-0013")

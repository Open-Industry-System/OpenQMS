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
    assert "./scripts/production-compose.sh run --rm --no-deps backend python -m app.seed --no-print-credentials" in commands
    assert "./scripts/production-compose.sh up -d --wait backend graph-worker web" in commands
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


@pytest.mark.parametrize(
    ("path", "start_heading", "end_heading"),
    [
        (README, "## Oracle ARM64 生产部署", "## 模块支持状态"),
        (ZH_DEPLOYMENT, "## 1. Oracle ARM64 生产部署", "## 2. 本地开发环境"),
        (EN_DEPLOYMENT, "## 1. Oracle ARM64 Production Deployment", "## 2. Local Development Environment"),
    ],
)
def test_operator_host_release_uses_remote_wrapper_commands(
    path, start_heading, end_heading
):
    commands = _normalized(_bash_blocks(_section(path, start_heading, end_heading)))
    assert 'INITIALIZE_CMD=\'ssh -i "$ORACLE_SSH_KEY"' in commands
    assert 'ROLLOUT_CMD=\'ssh -i "$ORACLE_SSH_KEY"' in commands
    assert "./scripts/production-compose.sh run --rm --no-deps backend python -m app.seed --no-print-credentials" in commands
    assert "./scripts/production-compose.sh up -d --wait backend graph-worker web" in commands


def test_runbooks_provision_reachable_isolated_test_database_before_release():
    for path in (README, ZH_DEPLOYMENT, EN_DEPLOYMENT):
        text = _text(path)
        commands = _normalized(_bash_blocks(text))
        assert "-L 15432:127.0.0.1:5432" in commands
        assert "127.0.0.1:15432/qms" in commands
        assert 'export RELEASE_GATE_DB="qms_release_gate_$(date +%Y%m%d%H%M%S)"' in commands
        assert 'make check-test-db TEST_DB="$RELEASE_GATE_DB"' in commands
        assert "127.0.0.1:5432/${RELEASE_GATE_DB}" in commands
        assert "export TEST_DATABASE_URL=" in commands
        assert "127.0.0.1:5433" not in commands
        assert commands.index("make check-test-db") < commands.index("make deploy-release")


@pytest.mark.parametrize("path", (README, ZH_DEPLOYMENT, EN_DEPLOYMENT))
def test_pre_public_proxy_probe_uses_tailscale_http_site_explicitly(path):
    commands = _normalized(_bash_blocks(_text(path)))
    assert "SITE_HOST=100.84.141.70" in commands
    assert "SITE_SCHEME=http" in commands
    assert commands.index("SITE_SCHEME=http") < commands.index("./scripts/check-proxy-rate-limit.sh")


@pytest.mark.parametrize("path", (README, ZH_DEPLOYMENT, EN_DEPLOYMENT))
def test_rollback_rebuild_does_not_stop_recovered_stack(path):
    text = _text(path)
    checkout_index = text.index("git checkout '<previous-release-tag>'")
    rollback_section = text[text.rfind("###", 0, checkout_index) :]
    rollback_commands = _normalized(_bash_blocks(rollback_section))
    assert "Mac" in rollback_section
    assert "Oracle" in rollback_section
    assert "./scripts/production-compose.sh up -d --build backend graph-worker web" in rollback_commands
    assert "./scripts/production-compose.sh ps" in rollback_commands
    assert "./scripts/production-compose.sh down" not in rollback_commands


@pytest.mark.parametrize("path", (README, ZH_DEPLOYMENT, EN_DEPLOYMENT))
def test_operator_and_oracle_use_one_tracked_immutable_release(path):
    text = _text(path)
    commands = _normalized(_bash_blocks(text))
    checkout = "git checkout --detach '<immutable-release-sha>'"
    release_sha = 'export RELEASE_SHA=$(git rev-parse HEAD)'
    stage = 'RELEASE_STAGE=$(mktemp -d)'
    archive = 'git archive --format=tar "$RELEASE_SHA"'
    tree_paths = 'git ls-tree -r -z --name-only "$RELEASE_SHA"'
    create_manifest = 'python3 "$RELEASE_STAGE/scripts/check-release-tree.py" create --root "$RELEASE_STAGE"'
    manifest = 'RELEASE_MANIFEST="$RELEASE_STAGE/.release-manifest"'
    marker = "/opt/openqms/.release-sha"
    remote_sha = 'REMOTE_RELEASE_SHA=$(ssh -i "$ORACLE_SSH_KEY" "$ORACLE_SSH_TARGET" \'cat /opt/openqms/.release-sha\')'
    local_comparison = 'test "$(git rev-parse HEAD)" = "$RELEASE_SHA"'
    remote_comparison = 'test "$REMOTE_RELEASE_SHA" = "$RELEASE_SHA"'
    remote_command_guard = 'test \\"\\$(cat .release-sha)\\" = \\"$RELEASE_SHA\\"'
    content_guard = "python3 scripts/check-release-tree.py verify --root . --manifest .release-manifest >/dev/null"

    assert checkout in commands
    assert "git diff --quiet" in commands
    assert "git diff --cached --quiet" in commands
    assert release_sha in commands
    assert stage in commands
    assert "chmod 700 \"$RELEASE_STAGE\"" in commands
    assert "cleanup_release_stage" in commands
    assert "trap cleanup_release_stage EXIT" in commands
    assert "trap handle_release_signal HUP INT TERM QUIT" in commands
    assert archive in commands
    assert commands.count(tree_paths) >= 2
    assert "git ls-files -z" not in commands
    assert create_manifest in commands
    assert '"$RELEASE_STAGE/" "$ORACLE_SSH_TARGET:/opt/openqms/"' in commands
    assert manifest in commands
    assert "/opt/openqms/.release-manifest" in commands
    assert "export RELEASE_MANIFEST_SHA=" in commands
    assert "export RELEASE_GUARD_SHA=" in commands
    assert "export REMOTE_RELEASE_VERIFY=" in commands
    assert "sha256sum .release-manifest" in commands
    assert "sha256sum scripts/check-release-tree.py" in commands
    assert content_guard in commands
    assert "sha256sum -c .release-manifest" not in commands
    assert commands.count("$REMOTE_RELEASE_VERIFY") >= 3
    assert "--delete" not in commands
    assert marker in commands
    assert remote_sha in commands
    assert local_comparison in commands
    assert remote_comparison in commands
    assert commands.count(remote_command_guard) >= 2
    assert "100644" in text and "100755" in text

    assert commands.index(checkout) < commands.index(release_sha)
    assert commands.index(release_sha) < commands.index(stage)
    assert commands.index(stage) < commands.index(archive)
    assert commands.index(archive) < commands.index(create_manifest)
    assert commands.index(create_manifest) < commands.index(tree_paths, commands.index(create_manifest) + 1)
    assert commands.index(tree_paths, commands.index(create_manifest) + 1) < commands.index("/opt/openqms/.release-manifest")
    assert commands.index(content_guard) < commands.index("cat > /opt/openqms/.release-sha")
    assert commands.rindex(local_comparison) < commands.index("make deploy-release")
    assert commands.rindex(remote_comparison) < commands.index("make deploy-release")


def test_readme_quick_start_is_explicitly_local_development_only():
    readme = _text(README)
    assert "## 本地开发快速开始（非生产）" in readme
    local_start = _section(
        README,
        "## 本地开发快速开始（非生产）",
        "## Oracle ARM64 生产部署",
    )
    assert "docker compose" in local_start
    assert "production-compose.sh" in local_start
    assert "部署指南" in local_start


@pytest.mark.parametrize("path", (README, ZH_DEPLOYMENT, EN_DEPLOYMENT))
def test_production_mode_documents_single_tenant_and_e2e_disabled(path):
    text = _text(path)
    assert "TENANT_MODE=single" in text
    assert "E2E_MODE=false" in text


@pytest.mark.parametrize("path", (README, ZH_DEPLOYMENT, EN_DEPLOYMENT))
def test_latest_backup_selection_is_nonrecursive_and_nonempty(path):
    commands = _normalized(_bash_blocks(_text(path)))
    selection = "latest=$(find /opt/openqms/backups/postgres -maxdepth 1 -type f -name '*.dump' | sort | tail -1)"
    assert selection in commands
    assert 'test -n "$latest"' in commands
    assert commands.index(selection) < commands.index('test -n "$latest"')
    assert commands.index('test -n "$latest"') < commands.index(
        "./scripts/production-compose.sh exec -T db pg_restore --list"
    )


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

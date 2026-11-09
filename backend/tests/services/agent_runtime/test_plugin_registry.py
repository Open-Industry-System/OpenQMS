"""Long-term credentials are one-time outputs, never safe metadata or audit data."""
import json
import uuid
import asyncio

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.models.agent_plugin import AgentPluginGrant, AgentPluginInstallation
from app.models.audit import AuditLog
from app.models.role import RoleDefinition, RolePermission
from app.models.user import User

MANIFEST = {"protocol_versions": ["1"], "required_capabilities": [],
    "optional_capabilities": [], "supports_resume": False}


def registry():
    from app.services.agent_runtime import plugin_registry
    return plugin_registry


@pytest.mark.asyncio
async def test_registration_returns_secret_once_and_safe_metadata(db, admin_user):
    from app.schemas.agent_plugin import PluginOut, PluginSecretOut
    plugin, secret = await registry().register_plugin(db, admin_user, "sample", "1.0.0", MANIFEST)
    assert secret and secret != plugin.secret_hash and plugin.secret_hash.startswith("$2")
    assert not plugin.enabled and plugin.credential_epoch == 0
    assert await registry().verify_plugin_secret(db, plugin.installation_id, secret) is plugin
    safe = PluginOut.model_validate(plugin)
    serialized = safe.model_dump_json()
    assert secret not in serialized and plugin.secret_hash not in serialized
    assert "secret" not in serialized
    response = PluginSecretOut(plugin=safe, secret=secret)
    assert response.secret == secret
    logs = (await db.scalars(select(AuditLog).where(AuditLog.record_id == plugin.installation_id))).all()
    assert len(logs) == 1 and logs[0].operated_by == admin_user.user_id
    metadata = logs[0].changed_fields
    assert set(metadata) == {"installation_id", "plugin_version", "credential_epoch"}
    assert secret not in json.dumps(metadata) and plugin.secret_hash not in json.dumps(metadata)


@pytest.mark.asyncio
async def test_rotation_changes_secret_and_epoch_without_enabling(db, admin_user):
    plugin, old = await registry().register_plugin(db, admin_user, "sample", "1.0.0", MANIFEST)
    same, new = await registry().rotate_plugin_secret(db, admin_user, plugin.installation_id)
    assert same is plugin and new != old and plugin.credential_epoch == 1 and not plugin.enabled
    with pytest.raises(PermissionError, match="Invalid plugin credential"):
        await registry().verify_plugin_secret(db, plugin.installation_id, old)
    assert await registry().verify_plugin_secret(db, plugin.installation_id, new) is plugin


@pytest.mark.asyncio
async def test_duplicate_key_version_is_safe_conflict(db, admin_user):
    await registry().register_plugin(db, admin_user, "sample", "1.0.0", MANIFEST)
    with pytest.raises(ValueError, match="already registered"):
        await registry().register_plugin(db, admin_user, "sample", "1.0.0", MANIFEST)
    # Another version is independently installable.
    plugin, _ = await registry().register_plugin(db, admin_user, "sample", "2.0.0", MANIFEST)
    assert plugin.plugin_version == "2.0.0"


@pytest.mark.asyncio
async def test_pending_unrelated_invalid_write_is_not_reported_as_plugin_duplicate(db, admin_user):
    from app.models.factory import Factory

    db.add(Factory(id=uuid.uuid4(), code=None, name="Unrelated invalid pending write"))
    with pytest.raises(IntegrityError):
        await registry().register_plugin(db, admin_user, "sample", "1.0.0", MANIFEST)


@pytest.mark.asyncio
@pytest.mark.parametrize("manifest", [dict(MANIFEST, hidden_egress=True),
    dict(MANIFEST, protocol_versions=["2"]), dict(MANIFEST, protocol_versions=[]),
    dict(MANIFEST, required_capabilities=["x" * 161]), dict(MANIFEST, required_capabilities=[1]),
    dict(MANIFEST, supports_resume="yes"), dict(MANIFEST, optional_capabilities="read")])
async def test_manifest_rejects_unknown_or_invalid_claims(db, admin_user, manifest):
    with pytest.raises(ValueError):
        await registry().register_plugin(db, admin_user, "sample", "1.0.0", manifest)
    assert not (await db.scalars(select(AgentPluginInstallation))).all()


@pytest.mark.asyncio
@pytest.mark.parametrize("key,version", [("", "1"), ("x" * 101, "1"), ("x", ""), ("x", "v" * 41)])
async def test_registration_bounds_key_and_version(db, admin_user, key, version):
    with pytest.raises(ValueError):
        await registry().register_plugin(db, admin_user, key, version, MANIFEST)


@pytest.mark.asyncio
async def test_unknown_and_deny_capabilities_are_declarations_only(db, admin_user):
    manifest = dict(MANIFEST, required_capabilities=["unknown.v1", "capa.d4.summary.masked.v1"])
    plugin, _ = await registry().register_plugin(db, admin_user, "sample", "1", manifest)
    assert plugin.manifest == manifest and not plugin.enabled
    assert not (await db.scalars(select(AgentPluginGrant))).all()


@pytest.mark.asyncio
@pytest.mark.parametrize("revocation", ["user", "role", "permission", "membership"])
async def test_administration_uses_current_actor_role_and_permissions(db, admin_user, viewer_user, revocation):
    if revocation == "user":
        await db.execute(update(User).where(User.user_id == admin_user.user_id).values(is_active=False).execution_options(synchronize_session=False))
    elif revocation == "role":
        await db.execute(update(RoleDefinition).where(RoleDefinition.id == admin_user.role_id).values(is_active=False).execution_options(synchronize_session=False))
    elif revocation == "permission":
        await db.execute(update(RolePermission).where(RolePermission.role_id == admin_user.role_id, RolePermission.module == "permission_mgmt").values(permission_level=4).execution_options(synchronize_session=False))
    else:
        await db.execute(update(User).where(User.user_id == admin_user.user_id).values(role_id=viewer_user.role_id).execution_options(synchronize_session=False))
    with pytest.raises(PermissionError):
        await registry().register_plugin(db, admin_user, "sample", "1", MANIFEST)


@pytest.mark.asyncio
async def test_nonadmin_cannot_register_or_rotate(db, admin_user, viewer_user):
    plugin, _ = await registry().register_plugin(db, admin_user, "sample", "1", MANIFEST)
    with pytest.raises(PermissionError):
        await registry().register_plugin(db, viewer_user, "viewer", "1", MANIFEST)
    with pytest.raises(PermissionError):
        await registry().rotate_plugin_secret(db, viewer_user, plugin.installation_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("stored,secret", [("malformed", "bad"), ("$2b$bad", "bad"), ("fixture", "x" * 1000), ("fixture", None)])
async def test_invalid_or_malformed_credentials_use_fixed_error(db, enabled_plugin, stored, secret):
    enabled_plugin.secret_hash = stored
    await db.flush()
    with pytest.raises(PermissionError, match="^Invalid plugin credential$"):
        await registry().verify_plugin_secret(db, enabled_plugin.installation_id, secret)
    with pytest.raises(PermissionError, match="^Invalid plugin credential$"):
        await registry().verify_plugin_secret(db, uuid.uuid4(), "missing")


@pytest.mark.asyncio
async def test_registry_mutation_commit_is_owned_by_caller(committed_runtime):
    owned = committed_runtime
    async with owned.factory(binding=owned.binding) as writer:
        user = await writer.get(User, owned.user_id)
        plugin, secret = await registry().register_plugin(writer, user, "transaction", "1", MANIFEST)
        async with owned.factory(binding=owned.binding) as observer:
            assert await observer.get(AgentPluginInstallation, plugin.installation_id) is None
            assert not (await observer.scalars(select(AuditLog).where(AuditLog.record_id == plugin.installation_id))).all()
        await writer.commit()
        async with owned.factory(binding=owned.binding) as observer:
            assert (await registry().verify_plugin_secret(observer, plugin.installation_id, secret)).installation_id == plugin.installation_id


@pytest.mark.asyncio
async def test_concurrent_rotation_reloads_locked_epoch_and_invalidates_old_secret(committed_runtime):
    owned = committed_runtime
    ready = asyncio.Event()
    async with owned.factory(binding=owned.binding) as winner:
        user = await winner.get(User, owned.user_id)
        _, first_secret = await registry().rotate_plugin_secret(winner, user, owned.plugin_id)
        async def rival():
            async with owned.factory(binding=owned.binding) as db:
                # Cache epoch 0 while the winning transaction still owns the row lock.
                cached = await db.get(AgentPluginInstallation, owned.plugin_id)
                assert cached.credential_epoch == 0
                actor = await db.get(User, owned.user_id)
                ready.set()
                plugin, second_secret = await registry().rotate_plugin_secret(db, actor, owned.plugin_id)
                await db.commit()
                return plugin.credential_epoch, second_secret
        pending = asyncio.create_task(rival())
        try:
            await asyncio.wait_for(ready.wait(), timeout=10)
            # Rival has reached rotation with a cached old row, but cannot finish
            # while winner owns the installation's FOR UPDATE lock.
            assert not pending.done()
            await winner.commit()
            epoch, second_secret = await asyncio.wait_for(pending, timeout=10)
            assert epoch == 2
        finally:
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
    async with owned.factory(binding=owned.binding) as db:
        for old in (owned.secret, first_secret):
            with pytest.raises(PermissionError):
                await registry().verify_plugin_secret(db, owned.plugin_id, old)
        assert (await registry().verify_plugin_secret(db, owned.plugin_id, second_secret)).credential_epoch == 2


@pytest.mark.asyncio
async def test_external_admin_revocation_denies_cached_actor_rotation(committed_runtime):
    owned = committed_runtime
    async with owned.factory(binding=owned.binding) as writer:
        actor = await writer.get(User, owned.user_id)
        async with owned.factory(binding=owned.binding) as other:
            await other.execute(update(RolePermission).where(RolePermission.role_id == owned.role_id,
                RolePermission.module == "permission_mgmt").values(permission_level=0))
            await other.commit()
        with pytest.raises(PermissionError):
            await registry().rotate_plugin_secret(writer, actor, owned.plugin_id)

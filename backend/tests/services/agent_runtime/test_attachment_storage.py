"""Private, descriptor-safe storage tests for controlled task attachments."""
import hashlib
import os
from uuid import uuid4

import pytest


def storage_module():
    try:
        from app.services.agent_runtime import attachment_storage
    except ImportError:
        pytest.fail("attachment storage is not implemented")
    return attachment_storage


def public_namespace():
    return storage_module().AttachmentNamespace(
        tenant_id=None,
        origin_generation=None,
        storage_namespace="public",
    )


def private_storage(tmp_path):
    storage = storage_module().PrivateAttachmentStorage(tmp_path / "attachments")
    storage.validate_root()
    return storage


def test_storage_rejects_symlink_root_and_filename_paths(tmp_path):
    root = tmp_path / "root"
    root.symlink_to(tmp_path)
    with pytest.raises(ValueError):
        storage_module().PrivateAttachmentStorage(root).validate_root()

    namespace = public_namespace()
    with pytest.raises(ValueError):
        storage_module().AttachmentNamespace(None, None, "../outside")
    with pytest.raises(ValueError):
        storage_module().AttachmentNamespace(uuid4(), None, "tenant")
    with pytest.raises(ValueError):
        storage_module().AttachmentNamespace(None, 1, "public")
    assert namespace.storage_namespace == "public"


def test_create_staging_is_private_and_promote_requires_exact_size_and_digest(tmp_path):
    storage = private_storage(tmp_path)
    attachment_id = uuid4()
    handle = storage.create_staging(public_namespace(), attachment_id)
    handle.write(b"clean")
    handle.close()

    with pytest.raises(storage_module().AttachmentIntegrityError):
        storage.promote(public_namespace(), attachment_id, "0" * 64, 5)

    with pytest.raises(storage_module().AttachmentIntegrityError):
        storage.promote(public_namespace(), attachment_id, hashlib.sha256(b"clean").hexdigest(), 4)

    storage.promote(public_namespace(), attachment_id, hashlib.sha256(b"clean").hexdigest(), 5)
    with storage.open_clean(
        public_namespace(), attachment_id, hashlib.sha256(b"clean").hexdigest(), 5
    ) as clean:
        assert clean.read() == b"clean"
    assert os.stat(tmp_path / "attachments").st_mode & 0o777 == 0o700


def test_open_clean_rechecks_digest_and_remove_is_idempotent(tmp_path):
    storage = private_storage(tmp_path)
    attachment_id = uuid4()
    digest = hashlib.sha256(b"clean").hexdigest()
    handle = storage.create_staging(public_namespace(), attachment_id)
    handle.write(b"clean")
    handle.close()
    storage.promote(public_namespace(), attachment_id, digest, 5)

    with pytest.raises(storage_module().AttachmentIntegrityError):
        storage.open_clean(public_namespace(), attachment_id, "0" * 64, 5)

    storage.remove(public_namespace(), attachment_id, "clean")
    storage.remove(public_namespace(), attachment_id, "clean")
    with pytest.raises(FileNotFoundError):
        storage.open_clean(public_namespace(), attachment_id, digest, 5)

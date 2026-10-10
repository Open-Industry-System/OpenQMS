"""Descriptor-safe private storage for scan-gated task attachments."""
from __future__ import annotations

import hashlib
import hmac
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal
from uuid import UUID


class AttachmentIntegrityError(ValueError):
    """Stored bytes differ from the lifecycle metadata expected by the caller."""


@dataclass(frozen=True)
class AttachmentNamespace:
    tenant_id: UUID | None
    origin_generation: int | None
    storage_namespace: str

    def __post_init__(self) -> None:
        if (self.tenant_id is None) != (self.origin_generation is None):
            raise ValueError("tenant identity and generation must be paired")
        if self.origin_generation is not None and self.origin_generation < 0:
            raise ValueError("origin generation must be non-negative")
        if (
            not self.storage_namespace
            or len(self.storage_namespace) > 160
            or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in self.storage_namespace)
        ):
            raise ValueError("storage namespace must be an opaque server-generated key")
        if self.tenant_id is None and self.storage_namespace != "public":
            raise ValueError("public storage must use the public namespace")
        if self.tenant_id is not None and self.storage_namespace == "public":
            raise ValueError("tenant storage must not use the public namespace")


class PrivateAttachmentStorage:
    """Stores opaque attachment UUIDs only; it never accepts or returns paths."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def validate_root(self) -> None:
        try:
            info = os.lstat(self._root)
        except FileNotFoundError:
            self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
            info = os.lstat(self._root)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise ValueError("attachment root must be a directory, not a symlink")
        if stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("attachment root must have mode 0700")

    def create_staging(self, namespace: AttachmentNamespace, attachment_id: UUID) -> BinaryIO:
        with self._area_fd(namespace, "staging") as area_fd:
            fd = os.open(
                self._attachment_name(attachment_id),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=area_fd,
            )
        os.fchmod(fd, 0o600)
        return os.fdopen(fd, "wb")

    def promote(
        self,
        namespace: AttachmentNamespace,
        attachment_id: UUID,
        expected_sha256: str,
        expected_size: int,
    ) -> None:
        with self._area_fd(namespace, "staging") as staging_fd, self._area_fd(namespace, "clean") as clean_fd:
            self._verify_file(staging_fd, attachment_id, expected_sha256, expected_size)
            os.replace(
                self._attachment_name(attachment_id),
                self._attachment_name(attachment_id),
                src_dir_fd=staging_fd,
                dst_dir_fd=clean_fd,
            )

    def open_clean(
        self,
        namespace: AttachmentNamespace,
        attachment_id: UUID,
        expected_sha256: str,
        expected_size: int,
    ) -> BinaryIO:
        with self._area_fd(namespace, "clean") as clean_fd:
            fd = self._open_regular(clean_fd, attachment_id)
        try:
            self._verify_fd(fd, expected_sha256, expected_size)
            os.lseek(fd, 0, os.SEEK_SET)
            return os.fdopen(fd, "rb")
        except BaseException:
            os.close(fd)
            raise

    def remove(self, namespace: AttachmentNamespace, attachment_id: UUID, area: Literal["staging", "clean"]) -> None:
        """Remove one opaque file and prune only now-empty server-owned directories."""
        if area not in {"staging", "clean"}:
            raise ValueError("unknown attachment storage area")
        self.validate_root()
        root_fd = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            try:
                namespace_fd = os.open(
                    namespace.storage_namespace,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=root_fd,
                )
            except FileNotFoundError:
                return
            try:
                try:
                    area_fd = os.open(area, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=namespace_fd)
                except FileNotFoundError:
                    return
                try:
                    try:
                        os.unlink(self._attachment_name(attachment_id), dir_fd=area_fd)
                    except FileNotFoundError:
                        pass
                finally:
                    os.close(area_fd)
                try:
                    os.rmdir(area, dir_fd=namespace_fd)
                except OSError:
                    pass
            finally:
                os.close(namespace_fd)
            try:
                os.rmdir(namespace.storage_namespace, dir_fd=root_fd)
            except OSError:
                pass
        finally:
            os.close(root_fd)

    def list_attachment_ids(self, namespace: AttachmentNamespace, area: Literal["staging", "clean"]) -> set[UUID]:
        """Return only server-shaped regular file names; preserve anything else."""
        attachment_ids: set[UUID] = set()
        with self._area_fd(namespace, area) as area_fd:
            with os.scandir(area_fd) as entries:
                for entry in entries:
                    if not entry.is_file(follow_symlinks=False) or len(entry.name) != 32:
                        continue
                    try:
                        attachment_id = UUID(hex=entry.name)
                    except ValueError:
                        continue
                    if attachment_id.hex == entry.name:
                        attachment_ids.add(attachment_id)
        return attachment_ids

    def list_namespaces(self) -> set[str]:
        """List only safe opaque namespace directories; unknown values are not opened."""
        self.validate_root()
        names: set[str] = set()
        root_fd = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            with os.scandir(root_fd) as entries:
                for entry in entries:
                    name = entry.name
                    if (entry.is_dir(follow_symlinks=False) and 0 < len(name) <= 160
                            and all(char in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in name)):
                        names.add(name)
        finally:
            os.close(root_fd)
        return names

    def remove_namespace(self, namespace: AttachmentNamespace) -> bool:
        """Remove a disposition-authorized namespace without following links.

        Returns whether an existing namespace was physically removed.
        """
        self.validate_root()
        root_fd = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            try:
                namespace_fd = os.open(
                    namespace.storage_namespace,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=root_fd,
                )
            except FileNotFoundError:
                return False
            try:
                self._remove_tree(namespace_fd)
            finally:
                os.close(namespace_fd)
            os.rmdir(namespace.storage_namespace, dir_fd=root_fd)
            return True
        finally:
            os.close(root_fd)

    @classmethod
    def _remove_tree(cls, directory_fd: int) -> None:
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    child_fd = os.open(
                        entry.name,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=directory_fd,
                    )
                    try:
                        cls._remove_tree(child_fd)
                    finally:
                        os.close(child_fd)
                    os.rmdir(entry.name, dir_fd=directory_fd)
                else:
                    os.unlink(entry.name, dir_fd=directory_fd)

    def _area_fd(self, namespace: AttachmentNamespace, area: Literal["staging", "clean"]):
        if area not in {"staging", "clean"}:
            raise ValueError("unknown attachment storage area")
        self.validate_root()
        root_fd = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            namespace_fd = self._open_or_create_directory(root_fd, namespace.storage_namespace)
            try:
                area_fd = self._open_or_create_directory(namespace_fd, area)
            finally:
                os.close(namespace_fd)
        finally:
            os.close(root_fd)
        return _DirectoryFD(area_fd)

    @staticmethod
    def _attachment_name(attachment_id: UUID) -> str:
        return attachment_id.hex

    @staticmethod
    def _open_or_create_directory(parent_fd: int, name: str) -> int:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError:
            pass
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
            os.close(fd)
            raise ValueError("attachment storage directory must have mode 0700")
        return fd

    def _verify_file(
        self,
        area_fd: int,
        attachment_id: UUID,
        expected_sha256: str,
        expected_size: int,
    ) -> None:
        fd = self._open_regular(area_fd, attachment_id)
        try:
            self._verify_fd(fd, expected_sha256, expected_size)
        finally:
            os.close(fd)

    def _open_regular(self, area_fd: int, attachment_id: UUID) -> int:
        fd = os.open(
            self._attachment_name(attachment_id),
            os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
            dir_fd=area_fd,
        )
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise AttachmentIntegrityError("attachment must be a regular file")
        return fd

    @staticmethod
    def _verify_fd(fd: int, expected_sha256: str, expected_size: int) -> None:
        if expected_size < 0:
            raise AttachmentIntegrityError("attachment size is invalid")
        info = os.fstat(fd)
        if info.st_size != expected_size:
            raise AttachmentIntegrityError("attachment size does not match")
        with os.fdopen(os.dup(fd), "rb") as duplicate:
            digest = hashlib.file_digest(duplicate, "sha256").hexdigest()
        if not hmac.compare_digest(digest, expected_sha256):
            raise AttachmentIntegrityError("attachment digest does not match")


class _DirectoryFD:
    def __init__(self, fd: int) -> None:
        self._fd = fd

    def __enter__(self) -> int:
        return self._fd

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        os.close(self._fd)
